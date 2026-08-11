#!/usr/bin/env python3
"""Build the weekly 粤语财经爆款周报 site from data/ + curation/ into index.html.

Usage: python3 build.py [2026-W30]   (defaults to newest week in data/)
"""
import json, math, sys, html, re, datetime
from pathlib import Path

ROOT = Path(__file__).parent

# ---------- load ----------
if len(sys.argv) > 1:
    WEEK = sys.argv[1]
else:
    WEEK = sorted(p.stem for p in (ROOT / "data").glob("*.json"))[-1]

data = json.loads((ROOT / "data" / f"{WEEK}.json").read_text())
cur_path = ROOT / "curation" / f"{WEEK}.json"
cur = json.loads(cur_path.read_text()) if cur_path.exists() else {}
notes = cur.get("notes", {})

# Merge last week's archive: the collector keeps only 10 candidates per channel, so a
# prolific channel's older videos drop out of the window. Current numbers win; archived
# ones fill the gaps and provide the "发酵增量" baseline.
prev_files = sorted(p.stem for p in (ROOT / "data").glob("*.json") if p.stem < WEEK)
prev_metrics = {}
if prev_files:
    prev = json.loads((ROOT / "data" / f"{prev_files[-1]}.json").read_text())
    have = {v["id"] for v in data["videos"]}
    for v in prev["videos"]:
        # Backfilled rows carry today's counts, not last week's — using them as a delta
        # baseline would report 0% growth and misfire the 播放停滞 flag.
        if not v.get("_backfilled"):
            prev_metrics[v["id"]] = {"view_count": v.get("view_count"), "like_count": v.get("like_count"),
                                     "comment_count": v.get("comment_count")}
        if v["id"] not in have:
            v["_stale"] = True          # numbers are from last week's snapshot
            data["videos"].append(v)

# ---------- classify ----------
# ISO week boundaries derived from week label
year, wnum = WEEK.split("-W")
monday = datetime.date.fromisocalendar(int(year), int(wnum), 1)
WK_START = monday.strftime("%Y%m%d")
# The merged archive spans two weeks, so anything older than the comparison week is
# kept only as a delta baseline — never shown.
PREV_START = (monday - datetime.timedelta(days=7)).strftime("%Y%m%d")
# Upper bound matters once a file has been backfilled: without it, a later week's videos
# that landed in this file would render as if they were part of this issue.
WK_END = (monday + datetime.timedelta(days=7)).strftime("%Y%m%d")

def lpk(v):  # likes per 1000 views
    return (v.get("like_count") or 0) / max(v.get("view_count") or 1, 1) * 1000

def classify(v):
    """hit  = 爆款      播放≥3w   · 赞≥1k  · 评论≥20
       mid  = 中腰部    播放≥1.5w · 赞≥500 · 评论≥10   (选题/关键词参考层)
       paid = 疑似投流  高播放但互动断崖 — 判定优先于 hit/mid"""
    vc, lc, cc = v.get("view_count") or 0, v.get("like_count") or 0, v.get("comment_count") or 0
    if (vc >= 30000 and (lpk(v) < 8 or cc <= 5)) or (vc >= 25000 and lpk(v) < 4) \
       or (vc >= 15000 and lpk(v) < 6):
        return "paid"
    if vc >= 30000 and lc >= 1000 and cc >= 20:
        return "hit"
    if vc >= 28000 and lpk(v) >= 10:          # already at 爆款 scale, one metric short
        return "near"
    if vc >= 15000 and lc >= 500 and cc >= 10:
        return "mid"
    return "miss"

for v in data["videos"]:
    v["status"] = classify(v)
    v["lpk"] = round(lpk(v), 1)
    v["week"] = ("this" if WK_START <= v["upload_date"] < WK_END
                 else "prev" if PREV_START <= v["upload_date"] < WK_START else "older")

data["videos"] = [v for v in data["videos"] if v["week"] != "older"]

CN = [v for v in data["videos"] if v["lang"] in ("粤语", "普通话")]
EN = [v for v in data["videos"] if v["lang"] == "英语"]

def sort_v(vs):
    return sorted(vs, key=lambda x: -(x.get("view_count") or 0))

cn_this = sort_v([v for v in CN if v["week"] == "this"])
cn_prev = sort_v([v for v in CN if v["week"] == "prev"])
en_all = sort_v(EN)

STATUS_META = {
    "hit":  ("爆款", "hit"),
    "mid":  ("中腰部", "mid"),
    "near": ("差一口气", "near"),
    "paid": ("疑似投流", "paid"),
    "miss": ("未达标", "miss"),
}

def esc(s):
    return html.escape(str(s or ""))

def fmt(n):
    if n is None:
        return "—"
    if n >= 10000:
        s = f"{n/10000:.1f}".rstrip("0").rstrip(".")
        return f"{s}w"
    if n >= 1000:
        return f"{n:,}"
    return str(n)

# ---------- keyword mining ----------
# Segment the two-week Chinese titles to surface what topics are actually being made
# (中腰部 included — that layer is where the 选题 patterns show up, not just the hits).
import jieba
jieba.setLogLevel(60)

