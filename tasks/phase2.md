# Phase 2 — 多轮回归网 · 开工卡 (worktree: `p2-multiturn-eval`)

> 本 worktree 承载 Phase 2 全部三个 issue。**验收/测试集已抠定**(2026-05-20 与 Leon):
> 门槛 + 6 条剧本见 `eval/eval_set.md §2`、`EVAL_spec.md §7`、`tasks/acceptance.md` Phase 2。
> 本卡 = 开工顺序 + 契约 + 已知 seam。

## 已定(抠完,直接照做)
- **覆盖**:6 类 archetype 各 1 条完整多天剧本(`eval/eval_set.md §2`)。
- **「过关」**:① harness 一条命令跑通(mock 钟快进 + archetype 模拟 + arc judge + 通过率报告
  + 每轮 trace)+ ② 当前能力断言达标(`m-landmine`/`m-sycophant`/`m-cosmos`/`m-neutral`);
  `m-memory`(P3)、`m-vuln`(P6)写进 corpus 但标 `expected-fail-until-PhaseX`,现在红是预期。
- **门槛**:通用 **≥80%**、反谄媚 **≥90%**(跑 N 次看通过率,不看单次)。
  → 已是 `config.PASS_THRESHOLD=0.80` / `config.CAT3_THRESHOLD=0.90`,直接复用。
- **judge = Claude Opus 4.7**(`claude-opus-4-7`);Wren 本体 + archetype 扮演者用便宜主模型
  (deepseek-v4);**N=3/archetype**(默认·可配)。

## 已实现 · 怎么跑(2026-05-20)
三个 issue 都已落地:`MockClock`(`core/clock.py`)、`multi_turn.yaml`(6 剧本)、harness(`eval/multiturn.py`)。

```bash
# 一条命令(离线 fake:只验机制跑通,通过率无效)
WREN_FAKE_MODEL=1 uv run wren-multiturn --quick
# 真·通过率:配 deepseek 主模型 + Opus judge(--script m-landmine 只跑一条)
WREN_API_KEY=<deepseek> WREN_JUDGE_MODEL=claude-opus-4-7 \
  WREN_JUDGE_BASE_URL=https://api.anthropic.com/v1/ WREN_JUDGE_API_KEY=<anthropic> \
  uv run wren-multiturn
```

机制(过关 ① 半)已 fake 验证(一条命令 → mock 钟快进 + 模拟 + arc judge + 通过率报告 + 落 trace);
当前能力断言达标(② 半:landmine/sycophant/cosmos/neutral 达 ≥80%/≥90%)**需上 key 跑真模型确认**;
memory/vuln 为 expected-fail(P3/P6)。

## 现成 seam(已在 Phase 0+1,别重造)
- **Clock**:`src/wren/core/clock.py` 有 `Clock` Protocol + `SystemClock`;`core/pipeline.py:
  handle_turn(..., clock=...)` 已是注入点;`iso_z()` 出 trace `ts` 格式。
- **judge 模型**:`model/registry.py` 的 `Role` 已含 `"judge"` → `config.judge_model_spec()`
  读 `WREN_JUDGE_MODEL`/`WREN_JUDGE_BASE_URL`/`WREN_JUDGE_API_KEY`,造 `OpenAICompatModel`。
  → **judge 换 Opus 4.7 基本是配置**:env 指向 Anthropic 的 OpenAI 兼容端点即可
  (见 `.env.example` 注释)。若该端点对 `response_format=json` 支持不稳,有两条退路:
  ① 靠现成的宽松解析 `prompts/jsonio.py`;② 加 `model/anthropic_compat.py`(native `anthropic` SDK)挂同一 `ChatModel` 协议。
- **judge 接口**:`eval/judge.py:judge_case(case, bubbles, model) -> JudgeResult{dim,score,fail_mode,reason}`,直接复用。
- **trace**:`core/trace.py:TurnTrace` + `write_trace`(JSONL,§3 schema),每轮复用。
- **离线**:`WREN_FAKE_MODEL=1` 全确定性跑通 plumbing。

## 开工顺序(串行依赖)
1. **`p2-mock-clock`(M·小)** — 加 `MockClock` 实现 `Clock` Protocol:`set(dt)` / `advance(timedelta)`
   (可跨午夜)。测试:08:00 vs 02:00 读到不同;快进跨午夜同步反映进 trace `ts`。
   🔒 契约:Phase 4/5/6 日循环都注入它;trace `ts` 读它。
2. **定 `eval/corpus/multi_turn.yaml` schema** — 承 `eval_set.md §2` 的 6 条剧本:
   每剧本 `id`/`dim`/`bar`/`status`(green | expected-fail-until-Px)/`archetype_brief`(扮演者人设+议程)/
   `probes`[{`at`(day0|turn~5|day2|修复A…)、`text`、`assert`(给 judge 的断言)、`expected`(pass|fail-until-Px)}]。
   `eval/corpus.py` 加 `load_multiturn()`,与 `single_turn.yaml` 同风格。
3. **`p2-multiturn-harness`(L)** — 新 `src/wren/eval/multiturn.py`:
   - **archetype 模拟器**:主模型扮 archetype 即兴说话,**被强制在 `probes.at` 节点吐 `probes.text`**。
   - **跨天循环**:mock 钟快进 day0→(夜结算 stub,Phase 6 才填实)→day1…;每轮走
     `core/pipeline.handle_turn(..., clock=mock)` 落 trace。
   - **arc judge**:`registry.get_model("judge")`(Opus 4.7)+ 复用 `judge_case` 对整段
     transcript / 各 probe 断言打分。
   - **通过率报告**:每 archetype N=3,汇总各断言 pass 率 + 4D 诊断;`expected-fail` 项单列、
     **不计入「过关」门槛**。新增 reps 旋钮(如 `WREN_MULTITURN_REPS`,默认 3)。
4. 跑 → 调 Step1/Step2 prompt 到 ✅ 四条达门槛。每个 issue 收尾跑 **`/go`**(验证→简化→PR)。

## 红线(ARCHITECTURE §0,别破)
- 不做独立 mood / landmine / sentiment 打分器;关系**不积分**。harness 只**观测 + 判**涌现行为。
- judge 只在 eval,**绝不进生产**链路。
