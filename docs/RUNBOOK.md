# Wren 运维手册(RUNBOOK)

生产级单实例部署 + 备份/恢复 + 监测 + 放行清单。配套:[DATA_MODEL](DATA_MODEL.md)、
[OBSERVABILITY](OBSERVABILITY.md)、[ADR](adr/0001-mvp-distribution.md)。

## 1. 部署(便宜 VPS + Docker)
```bash
git clone <repo> /srv/wren && cd /srv/wren
cp .env.example .env && vi .env     # 填 TELEGRAM_BOT_TOKEN、WREN_API_KEY、WREN_OWNER_CHAT_IDS、WREN_METRICS_SALT…
docker compose up -d --build        # 起 bot + metrics 两个服务
docker compose logs -f bot          # 应看到:✓ 夜结算已挂 / ✓ 主动消息调度已挂
```
镜像内置 `python-telegram-bot[job-queue]` → 夜结算(2:30 ET)与主动调度(~10min)自动挂上。
`data/` + `world/` 挂卷持久化。时区无需配:夜结算硬编码 `America/New_York` 且 TZ-aware。

## 2. ⚠️ 单实例(不可水平扩容)
long-poll + 内存锁(per-chat)+ 内存 debounce + 进程内 JobQueue → **只能跑一个 bot 实例**。
**勿** `docker compose up --scale bot=2`(双实例会争抢 getUpdates + 竞写同一用户目录)。50–200 用户单台足够。