ENTITY_HINTS = """SK海力士 三星 英偉達 英伟达 輝達 台積電 美光 Nvidia MU Kimi K3 月之暗面 楊植麟 OpenAI Anthropic
長鑫 中芯 阿里巴巴 騰訊 美團 百度 小米 比亞迪 滙控 渣打 國泰 寧德時代 聯想 瀾起科技 智譜 SpaceX TVB
恒指 科指 港股 美股 A股 韓股 納指 日經 KOSPI 樓市 一手 息口 減息 加息 關稅 國家隊 港股通
施永青 許楨 熊麗萍 雷鼎鳴 蔡金強 洪灝 陸東 譚新強 李浩德 王良享 特朗普 習近平 巴菲特
AI泡沫 泡沫 股災 爆倉 熔斷 業績 財報 IPO ETF 比特幣 黃金 白銀 半導體 存儲 記憶體 機器人 具身智能
外星人 UFO 失業 求職 移民 退休 保險 基金 期權 槓桿""".split()
for w in ENTITY_HINTS:
    jieba.add_word(w)

STOP = set("""的 了 是 在 有 和 就 不 都 而 及 與 与 著 或 我們 你們 他們 什麼 怎麼 為何 如何 點解 點樣
可以 不能 已經 仍然 還是 但係 因為 所以 如果 究竟 到底 其實 真係 一定 唔會 唔係 有冇 係咪 定係
今集 今期 本周 今日 昨日 直播 節目 嘉賓 主持 分析 分享 講解 介紹 影片 完整 足本 全集 精華 重溫
一個 一次 一種 這個 那個 呢個 我哋 你哋 佢哋 大家 之後 之前 現在 未來 目前 最新 最近 以及 加上
part Part EP ep Ep""".split())

HOOKS = {
    "恐慌词": ["暴跌", "暴瀉", "崩盤", "股災", "爆倉", "熔斷", "危機", "警號", "恐慌", "血洗", "腰斬", "輸清光",
             "一頸血", "散水", "接火棒", "末日", "風暴", "災難", "慘遭", "殺到"],
    "悬念词": ["真相", "揭秘", "揭露", "拆解", "秘密", "內幕", "謎團", "曝光", "竟然", "原來", "背後", "不為人知",
             "點算", "邊個", "邊隻", "咩事", "會唔會"],
    "冲击词": ["震驚", "史上最", "首次", "突發", "驚人", "離奇", "癲", "狂", "爆升", "勁", "最強", "終極",
             "橫空出世", "王炸", "封神"],
    "利益词": ["黑馬", "必買", "抵買", "撈底", "翻倍", "十倍", "機會", "部署", "策略", "賺", "回報", "財自",
             "上車", "致富"],
}

# Column/series names carry no 选题 information — they say who made it, not what it's about.
SERIES_WORDS = set("""recap Recap RECAP KellyMarket 股壇 財經 懶人包 信箱 曾生 股動 萍台 講經 talk Talk
HOT 訪問 專訪 拆局 觀天下 楨觀 天下 得嫻 Vera podcast Podcast 系列 完整版""".split())
HOOK_ALL = {w for ws in HOOKS.values() for w in ws}

