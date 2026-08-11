#!/usr/bin/env python3
"""Re-fetch the videos collect.py lost to YouTube's bot check.

collect.py runs 6 workers; when the candidate list is large that trips rate limiting and
whole channels can vanish from a week's data. This walks the same candidate list
single-threaded with a delay, fetches only what's missing, and merges it back in.

Usage: python3 backfill.py [2026-W32]
"""
import json, sys, time, datetime
from pathlib import Path
import yt_dlp

from collect import CHANNELS, CUTOFF, CAND_VIEWS, MAX_CAND, FLAT_OPTS, FULL_OPTS

ROOT = Path(__file__).parent
WEEK = sys.argv[1] if len(sys.argv) > 1 else sorted(p.stem for p in (ROOT / "data").glob("*.json"))[-1]
PATH = ROOT / "data" / f"{WEEK}.json"
DELAY = 2.5          # seconds between full fetches — the whole point of this script

# Backfilling an older week must not pull in videos from weeks after it: collect.py's
# CUTOFF is relative to today, so bound the window by the issue's own dates.
_y, _w = WEEK.split("-W")
_mon = datetime.date.fromisocalendar(int(_y), int(_w), 1)
WIN_LO = (_mon - datetime.timedelta(days=7)).strftime("%Y%m%d")   # issue covers its week + the comparison week
WIN_HI = (_mon + datetime.timedelta(days=7)).strftime("%Y%m%d")   # exclusive

data = json.loads(PATH.read_text())
have = {v["id"] for v in data["videos"]}
print(f"{WEEK}: {len(have)} videos already in file")

missing = []
for cat, name, handle, lang in CHANNELS:
    try:
        with yt_dlp.YoutubeDL(FLAT_OPTS) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/@{handle}/videos", download=False)
    except Exception as e:
        print(f"[flat ERR] {name}: {str(e)[:80]}")
        continue
    cands = [e for e in (info.get("entries") or []) if (e.get("view_count") or 0) >= CAND_VIEWS][:MAX_CAND]
    for e in cands:
        if e["id"] not in have:
            missing.append((cat, name, handle, lang, info.get("channel_follower_count"), e["id"]))
    time.sleep(0.5)

print(f"{len(missing)} candidates missing — fetching at {DELAY}s intervals\n")

added, still_failing = 0, []
for i, (cat, name, handle, lang, subs, vid) in enumerate(missing, 1):
    try:
        with yt_dlp.YoutubeDL(FULL_OPTS) as ydl:
            d = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except Exception as e:
        still_failing.append((name, vid, str(e)[:60]))
        print(f"[{i}/{len(missing)}] FAIL {name} {vid}")
        time.sleep(DELAY * 2)
        continue
    up = d.get("upload_date") or ""
    if not (WIN_LO <= up < WIN_HI):
        time.sleep(DELAY)
        continue
    rec = {k: d.get(k) for k in ("id", "title", "upload_date", "view_count", "like_count",
                                 "comment_count", "duration", "channel", "thumbnail", "description")}
    if rec.get("description"):
        rec["description"] = rec["description"][:400]
    rec.update({"cat": cat, "channel_name": name, "handle": handle, "lang": lang, "subs": subs,
                # counts were read today, not during that week — never use as a delta baseline
                "_backfilled": True})
    data["videos"].append(rec)
    added += 1
    print(f"[{i}/{len(missing)}] {name} | {rec['upload_date']} | v={rec['view_count']} "
          f"l={rec['like_count']} c={rec['comment_count']} | {(rec['title'] or '')[:46]}")
    time.sleep(DELAY)

data["backfilled"] = datetime.datetime.now().isoformat()
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1))
print(f"\nadded {added} videos → {PATH} (total {len(data['videos'])})")
if still_failing:
    print(f"{len(still_failing)} still failing:")
    for n, v, e in still_failing[:10]:
        print(f"  {n} {v}: {e}")
