#!/usr/bin/env python3
"""Build the single self-contained HTML file for cloud publishing (Claude Artifact).

Why a separate script from build.py: an Artifact page runs under a strict CSP that
blocks remote images and has exactly one URL — there's no `weeks/2026-W29.html` to link
to. So this script takes the already-built *current* week page (full visual treatment,
same as the local site), inlines every YouTube thumbnail as a base64 data: URI, and
folds every earlier week into a text-only "往期存档" accordion appended to the same
document instead of separate pages.

Usage: python3 build_artifact.py
Output: cloud/report.html  — hand this path to the Artifact tool.

First publish:  Artifact({file_path: "cloud/report.html", favicon: "📊", ...})
                → save the returned URL into README.md and memory.
Later updates:  python3 collect.py && python3 build.py && python3 build_artifact.py
                then Artifact({file_path: "cloud/report.html", url: "<saved URL>"})
                — passing url= is what makes it update in place instead of minting
                a new link; a fresh conversation has no memory of the URL otherwise.
"""
import base64
import json
import re
import urllib.request
from pathlib import Path

import build  # noqa: F401 — importing runs build.py's own main pass as a side effect,
               # which (a) refreshes weeks/*.html + index.html and (b) exposes the pure
               # helpers (classify, lpk, esc, fmt, date_md, STATUS_META) reused below.

ROOT = Path(__file__).parent
CACHE = ROOT / "thumb_cache"
CACHE.mkdir(exist_ok=True)

esc, fmt, classify, lpk, date_md, STATUS_META = (
    build.esc, build.fmt, build.classify, build.lpk, build.date_md, build.STATUS_META)

WEEK = build.WEEK
ALL_WEEKS = sorted((p.stem for p in (ROOT / "data").glob("*.json")), reverse=True)
OLDER_WEEKS = [w for w in ALL_WEEKS if w != WEEK]


# ---------- thumbnail inlining ----------
def fetch_data_uri(url: str) -> str | None:
    """Download once, cache to disk by filename, return a data: URI. None on failure —
    callers must handle that by dropping the image rather than leaving a dead remote src
    (the Artifact CSP blocks it anyway, so a broken icon is strictly worse than no image)."""
    name = re.sub(r"[^\w.-]", "_", url.split("://", 1)[1])
    cached = CACHE / name
    if not cached.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            cached.write_bytes(urllib.request.urlopen(req, timeout=10).read())
        except Exception as e:
            print(f"  [thumb FAIL] {url}: {e}")
            return None
    try:
        b = cached.read_bytes()
        if len(b) < 500:          # YouTube serves a tiny grey placeholder for missing thumbs
            return None
        return f"data:image/jpeg;base64,{base64.b64encode(b).decode()}"
    except Exception:
        return None


def inline_images(html: str) -> str:
    urls = sorted(set(re.findall(r'src="(https://i\.ytimg\.com/[^"]+)"', html)))
    print(f"inlining {len(urls)} thumbnails...")
    n_ok = 0
    for url in urls:
        data_uri = fetch_data_uri(url)
        if data_uri:
            html = html.replace(f'src="{url}"', f'src="{data_uri}"')
            n_ok += 1
        else:
            # drop the whole <img> tag rather than ship a src the CSP will block anyway
            html = re.sub(rf'<img[^>]*src="{re.escape(url)}"[^>]*>', "", html)
    print(f"  {n_ok}/{len(urls)} inlined")
    return html


# ---------- archive (older weeks, text-only) ----------
def week_window(week_label):
    import datetime
    y, w = week_label.split("-W")
    monday = datetime.date.fromisocalendar(int(y), int(w), 1)
    return monday.strftime("%Y%m%d"), (monday + datetime.timedelta(days=7)).strftime("%Y%m%d")


def archive_row(v, note):
    st_label, st_cls = STATUS_META[v["status"]]
    url = f'https://www.youtube.com/watch?v={v["id"]}'
    return f"""
    <div class="row st-{st_cls}">
      <span class="chip {st_cls} sm">{st_label}</span>
      <div class="rmain">
        <a href="{url}" target="_blank" rel="noopener">{esc(v["title"])}</a>
        <span class="rmeta">{esc(v["channel_name"])} · {date_md(v)} · {fmt(v["view_count"])} 播放 · {fmt(v["like_count"])} 赞 · {fmt(v["comment_count"])} 评论 · 赞/千播 {round(lpk(v), 1)}</span>
        {f'<p class="note sm">{esc(note)}</p>' if note else ''}
      </div>
    </div>"""


