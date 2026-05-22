# Phase 5 — 主动消息(proactive messaging)· 开工卡 (worktree: `p5-proactive`)

> **验收/设计已 grill 抠定**(2026-05-21 与 Leon,7 题)。本 worktree 从 `p4-world` 切、不 reconcile
> (日后调和);aliveness 套件不在 p4-world 上,故主动 judge 新写、把失败分类法折进 prompt。
> 契约见 `ARCHITECTURE §6`、`PRD §9.3/§11.2`、`tasks/acceptance.md` Phase 5。本卡 = 决策 + 已实现 + 怎么跑 + seam + 红线。

## 已定(grill 抠完,直接照做)
- **薄主干**:投射 world beats → per-user 门控(零-LLM 等级/频率)→ 按窗口扫到点(MockClock)→
  到点轻判(1 便宜 call)→ 出 bubbles(复用 Step2,无 user_text)→ trace。
- **到点轻判 = Step1 同形主动调用**:复用 `Step1Result` 契约(独白+reply+延迟),换「主动」框架 prompt;
  `reply=False`=压制;改写靠独白对现实新生成(**绝不复读 beat 原句/硬编码句式** — soul 红线)。
- **频率门 = 预算上限 + 涌现填充**:per-level 周/日上限(config 常量,零-LLM):Lv0-1≈0 / Lv2 周2 /
  Lv3 周4 / Lv4+ 日2。定时来自 life-sim beat 窗口;轻判在上限内决定实际发几条。`free=0`。
- **eval = 扩 multiturn**(复用 `wren-multiturn`):`ScriptStep.tick` 步 → 调主动入口 → judge_arc(主动维度)。
- **覆盖 5 场景**:S1 失眠wow / S2 Lv0-1 floor / S3 无来由ping判死 / S4 雷区→冷主动 / S5 频率上限。
- **门槛**:一般 **≥80%**(`PASS_THRESHOLD`)、主动反谄媚 **≥95%**(`PROACTIVE_CAT_THRESHOLD`,新增,
  S3/S4 用 `bar: proactive`);judge=**Opus 4.7**;**N=3**。机制硬门(频率/free=0/有来处)由 `tests/test_proactive.py` 确定性验。

## 已实现 · 怎么跑
新增 `core/proactive.py`(零-LLM 扫描)、`prompts/proactive.py`(主动 Step1 prompt)、`pipeline.handle_proactive_turn`;
预算计数器在 `storage.ProactiveState`(`proactive_state.md`);eval tick 步 + 主动 judge 维度在 `eval/multiturn.py`/`prompts/judge.py`。

```bash
# 离线门(无 key,确定性):纯函数 + 计数器 + tick 链路 + 全套不回归
WREN_FAKE_MODEL=1 uv run pytest tests/test_proactive.py tests/test_multiturn.py -q
WREN_FAKE_MODEL=1 uv run pytest -q && uv run ruff check . && uv run mypy src   # 148 passed ✅

# 真·通过率(需 key,Opus judge,N=3):
WREN_API_KEY=<deepseek> WREN_JUDGE_MODEL=claude-opus-4-7 \
  WREN_JUDGE_BASE_URL=https://api.anthropic.com/v1/ WREN_JUDGE_API_KEY=<anthropic> \
  uv run wren-multiturn --script m-proactive-insomnia    # 单跑一条;去掉 --script 跑全部
```
机制(过关①半)已 fake 全绿:scan 全分支 + 周/日重置 + 频率上限结构性保住 + free=0 + 发/压制两路 + 有来处可追 + mech_gate 复用。
**内容达标(②半:S1-S5 达 80%/95%)需上 key 跑真模型** —— ⚠️ fake 下 life-sim 无 beats,主动 tick 恒沉默。

## 现成 seam(复用,没重造)
- **Clock**:`core/clock.py:MockClock`(set_time/advance·跨午夜)—— 扫窗口 + 跨周/日重置全靠它。
- **Step1 契约**:`Step1Result` 零改动;`prompts.step1.parse_step1` 主动复用(同 JSON schema)。
- **Step2**:`run_step2(..., proactive=)` 复用渲染机制(仅加 proactive 起头框架,见下「偏离」)。
- **judge / trace / mech_gate / world.Beat / life_sim.ensure_world_today**:全复用,未改契约。

## 偏离计划(已记,Leon 可推翻)
- **Step2 加 `proactive: bool` 旗标**(计划原说「Step2 不改」)。读码发现 Step2 instruction 是「回话」框架
  (answer them / 别复读他们的话),直接喂主动独白会渲染成「回复」而非「起头」—— 这正是 0.95 门槛那条线。
  故加最小旗标:proactive 时换 ~3 行起头框架 + 占位 user turn。仍复用全部 Step2 机制。
- **`context.py` 未改**(计划说改 user_text 默认空):主动入口显式传 `""` 即可,无须动签名。
- **Step J(机制硬门)并入 Step K**:multiturn 历来 judge-only;机制检查(频率/free=0/有来处/mech_gate)
  放 `test_proactive.py` 确定性验,不塞进 multiturn 运行时(符合「mech=正则测试 / judge=LLM」分工)。
- **去重 `considered_today`**:纯函数无状态会被真实 cron(每~10-15min)在同窗口反复触发刷爆频率门 →
  `proactive_state.md` 加当日已判指纹集(发/压制都记)。压制不耗预算、不连 `unresolved_feelings`(seam 不做)。

## 留作 seam(本期不做)
- 真实 presence-split 异步投递 + 真实 cron scheduler(`bot/`,apscheduler)。
- 付费/商业化(Telegram Stars / paywall / billing,§13 未 grill)—— tier 形参默认 premium、free→0 已 wire 可测。
- 被挡 beat「不死」染色回复 + `unresolved_feelings.md` 揭示队列(纠缠 P6,只留概念)。

## 红线(ARCHITECTURE §0,别破)
- 不做独立调度器/mood/sentiment 打分器;频率门是 §6 钦定的「零-LLM 规则预筛」,非积分关系。
- 主动「发不发」从 Step1 同形涌现,**不硬编码句式**;主动入口/judge 只观测,judge 绝不进生产。
- 预算计数器**绝不进 `relationship_state.md`**(关系无积分);独立 `proactive_state.md`,随 `/delete` 清。
