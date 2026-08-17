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
LOG="logs/${WEEK}.log"
ln -sf "${WEEK}.log" logs/latest.log
exec > >(tee "$LOG") 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始跑 $WEEK ==="

notify() {  # $1=标题 $2=正文
  osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null || true
}

# --- 1. 采集 ---
echo; echo "--- 采集 ---"
"$PY" collect.py
ERRS=$(grep -c "vid ERR" "$LOG" 2>/dev/null); ERRS=${ERRS:-0}
echo "抓取失败条数: $ERRS"

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
