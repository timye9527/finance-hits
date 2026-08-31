#!/bin/bash
# 每周一自动跑:采集 → 补抓(如需) → 生成网页 → 推送到 GitHub Pages
# 由 ~/Library/LaunchAgents/com.timye.finance-hits.weekly.plist 在每周一 09:05 触发。
#
# 手动跑一次:  bash ~/finance-hits/weekly.sh
# 看上次日志:  cat ~/finance-hits/logs/latest.log
#
# 注意:这个脚本只负责「数据 + 网页 + 发布」,不写运营拆解。拆解(curation/<周>.json)
# 需要 Claude 来写——跑完会弹通知提醒。没有 curation 文件时网页照样生成,只是没有分析文字。

set -uo pipefail
cd "$(dirname "$0")" || exit 1

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# 必须写死这个解释器:yt_dlp 和 jieba 只装在 anaconda 这个 Python 里,
# 而 launchd 的 PATH 跟登录 shell 不一样,靠 `python3` 会解析到没装依赖的那个。
PY=/opt/anaconda3/bin/python3
if ! "$PY" -c "import yt_dlp, jieba" 2>/dev/null; then
  osascript -e 'display notification "缺 yt_dlp 或 jieba,跟 Claude 说一声" with title "周报跑不了"' 2>/dev/null
  echo "!!! $PY 缺依赖,中止"; exit 1
fi

mkdir -p logs
WEEK=$("$PY" -c "import datetime;i=(datetime.date.today()-datetime.timedelta(days=7)).isocalendar();print(f'{i[0]}-W{i[1]:02d}')")

# --- 幂等闸门 ---
# 这个脚本被三种事件触发(周一定时 / 开机登录 / 网络变化),一周内会被叫很多次。
# 用一个「本周已完成」的戳来保证只真跑一次;戳不匹配才继续,所以电脑周一没开、
# 周三才开机也能自动补跑。WEEK 在每周一零点自然翻页,戳随之失效。
STAMP="logs/.last_done"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$WEEK" ]; then
  exit 0                                    # 本周已完成,静默退出(不写日志、不弹通知)
fi

# --- 防并发 ---
# 采集要跑 8 分钟,期间网络一抖就可能再次触发。mkdir 是原子操作,抢不到就退出。
LOCK="logs/.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0                                    # 已有一个实例在跑
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

LOG="logs/${WEEK}.log"
ln -sf "${WEEK}.log" logs/latest.log
exec > >(tee "$LOG") 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始跑 $WEEK (触发源: ${TRIGGER:-手动}) ==="

notify() {  # $1=标题 $2=正文
  osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null || true
}

# --- 0. 等网络 ---
# 2026-08-24 09:05 就栽在这:笔记本刚唤醒、WiFi 还没连上,DNS 全解析不了,
# 结果抓到 0 条、拿空数据盖掉了好页面。开跑前必须先确认真能出网。
echo; echo "--- 等网络 ---"
NET_OK=0
for i in $(seq 1 20); do            # 最多等 10 分钟
  if curl -sI https://www.youtube.com --max-time 8 -o /dev/null; then
    echo "第 $i 次尝试:网络就绪"; NET_OK=1; break
  fi
  echo "第 $i 次尝试:还没网,30 秒后重试"
  sleep 30
done
if [ "$NET_OK" -ne 1 ]; then
  notify "周报跳过" "等了 10 分钟还没网,本周没跑。联网后手动跑 weekly.sh"
  echo "!!! 10 分钟内没等到网络,中止(没有改动任何文件)"; exit 1
fi

# --- 1. 采集 ---
echo; echo "--- 采集 ---"
"$PY" collect.py
ERRS=$(grep -c "vid ERR" "$LOG" 2>/dev/null); ERRS=${ERRS:-0}
echo "抓取失败条数: $ERRS"

# --- 1b. 数据健全性检查 ---
# 光看 collect.py 的退出码不够:它抓到 0 条也会「成功」退出并存一个空文件。
# 空数据喂给 build.py 会生成一个空报告、盖掉现有的好页面——必须在 build 之前拦住。
GOT=$("$PY" -c "import json;print(len(json.load(open('data/$WEEK.json'))['videos']))" 2>/dev/null || echo 0)
echo "入库视频数: $GOT"
if [ "$GOT" -lt 10 ]; then
  notify "周报数据异常" "只抓到 $GOT 条,已中止未覆盖网页。看 logs/latest.log"
  echo "!!! 只抓到 $GOT 条(正常 30+),中止以免空数据盖掉好页面"; exit 1
fi

# --- 2. 失败多就补抓(YouTube 反爬会整片丢频道) ---
if [ "$ERRS" -gt 5 ]; then
  echo; echo "--- 失败 $ERRS 条,启动补抓 ---"
  "$PY" backfill.py "$WEEK"
fi

# --- 3. 生成网页 ---
echo; echo "--- 生成网页 ---"
if ! "$PY" build.py; then
  notify "周报更新失败" "build.py 出错,看 logs/latest.log"
  echo "!!! build 失败,中止"; exit 1
fi

# --- 4. 推送(GitHub Pages 会自动重新部署) ---
echo; echo "--- 推送 ---"
git add -A
if git diff --cached --quiet; then
  echo "没有变化,跳过推送"
else
  git commit -q -m "$WEEK 数据更新(自动)"
  if git push -q; then
    echo "已推送,GitHub Pages 约 30-60 秒后生效"
  else
    notify "周报推送失败" "git push 出错,看 logs/latest.log"
    echo "!!! push 失败"; exit 1
  fi
fi

# 走到这里说明数据、网页、推送都成功了,盖戳。之后本周再被触发都会静默跳过。
echo "$WEEK" > "$STAMP"

# --- 5. 提醒补拆解 ---
HITS=$("$PY" - <<PY 2>/dev/null || echo "?"
import json,datetime
w="$WEEK"; y,n=w.split("-W")
mon=datetime.date.fromisocalendar(int(y),int(n),1).strftime("%Y%m%d")
d=json.load(open(f"data/{w}.json"))
def lpk(v): return (v.get("like_count") or 0)/max(v.get("view_count") or 1,1)*1000
print(sum(1 for v in d["videos"] if v["upload_date"]>=mon and v.get("lang") in ("粤语","普通话")
      and (v.get("view_count") or 0)>=30000 and (v.get("like_count") or 0)>=1000 and (v.get("comment_count") or 0)>=20))
PY
)

if [ -f "curation/${WEEK}.json" ]; then
  notify "周报已更新 ✓" "$WEEK · $HITS 条爆款 · 已发布到网站"
else
  notify "周报数据已就绪" "$WEEK · $HITS 条爆款 · 找 Claude 说「补一下 $WEEK 的拆解」"
fi

echo; echo "=== $(date '+%H:%M:%S') 完成 · 爆款 $HITS 条 · 失败 $ERRS 条 ==="
echo "网站: https://timye9527.github.io/finance-hits/"