def build_archive_section():
    if not OLDER_WEEKS:
        return ""
    blocks = []
    for i, w in enumerate(OLDER_WEEKS):
        data = json.loads((ROOT / "data" / f"{w}.json").read_text())
        cur_path = ROOT / "curation" / f"{w}.json"
        cur = json.loads(cur_path.read_text()) if cur_path.exists() else {}
        notes = cur.get("notes", {})
        wk_start, wk_end = week_window(w)
        hits = sorted(
            (v for v in data["videos"]
             if wk_start <= v["upload_date"] < wk_end and v.get("lang") in ("粤语", "普通话")
             and (v.__setitem__("status", classify(v)) or v["status"] == "hit")),
            key=lambda x: -(x.get("view_count") or 0))
        tldr = cur.get("tldr", [])
        tldr_html = "".join(f"<li><b>{esc(t['t'])}</b> — {esc(t['d'])}</li>" for t in tldr)
        rows_html = "".join(archive_row(v, notes.get(v["id"], {}).get("note", "")) for v in hits)
        open_attr = " open" if i == 0 else ""       # most recent archived week expands by default
        blocks.append(f"""
    <details class="archive-week"{open_attr}>
      <summary><b>{esc(cur.get("label", w))}</b>
        <span class="wkr">{esc(cur.get("range", ""))}</span>
        <span class="wkh">{len(hits)} 条爆款</span></summary>
      <div class="archive-body">
        {f'<ul class="archive-tldr">{tldr_html}</ul>' if tldr_html else ''}
        <div class="rows">{rows_html or "<p class='secdesc'>本周无三项达标内容。</p>"}</div>
      </div>
    </details>""")
    return f"""
<section id="archive">
  <h2>往期存档<span class="cnt">{len(OLDER_WEEKS)} 期</span></h2>
  <p class="secdesc">早于本期的历史报告——结论与爆款清单原样保留,缩略图只在最新一期内嵌(每期都嵌会让文件越滚越大)。点开期数展开。</p>
  <div class="archivelist">{"".join(blocks)}</div>
</section>"""


# ---------- assemble ----------
def main():
    src = (ROOT / "weeks" / f"{WEEK}.html").read_text()

    # The local nav links to sibling files (weeks/2026-W29.html) that don't exist once this
    # is a single hosted page — swap it for a jump link to the in-page archive below.
    src = re.sub(
        r'<nav class="weeks">.*?</nav>',
        '<a class="archivejump" href="#archive">↓ 往期存档</a>' if OLDER_WEEKS else "",
        src, flags=re.S)
    src = src.replace(
        '.wk.cur b { color: var(--c-hit); }\na.wk:hover { border-color: var(--c-hit); transform: translateY(-1px); }',
        '.wk.cur b { color: var(--c-hit); }\na.wk:hover { border-color: var(--c-hit); transform: translateY(-1px); }\n'
        '.archivejump { display: inline-block; margin-top: 18px; font-size: 13px; color: var(--c-hit); text-decoration: none; }\n'
        '.archivejump:hover { text-decoration: underline; }\n'
        '.archivelist { display: grid; gap: 10px; }\n'
        '.archive-week { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 4px 18px; }\n'
        '.archive-week summary { cursor: pointer; padding: 14px 0; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; list-style: none; }\n'
        '.archive-week summary::-webkit-details-marker { display: none; }\n'
        '.archive-week summary b { font-size: 15px; }\n'
        '.archive-body { padding: 4px 0 18px; }\n'
        '.archive-tldr { margin: 0 0 14px; padding-left: 20px; color: var(--ink2); font-size: 13.5px; display: grid; gap: 6px; }\n'
        '.archive-tldr b { color: var(--ink); }')

    archive_html = build_archive_section()
    src = src.replace(
        '<section>\n  <h2>方法论与周更流程</h2>',
        archive_html + '\n\n<section>\n  <h2>方法论与周更流程</h2>')

    src = inline_images(src)

    out = ROOT / "cloud" / "report.html"
    out.write_text(src)
    print(f"\nbuilt {out}  ({len(src)/1024:.0f} KB) · archived weeks: {len(OLDER_WEEKS)}")


if __name__ == "__main__":
    main()