def mine_keywords(vids, topn=18):
    """Returns (topic_rows, hook_rows). Weighted by views so 带量的词 rank first.
    Hook words and column names are excluded here — they get their own table."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "views": [], "best": None})
    for v in vids:
        seen = set()
        for w in jieba.cut(v["title"]):
            w = w.strip()
            if (len(w) < 2 or w in STOP or w in SERIES_WORDS or w in HOOK_ALL
                    or w.isdigit() or re.fullmatch(r"[a-zA-Z]{1,2}", w or "")):
                continue
            if w in seen:
                continue
            seen.add(w)
            a = agg[w]
            a["n"] += 1
            a["views"].append(v.get("view_count") or 0)
            if not a["best"] or (v.get("view_count") or 0) > (a["best"].get("view_count") or 0):
                a["best"] = v
    rows = [(w, a) for w, a in agg.items() if a["n"] >= 2]
    rows.sort(key=lambda r: (-sum(r[1]["views"]) / 1000, -r[1]["n"]))
    topics = rows[:topn]

    hooks = []
    for cat, words in HOOKS.items():
        hits = []
        for w in words:
            ms = [v for v in vids if w in v["title"]]
            if ms:
                hits.append((w, len(ms), max(ms, key=lambda x: x.get("view_count") or 0)))
        hits.sort(key=lambda h: -(h[2].get("view_count") or 0))
        if hits:
            hooks.append((cat, hits[:8]))
    return topics, hooks

def gap_reason(v):
    """Why a 'near' video missed, with exact gaps."""
    parts = []
    if (v.get("view_count") or 0) < 30000:
        parts.append(f"差 {30000 - v['view_count']:,} 播放")
    if (v.get("like_count") or 0) < 1000:
        parts.append(f"差 {1000 - (v['like_count'] or 0)} 个赞")
    if (v.get("comment_count") or 0) < 20:
        parts.append(f"差 {20 - (v['comment_count'] or 0)} 条评论")
    return "、".join(parts) if parts else ""

def tag_chips(v):
    n = notes.get(v["id"], {})
    return "".join(f'<span class="tag">{esc(t)}</span>' for t in n.get("tags", []))

def note_text(v):
    return notes.get(v["id"], {}).get("note", "")

def date_md(v):
    d = v["upload_date"]
    return f"{int(d[4:6])}.{int(d[6:])}"

def delta_badge(v):
    """Growth since last week's snapshot — the payoff of tracking week over week.
    Near-zero growth on a high-view video is itself a signal: paid reach stops dead
    once the buy ends, while organic hits keep compounding for 7-10 days."""
    p = prev_metrics.get(v["id"])
    if not p or v.get("_stale") or not p.get("view_count"):
        return ""
    d = (v.get("view_count") or 0) - p["view_count"]
    pct = d / p["view_count"] * 100
    if d < 0:
        # counts only go backwards when YouTube revises them or the two snapshots aren't a
        # week apart (e.g. a backfilled baseline) — noise, not a signal
        return ""
    if p["view_count"] >= 30000 and pct < 1:
        return f'<span class="m flat">较上期 <b>+{pct:.1f}%</b> 播放停滞</span>'
    if d < 1000:
        return ""
    return f'<span class="m grow">较上期 <b>+{fmt(d)}</b> 播放</span>'

def metrics_row(v):
    stale = '<span class="m stale">数据截至上期</span>' if v.get("_stale") else ""
    return (f'<span class="m"><b>{fmt(v["view_count"])}</b> 播放</span>'
            f'<span class="m"><b>{fmt(v["like_count"])}</b> 赞</span>'
            f'<span class="m"><b>{fmt(v["comment_count"])}</b> 评论</span>'
            f'<span class="m lpk"><b>{v["lpk"]}</b> 赞/千播</span>'
            f'{delta_badge(v)}{stale}')

def video_card(v, rank=None, hero=False):
    st_label, st_cls = STATUS_META[v["status"]]
    url = f'https://www.youtube.com/watch?v={v["id"]}'
    thumb = f'https://i.ytimg.com/vi/{v["id"]}/{"hq720" if hero else "mqdefault"}.jpg'
    fallback = f"this.onerror=null;this.src='https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg'" if hero else ""
    note = note_text(v)
    reason = gap_reason(v) if v["status"] == "near" else ""
    lang_chip = f'<span class="chip lang">{v["lang"]}</span>' if v["lang"] != "粤语" else ""
    return f"""
    <article class="card {'hero' if hero else ''} st-{st_cls}">
      <a class="thumbwrap" href="{url}" target="_blank" rel="noopener">
        <img loading="lazy" src="{thumb}" alt="" {'onerror="' + fallback + '"' if fallback else ''}>
        {f'<span class="rank">{rank}</span>' if rank else ''}
      </a>
      <div class="cbody">
        <div class="chiprow">
          <span class="chip {st_cls}">{st_label}</span>{lang_chip}
          <span class="chip ghost">{esc(v["channel_name"])}</span>
          <span class="chip ghost">{date_md(v)}</span>
          {f'<span class="chip gap">{reason}</span>' if reason else ''}
        </div>
        <h3><a href="{url}" target="_blank" rel="noopener">{esc(v["title"])}</a></h3>
        <div class="metrics">{metrics_row(v)}</div>
        {f'<div class="tags">{tag_chips(v)}</div>' if tag_chips(v) else ''}
        {f'<p class="note">{esc(note)}</p>' if note else ''}
      </div>
    </article>"""

def compact_row(v):
    st_label, st_cls = STATUS_META[v["status"]]
    url = f'https://www.youtube.com/watch?v={v["id"]}'
    note = note_text(v)
    return f"""
    <div class="row st-{st_cls}">
      <span class="chip {st_cls} sm">{st_label}</span>
      <div class="rmain">
        <a href="{url}" target="_blank" rel="noopener">{esc(v["title"])}</a>
        <span class="rmeta">{esc(v["channel_name"])} · {date_md(v)} · {fmt(v["view_count"])} 播放 · {fmt(v["like_count"])} 赞 · {fmt(v["comment_count"])} 评论 · 赞/千播 {v["lpk"]}{" · 数据截至上期" if v.get("_stale") else ""}</span>
        {f'<div class="rdelta">{delta_badge(v)}</div>' if delta_badge(v) else ''}
        {f'<p class="note sm">{esc(note)}</p>' if note else ''}
      </div>
    </div>"""

# ---------- scatter svg ----------
def scatter_svg():
    pts = [v for v in CN if (v.get("view_count") or 0) >= 20000]
    W, H = 860, 430
    L, R, T, B = 64, 20, 18, 46
    x0 = math.log10(20000)
    x1 = math.log10(max(50000, max((v["view_count"] or 0) for v in pts) * 1.15)) if pts else math.log10(500000)
    y1 = max(50.0, max(v["lpk"] for v in pts) * 1.12) if pts else 72.0
    def X(v): return L + (math.log10(max(v, 20000)) - x0) / (x1 - x0) * (W - L - R)
    def Y(l): return T + (1 - min(l, y1) / y1) * (H - T - B)
    color = {"hit": "var(--c-hit)", "mid": "var(--c-mid)", "near": "var(--c-near)",
             "paid": "var(--c-paid)", "miss": "var(--c-miss)"}
    label_ids = cur.get("chart_labels", {})
    xt = [(t, lbl) for t, lbl in [(20000, "2w"), (30000, "3w"), (50000, "5w"), (100000, "10w"),
                                  (200000, "20w"), (500000, "50w")] if math.log10(t) <= x1 + 1e-9]
    gx = "".join(
        f'<line x1="{X(v)}" y1="{T}" x2="{X(v)}" y2="{H-B}" class="grid"/>'
        f'<text x="{X(v)}" y="{H-B+18}" class="tick" text-anchor="middle">{t}</text>'
        for v, t in xt)
    gy = "".join(
        f'<line x1="{L}" y1="{Y(l)}" x2="{W-R}" y2="{Y(l)}" class="grid"/>'
        f'<text x="{L-8}" y="{Y(l)+4}" class="tick" text-anchor="end">{l}</text>'
        for l in range(0, int(y1) + 1, 20))
    dots, labels, placed = [], [], []
    for v in pts:
        cx, cy = X(v["view_count"]), Y(v["lpk"])
        tip = f'{v["channel_name"]}｜{v["title"][:34]}｜{fmt(v["view_count"])}播放 · {fmt(v["like_count"])}赞 · {fmt(v["comment_count"])}评论 · 赞/千播{v["lpk"]}'
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="{color[v["status"]]}" class="dot"><title>{esc(tip)}</title></circle>')
        if v["id"] in label_ids:
            anchor = "end" if cx > W - 130 else "start"
            dx = -10 if anchor == "end" else 10
            ly = cy - 9
            # flip below the dot when it would collide with a label already placed
            while any(abs(ly - py) < 13 and abs(cx - px) < 110 for px, py in placed):
                ly = cy + 18 if ly < cy else ly + 14
            placed.append((cx, ly))
            labels.append(f'<text x="{cx+dx:.1f}" y="{ly:.1f}" class="dlabel" text-anchor="{anchor}">{esc(label_ids[v["id"]])}</text>')
    return f"""
    <svg viewBox="0 0 {W} {H}" role="img" aria-label="播放量与互动率散点图">
      {gx}{gy}
      <line x1="{X(30000)}" y1="{T}" x2="{X(30000)}" y2="{H-B}" class="ref"/>
      <text x="{X(30000)+6}" y="{T+14}" class="reflabel">爆款播放门槛 3w</text>
      <line x1="{L}" y1="{Y(8)}" x2="{W-R}" y2="{Y(8)}" class="ref danger"/>
      <text x="{W-R-4}" y="{Y(8)-6}" class="reflabel danger" text-anchor="end">赞/千播 &lt; 8 → 投流红线</text>
      <line x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}" class="axis"/>
      {''.join(dots)}{''.join(labels)}
      <text x="{(L+W-R)/2}" y="{H-6}" class="tick" text-anchor="middle">播放量(对数刻度)→</text>
      <text x="14" y="{(T+H-B)/2}" class="tick" text-anchor="middle" transform="rotate(-90 14 {(T+H-B)/2})">赞/千播 →</text>
    </svg>"""

# ---------- sections ----------
hits_this = [v for v in cn_this if v["status"] == "hit"]
mid_this = [v for v in cn_this if v["status"] == "mid"]
near_this = [v for v in cn_this if v["status"] == "near"]
paid_all = [v for v in CN if v["status"] == "paid"]
hits_prev = [v for v in cn_prev if v["status"] == "hit"]
rest_prev = [v for v in cn_prev if v["status"] not in ("hit", "paid")]

# Issues collected before the 中腰部 tier existed used a 2w fetch threshold, so their
# 1.5–2w band is simply missing — say so rather than let it read as "nobody made any".
_floor = min((v.get("view_count") or 0) for v in data["videos"]) if data["videos"] else 0
legacy_note = ('<b class="warn">本期采集门槛为 2w,1.5–2w 区间未覆盖,此层不完整。</b>'
               if _floor >= 18000 else "")

# keyword pool: two weeks of real Chinese content, paid excluded
KW_POOL = [v for v in CN if v["status"] != "paid"]
TOPICS, HOOK_ROWS = mine_keywords(KW_POOL)

tldr_html = "".join(
    f'<div class="tcard"><div class="tnum">{i+1}</div><div><h4>{esc(t["t"])}</h4><p>{esc(t["d"])}</p></div></div>'
    for i, t in enumerate(cur.get("tldr", [])))

hero_html = "".join(video_card(v, rank=i + 1, hero=(i == 0)) for i, v in enumerate(hits_this))
mid_html = "".join(compact_row(v) for v in sort_v(mid_this))
near_html = "".join(video_card(v) for v in near_this)

def kw_rows(topics):
    out = []
    for w, a in topics:
        b = a["best"]
        tot = sum(a["views"])
        out.append(f"""<tr>
          <td class="kw">{esc(w)}</td>
          <td class="num">{a["n"]}</td>
          <td class="num">{fmt(tot)}</td>
          <td class="num">{fmt(tot // a["n"])}</td>
          <td><a href="https://www.youtube.com/watch?v={b["id"]}" target="_blank" rel="noopener">{esc(b["title"][:38])}</a>
              <span class="kwsrc">{esc(b["channel_name"])} · {fmt(b["view_count"])}</span></td></tr>""")
    return "".join(out)

hook_html = "".join(f"""
  <div class="hookcard"><h4>{esc(cat)}</h4>
    <div class="hooklist">{''.join(
      f'<span class="hk"><b>{esc(w)}</b><i>{n}条</i><em>最高 {fmt(b["view_count"])}</em></span>'
      for w, n, b in hits)}</div>
  </div>""" for cat, hits in HOOK_ROWS)
paid_html = "".join(compact_row(v) for v in sort_v(paid_all))
prev_html = "".join(video_card(v, rank=i + 1) for i, v in enumerate(hits_prev))
prev_rest_html = "".join(compact_row(v) for v in rest_prev)
en_html = "".join(compact_row(v) for v in en_all)

themes_html = "".join(f"""
  <div class="theme">
    <div class="thead"><h4>{esc(t["name"])}</h4>
      <span class="chip ghost">双周 {len(t["vids"])} 条</span>
      <span class="chip emo">{esc(t["emotion"])}</span></div>
    <p>{esc(t["note"])}</p>
  </div>""" for t in cur.get("themes", []))

patterns_html = "".join(f"""
  <div class="pat"><h4>{i+1}. {esc(p["name"])}</h4><p>{esc(p["desc"])}</p>
    <div class="ex">{''.join(f'<span>「{esc(e)}」</span>' for e in p["examples"])}</div>
  </div>""" for i, p in enumerate(cur.get("patterns", [])))

# channel table
ch_notes = cur.get("channel_notes", {})
by_ch = {}
for v in CN + EN:
    by_ch.setdefault(v["channel_name"], []).append(v)
CAT_ORDER = ["直接竞品", "财经APP", "中文财经顶流", "财经垂类(主持类)", "自媒体", "英文Podcast顶流"]
rows = []
for c in sorted(data["channels"], key=lambda c: (CAT_ORDER.index(c.get("cat")) if c.get("cat") in CAT_ORDER else 99, -(c.get("subs") or 0))):
    if c.get("error"):
        continue
    vs = by_ch.get(c["channel"], [])
    h_this = sum(1 for v in vs if v["status"] == "hit" and v["week"] == "this")
    h_prev = sum(1 for v in vs if v["status"] == "hit" and v["week"] == "prev")
    mx = max((v["view_count"] or 0) for v in vs) if vs else 0
    note = ch_notes.get(c["channel"], "")
    rows.append(f"""<tr>
      <td class="dim">{esc(c["cat"])}</td>
      <td><a href="https://www.youtube.com/@{c["handle"]}" target="_blank" rel="noopener">{esc(c["channel"])}</a></td>
      <td class="num">{fmt(c.get("subs"))}</td>
      <td class="num">{h_this or "·"}</td>
      <td class="num">{h_prev or "·"}</td>
      <td class="num">{fmt(mx) if mx else "·"}</td>
      <td class="notecell">{esc(note)}</td></tr>""")
excluded_html = "".join(f'<p class="excl">⚠ {esc(e["name"])}:{esc(e["reason"])}</p>' for e in cur.get("excluded", []))

gen_date = datetime.date.today().strftime("%Y.%m.%d")

# week switcher — __NAV__ is filled per output location (root vs weeks/)
all_weeks = sorted((p.stem for p in (ROOT / "data").glob("*.json")), reverse=True)

def week_stats(w):
    """Each issue's own date range + hit count, as counted when that issue was built."""
    yr, wn = w.split("-W")
    mon = datetime.date.fromisocalendar(int(yr), int(wn), 1).strftime("%Y%m%d")
    d = json.loads((ROOT / "data" / f"{w}.json").read_text())
    cp = ROOT / "curation" / f"{w}.json"
    rng = json.loads(cp.read_text()).get("range", "") if cp.exists() else ""
    n = sum(1 for v in d["videos"]
            if v["upload_date"] >= mon and v.get("lang") in ("粤语", "普通话") and classify(v) == "hit")
    return rng, n

WEEK_STATS = {w: week_stats(w) for w in all_weeks}

def nav(prefix):
    if len(all_weeks) < 2:
        return ""
    items = []
    for i, w in enumerate(all_weeks):
        rng, n = WEEK_STATS[w]
        cur_cls = " cur" if w == WEEK else ""
        tag = '<span class="wknew">最新</span>' if i == 0 else ""
        inner = (f'<b>{w.split("-W")[1].lstrip("0")} 周{tag}</b>'
                 f'<span class="wkr">{esc(rng.replace("2026.", ""))}</span>'
                 f'<span class="wkh">{n} 条爆款</span>')
        items.append(f'<span class="wk{cur_cls}">{inner}</span>' if w == WEEK
                     else f'<a class="wk" href="{prefix}{w}.html">{inner}</a>')
    return f'<nav class="weeks"><span class="wklab">期数</span>{"".join(items)}</nav>'

page = f"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>粤语财经爆款周报 · {esc(cur.get("label", WEEK))}</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axisc: #c3c2b7; --border: rgba(11,11,11,.10);
  --c-hit: #2a78d6; --c-near: #eda100; --c-paid: #e34948; --c-miss: #898781; --c-good: #006300; --c-mid: #4a3aa7;
  --mid-bg: rgba(74,58,167,.10);
  --hit-bg: rgba(42,120,214,.09); --near-bg: rgba(237,161,0,.12); --paid-bg: rgba(227,73,72,.09);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0d0d0d; --surface: #1a1a19; --ink: #fff; --ink2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axisc: #383835; --border: rgba(255,255,255,.10);
    --c-hit: #3987e5; --c-near: #c98500; --c-paid: #e66767; --c-good: #0ca30c; --c-mid: #9085e9;
    --mid-bg: rgba(144,133,233,.15);
    --hit-bg: rgba(57,135,229,.14); --near-bg: rgba(201,133,0,.16); --paid-bg: rgba(230,103,103,.13);
  }}
}}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.65 system-ui, -apple-system, "PingFang SC", "Segoe UI", sans-serif; }}
a {{ color: inherit; }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 80px; }}
header.top {{ padding: 34px 0 10px; }}
.kicker {{ color: var(--c-hit); font-weight: 700; letter-spacing: .12em; font-size: 13px; }}
h1 {{ font-size: 34px; line-height: 1.25; margin: 6px 0 10px; }}
.sub {{ color: var(--ink2); max-width: 72ch; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
.badge {{ background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 5px 14px; font-size: 13px; color: var(--ink2); }}
.badge b {{ color: var(--ink); }}
.weeks {{ margin-top: 22px; display: flex; gap: 10px; align-items: stretch; overflow-x: auto; padding-bottom: 4px; }}
.wklab {{ align-self: center; font-size: 12px; color: var(--muted); letter-spacing: .1em; flex: 0 0 auto; padding-right: 2px; }}
.wk {{ flex: 0 0 auto; display: flex; flex-direction: column; gap: 2px; min-width: 132px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      padding: 10px 14px; text-decoration: none; color: var(--ink2); transition: border-color .12s, transform .12s; }}
.wk b {{ font-size: 15px; color: var(--ink); display: flex; align-items: center; gap: 6px; }}
.wkr {{ font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }}
.wkh {{ font-size: 12.5px; color: var(--ink2); }}
.wknew {{ font-size: 10px; font-weight: 700; letter-spacing: .05em; color: var(--c-hit);
         background: var(--hit-bg); border-radius: 4px; padding: 1px 5px; }}
.wk.cur {{ border-color: var(--c-hit); box-shadow: inset 0 0 0 1px var(--c-hit); }}
.wk.cur b {{ color: var(--c-hit); }}
a.wk:hover {{ border-color: var(--c-hit); transform: translateY(-1px); }}
h2 {{ font-size: 22px; margin: 54px 0 6px; }}
h2 .cnt {{ color: var(--muted); font-weight: 400; font-size: 15px; margin-left: 8px; }}
.secdesc {{ color: var(--ink2); margin-bottom: 18px; max-width: 78ch; font-size: 14px; }}
/* tldr */
.tgrid {{ display: grid; gap: 12px; margin-top: 16px; }}
.tcard {{ display: flex; gap: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }}
.tnum {{ flex: 0 0 30px; height: 30px; border-radius: 8px; background: var(--hit-bg); color: var(--c-hit); font-weight: 800; display: grid; place-items: center; }}
.tcard h4 {{ font-size: 15.5px; margin-bottom: 3px; }}
.tcard p {{ color: var(--ink2); font-size: 14px; }}
/* cards */
.cards {{ display: grid; gap: 14px; }}
.card {{ display: flex; gap: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 14px; }}
.card.hero {{ flex-direction: column; gap: 10px; }}
.card.hero .thumbwrap {{ width: 100%; max-height: 380px; }}
.thumbwrap {{ position: relative; flex: 0 0 210px; width: 210px; border-radius: 10px; overflow: hidden; align-self: flex-start; }}
.card.hero .thumbwrap {{ width: 100%; flex: none; }}
.thumbwrap img {{ width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; }}
.rank {{ position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,.72); color: #fff; font-weight: 800; border-radius: 8px; padding: 2px 10px; font-size: 14px; }}
.cbody {{ flex: 1; min-width: 0; }}
.chiprow {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
.chip {{ font-size: 12px; font-weight: 700; border-radius: 999px; padding: 2px 10px; }}
.chip.sm {{ flex: 0 0 auto; align-self: flex-start; margin-top: 2px; }}
.chip.hit {{ background: var(--hit-bg); color: var(--c-hit); }}
.chip.near {{ background: var(--near-bg); color: var(--c-near); }}
.chip.paid {{ background: var(--paid-bg); color: var(--c-paid); }}
.chip.miss {{ background: var(--bg); color: var(--muted); border: 1px solid var(--border); }}
.chip.mid {{ background: var(--mid-bg); color: var(--c-mid); }}
/* keyword tables */
td.kw {{ font-weight: 700; white-space: nowrap; }}
.kwsrc {{ display: block; color: var(--muted); font-size: 12px; margin-top: 1px; }}
.hookgrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }}
.hookcard {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }}
.hookcard h4 {{ font-size: 15px; margin-bottom: 10px; }}
.hooklist {{ display: flex; flex-direction: column; gap: 7px; }}
.hk {{ display: flex; align-items: baseline; gap: 8px; font-size: 13.5px; }}
.hk b {{ color: var(--ink); min-width: 74px; }}
.hk i {{ font-style: normal; color: var(--muted); font-size: 12.5px; }}
.hk em {{ font-style: normal; margin-left: auto; color: var(--c-hit); font-size: 12.5px; font-variant-numeric: tabular-nums; }}
.chip.ghost {{ background: transparent; border: 1px solid var(--border); color: var(--ink2); font-weight: 500; }}
.chip.gap {{ background: var(--near-bg); color: var(--c-near); font-weight: 600; }}
.chip.lang {{ background: transparent; border: 1px dashed var(--border); color: var(--muted); font-weight: 500; }}
.chip.emo {{ background: var(--hit-bg); color: var(--c-hit); font-weight: 600; }}
.card h3 {{ font-size: 16.5px; line-height: 1.45; margin-bottom: 8px; }}
.card.hero h3 {{ font-size: 20px; }}
.card h3 a, .row a {{ text-decoration: none; }}
.card h3 a:hover, .row a:hover {{ text-decoration: underline; }}
.metrics {{ display: flex; flex-wrap: wrap; gap: 14px; color: var(--ink2); font-size: 13.5px; }}
.metrics b {{ color: var(--ink); font-size: 15px; }}
.m.lpk b {{ color: var(--c-hit); }}
.m.grow {{ color: var(--c-good); }} .m.grow b {{ color: var(--c-good); }}
.m.stale {{ color: var(--muted); font-size: 12.5px; }}
.m.flat {{ color: var(--c-paid); }} .m.flat b {{ color: var(--c-paid); }}
.tags {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.tag {{ font-size: 12px; color: var(--c-hit); background: var(--hit-bg); border-radius: 6px; padding: 1px 8px; }}
.note {{ margin-top: 9px; color: var(--ink2); font-size: 13.5px; border-left: 3px solid var(--grid); padding-left: 10px; }}
.note.sm {{ margin-top: 5px; }}
/* compact rows */
.rows {{ display: grid; gap: 10px; }}
.row {{ display: flex; gap: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }}
.rmain {{ min-width: 0; }}
.rmain > a {{ font-weight: 600; text-decoration: none; font-size: 14.5px; line-height: 1.45; display: block; }}
.rmeta {{ color: var(--muted); font-size: 12.5px; }}
.rdelta {{ margin-top: 4px; font-size: 12.5px; }}
/* chart */
.chartbox {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px 14px 8px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 18px; padding: 4px 10px 10px; font-size: 13px; color: var(--ink2); }}
.legend i {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 6px; }}
svg {{ width: 100%; height: auto; display: block; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.axis {{ stroke: var(--axisc); stroke-width: 1.5; }}
.tick {{ fill: var(--muted); font-size: 12px; }}
.dlabel {{ fill: var(--ink2); font-size: 12px; font-weight: 600; }}
.dot {{ stroke: var(--surface); stroke-width: 2; }}
.ref {{ stroke: var(--axisc); stroke-dasharray: 5 4; stroke-width: 1.4; }}
.ref.danger {{ stroke: var(--c-paid); opacity: .75; }}
.reflabel {{ fill: var(--muted); font-size: 12px; font-weight: 600; }}
.reflabel.danger {{ fill: var(--c-paid); }}
/* themes & patterns */
.themes {{ display: grid; gap: 12px; }}
.theme {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }}
.thead {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 6px; }}
.theme h4 {{ font-size: 16px; }}
.theme p {{ color: var(--ink2); font-size: 14px; }}
.pgrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
.pat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }}
.pat h4 {{ margin-bottom: 4px; font-size: 15.5px; }}
.pat p {{ color: var(--ink2); font-size: 13.5px; }}
.ex {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.ex span {{ font-size: 12.5px; color: var(--c-hit); background: var(--hit-bg); border-radius: 6px; padding: 2px 8px; }}
/* table */
.tblwrap {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; }}
table {{ border-collapse: collapse; width: 100%; min-width: 880px; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 9px 12px; border-top: 1px solid var(--grid); vertical-align: top; }}
thead th {{ border-top: none; color: var(--muted); font-size: 12.5px; white-space: nowrap; position: sticky; top: 0; background: var(--surface); }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.dim {{ color: var(--muted); white-space: nowrap; }}
td a {{ text-decoration: none; font-weight: 600; }}
.notecell {{ color: var(--ink2); font-size: 12.8px; min-width: 300px; }}
.excl {{ color: var(--c-paid); font-size: 13.5px; margin-top: 10px; }}
.warn {{ color: var(--c-near); }}
/* footer */
.method {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px; margin-top: 16px; }}
.method h4 {{ margin: 12px 0 4px; }} .method h4:first-child {{ margin-top: 0; }}
.method p, .method li {{ color: var(--ink2); font-size: 14px; }}
.method code {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 1px 7px; font-size: 12.5px; }}
footer {{ margin-top: 40px; color: var(--muted); font-size: 12.5px; }}
@media (max-width: 720px) {{
  .card {{ flex-direction: column; }}
  .thumbwrap {{ width: 100%; flex: none; }}
  h1 {{ font-size: 26px; }}
}}
</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <div class="kicker">粤语财经 YOUTUBE 情报站</div>
  <h1>爆款周报 · {esc(cur.get("label", WEEK))}</h1>
  <p class="sub">统计窗口 {esc(cur.get("range", ""))}(上周 {esc(cur.get("prev_range", ""))} 做对照)。榜单以粤语频道为主,普通话账号打标对照,英文 Podcast 顶流单列为选题预警雷达。</p>
  <div class="badges">
    <span class="badge">爆款标准:播放 ≥ <b>3w</b> · 评论 ≥ <b>20</b> · 点赞 ≥ <b>1k</b></span>
    <span class="badge">投流红线:赞/千播 &lt; <b>8</b></span>
    <span class="badge">监测频道 <b>{len(data["channels"])}</b> 个 · 入库视频 <b>{len(data["videos"])}</b> 条</span>
    <span class="badge">数据采集 <b>{gen_date}</b></span>
  </div>
  __NAV__
