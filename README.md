# 粤语财经 YouTube 爆款周报

## 网站(分享这个链接,不用登录直接打开)
**https://timye9527.github.io/finance-hits/**

真·公开网站,GitHub Pages 托管,谁都能直接打开,不需要 GitHub 账号也不需要 claude.ai 账号。
页头期数卡片可以在各期之间跳转(每期是独立页面 `weeks/<周>.html`),缩略图直接从 YouTube 加载。
源码仓库(公开):https://github.com/timye9527/finance-hits

## 每周一 09:05 自动更新(已配置好,不用管)
系统会自动跑采集 → 生成网页 → 推送到网站,跑完弹一条 macOS 通知告诉你结果。

**但拆解要我写。** 脚本只做「数据 + 网页 + 发布」,运营分析(`curation/<周>.json`)还是得找
Claude——这部分是判断,不是流程。所以每周一你会看到两种通知之一:
- 「周报数据已就绪」→ 数据在网上了,但还没有分析文字。跟 Claude 说**「补一下这周的拆解」**
- 「周报更新失败」→ 看 `logs/latest.log`,大概率是 YouTube 限流,跟 Claude 说一声就行

```bash
cat ~/finance-hits/logs/latest.log     # 看上次跑的完整日志
bash ~/finance-hits/weekly.sh          # 想立刻手动跑一次
launchctl list | grep finance-hits     # 第二列是上次退出码,0=成功
```

**最常见的失败:9:05 时电脑还没联网。** 2026-08-24 就栽过一次——任务准时触发,但笔记本刚
唤醒 WiFi 没连上,DNS 全解析失败,抓到 0 条还用空数据盖掉了本地网页。现在有两道防线:开跑前
先探测网络(最多等 10 分钟,每 30 秒重试),以及抓完检查入库条数(少于 10 条直接中止)。
两种情况都会**干净退出、不碰任何文件**,并弹通知告诉你。看到「周报跳过」的通知,联网后手动
跑一次 `bash ~/finance-hits/weekly.sh` 就行。

定时任务定义在 `~/Library/LaunchAgents/com.timye.finance-hits.weekly.plist`。电脑周一 9 点
关机或睡眠的话,launchd 会在下次开机后补跑,不会整周漏掉。要暂停就
`launchctl unload ~/Library/LaunchAgents/com.timye.finance-hits.weekly.plist`。

**手动更新(想自己跑的话):**
```bash
cd ~/finance-hits
python3 collect.py && python3 build.py
git add -A && git commit -m "第 <周数> 周" && git push
```
`git push` 之后 GitHub Pages 会自动重新部署,通常 30–60 秒内生效。`gh`(GitHub CLI)已经
登录过,`git push` 不需要重新授权。

### 备用:claude.ai 分享链接(单文件版,含往期折叠存档)
**https://claude.ai/code/artifact/97b4cba4-9842-4024-84d2-950426edf357**

GitHub Pages 部署前做的第一版,单文件、缩略图内嵌成 base64,往期折叠收在同一页底部。默认私密,
要分享得去页面右上角分享菜单切成「公开」,而且访客可能需要 claude.ai 账号——不如 GitHub Pages
直接。保留是因为「所有历史一页看完」这个形态有它的价值,更新方法见 `build_artifact.py` 顶部注释,
两个版本可以都更新也可以只更新 GitHub Pages 那个。

