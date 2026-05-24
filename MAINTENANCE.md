# Wren 运维手册（MAINTENANCE）

> 这份是给「下一个 agent / 接手的人 / Leon 自己几个月后」的入口手册。读完一份你就知道项目当前形态、怎么改、怎么部署、怎么排障、怎么回滚。深入细节链到 `docs/` 里的专项文档。

---

## 0. 30 秒速览

**Wren** = 英文人格 Telegram 关系模拟 bot（@Ewan63737bot），单实例部署在 **RAKsmart VPS** (`104.233.146.220:62769`)，Docker compose 跑 3 个容器（`bot` 对话 + `metrics` 监测 + `viewer` 运维 dashboard）。

- **代码进度**：P0–P6 完成 + W0–W8.1 上线硬化与运维平台完成。详见 [CLAUDE.md](CLAUDE.md) 的「Build state」段（**接手时第一步：读这一段确认是否过时**）。
- **分发链接**：`https://t.me/Ewan63737bot?start=<campaign>`（公开，任何 Telegram 用户都能聊；`<campaign>` 落 `data/users/<chat_id>/source.md` 做归因）。
- **dashboard 入口**：本机起 SSH 隧道后 `http://localhost:8002`（详见 §3 dashboard 用法）。

---

## 1. 心智模型（一张图）

```
你的电脑                              VPS (104.233.146.220)              Telegram 用户
─────────                              ──────────────────                ─────────────
/Users/leon/project/HERR        ─►    /srv/wren                  ─►     bot 在跑
(改代码 + 跑测试)              rsync   (docker compose: 3 容器)           接收/回复
                                推到   bot · metrics · viewer
                                                                ◄───────
                                                              (浏览器 + SSH 隧道)
                                                               你看 dashboard
                                                               localhost:8002
```

**三个动作循环**：
1. **改**：本机改代码
2. **测**：本机跑 `WREN_FAKE_MODEL=1 uv run pytest -q && uv run ruff check . && uv run mypy src` —— 三连绿才往下走
3. **推 + 重启**：rsync 改动到 VPS + `docker compose up -d --build <service>`

**没改 = 不推。** 不要定期 rsync，只在真改了之后才推。

---

## 2. 关键路径与文件

### 仓库根（你日常会改的）

| 文件 / 目录 | 干什么用 |
|---|---|
| `src/wren/bot/` | Telegram 入口：`app.py` 启动、`handlers.py` 路由、`scheduler.py` 夜结算/主动消息 |
| `src/wren/core/` | 业务核心：`pipeline.py` think→speak 编排、`step1.py`/`step2.py` 两步 LLM、`settlement.py` 夜结算、`world.py`/`life_sim.py` 世界、`proactive.py` 主动消息、`storage.py` 持久化、`trace.py` JSONL trace、`clock.py` 时钟 |
| `src/wren/prompts/` | **调 voice 改这里**：`system.py` 人设、`step1.py`/`step2.py`/`judge.py` prompts |
| `canon/` | 人设 ground truth（persona / voice spec / 关系 arc 等）— 跟着代码版本化 |
| `world/life_arcs.md` | Wren 的全局生活弧线（世界种子） |
| `src/wren/ops/` | 运维栈：`cli.py` (`wren-metrics`)、`web.py` (`wren-view`)、`health.py` 探针、`ingest.py` DuckDB 灌库、`queries.py` 12 个命名 SQL、`diagnose.py` CLI 单用户旅程 |
| `src/wren/ops/templates/`, `static/` | viewer dashboard 8 页 + `style.css` + `dash.js`（echarts） |
| `tests/` | 240+ 测试，`WREN_FAKE_MODEL=1 uv run pytest -q` 离线跑 |
| `eval/` | bake-off / 多轮 / aliveness 三套 eval（dev only，不进生产容器）|
| `Dockerfile`, `compose.yaml`, `.dockerignore` | 部署制品 |
| `scripts/backup.sh`, `restore.sh` | 备份/恢复脚本（cron 跑 + 灾难恢复用） |
| `.env`（**gitignored**）| secrets：BOT_TOKEN / API_KEY / OWNER_CHAT_IDS / METRICS_SALT / DAILY_CAP |
| `.env.example` | 模板，**改 .env 必看第 2 行那条警告**：值后面**不要写行内注释**（python-dotenv 会吞进值） |