</header>

<section>
  <h2>本周结论 TL;DR</h2>
  <div class="tgrid">{tldr_html}</div>
</section>

<section>
  <h2>本周爆款榜<span class="cnt">{esc(cur.get("range", ""))} · 三项全达标 {len(hits_this)} 条</span></h2>
  <p class="secdesc">同时满足播放 ≥3w、评论 ≥20、点赞 ≥1k 的中文内容,按播放量排序。</p>
  <div class="cards">{hero_html}</div>
</section>

<section>
  <h2>中腰部选题池<span class="cnt">{esc(cur.get("range", ""))} · {len(mid_this)} 条</span></h2>
  <p class="secdesc">播放 ≥1.5w、点赞 ≥500、评论 ≥10 —— 达不到爆款量级,但数据真实、题材成立。这一层看的不是「怎么打爆」,而是<b>「大家在做什么题」</b>:可复用的选题、可借的角度、可测试的方向都在这里。{legacy_note}</p>
  <div class="rows">{mid_html}</div>
</section>

<section>
  <h2>选题关键词<span class="cnt">双周中文内容 {len(KW_POOL)} 条 · 已剔除投流</span></h2>
  <p class="secdesc">对两周所有真实中文内容的标题做分词统计,按<b>累计播放</b>排序——出现得多不等于带量,这张表看的是「哪个词真的带来播放」。均播是该词下的平均水平,可以据此判断一个题值不值得做。</p>
  <div class="tblwrap"><table>
    <thead><tr><th>关键词</th><th class="num">出现</th><th class="num">累计播放</th><th class="num">均播</th><th>该词下最高播放的一条</th></tr></thead>
    <tbody>{kw_rows(TOPICS)}</tbody>
  </table></div>
