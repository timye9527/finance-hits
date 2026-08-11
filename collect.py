#!/usr/bin/env python3
"""Collect recent videos from HK Cantonese finance YouTube channels + benchmarks."""
import json, sys, time, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import yt_dlp

CHANNELS = [
    ("直接竞品", "富途牛牛", "futuhk", "粤语"),
    ("直接竞品", "老虎证券", "tigerbrokershk", "粤语"),
    ("直接竞品", "漲樂全球通 ZL Global", "zlglobal_hk", "粤语"),
    ("直接竞品", "光大证券国际", "everbrightsecuritiesintl", "粤语"),
    ("直接竞品", "致富 CHIEF", "ChiefGroup", "粤语"),
    ("直接竞品", "華盛証券", "vbrokers_app", "粤语"),
    ("财经APP", "AASTOCKS", "AASTOCKS_AATV", "粤语"),
    ("中文财经顶流", "小Lin说", "xiao_lin_shuo", "普通话"),
    ("财经垂类(主持类)", "财自FM", "fmchoyg", "粤语"),
    ("财经垂类(主持类)", "Finance730", "Finance730hk", "粤语"),
    ("自媒体", "张志云Papa", "ChiefPaPa", "普通话"),
    ("自媒体", "加密大漂亮", "GiantCutie-CH", "普通话"),
    ("自媒体", "RainIsHere", "RainIsHere", "粤语"),
    ("自媒体", "30岁财务自由", "30FinancialFreedomByAge30", "粤语"),
    ("自媒体", "Homily小金-投资有道", "homilycharthk1998", "粤语"),
    ("自媒体", "阿豬 Ah Ju", "ahju", "粤语"),
    ("自媒体", "Chart-reader CUP", "chartreadercup", "粤语"),
    ("自媒体", "東網Money18", "Money18-oncc", "粤语"),
    ("自媒体", "菠蘿包工作室 BoLoo", "BolooFinance", "粤语"),
    ("自媒体", "RagaFinance財經台", "RagaFinance", "粤语"),
    ("自媒体", "InvesTalk 講投資", "InvesTalk", "粤语"),
    ("自媒体", "etnet經濟通", "etnethk", "粤语"),
    ("自媒体", "熊麗萍Conita", "conita3706", "粤语"),
    ("英文Podcast顶流", "All-In Podcast", "allin", "英语"),
    ("英文Podcast顶流", "BG2 Pod", "BG2Pod", "英语"),
    ("英文Podcast顶流", "The Compound", "TheCompoundNews", "英语"),
]

import pathlib
TODAY = datetime.date.today()
# 统计上一自然周 + 再前一周做对照:窗口 = 上上周一 至今
_monday = TODAY - datetime.timedelta(days=TODAY.weekday())
CUTOFF = (_monday - datetime.timedelta(days=14)).strftime("%Y%m%d")
ISO = (TODAY - datetime.timedelta(days=7)).isocalendar()  # 报告周 = 上一自然周
WEEK = f"{ISO[0]}-W{ISO[1]:02d}"
OUT = pathlib.Path(__file__).parent / "data" / f"{WEEK}.json"
CAND_VIEWS = 12000           # flat-list view threshold to fetch full metadata
                             # (below the 1.5w 中腰部 line, so nothing near it is missed)
MAX_CAND = 16                # max full fetches per channel

FLAT_OPTS = {"quiet": True, "extract_flat": True, "playlistend": 40, "no_warnings": True}
FULL_OPTS = {"quiet": True, "skip_download": True, "no_warnings": True}


def get_channel_videos(cat, name, handle, lang):
    url = f"https://www.youtube.com/@{handle}/videos"
    try:
        with yt_dlp.YoutubeDL(FLAT_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return {"channel": name, "error": str(e)[:200], "candidates": []}
    entries = info.get("entries") or []
    cands = [e for e in entries if (e.get("view_count") or 0) >= CAND_VIEWS][:MAX_CAND]
    return {"cat": cat, "channel": name, "handle": handle, "lang": lang,
            "subs": info.get("channel_follower_count"),
            "n_listed": len(entries), "candidates": cands}


def fetch_video(vid, tries=2):
    """One retry with a pause — YouTube's bot check trips on bursts, and a lost fetch
    can silently drop a whole channel from the week. backfill.py is the second line."""
    for attempt in range(tries):
        try:
            with yt_dlp.YoutubeDL(FULL_OPTS) as ydl:
                d = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return {k: d.get(k) for k in
                    ("id", "title", "upload_date", "view_count", "like_count",
                     "comment_count", "duration", "channel", "thumbnail", "description")}
        except Exception as e:
            if attempt == tries - 1:
                return {"id": vid, "error": str(e)[:200]}
            time.sleep(4 + attempt * 4)


def main():
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(get_channel_videos, *c): c for c in CHANNELS}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            print(f"[chan] {r['channel']}: {len(r.get('candidates', []))} candidates"
                  + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)

    # full fetch candidates
    vids = []
    for r in results:
        for e in r.get("candidates", []):
            vids.append((r, e["id"]))
    print(f"total candidate videos: {len(vids)}", flush=True)

    videos = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch_video, vid): (r, vid) for r, vid in vids}
        for f in as_completed(futs):
            r, vid = futs[f]
            d = f.result()
            if d.get("error"):
                print(f"[vid ERR] {vid}: {d['error']}", flush=True)
                continue
            if (d.get("upload_date") or "") < CUTOFF:
                continue
            d.update({"cat": r["cat"], "channel_name": r["channel"],
                      "handle": r["handle"], "lang": r["lang"], "subs": r.get("subs")})
            # trim description
            if d.get("description"):
                d["description"] = d["description"][:400]
            videos.append(d)
            print(f"[vid] {d['channel_name']} | {d['upload_date']} | v={d['view_count']} "
                  f"l={d['like_count']} c={d['comment_count']} | {(d['title'] or '')[:50]}", flush=True)

    out = {"generated": datetime.datetime.now().isoformat(), "cutoff": CUTOFF,
           "channels": [{k: v for k, v in r.items() if k != "candidates"} for r in results],
           "videos": videos}
    with open(OUT, "w") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"\nsaved {len(videos)} videos -> {OUT}")


if __name__ == "__main__":
    main()