### 文档矩阵

| 文档 | 主题 |
|---|---|
| **本文件 MAINTENANCE.md** | 入口运维手册（你正在看） |
| [CLAUDE.md](CLAUDE.md) | 产品定位 + 架构原则 + Build state（**接手必读**） |
| [README.md](README.md) | 项目一句话介绍 |
| [PRD_product.md](PRD_product.md) | 产品规格（§3 红线必读、§6 backstory、§7 voice spec） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 15 个 ADR-style 决策 + §12 阶段进度 |
| [EVAL_spec.md](EVAL_spec.md) | eval 设计 |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 部署/备份/BotFather/Release Gate（W5 写的运维细节） |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | 监测哲学 + 隐私铁律（chat_id 哈希 / 原文不出机） |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | per-user 数据布局 |
| [docs/adr/0001-mvp-distribution.md](docs/adr/0001-mvp-distribution.md) | 分发 / 监测 / 付费决策记录 |
| [tasks/test_campaign_log.md](tasks/test_campaign_log.md) | 真机 verify 台账（之前手工测过的全部案例） |

### VPS 路径

```
/srv/wren/                  # 代码 + 卷的根
├── data/users/<chat_id>/   # 每用户关系命脉(trace.jsonl / settlement.jsonl / *.md)
├── world/                  # life skeleton
├── data/metrics.duckdb     # 监测库
├── .env                    # secrets(chmod 600)
└── scripts/backup.sh       # 备份脚本(cron 自动调)

/srv/wren-backups/          # 备份归档:.tgz.age 加密(生产 cron `--encrypt`,#36)
                            # 或 .tgz 明文(本机短期,umask 077);保留 14 份;
                            # cron 每日 UTC 08:00。**异地副本只 rsync .tgz.age**
```

---

## 3. dashboard 用法（Wren ops viewer）

8 页运维平台，浅色 admin 风格 + echarts 图表 + 聊天泡泡 + 完整 trace。**只读**（不会改生产数据）。

### 起隧道 + 打开(生产必带 token,#45)
```bash
# 1) 一次性后台起隧道
ssh -fN -L 8002:127.0.0.1:8002 -p 62769 root@104.233.146.220

# 2) 浏览器首次带 ?token,后续点 /users / /u/<chat_id> 自动走 cookie session
open "http://localhost:8002/?token=$WREN_VIEWER_TOKEN"

# 用完关
pkill -f "ssh -fN -L 8002"
```
(curl 用 `Authorization: Bearer $WREN_VIEWER_TOKEN`;生产无 token 时 viewer 启动会 503 fail closed。)

### 8 页都看什么

| 路由 | 你想看时去这里 |
|---|---|
| `/` 总览 | 4 大 KPI（总用户/今日活跃/Lv≥2 占比/今日 cost）+ 6 mini + 容器/出网/资源 + 6 业务 echarts |
| `/users` | 全部用户表格 + 搜索 + 5 个筛选 chip（冻结/沉默/Lv≥2/今日活跃）+ 排序 |
| `/u/<chat_id>` | **★ 单用户完整 trace** — 左 banner（lv/prose/source/core/events）+ 右聊天泡泡时间线（user 灰 / wren 蓝），点 wren 气泡展开看 **inner_voice + impression**；🌙 夜结算月亮卡点开看 **完整 prose 重写** |
| `/levels` | 等级分布环形 + 14d 跃迁堆叠柱状 + 中位 Lv2/Lv3 时间 + 卡级用户 + 用户等级排行 |
| `/sources` | acquisition 横向柱 + 激活率柱 + D1/D7 cohort 表 |
| `/cost` | 今日 cost + DAILY_CAP 进度 + 30d turn/tokens 双轴柱状 |
| `/nightly` | 14d 夜结算健康 + 最近 50 次 settlement 列表（点开看 prose） |
| `/errors` | 近 1h / 24h `docker logs bot` grep error/exception/conflict |
| `/system` | 3 容器状态 + 资源 + 备份时间 + env 状态表 |