</section>

<section>
  <h2>标题钩子词<span class="cnt">按最高播放排序</span></h2>
  <p class="secdesc">四类情绪钩子在本双周内容里的实际使用情况。写标题时按类取词,不要同类堆叠——一个恐慌词 + 一个悬念词的组合,比三个恐慌词更有效。</p>
  <div class="hookgrid">{hook_html}</div>
</section>

<section>
  <h2>差一口气<span class="cnt">{len(near_this)} 条</span></h2>
  <p class="secdesc">播放接近或已过 3w、互动真实,但有一项未达标——标出的差距就是下一步的优化目标。</p>
  <div class="cards">{near_html}</div>
</section>

<section>
  <h2>播放 × 互动:一张图识别投流</h2>
  <p class="secdesc">每个点是一条近两周播放 ≥2w 的中文视频。横轴播放量(对数),纵轴赞/千播。右下角=高播放低互动,基本可判定买量;右上角才是真爆款。悬停查看明细。</p>
  <div class="chartbox">
    <div class="legend">
      <span><i style="background:var(--c-hit)"></i>爆款</span>
      <span><i style="background:var(--c-near)"></i>差一口气</span>
      <span><i style="background:var(--c-paid)"></i>疑似投流</span>
      <span><i style="background:var(--c-miss)"></i>未达标</span>
    </div>
    {scatter_svg()}
  </div>