## 3. 备份 + 恢复(命脉 · D3.4)
丢 `data/` = 丢掉所有人挣来的关系。**备份是头号安全网。异地副本必须加密**(#36):
data/users 含原始聊天 / inner voice / chat_id 目录名,明文 .tgz 离机违反"内容不出机器"。
```bash
# 每晚备份(cron;passphrase 走 env 不进 process args,防 ps 偷):
30 3 * * *  WREN_BACKUP_PASSPHRASE=<random-pass> WREN_APP_DIR=/srv/wren \
            WREN_BACKUP_DIR=/srv/wren-backups /srv/wren/scripts/backup.sh --encrypt
# (产物 wren-<TS>.tgz.age,openssl AES-256-CBC + PBKDF2;passphrase 写 cron 的 env 文件)

# 异地副本:**只 rsync .tgz.age 后缀**,绝不 cp 明文 .tgz
30 4 * * *  rsync -avz --include='wren-*.tgz.age' --exclude='*' \
            /srv/wren-backups/ <offsite>:/path/

# 恢复演练(加密 .tgz.age):openssl 解密 → staging restore(不碰 live)
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:WREN_BACKUP_PASSPHRASE \
  -in /srv/wren-backups/wren-<TS>.tgz.age -out /tmp/wren-<TS>.tgz
scripts/restore.sh /tmp/wren-<TS>.tgz --staging /tmp/restore-check && rm /tmp/wren-<TS>.tgz
diff -r /srv/wren/data /tmp/restore-check/data && echo OK
# 真灾备恢复 live(**必须先停服**;详见 MAINTENANCE.md §6 "数据恢复"):
#   docker compose stop bot metrics viewer
#   openssl enc -d -aes-256-cbc -pbkdf2 -pass env:WREN_BACKUP_PASSPHRASE \
#     -in /srv/wren-backups/wren-<TS>.tgz.age -out /tmp/wren-<TS>.tgz
#   scripts/restore.sh /tmp/wren-<TS>.tgz --live && rm /tmp/wren-<TS>.tgz
#   docker compose up -d --build
```

## 4. BotFather
- `/setname` Wren · `/setdescription`(如 "brooklyn. paints. not really looking to talk.")· `/setabouttext`。
- 命令菜单**无需手设**:bot 启动经 `post_init` 自动只暴露 `/start /help /delete`(`/setlevel`/`/tick`
  是 owner-only 调试命令,不进菜单、非 owner 静默)。
- 宣传链接:`t.me/<bot>?start=<campaign>`(`<campaign>` 落 source.md → 监测按来源归因)。

## 5. 监测 + 诊断闭环
`metrics` 服务每 ~15min `wren-metrics ingest` 灌 `data/metrics.duckdb`(只指标维度、chat_id 哈希、内容不出机器)。
```bash
docker compose exec bot uv run wren-metrics query per_user_overview   # 看板:问题用户置顶
docker compose exec bot uv run wren-metrics diagnose --chat-id <id>   # 深挖某用户完整旅程
# Datasette 看板 UI(只读、绑 localhost、SSH 隧道,绝不公网):
uv tool install datasette && datasette serve data/metrics.duckdb --host 127.0.0.1 --port 8001
#   本机:ssh -L 8001:127.0.0.1:8001 <vps> → 开 http://localhost:8001
```

### 5.1 W8 运维平台 `wren-view`(推荐主入口)
viewer 容器(`network_mode: host`, bind `127.0.0.1:8002`)合并了健康总览 + 用户列表 + 单用户时间线(每轮内心独白 + 夜结算重写):
```bash
# 0)【生产必设】.env 加 viewer 认证 token(#45):
#    WREN_VIEWER_TOKEN=$(openssl rand -hex 32)
#    本机/CI 演示不需要 token:WREN_ALLOW_VIEWER_NO_AUTH=1

# 1) 本机起 SSH 隧道一次性映射 viewer:
ssh -fN -L 8002:127.0.0.1:8002 -p <SSH_PORT> root@<VPS_IP>

# 2) 浏览器首次访问带 ?token=(后续导航自动 cookie session,无需再带):
open "http://localhost:8002/?token=<WREN_VIEWER_TOKEN>"

# 3) curl 走 Authorization: Bearer:
curl -H "Authorization: Bearer <WREN_VIEWER_TOKEN>" http://localhost:8002/api/users

# 用完关掉隧道(可选):
pkill -f "ssh -fN -L 8002"
```
**隐私铁律守住(双层防御 #45)**: viewer `before_request` (a) 硬限 `request.remote_addr ∈ {127.0.0.1, ::1}` (b) 校验 `WREN_VIEWER_TOKEN`(`Authorization: Bearer` / `?token=` / cookie 任一);缺 token + 未开 `WREN_ALLOW_VIEWER_NO_AUTH=1` → 503 fail closed。原文仅在本机渲染,不进库不出机。
闭环详见 [OBSERVABILITY](OBSERVABILITY.md):看板发现 → diagnose / viewer 看每轮内心 → 改 step1/persona → 重跑 aliveness+multiturn → 信号回落。

## 6. 环境变量速查
| 变量 | 用途 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 必填,bot token |
| `WREN_API_KEY` / `WREN_BASE_URL` / `WREN_MODEL` | 主模型(Step1/2,默认 deepseek-v4-flash) |
| `WREN_SETTLEMENT_MODEL`/`_API_KEY`/`_BASE_URL` | 夜结算模型(默认 v4-pro;升 Opus 改这行) |
| `WREN_OWNER_CHAT_IDS` | 调试命令 owner 白名单(逗号分隔;**公开发布必设**,空=锁死) |
| `WREN_RATE_LIMIT_PER_MIN` | 每用户每分钟消息上限(默认 20;0=不限) |
| `WREN_DAILY_TURN_CAP` / `WREN_DAILY_CAP_HARD` | 全局每日 LLM complete() 调用天花板(默认 0=不限;**公开发布建议设**) |
| `WREN_METRICS_SALT` | chat_id 哈希盐(**勿提交**) · `WREN_METRICS_DB` 库路径覆盖 |
| `WREN_DEBOUNCE_S` / `WREN_EVENTS_CAP` / `WREN_DATA_ROOT` / `WREN_WORLD_ROOT` | 行为/路径调参 |

## 7. Release Gate(公开链接放行前必须全绿)
- [ ] **D1** 隔离/完整性:`pytest tests/test_isolation.py` 绿;原子写 + 跨用户零污染 + /delete 全清
- [ ] **D2** 可观测/闭环:`wren-metrics ingest`+`diagnose` 跑通;看板 per_user_overview 可看(D2 实跑)
- [ ] **D3** 部署/可靠性:`docker compose up` 起;杀容器重启数据无损;**恢复演练通过**;日志见两个定时任务挂上
- [ ] **D4** 可维护/付费:离线门绿(`WREN_FAKE_MODEL=1 pytest -q` + ruff + mypy);runbook+ADR 在;tier seam 在
- [ ] **真机冒烟**:owner 聊几轮看 trace;`/tick force` 验主动消息;`wren-nightly --chat-id <自己>` 验等级真动;非 owner 验 `/setlevel` 被挡
- [ ] **WREN_OWNER_CHAT_IDS / WREN_METRICS_SALT / WREN_DAILY_TURN_CAP 已在 .env 设妥**
- [ ] 全绿 → 才把 `t.me/<bot>?start=<campaign>` 拿去宣传

## 8. 故障排查
- 没有夜结算/主动消息日志 → 确认镜像装了 `[job-queue]`(本 Dockerfile 已含)。
- Wren 不主动找人 → 正常:Lv0-1 不主动,要挨到 Lv2+(夜结算慢推);或用户最近 25min 有对话(新近度护栏让路)。
- 花费异常 → 看 `cost_daily`;设/调 `WREN_DAILY_TURN_CAP`(+`WREN_DAILY_CAP_HARD=1` 硬停;按 LLM complete() 次数执行)。
- 任何人能跳级 → 检查 `WREN_OWNER_CHAT_IDS` 是否设妥(空=没人能用调试命令,但务必确认没误填)。