### 隐私铁律（重要）

- 端口 **只 listen `127.0.0.1`**（`ss -tlnp` 验证），公网 curl IP:8002 永远 timeout
- Flask `before_request` 中间件硬限 `remote_addr ∈ {127.0.0.1, ::1}`，非本机 → 403
- 命令行传 `--host 0.0.0.0` 会被强制改回 `127.0.0.1`
- **原文（inner_voice/raw_out/prose）只在本机渲染，不进 metrics.duckdb，不出机**

详见 [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md)。

---

## 4. 日常 4 个场景的实操步骤

### 场景 A · 调 voice / 改 prompts（**最高频**）

```bash
cd /Users/leon/project/HERR

# 1. 改 prompts(IDE / vi 都行)
vi prompts/step1.py    # 比如让 Wren Lv0 更刺

# 2. 离线门测试
WREN_FAKE_MODEL=1 uv run pytest -q                   # 必须 240+ passed
uv run ruff check . && uv run mypy src               # 必须全绿

# 3. 看自己改了啥
git diff prompts/step1.py

# 4. commit(留个记号)
git add prompts/step1.py
git commit -m "tune(voice): Lv0 更刺一点 — 引用 mom's texts"

# 5. rsync 推 VPS + 重启 bot
./scripts/deploy.sh bot      # 见 §5 一键脚本

# 6. 真机试一句(用你的 Telegram 找 @Ewan63737bot)
# 7. 不满意 → 回到步骤 1 / 改坏了 → §6 回滚
```

### 场景 B · 改 dashboard / 加图表

```bash
# 改 src/wren/ops/templates/*.html 或 static/*.css 或 static/dash.js 或 web.py
WREN_FAKE_MODEL=1 uv run pytest -q
./scripts/deploy.sh viewer
# 浏览器刷新 http://localhost:8002 看效果
```

### 场景 C · 改环境变量

`.env` **不在 git 里**（gitignored），所以**不能 rsync**。直接在 VPS 上改：

```bash
ssh -p 62769 root@104.233.146.220 'vi /srv/wren/.env'
# 改完重启对应服务(env_file 在容器启动时读)
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose restart bot'
```

**永远不要 commit `.env`！** 如果 secret 误进了 git，立即 `git reset` + 去 BotFather `/revoke` 重发 token。

### 场景 D · 加新功能（多文件）

```bash
cd /Users/leon/project/HERR
git checkout -b feat/W9-xxx    # 开特性分支
# ... 改一堆文件
WREN_FAKE_MODEL=1 uv run pytest -q && uv run ruff check . && uv run mypy src
git add -A
git commit -m "feat(W9): 新功能描述"

# 回主分支合并
git checkout main
git merge feat/W9-xxx          # 快进合并
git push origin main
./scripts/deploy.sh all        # 全部重启(bot/metrics/viewer 都重 build)
```

---

## 5. 一键部署脚本

仓库根 `scripts/deploy.sh`（如已存在直接用，否则按场景 A/B/D 手敲；推荐第一次进项目就把它创出来）：

```bash
#!/usr/bin/env bash
# 用法: ./scripts/deploy.sh [service]   service 默认 bot,可选 viewer / metrics / all
set -e
SERVICE="${1:-bot}"

cd /Users/leon/project/HERR
echo "== 1) 本机离线门 =="
WREN_FAKE_MODEL=1 uv run pytest -q
uv run ruff check . > /dev/null
uv run mypy src > /dev/null

echo "== 2) rsync → VPS =="
rsync -az --exclude data/ --exclude world/today.md --exclude world/yesterday.md \
  --exclude '*.duckdb*' --exclude '__pycache__/' --exclude '.venv/' \
  --exclude '.env.bak.*' --exclude '*.vps' --exclude '.claude/' \
  -e "ssh -p 62769" \
  /Users/leon/project/HERR/ root@104.233.146.220:/srv/wren/

echo "== 3) rebuild + restart =="
if [ "$SERVICE" = "all" ]; then
  ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose up -d --build'
else
  ssh -p 62769 root@104.233.146.220 "cd /srv/wren && docker compose up -d --build $SERVICE"
fi

echo "== 4) tail logs =="
sleep 4
ssh -p 62769 root@104.233.146.220 "cd /srv/wren && docker compose logs --tail=20 $SERVICE"
```

