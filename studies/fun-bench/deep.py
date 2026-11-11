import yt_dlp,json,sys,os
IDS={"ahju":["CszEkQK8qqQ","yU5HXmOPZmY","rfve2cU9hxA"],"xiao_lin_shuo":["iGz2uWl-kGc","B4jIyufgy-s"],
"Finance730hk":["9KgGdCJBskM","ojChLoZalPU","l8iHTZmhEsI"],"RainIsHere":["Yi9v9sD-a_c","QO8aVjtWyr8"],"ChiefPaPa":["WvA4Xa7h014","g70ho6HJE_0"],"GiantCutie-CH":["k9L3_qEa4kg"]}
os.makedirs("v",exist_ok=True); out={}
for h,ids in IDS.items():
  for i in ids:
    o={"quiet":True,"no_warnings":True,"format":"worstvideo[height>=240][ext=mp4]/worst[ext=mp4]/worst","outtmpl":f"v/{i}.%(ext)s",
       "writeautomaticsub":True,"writesubtitles":True,"subtitleslangs":["zh-HK","yue","zh-Hant","zh-Hans","zh-TW","zh","en"],"subtitlesformat":"vtt"}
    try:
      with yt_dlp.YoutubeDL(o) as y: d=y.extract_info(f"https://www.youtube.com/watch?v={i}")
      out[i]={"ch":h,"title":d["title"],"date":d.get("upload_date"),"views":d.get("view_count"),"likes":d.get("like_count"),"comments":d.get("comment_count"),"dur":d.get("duration"),"chapters":d.get("chapters"),"desc":(d.get("description") or "")[:600]}
      print("ok",i,d.get("upload_date"),flush=True)
    except Exception as e: print("ERR",i,str(e)[:150],flush=True)
json.dump(out,open("deep.json","w"),ensure_ascii=False,indent=1)