</section>

<section>
  <h2>投流观察席<span class="cnt">{len(paid_all)} 条</span></h2>
  <p class="secdesc">高播放但互动断崖(赞/千播 &lt;8 或评论 ≤5)。这些数字不构成内容参考,但能看出谁在花钱、钱花在什么题材上。</p>
  <div class="rows">{paid_html}</div>
</section>

<section>
  <h2>选题地图<span class="cnt">双周题材聚类</span></h2>
  <div class="themes">{themes_html}</div>
</section>

<section>
  <h2>爆款六式<span class="cnt">从双周爆款反推的标题打法</span></h2>
  <div class="pgrid">{patterns_html}</div>
</section>

<section>
  <h2>上周对照榜<span class="cnt">{esc(cur.get("prev_range", ""))} · 爆款 {len(hits_prev)} 条</span></h2>
  <div class="cards">{prev_html}</div>
  <div class="rows" style="margin-top:12px">{prev_rest_html}</div>
</section>

<section>
  <h2>英文区预警雷达<span class="cnt">All-In / BG2 / The Compound</span></h2>
  <p class="secdesc">英文顶流的题材通常领先中文区 3–7 天。每周扫一遍,提前锁定下周粤语选题。</p>
  <div class="rows">{en_html}</div>
</section>

<section>
  <h2>频道体检表<span class="cnt">{len(data["channels"])} 个监测位</span></h2>
  <div class="tblwrap"><table>
    <thead><tr><th>类型</th><th>频道</th><th class="num">订阅</th><th class="num">本周爆款</th><th class="num">上周爆款</th><th class="num">双周最高播放</th><th>运营观察</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  {excluded_html}
