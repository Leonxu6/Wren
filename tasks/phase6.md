# Phase 6 — 关系夜结算「关系会长」· 开工卡 (worktree: `p6-night-settlement`)

> 单 issue `p6-night-settlement`(size L)。**验收/决策已 co-design**(2026-05-21 与 Leon,grill-me)。
> 完整效果/样例 → `tasks/acceptance.md` Phase 6;本卡 = 决策 + 现状 + 实现 + 契约 + seam。
> 依赖:`p3-memory`(已合并 main)+ `p2-mock-clock` + Phase 1。**不依赖 P4/P5**(P5 反而读 P6 的 level)。

## 已定(co-design 锁定,直接照做)
- **范围 = 5 件全上**:夜里读 `impressions_today` + `events` + `relationship_state`(+ 长期印象 + 未了情绪)→
  ① 重写关系散文(voice-fuel)② 整体裁决离散 level ③ 蒸馏长期核心印象(**写入永久注入文件**)
  ④ 更新 `unresolved_feelings` ⑤ 清空 `impressions_today`。
- **level 升降 = 自由双向、无 clamp**:完全信任夜间整体裁决;**「黏性棘轮」靠 prompt 涌现**(关系 earned、慢、
  极少动、只在真证据下动),绝不靠代码 clamp(§0①)。真破裂(踩雷/未被真正读懂)可退级 + 进 freeze。
- **freeze = 散文承载 + 夜结算置位**:结算是 level 与 freeze **唯一**写入方;Step1 只读散文涌现冷/回温。
  当下变冷 / 真懂回温靠 Step1 涌现(已绿);**跨夜持久**靠结算重写冷散文 + 置 freeze。
- **触发 = 后台调度器**:复用 PTB `JobQueue.run_daily` @ **02:30 ET** 遍历活跃用户;`settle_nightly()` 仍
  clock 可注入 + 同步,eval 用 MockClock 直接驱动,`wren-nightly` CLI 供手动/Opus 手判。
