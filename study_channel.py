#!/usr/bin/env python3
"""One-off deep pull of a single channel, for studying how it grew (起号研究).

The weekly collector only sees each channel's latest 40 uploads. To see how an account
started — first videos, when it broke out, what changed around the breakout — we need
its whole upload history once.

Run on the Mac (YouTube is not reachable from the cloud session):
    /opt/anaconda3/bin/python3 study_channel.py <handle> [--max 400]
    git add studies/ && git commit -m "起号研究: <handle>" && git push
Out: studies/<handle>.json  — channel info + every video (videos / streams / shorts tabs)
     with upload date, views, likes, comments, duration, title, description head.
Takes ~10–20 minutes for a few hundred videos; it paces itself to avoid YouTube's bot check.
"""
import argparse, datetime, json, pathlib, sys, time
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

ROOT = pathlib.Path(__file__).parent
FLAT_OPTS = {"quiet": True, "extract_flat": True, "no_warnings": True}
FULL_OPTS = {"quiet": True, "skip_download": True, "no_warnings": True}


def flat(handle, tab):
    try:
        with yt_dlp.YoutubeDL(FLAT_OPTS) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/@{handle}/{tab}", download=False)
    except Exception as e:
        print(f"[flat ERR] {tab}: {str(e)[:160]}", file=sys.stderr)
        return None, []
    return info, [e for e in (info.get("entries") or []) if e.get("id")]


def full(vid):
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(FULL_OPTS) as ydl:
                d = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return {k: d.get(k) for k in ("id", "title", "upload_date", "timestamp", "view_count", "like_count",
                                          "comment_count", "duration", "was_live", "tags")} | {
                "description": (d.get("description") or "")[:400]}
        except Exception as e:
            if attempt == 2:
                print(f"[vid ERR] {vid}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(5 + attempt * 5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle", help="channel handle without @")
    ap.add_argument("--max", type=int, default=400, help="max videos to fetch in full")
    a = ap.parse_args()
    handle = a.handle.lstrip("@")

    rows, chan = [], {}
    for tab in ("videos", "streams", "shorts"):
        info, entries = flat(handle, tab)
        if info and not chan:
            chan = {"title": info.get("channel") or info.get("title"), "subs": info.get("channel_follower_count"),
                    "channel_id": info.get("channel_id")}
        rows += [(tab, e["id"]) for e in entries]
        print(f"[{tab}] {len(entries)}", file=sys.stderr)
    rows = rows[:a.max]

    out = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        for (tab, _), d in zip(rows, ex.map(full, [vid for _, vid in rows])):
            if d:
                d["tab"] = tab
                out.append(d)
                print(f"[vid] {d['upload_date']} v={d['view_count']} | {(d['title'] or '')[:50]}", file=sys.stderr)

    out.sort(key=lambda d: d.get("upload_date") or "")
    dest = ROOT / "studies" / f"{handle}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps({"handle": handle, "fetched": datetime.datetime.now().isoformat(),
                                "channel": chan, "videos": out}, ensure_ascii=False, indent=1))
    print(f"saved {len(out)} videos -> {dest}")


if __name__ == "__main__":
    main()