</section>

<section>
  <h2>方法论与周更流程</h2>
  <div class="method">
    <h4>爆款判定</h4>
    <p>播放 ≥ 30,000 且 评论 ≥ 20 且 点赞 ≥ 1,000,三项同时满足。单看播放会被投流骗:本期 42.6w 播放的视频只有 8 个赞。辅助指标「赞/千播」:真爆款均 ≥14,&lt;8 判疑似投流,8–14 为混合区。</p>
    <h4>采集口径</h4>
    <p>每频道取最新 40 条常规视频(不含 Shorts),播放 ≥2w 的抓取完整互动数据。周五至周日发布的视频可能尚未发酵完,下一期复查补录。{esc(cur.get("workflow_note", ""))}</p>
    <h4>周更操作(每周一上午)</h4>
    <p><code>cd ~/finance-hits && python3 collect.py && python3 build.py</code>,然后让 Claude 补当周运营拆解(curation/当周.json)即可重新生成本页。</p>
  </div>
</section>

<footer>粤语财经爆款周报 · {WEEK} · 数据来自 YouTube 公开页面,采集于 {gen_date} · 仅供内部选题参考</footer>
</div>
</body>
</html>"""

(ROOT / "weeks").mkdir(exist_ok=True)
(ROOT / "weeks" / f"{WEEK}.html").write_text(page.replace("__NAV__", nav("")))
outs = [f"weeks/{WEEK}.html"]
if WEEK == all_weeks[0]:                      # newest week is also the landing page
    (ROOT / "index.html").write_text(page.replace("__NAV__", nav("weeks/")))
    outs.append("index.html")
print(f"built {' + '.join(outs)}  ({len(page)//1024} KB) · 本周爆款 {len(hits_this)} · "
      f"差一口气 {len(near_this)} · 投流 {len(paid_all)} · 上周爆款 {len(hits_prev)}")
