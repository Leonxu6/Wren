# 可观测 + 自我纠正闭环(W6)

**形态(与 Leon 对齐):完整捕获 + 显眼看板 + 按需人工深挖。** 不跑常驻的自动判定管线;真出问题时
你在看板发现 → 点我 → 我读那个用户的 trace 定位 → 据 trace 改。内容**不出机器**。

## 三层
1. **完整捕获(D2.1)** — 每轮 100% 落 `data/users/{id}/trace.jsonl`(step1 思考 / step2 / 发送 / 记忆 /
   reply-or-silence),每晚结算落 `settlement.jsonl`。这是真相源,可一键拉全(`diagnose`)。
2. **监测库 + 看板(D2.2)** — `wren-metrics ingest`(cron 每 ~15min,bot 进程**之外**)增量幂等把
   trace/settlement/source 灌进 `data/metrics.duckdb`(**只存指标+维度,绝不存原文**;`chat_id` 哈希)。
   Datasette 把 `ops/queries.py` 的命名查询变成看板页;`per_user_overview` 把**有问题的用户置顶**
   (冻结 / 沉默率高 / 卡级 一眼可见)。
3. **按需诊断(D2.3)** — `wren-metrics diagnose --chat-id X` 输出该用户人类可读的完整旅程(读机器上的
   原始 trace,供深挖),据此定位「声音塌 / 记错 / 错误冻结」。

## 闭环(D2.4)
```
看板(per_user_overview / engagement_daily 等)发现异常用户/信号
  → wren-metrics diagnose --chat-id <X>      # 读完整旅程,定位哪一轮、哪种 AI 味
  → 改 prompts/step1.py 或 persona/voice canon  # 杠杆永远是 prompt,不是硬编码句式(§0①)
  → uv run wren-aliveness && uv run wren-multiturn   # 复验:魂活不活 + 多轮弧线转绿
  → 真机 wren-bot 再聊几轮 → 下个 cohort 看板信号回落
```
关键指标(看板):按来源获取/激活/留存、**等级分布 + 每晚跃迁(头号)**、freeze/解冻、主动发vs压、
沉默率、按模型 token 成本、p50/p95 延迟、夜结算成功率。

## 跑起来
```bash
uv run wren-metrics ingest                 # 灌库(cron: */15 * * * *)
uv run wren-metrics query                  # 列出所有命名查询
uv run wren-metrics query per_user_overview
uv run wren-metrics diagnose --chat-id 12345
uv run wren-metrics forget --chat-id 12345 # 对齐 /delete:从库里硬删该用户

# 看板(只读、绑 localhost,SSH 隧道访问,绝不公网暴露):
uv tool install datasette
datasette serve data/metrics.duckdb --host 127.0.0.1 --port 8001   # 本机:ssh -L 8001:127.0.0.1:8001 vps
```
`WREN_METRICS_SALT`(env,勿提交)= chat_id 哈希盐;`WREN_METRICS_DB` 可覆盖库路径。

## 隐私
库里**只有**计数 + 维度(`user_turn_len` 是长度非文本;无 inner_voice/prose/raw_out);`chat_id`、
`turn_id`/`settlement_id` 前缀全哈希。原始 transcript 只在机器上的 `trace.jsonl`,供 `diagnose` 人工看,
不进库、不出机器。`tests/test_ops_ingest.py::test_privacy_no_raw_content_in_db` 守这条线(扫全表断言无原文)。

## 诚实标注的盲点(后补 trace seam,本期未做)
- **错误/超时率**:trace 无 error 字段(模型失败只 stderr 日志)。
- **主动消息门级压制全分解**:`ProactiveDecision.reason`(budget/level/window)未落 trace;看板只看得到
  到判断后的 发/压(`proactive_daily`)。
- **精确成本**:trace 只记 completion token → `cost_daily` 为下界。补 `prompt_tokens` seam 后才精确。

依赖这些的看板格子标 "n/a — 需 trace seam"。
