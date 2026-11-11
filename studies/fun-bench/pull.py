import yt_dlp,json,sys
from concurrent.futures import ThreadPoolExecutor
H=["ahju","xiao_lin_shuo","RainIsHere","Finance730hk","BolooFinance","ChiefPaPa","GiantCutie-CH","conita3706"]
def go(h):
    o={"quiet":True,"extract_flat":True,"no_warnings":True,"playlistend":80}
    try:
        with yt_dlp.YoutubeDL(o) as y: i=y.extract_info(f"https://www.youtube.com/@{h}/videos",download=False)
    except Exception as e: return h,{"err":str(e)[:200]}
    return h,{"title":i.get("channel") or i.get("title"),"subs":i.get("channel_follower_count"),
      "videos":[{k:e.get(k) for k in("id","title","view_count","duration")} for e in i.get("entries") or []]}
with ThreadPoolExecutor(4) as ex: R=dict(ex.map(go,H))
json.dump(R,open("flat.json","w"),ensure_ascii=False,indent=1)
for h,r in R.items(): print(h,r.get("title"),r.get("subs"),len(r.get("videos",[])),r.get("err",""))