---

## 6. 紧急情况 & 回滚

### 🔥 改坏了

| 状态 | 怎么救 |
|---|---|
| **没 `git add`** | `git checkout -- <文件>` 丢弃改动 |
| **已 commit 没推 VPS** | `git reset --hard HEAD~1` 回退；之后正常 deploy |
| **已推 VPS / bot 在线挂了** | 见下方"VPS 端回滚" |

### VPS 端回滚到任一历史 commit
```bash
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && git log --oneline | head -10'
# 选一个稳定的 hash
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && git checkout <hash>'
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose up -d --build'
# ./data/ 是挂卷,回滚版本不丢用户关系数据
```

### 🔥 看实时日志
```bash
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose logs -f bot'
# 或者打开 dashboard `/errors` 自动 grep 24h
```

### 🔥 数据恢复（最坏情况，data/ 误删）
```bash
# 1) 列归档(优先找 .tgz.age 加密产物;若环境还在过渡,可能也有 .tgz 明文)
ssh -p 62769 root@104.233.146.220 'ls -lh /srv/wren-backups/'

# 2) 加密归档(.tgz.age):先 openssl 解密到 tmp(passphrase 走 env 不留命令行)
ssh -p 62769 root@104.233.146.220 \
  'WREN_BACKUP_PASSPHRASE=<pass> openssl enc -d -aes-256-cbc -pbkdf2 \
     -pass env:WREN_BACKUP_PASSPHRASE \
     -in /srv/wren-backups/wren-<TS>.tgz.age -out /tmp/wren-<TS>.tgz'

# 3) **必须先停服**(否则 live 写入与恢复交错 → 半新半旧,#27)
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose stop bot metrics viewer'

# 4) 真要恢复 live(/srv/wren):
ssh -p 62769 root@104.233.146.220 \
  'bash /srv/wren/scripts/restore.sh /tmp/wren-<TS>.tgz --live && rm /tmp/wren-<TS>.tgz'
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose up -d --build && docker compose logs --tail=20 bot'
# --live 自动备份当前 data/+world/ 到 /srv/wren/.pre-restore-<ts>/(失败时手动 mv 回滚)
```

### 🔥 token 冲突 `Conflict: terminated by other getUpdates`
说明别的进程在用同 token long-poll：要么 kill 那个进程，要么 BotFather `/revoke` 重发 + 更新 `.env`。

### 🔥 dashboard 打不开 `localhost:8002 拒绝连接`（**最高频**）
**99% 是 SSH 隧道断了**（开机重启 / 锁屏久了 / 你之前手动 `pkill` 过）。1 分钟内修：

```bash
# 1. 确认 VPS 端 viewer 还在跑
ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose ps viewer'
# 应看到 Up X hours

# 2. 重新起本机 SSH 隧道(后台 -fN,跑一次即可)
ssh -fN -L 8002:127.0.0.1:8002 -p 62769 root@104.233.146.220

# 3. 验证(生产带 WREN_VIEWER_TOKEN 必须用 Authorization Header 或 ?token;#45)
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $WREN_VIEWER_TOKEN" http://localhost:8002/   # 应 200
# 无 token 时应 401;WREN_VIEWER_TOKEN 未设 + 未开 bypass 时应 503(fail closed)
open "http://localhost:8002/?token=$WREN_VIEWER_TOKEN"

# 4. 看进程
ps aux | grep 'ssh -fN -L 8002' | grep -v grep
```

**判断是哪边断**：
- `curl localhost:8002` 失败 = **本机隧道断**（重起就行，按上面 4 步）
- VPS 上 `docker compose ps viewer` 显示 exited / restarting = **viewer 容器挂了**（`docker compose up -d viewer`）
- VPS 上 `ss -tlnp | grep 8002` 没结果 = **viewer 进程没 listen**（看 logs：`docker compose logs viewer`）

