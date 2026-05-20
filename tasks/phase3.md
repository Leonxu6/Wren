# Phase 3 — 记忆「她记住你」· 开工卡 (worktree: `p3-memory`)

> 单 issue `p3-memory`(size L)。**验收/测试集已抠定**(2026-05-20 与 Leon co-design)。
> 完整验收/样例 → `tasks/acceptance.md` Phase 3;本卡 = 决策 + 现状 + 开工顺序 + 契约 + seam。

## 已定(co-design 锁定,直接照做)
- **范围 = 中期为主,长期留 seam**:短期(~30 轮,**已有**)+ **中期**(`events.md` 带
  `topic·valence·salience` 标签,**只进 Step1**)= 本阶段主体。**长期「夜间蒸馏」留给 Phase 6**
  (`p6-night-settlement` 本就 blocked-by p3;todo.md p3 红线把"标签做夜间蒸馏"标为 seam)。
  → m-memory 不需要夜间作业即可过:events.md 落盘**跨天持久**,每轮注入 Step1,day2 直接读到 day0。
- **记忆性格 = 选择性·情感加权**:event 在 Step1 **同一次 call 涌现写入**(零额外调用,§0①)。
  她**只存"真的会记住"的事**,多数轮 `event=null`;salience 由她的反应涌现,不靠规则。
  **不全量记录、不另立抽取器/分类器。**
- **验收覆盖(扩充 m-memory)**:① day0→day2 主动捞 + ② 反污染(中性轮不炫耀没递下来的旧事)
  + ③ 不机械复读 / 不硬捞(无相关记忆时硬塞 callback 也算错)。
- **门槛**:通用 **≥80%**(`m-memory` bar=general)· **N=3**/archetype · **judge=Claude Opus 4.7**。
  → 已是 `config.PASS_THRESHOLD=0.80` / `config.multiturn_reps()` / `WREN_JUDGE_MODEL`,直接复用。

## 关键现状:召回的「读侧」已接好一半(本阶段是补缝,不是造新)
- Step1 **已产出** `memory`(0–1 条想捞起的旧事)字段;Step2 **已消费**它当 `[ONE THING YOU MIGHT BRING UP]`。
- **缺**:① Step1 没有持久 `events.md` 可供召回(只有 30 轮 `recent_dialogue`,day2 时 day0 早滚出窗口);
  ② **没有任何代码写 `events.md`**——它现在是 stub(`storage._STUB_EVENTS`)。
- 所以 Phase 3 = 补齐:**涌现写侧 → events.md → 注入 Step1 → capping → Step2 自然捞起**。

## 现成 seam(别重造)
- **存储**:`core/storage.py` 已有 `_events` 路径 + `_STUB_EVENTS` 头 + `append_impression`/
  `read_recent_dialogue` 同款 append/read 模式;`init_user()` 已写 events stub。
- **召回字段**:`prompts/step1.py` 的 `parse_step1` 已解析 `memory`;`core/step1.py:Step1Result.selected_memory`;
  `core/pipeline.py` 已把 `selected_memory` 落 trace + 传给 Step2。
- **注入点**:`core/context.py:assemble_context` 是组装 Step1 context 的单点;`TurnContext` 加字段即可。
- **反污染是结构性的**:`prompts/step2.py:build_step2_messages` **无 events 参数** —— Step2 永不接收
  完整 dossier,只见 Step1 选出的 0–1 条。Phase 3 **保持不变**。
- **离线**:`WREN_FAKE_MODEL=1` 全确定性跑通 plumbing(脚本可模拟 event 写入→跨"天"召回)。

## 开工顺序(串行;每步带验收)
1. **存储 events 读写**(`core/storage.py`,S)
   - `+ append_event(text, topic, valence, salience)` → 写 `- [topic|valence|salience] text`。
   - `+ read_events(cap)` → 解析标签行,按 **recency + salience** 选,token/条数 cap 内返回。
   - `+ config.events_cap()` seam(默认 ~40 条/~1500 tok,env 可覆盖)。
   - 验收:round-trip;cap 排序(高 salience + 近期优先,溢出丢最旧最低)。
2. **Step1 涌现写 + 注入**(`prompts/step1.py` + `core/step1.py` + `core/context.py`,L)
   - `assemble_context` 读 `read_events()` → `TurnContext.events`;`build_step1_messages` 加
     `[THINGS YOU KNOW ABOUT THIS PERSON]` block(= capped events)。
   - `_STEP1_INSTRUCTION` 加**涌现写侧**:让她在真实反应里"是否有真会记住的事"自然冒出来 →
     输出字段 `event`(可空 `{text, topic, valence, salience}`)。**选择性·情感加权,不写死句式**
     (见 `voice-emerges`:只描述质感,绝不规定"该说什么")。`parse_step1` 解析 `event`(有/null/坏都稳)。
   - `Step1Result += event_to_store: dict|None`;`run_step1` 传 `ctx.events`、映射 parsed `event`。
   - 验收:context 含 events block;parse 稳;独白人读着"像她在想该不该记住这事"。