## 本地入口(自己看,不分享的话用这个)
双击桌面的「📊 粤语财经爆款周报」,浏览器会打开最新一期;页头的期数卡片可切换往期。
桌面那个文件是个跳转页(`~/Desktop/📊 粤语财经爆款周报.html`),指向 `~/finance-hits/index.html` —
换目录的话改它里面的两处路径即可。(macOS 的 .webloc 快捷方式对 file:// 已受限,所以用 HTML 跳转。)

`index.html` 永远是最新一期,直接打开也可以(数据静态嵌入,缩略图从 YouTube 加载需联网)。

## 分层标准
| 层 | 标准 | 用途 |
|---|---|---|
| **爆款** | 播放 ≥3w 且 赞 ≥1k 且 评论 ≥20 | 看**怎么打爆**:标题打法、叙事框架 |
| **差一口气** | 播放 ≥2.8w、赞/千播 ≥10,但差一项 | 看**差在哪**,页面标出精确差距 |
| **中腰部** | 播放 ≥1.5w 且 赞 ≥500 且 评论 ≥10 | 看**大家在做什么题**:可复用选题、日常内容形态 |
| **疑似投流** | 赞/千播 <8(1.5w 档 <6),或评论 ≤5,或较上期播放增幅 <1% | 排除,不作参考 |

投流有两个交叉验证的信号:**赞/千播过低**,以及**播放停滞**(投放一停数字立刻死,自然内容会持续
发酵 7–10 天)。两者页面都会自动标注。

## 周更流程(每周一上午)
```bash
cd ~/finance-hits
python3 collect.py     # 抓上两周数据 → data/<上一ISO周>.json,约 8 分钟
python3 build.py       # 生成 index.html(默认取 data/ 里最新一周)
```

**采集完先看一眼日志末尾的 `[vid ERR]` 数量。** YouTube 有反爬限流,量大时会整片丢频道
(2026-08-10 那次丢了 34 条,英文频道全军覆没)。发现缺失就跑补抓:

```bash
python3 backfill.py    # 单线程 2.5s 间隔,只补该周缺的,可反复跑
```

补抓的条目会打上 `_backfilled` 标记——它们的数字是补抓当天读的、不是那一周的,所以
build 不会拿它们当「发酵增量」的基线(否则会误报成播放停滞)。
然后让 Claude 根据新数据补写 `curation/<周>.json`(TL;DR、逐条拆解、选题地图、
爆款六式、频道观察),再跑一次 `build.py`。没有 curation 文件时页面也能生成,
只是没有运营拆解文字。

## 目录
- `collect.py` — yt-dlp 抓取 26 个频道最新 40 条视频,播放 ≥1.2w 的抓完整互动数据(并发 3 + 自动重试)
- `backfill.py [周]` — 补抓被限流丢掉的条目,单线程慢速,只补该周窗口内的
- `build.py [2026-W29]` — 数据 + 拆解 → `weeks/<周>.html`,最新一周同时写 `index.html`(本地多页版)
- `build_artifact.py` — 读 `weeks/<最新周>.html`,内嵌所有缩略图为 base64、把往期折叠进同一
  文件底部 → `cloud/report.html`(单文件云端版,交给 Artifact 工具发布用)
- `data/` — 每周原始数据存档
- `curation/` — 每周运营拆解(人写)
- `weeks/` — 每期归档页(本地多页版专用,云端版不用这个,靠 build_artifact.py 内嵌历史)
- `thumb_cache/` — 缩略图下载缓存,按文件名去重,不会重复下载同一张图

## 机制说明
- **对照周自动补全**:采集器每频道只留 10 条候选,高产频道(如 Finance730)的旧片会
  掉出窗口。build 时会并入上一期存档补齐对照周,补进来的条目标注「数据截至上期」。
- **发酵增量**:同一条视频若上期已收录,卡片会显示「较上期 +N 播放」。恐慌类选题
  长尾可达 7–10 天,这个数字能看出题材的续航力。
- **散点图标注**:在 curation 的 `chart_labels` 里配 `{视频id: 标注文字}`,每周可换。
- **关键词挖掘**:用 jieba 对双周中文标题分词(已剔除投流内容),产出两张表——「选题关键词」
  按累计播放排序看哪个词真的带量,「标题钩子词」按恐慌/悬念/冲击/利益四类统计实际用法。
  词典在 build.py 顶部:`ENTITY_HINTS`(财经实体,新标的记得加)、`HOOKS`(钩子词表)、
  `SERIES_WORDS`(栏目名,会被过滤掉)、`STOP`(停用词)。
- **历史期次的限制**:W29/W30 是按 2w 门槛采集的,1.5–2w 区间缺失,页面会自己标出来。

## 已知事项
- Chart-reader CUP(@chartreadercup)链接 404,待更新 handle
- 周五至周日发布的视频统计时可能未发酵完,下期复查补录
- 名单频道见 collect.py 里的 CHANNELS(改名单直接编辑它)
- 仓库是公开的:`data/`、`curation/`、源码都在里面。内容是 YouTube 公开数据 + 我们自己写的
  运营分析,不含任何密钥或私人信息,公开无妨;但如果哪期拆解写了不方便公开的内容,发布前提醒 Claude 处理。