### 🔥 公网到 telegram.org / api.deepseek.com 不通
RAKsmart 节点（美西硅谷）平时都通。如果某天显示 down：
- dashboard `/` 首页「出网」卡看 3 个 endpoint 状态
- SSH 到 VPS 跑 `curl -m 8 https://api.telegram.org/` 验证
- 大概率是临时网络抖动，再观察 5 分钟

---

## 7. 测试 / 离线门

**任何 commit 前都跑这三连**：

```bash
# 1. 全套 pytest(fake 模式,无需 API key)
WREN_FAKE_MODEL=1 uv run pytest -q
# 期望: 240+ passed in ~6s

# 2. lint
uv run ruff check .

# 3. 类型检查
uv run mypy src
```

**特殊跑法**：

```bash
# 跑某个文件
WREN_FAKE_MODEL=1 uv run pytest tests/test_isolation.py -q

# 跑某个关键字测试
WREN_FAKE_MODEL=1 uv run pytest -k landmine -q

# eval(需要真 WREN_API_KEY)
uv run wren-harness --quick           # 单轮 voice eval
uv run wren-multiturn --quick         # 多轮关系弧线 eval
uv run wren-aliveness                 # AI-tell 检测(Opus 4.7 judge)
```

---

## 8. Git workflow（单人 / 小团队推荐）

### 分支模型

- **`main`** = 已部署 VPS 的稳定版（不直接在 main 改东西）
- **`feat/<name>`** = 新功能特性分支（开 → 改 → 测 → 合回 main → 删）
- **`fix/<name>`** = bug 修复分支
- **`tune/<name>`** = voice / prompt 调教（其实就是 fix 的子类，习惯分开记录）

### 标准流程

```bash
git checkout main && git pull origin main
git checkout -b fix/lv3-money-too-soft
# ... 改代码 + 测试
git add -A && git commit -m "fix(voice): Lv3 钱雷不能太软,引 mom's texts 内化"
git checkout main
git merge fix/lv3-money-too-soft
git push origin main
git branch -d fix/lv3-money-too-soft     # 删特性分支
./scripts/deploy.sh bot
```

### Commit message 约定

`<type>(<scope>): <summary>`，**写「为什么」不写「改了什么」**（diff 自己会说）：

| type | 用法 | 例子 |
|---|---|---|
| `feat` | 新功能 | `feat(W9): 加 Lv4 vulnerability gate` |
| `fix` | 修 bug | `fix(bot): debounce 窗口偶发漏消息` |
| `tune` | voice / prompt 调教 | `tune(voice): Lv3 钱雷更尖,引 mom's texts` |
| `docs` | 文档 | `docs: 校准 MAINTENANCE.md backup 频率` |
| `chore` | 杂活 | `chore: 升级 flask 3.0→3.1` |
| `refactor` | 重构（外部行为不变） | `refactor(core): 拆 storage.py 成 module` |

### 永远不做的事

- `git push --force` 到 main（会覆盖别人/旧版本，灾难）
- 把 `.env` / token / API key commit 进 git（一旦进了即使 `git reset` 还在 reflog 里，要 revoke + 重发）
- 在 VPS 上直接改代码不同步回本机（下次 rsync 会被本机覆盖）

---

## 9. 环境变量速查

详见 [.env.example](.env.example)。**公开发布必填**：