3. **写侧落盘 + trace**(`core/pipeline.py`,S)
   - Step1 写回后:`if s1.event_to_store: store.append_event(**s1.event_to_store)`。
   - trace `step1_dict` += `event_stored` + 注入的 events 进 prompt block(任一轮可复盘"记了什么/捞了什么")。
   - 验收:emit→落盘;`event=null` 轮不写;沉默轮也照常(写侧在 Step1 后、reply 分支前)。
4. **Step2 自然捞起**(`prompts/step2.py`,S)
   - `[ONE THING YOU MIGHT BRING UP]` 轻推:像**刚想起**、自然织入,**不**「you mentioned earlier」
     (涌现,非规则)。已有"don't quote their message back",在其上加"像随口想起"质感。
   - 验收:judge 判"像真记得"而非"复读"。
5. **eval 转绿**(`eval/corpus/multi_turn.yaml`,M)
   - `m-memory`:`status: green`、去 `blocked_until: P3`;加 **反污染探针**(中性轮)+ **无相关记忆探针**。
     〔构造〕措辞与 Leon 校准。
   - 跑 → 调 Step1/Step2 到 ✅ 三条达 ≥80%;**其余 archetype 保持绿**(回归无破)。
   - 收尾跑 **`/go`**(验证 → 简化 → PR)。

## 怎么跑 / 验证
```bash
# 离线机制(无 key):全确定性
WREN_FAKE_MODEL=1 uv run wren-multiturn --script m-memory
uv run ruff check src tests && uv run mypy src && uv run pytest -q

# 真·通过率(需 deepseek 主模型 + Opus judge):
WREN_API_KEY=<deepseek> WREN_JUDGE_MODEL=claude-opus-4-7 \
  WREN_JUDGE_BASE_URL=https://api.anthropic.com/v1/ WREN_JUDGE_API_KEY=<anthropic> \
  uv run wren-multiturn --script m-memory

# 真机调 voice(day0 提事 → mock 进 day2 → 看捞得像不像人):
uv run wren-bot   # @Her3636bot
```

## 红线(ARCHITECTURE §0,别破)
- **§0① 涌现**:event 写侧在 Step1 **同一次 call** 涌现 —— 不做独立抽取器/分类器,**不全量记录**(选择性)。
- **§0② 轻量留 seam**:`read_events` 的 cap/tag **就是** "夜间蒸馏 + 关键词召回" 的缝;**非 RAG**。
- **§4/§8 反污染**:events **只进 Step1**;Step2 只见 0–1 条 Step1 选出的。
- **voice-emerges**:Step1/Step2 指令只描述"像人"的质感(像真记得 / 像随口想起),**永不规定句式**。

## Review(实现回填 · 2026-05-21)

**已落地(p3-memory 分支)**:storage events 读写 + cap seam → Step1 涌现写 + 注入 → pipeline 落事件 + trace → Step2 自然捞起 → m-memory 转绿 + 反污染/不硬捞探针 → 合成 Lv3 + 召回 deliberate re-read。离线:ruff/mypy + 108 pytest 全绿。

**真模型验证(in-session Opus 判,deepseek 生成)**:
- ✅ **机制全通**:capture(选择性存「heat 修好」「sister 借住」,跳过 filler/她自己的反应)→ inject(`[THINGS YOU KNOW]` 进 Step1)→ select(Step1 出 0–1 召回)→ surface(Step2 自然说,非机械复读)。
- ✅ ② 反污染 **5/5**、③ 不硬捞 **5/5**(中性/无关轮不倒旧事、不硬塞 callback)。
- ⚠️ ① **间接召回 = 模型能力门槛(§15#4)**:v4-flash **~0/5**(做不出 freezing→heat 跨话题联想;用「cold→heating」示例诱导 = teaching-the-test,撤掉即归零),**v4-pro 2/2**(自然 `thought the heat was fixed`)。**Leon 决策(2026-05-21):保持 v4-flash + 记录限制**;① 标 `blocked_until: stronger-step1-model`(不计门槛),换更强 Step1 模型应转绿。

**留给后续**:Step1 选型(§15#4 · model-routing seam 已在,可只把 Step1 路由到强模型);长期记忆夜间蒸馏 → Phase 6;真机 `wren-bot` voice 调。