- **结算模型 = deepseek-v4-pro(强档)**:holistic 跨天裁决正是 v4-flash 弱项(§15#4);新增 `settlement` role,
  留 `WREN_SETTLEMENT_MODEL/BASE_URL/API_KEY` seam(可升 Opus)。结算每晚一次/用户,成本低。
- **验收 = 双层**:白盒机制(pytest·fake 确定性)+ 黑盒行为(multiturn·Opus 判,N=3,通用 ≥80%);
  黑盒验**升级与降级两方向 + 跨天结算运行 + 用户视角明显变化**。

## 现成 seam(复用,别重造)
- **存储**:`Relationship(level, prose, freeze)` 已在(无积分字段);`append_impression` 注释已写「夜结算消费」。
- **关系写入**:`write_relationship()` 已在——结算就是它(此前唯一)的写入方;`level`/`freeze` 此前从没被改过。
- **clock**:`MockClock`/`SystemClock` + `iso_z` 已在;`settle_nightly(clock=)` 注入同 `handle_turn`。
- **模型路由**:`registry.Role` 已留 `background` 位 + `config.judge_model_spec()` 的独立 key/base_url 范式。
- **eval**:`multiturn` 的 `advance_days`/`set_time`/`ScriptSetup` 注入态已在;judge=`judge_arc`、N=`multiturn_reps()`。
- **trace**:`write_trace` 单点 JSONL 模式;结算另落 `settlement.jsonl`(不污染 `count_traces` 的 turn_id 计数)。

## 实现(已落地 · p6-night-settlement 分支)
1. **存储**(`core/storage.py`):`read_impressions`/`clear_impressions` + `core_impression.md`/`unresolved_feelings.md`
   读写 + `init_user` 种空文件;`_read_bullets` 共用解析。
2. **结算 prompt**(`prompts/settlement.py`):`build_settlement_messages`(Wren 夜里整体重读关系;阶梯=gate-key 含义;
   earned/慢/黏、退级+freeze、空泛 sorry 不解冻只真懂回温;输出 JSON)+ `parse_settlement`(缺字段 None → 回退旧值)。
3. **结算编排**(`core/settlement.py`):`settle_nightly(store, settle_model, clock=)` → 无印象早返回;裁决 → 写
   relationship/core/unresolved → 清印象 → 落 `SettlementTrace`。
4. **模型**(`config.settlement_model_spec()` 默认 v4-pro + `registry` 加 `settlement` role)。
5. **读侧注入**(`core/context.py` + `prompts/step1.py`):core_impression / unresolved 注入 Step1(空则不注入;反污染保持只进 Step1);pipeline trace 记录之。
6. **trace**(`core/trace.py`):`SettlementTrace` + `write_settlement_trace` → `settlement.jsonl`。
7. **调度器 + CLI**(`bot/scheduler.py` `register_nightly` 接进 `app.py`;`bot/nightly.py` = `wren-nightly`;
   `pyproject` 依赖加 `[job-queue]` extra + `wren-nightly` script)。
8. **eval**(`multiturn` 在 `advance_days` 跨夜跑 `settle_nightly`(仅 `script.settle` 开)+ 记录 level 升降轨迹打印;
   新增 `m-grow`(升级+earned)/ `m-rupture`(退级+freeze+跨夜修复);`m-vuln` 重标 `P7`)。
9. **白盒**(`tests/test_settlement_flow.py`:消费/写/清/退级+freeze/解析失败回退;`test_multiturn` 加结算钩子触发)。

## 怎么跑 / 验证
```bash
# 离线机制(无 key · 确定性):pytest 把「读印象→裁决→写→清→落 trace」证死
WREN_FAKE_MODEL=1 uv run pytest -q && uv run ruff check . && uv run mypy src
WREN_FAKE_MODEL=1 uv run wren-multiturn --script m-grow --no-judge   # 仅 plumbing + 看 level 轨迹打印

# 真·黑盒(需 deepseek 主模型 + v4-pro 结算 + Opus judge):
WREN_API_KEY=<deepseek> WREN_JUDGE_MODEL=claude-opus-4-7 \
  WREN_JUDGE_BASE_URL=https://api.anthropic.com/v1/ WREN_JUDGE_API_KEY=<anthropic> \
  uv run wren-multiturn --script m-grow      # 看 level 轨迹 0→…↑ + 行为转暖 ≥80%(N=3)
  uv run wren-multiturn --script m-rupture    # 看 3→2❄ + 跨夜仍冷 + 空泛sorry无效 + 真懂回温
uv run wren-nightly                          # 手动跑一次,肉眼看 before→after 散文/level
```

## 红线(ARCHITECTURE §0,别破)
- **§0① 涌现**:印象→等级是 LLM **整体裁决**,**非积分**;`Relationship` 无 score 字段。
- **level 只 gate,散文驱动语气**:level/freeze 数字**永不**进 voice prompt 当语气旋钮。
- **黏性棘轮 = prompt 性质**,非代码 clamp(本阶段定:自由双向 + 无 clamp,黏性靠指令)。
- **修复**:空泛 sorry / 奉承不解冻,只「真懂为什么」才回温(Step1 当下涌现 + 结算跨夜持久)。**无永久 lockout**(推 V2)。
- **反污染**:core_impression / unresolved **只进 Step1**;Step2 不接收 dossier。

## 留给后续 / 待 Leon
- **#1 风险**:真模型跑 `m-grow`/`m-rupture` N=3 看 level 轨迹与行为转暖是否稳;不稳则 `WREN_SETTLEMENT_MODEL` 升 Opus(零代码)。
- `unresolved_feelings` 的下游消费(延迟揭示)在 **P5**;本阶段已写 + 注入 Step1 染色,非死码。
- 真·2:30 cron 已接 PTB JobQueue;P5 的「每 10-15min 扫 beat」共用这套调度 seam。