| 变量 | 必要性 | 说明 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **必填** | BotFather 给的 token，缺这个 bot 起不来 |
| `WREN_API_KEY` | 必填（否则 fake 模式） | LLM API key（默认 DeepSeek） |
| `WREN_BASE_URL` | 可选 | LLM endpoint，默认 `https://api.deepseek.com` |
| `WREN_MODEL` | 可选 | 默认 `deepseek-v4-flash` |
| `WREN_OWNER_CHAT_IDS` | **公开发布必填** | owner Telegram chat_id（逗号分隔），保护 `/setlevel` `/tick` 调试命令，空=没人能用 |
| `WREN_METRICS_SALT` | **公开发布必填** | chat_id 哈希盐（随机串），空=用源码默认盐可被反推 |
| `WREN_DAILY_TURN_CAP` | 建议设 | 全局每日 turn 上限（成本天花板），0=不限 |
| `WREN_DAILY_CAP_HARD` | 可选 | =1 时硬停，否则只告警 |
| `WREN_RATE_LIMIT_PER_MIN` | 可选 | 每用户每分钟消息上限，默认 20 |
| `WREN_SETTLEMENT_MODEL` | 可选 | 夜结算模型，默认 `deepseek-v4-pro`；可升 Opus（改这行 + `_BASE_URL` + `_API_KEY`） |
| `WREN_DATA_ROOT` | 可选 | 用户数据根，默认 `./data/users` |
| `WREN_DEBOUNCE_S` | 可选 | 消息合并窗口（秒），默认 4 |
| `WREN_FAKE_MODEL` | dev / CI 用 | `=1` 强制 fake 模式 |

**⚠️ 警告**：`.env` 每行 `KEY=VALUE` 后**不要加行内注释**（`python-dotenv` 会吞进值，曾导致数据写到怪目录）。注释另起一行 `#` 开头。

---

## 10. VPS / 服务参数

| 项 | 值 |
|---|---|
| VPS 厂商 | RAKsmart |
| IP | `104.233.146.220` |
| SSH 端口 | `62769`（非默认 22） |
| SSH 用户 | `root` |
| OS | Ubuntu 22.04 LTS |
| Docker | 29.0.2（预装） + Compose v2.40.3 |
| 区域 | SV 硅谷美西（出网到 Telegram/DeepSeek/GitHub 全通） |
| CPU / RAM / 磁盘 | 2 核 / 2 GB / 50 GB |
| 价格 | $2.99/月 |
| 时区 | UTC（bot 内部 ET TZ-aware） |
| **viewer 端口** | `127.0.0.1:8002`（绝不公网） |
| **bot 进程模式** | long-poll（不是 webhook，不需要 HTTPS 域名） |
| **单实例** | 不可水平扩容（long-poll + 内存锁 + 进程内 JobQueue） |
| 备份 cron | 每日 UTC 08:00（夜结算 ET 02:30 之后 ~30 分钟） |
| 备份保留 | 14 天 |

### Bot 信息

| | |
|---|---|
| Username | `@Ewan63737bot` |
| 分发链接 | `https://t.me/Ewan63737bot?start=<campaign>` |
| Owner chat_id（调试命令白名单） | `7952767637` |

---

## 11. 进度状态（接手时第一眼看这里 — 可能过时）

> **接手时必做：跑 `git log --oneline | head -20` 看最近 commits 验证下方是否过时；过时则更新这一段。**

