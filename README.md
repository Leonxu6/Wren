# Wren — Phase 0 eval + Telegram walking skeleton

英文 AI 关系模拟 Telegram bot "Wren" 的第一段可运行实现:**Phase 0 单轮 eval + voice bake-off**(掐头号风险 §15#4)+ **Phase 1 walking skeleton**(Telegram ↔ think→speak ↔ per-user markdown ↔ trace)。

设计权威在仓库根:`PRD_product.md` / `ARCHITECTURE.md` / `EVAL_spec.md` / `eval/eval_set.md` / `tasks/`。

## 装

```bash
uv sync
cp .env.example .env   # 填 key/token;留空 WREN_API_KEY → 自动 fake 模式
```

## 离线验证(无需 key/token)

```bash
WREN_FAKE_MODEL=1 uv run pytest -q     # 67 用例:机械门/语料/judge/管线/trace/bot handler…
uv run ruff check . && uv run mypy src
```
所有逻辑、契约、管线、写边界铁律在 fake 下端到端可验证。

## 跑 Phase 0 voice bake-off(需 WREN_API_KEY,真出结论)

```bash
uv run wren-harness                 # 全语料 × 候选模型 × N reps → 模型×Cat×通过率矩阵 + bake-off + verdict
uv run wren-harness --quick --reps 2 --no-bakeoff   # 省钱冒烟
uv run wren-harness --category 3    # 只跑反谄媚(pillar#2)
```
产出:每个候选模型的「Cat × 通过率」+ 反谄媚 Cat3 通过率(门槛 90%)+ 对甜妹 baseline 胜率(门槛 70%)+ 失败样本明细。结论见 `docs/p0_verdict.md`。

## 起 Telegram bot(需 TELEGRAM_BOT_TOKEN + WREN_API_KEY)

```bash
uv run wren-bot
```
真机:对 bot `/start` → 18+/AI 披露 + 背景文案 + 她沉默 → 打一句 → 几秒后多条短气泡。每轮落一条 trace 到 `data/users/{chat_id}/trace.jsonl`;`/delete` 清空。

## 模型(§15 开放项)

文档原写候选 **DeepSeek-V3**;供应商已升级到 V4 代(V3 下线),依「LLM 选型是开放提案」改用当前模型:
- `deepseek-v4-flash` = 便宜候选(头号风险:它能否撑住 Wren voice)。
- `deepseek-v4-pro` = 更强对照 + 判官(judge)。

换任何 openai 兼容供应商只改 `.env`(`WREN_BASE_URL/WREN_MODEL`),**零改代码**(model-router seam,`src/wren/model/`)。

## 红线(贯穿,见 `ARCHITECTURE.md §0` / `PRD §3`)

涌现 > 模块:机械门/judge 只在 `src/wren/eval/`(**生产 `src/wren/core/` 不 import 它**);关系只存离散 level + 定性散文 + freeze(**非积分**);level 永不当语气旋钮;memory 只进 Step1;think→speak 两次 call,判断锁在 Step1,**沉默是头等 branch**;用户线永不写 `world/`/`canon/`。

## 目录

```
canon/            Wren ground truth(backstory/voice/golden;§15 提案标 proposal)
eval/corpus/      单轮语料 fixture(Cat1-6)
src/wren/
  model/          ★ model-router seam(fake + openai 兼容真实适配器 + registry)
  prompts/        Wren system 种子(反谄媚两轴)+ step1/step2/judge prompt
  eval/           机械门 + judge + 打分内核(scorer)+ harness + bakeoff + replay
  core/           生产链路:storage / clock / context / step1 / step2 / pipeline / trace
  onboarding/     §9.1 静态文案(不走 LLM)
  bot/            Telegram I/O:handlers / debounce / sender / app
tests/            离线 fake 下全绿
```