- **2026-05-22 部署**：W0–W7 上线硬化全部完成，VPS 部署上线，Release Gate D1-D4 全过，真机冒烟通过。详见 [W8_verify.md（VPS 上）](#) 或 `git log --grep="^W"` 找历史。
- **2026-05-23 W8 + W8.1**：viewer 运维平台完整实现 — 8 个页面（总览/用户/单用户/等级/来源/成本/夜结算/错误/系统）+ 浅色 admin dashboard + echarts + 聊天泡泡（user 灰 / wren 蓝，点开看 `inner_voice_after`）+ 🌙 settlement 月亮卡 + 隐私铁律守住。Chrome MCP 自主验收 V1-V6 全过。详见 VPS `/srv/wren/W8.1_verify.md`。
- **当前已知 follow-up（W8.2）**：
  1. viewer 容器 `network_mode: host` + `uv run` 时 env_file 没继承 → 系统页 env 表显示部分必填项为"空"（实际 .env 都填了，只是 viewer 进程读不到）。修法：viewer command 改 `bash -c "set -a && . .env && uv run wren-view"`。
  2. 单用户页 banner lv badge 显示 `Lv?`（jinja set 作用域 bug，列表页解析正确，仅这一页用 macro 或后端预解析）。
  3. echart 空数据占位（细虚线更优雅）。
- **未做**：P7 Lv4 深度脆弱专门的崩溃/恢复引擎（level-gate 已开、对错分支已通，没有专门状态机）。

---

## 12. 常见调试场景速查

| 现象 | 第一步排查 |
|---|---|
| **Bot 不回消息** | `docker compose logs --tail=50 bot` 找 conflict/error；或 dashboard `/errors` 页 |
| **突然全沉默 / 所有人不回** | dashboard `/cost` 看 `DAILY_TURN_CAP` 是否命中；或 `.env` 里 `WREN_DAILY_CAP_HARD=1` 是否误设 |
| **任何人 `/setlevel` 都能用** | `grep OWNER /srv/wren/.env` 确认 `WREN_OWNER_CHAT_IDS` 设了 |
| **特定用户卡 Lv0 / 沉默率高** | dashboard `/users` 筛选 → 点进 `/u/<id>` 看每轮 `inner_voice_after` 判断 voice 是否塌；如塌改 `prompts/step1.py` |
| **磁盘满** | `df -h /srv` + `du -sh /srv/wren/data /srv/wren-backups`；`trace.jsonl` 涨的话考虑 archive 旧月 |
| **token 冲突** | logs 看 `Conflict: terminated by other getUpdates` → 别的机器还在跑同 token → BotFather `/revoke` 重发 |
| **网络抖动** | `httpx.ConnectError` 偶发出现是 cold start glitch（首次 init）；持续出现要查 VPS 出网 |
| **夜结算没动 prose** | `/nightly` 看最近一条 settlement 的 `raw_out` 是否真重写；如没动看 `settle_tokens` 是否被截断（`WREN_SETTLEMENT_MAX_TOKENS` 默认 8000） |
| **主动消息从不发** | 正常 — Lv0-1 不主动（PRD 设计），需要挨到 Lv2+；或者 25 分钟内有对话（新近度护栏） |

---

## 13. 给下一个 agent 的几条心法

1. **§0 红线**（CLAUDE.md 顶部 + ARCHITECTURE.md §0）永远先读 — 反硬编码（`prompts/` 里不写"该说 X"）、emergence > modules、轻量+留 seam。**违反 §0 的方案直接退回**。
2. **改 prompt 是高频，改代码是中频，改 compose/Dockerfile 是低频**。前两者随便上、后者改完先 `docker compose build` 本机一遍再推。
3. **`./data/users/<chat_id>/`** 是每个用户的关系命脉。不要 `rm -rf` 它，不要让 rsync 加 `--delete`（我给的 rsync 命令默认不带）。
4. **隐私铁律**：原文（inner_voice/raw_out/prose）**只在本机 viewer 渲染**，绝不进 `metrics.duckdb`，绝不公网暴露。任何"把 trace 推到云"的设计先 stop。
5. **小步快跑**：一次改一件事 + 一次 commit + 一次 deploy。别囤一堆改动一起推（出问题难定位）。
6. **`tune(voice):` 高频出现是正常的** — voice 调教是这个产品的核心动作（PRD §7 + CLAUDE.md 多次强调"在真实 bot + 真 trace 上调，不在抽象层猜"）。每次调 prompt 都该是一次 commit。
7. **遇到不懂的代码先看 [CLAUDE.md](CLAUDE.md) 「How the design maps to code」段** — 它把每个目录是什么意思讲了一遍。
8. **接手时确认 `Build state` 段是否还准** — `git log --oneline | head -20` + 对照 `tasks/todo.md` + `ARCHITECTURE.md §12`。如果发现这文档过时了，**就地更新**（这文档跟着代码一起演进）。

---

## 14. 联系信息 / 资源

- GitHub 仓库：`https://github.com/Leonxu6/Her-to-foreign`
- Owner：Leon (`nutleysilman@mail.com`)
- BotFather：`@BotFather` (Telegram，重置 token 用)

---

**最后一句**：这文档跟着仓库版本化。**如果你发现这里写的跟实际不一样，先信代码 + git log，然后更新这里**。文档腐烂比代码腐烂更隐蔽，但更致命。
