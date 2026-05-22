# 「Wren」MVP 技术架构 (Technical Architecture)

> **配套** `PRD_product.md`。本文 = 把三大支柱(**主动性 / 自我思想 / 关系阶段**)落成一个可建系统的技术决策与架构。
> **本文取代/细化** PRD 附录 A(技术架构与因果链工程)。
> **来源**:2026-05-20 与 Leon 的架构 grill,**15 条决策**全部对齐。
> **语言约定**:正文中文;技术术语 + 所有「她说的话」样本英文(沿用 PRD)。

---

## 0. 两条贯穿全篇的铁律

1. **涌现 > 模块**:凡是能从「人设 + 世界」推导出来的东西(踩雷、姿态、态度、印象、修复判定),**都不拎出来做独立分类器**——它们活在 canon 里,在 Step1 那一刻**涌现**成她的当下想法。把派生物 reify 成模块,既多余又把「涌现」降格成「规则匹配」,丢魂。
2. **轻量优先,留好 seam**:MVP 做**最薄能跑**的版本,但在「模型路由 / 记忆召回 / eval」等处**预留升级缝**,使后续迭代是 drop-in 而非返工。

---

## 1. 决策记录 (15 条 ADR)

| # | 决策点 | 选择 | 一句话理由 |
|---|---|---|---|
| 1 | 世界时间线模型 | **晨间种 beat**(全局 life skeleton)| 兑现「早上就知道下午会寂寞」,又不养一个连续 tick 的模拟器 |
| 2 | beat 触发对齐 | **到点轻判改写** | beat 是 intent 非脚本;到点拿现实重新落地(压制/照发/改写/迁移),防穿帮 |
| 3 | 被门控挡下的 beat | **留作内在状态** | 门控只关「表达」不关「内心」;渗进回复 + 喂延迟揭示 + 付费墙的牙 |
| 4 | 认知架构 | **Step1 涌现内心 → Step2 voice** | 判断先于措辞 = 反谄媚;沉默是头等 branch;踩雷不单列(活在 canon) |
| 5 | 模型策略 | **单一便宜 DeepSeek,不路由** | MVP 不过早复杂;唯一硬 gate = Step2 过 §7.4 盲测,不过只换这一步 |
| 6 | 印象 → 等级 | **夜间 LLM 整体裁决** | 靠定性印象不靠积分;level 只当 gate-key,语气靠散文(绝不当语气旋钮) |
| 7 | 世界实例化 | **共享 life + per-user 关系** | 她一个人一条命;用户只写自己线、不改全局;earn 的是 access 不是改写权 |
| 8 | 失败 / lockout | **全程可修复,永久 lockout 推 V2** | 无不可逆动作 → 纯涌现安全;魂靠冷/freeze/退级(可修复)保住 |
| 9 | 延迟揭示 | **复用主动管线** | = 来源是「关系」的 beat + Step1 的 context 来源;零新机制 |
| 10 | 中期记忆 | **轻量:打标签、只进 Step1、Step2 门控** | 防上下文污染;YAGNI 先全量后召回,标签从 day1 留 seam |
| 11 | 消息延迟 | **调度延迟发送 + presence-split** | 在场 ≤10min;长 realism 转异步通知;延迟期新消息取消重跑 |
| 12 | 输入连发 | **固定 debounce 窗口(~3–5s)** | 合成一个 user turn,防回碎片 |
| 13 | 验证体系 | **全自动多轮(hybrid 模拟用户)** | 价值全在多轮微妙处;N 次看通过率;mock 时钟快进多天 |
| 14 | eval 北极星 | **对照 A/B + 四维 rubric** | 「特别」是相对竞品的 → 对 baseline 胜率;四维 D1–D4 诊断 |
| 15 | 建造顺序 | **风险优先 → 垂直切片** | 先掐 voice 风险 → 最薄端到端 → 按「最快卧槽」叠层 |

---

## 2. 数据布局

```
# ===== 全局(一个 Wren,一条命)=====
canon/
├── backstory.md          §6 人设锚点(不可变)
├── voice_spec.md         §7 voice 规格(不可变)
└── golden_dialogues.md   §7.4 金标准(eval 用)

world/
└── today.md              ② 今日 life skeleton:日程 + 硬 life 事件 + base mood
                          ← life-sim 每天全局跑【一次】写入

# ===== per-user: data/users/{telegram_chat_id}/ =====
# 用户对话只写这里,【永不】碰 world/ 或 canon/
relationship_state.md     ③ 离散 level(gate-key) + 关系定性散文(voice-fuel)
                            + freeze 状态(可修复,无不可逆 lockout flag)
inner_voice.md            她对你当下的内心独白(每轮 Step1 后更新)
events.md                 中期记忆,每条带 topic / valence / salience 标签(只喂 Step1)
impressions_today.md      当天攒的印象 delta(夜间结算消费后清空)
beats_today.md            今日对「你」的表达计划(从 world/today.md 投射 + 你这条线的门控)
unresolved_feelings.md    延迟揭示队列
billing.md (or flag)      premium 状态 + 免费额度计数(见 §11,待 grill)
```

---

## 3. 三层世界模型(决策 1 / 6 / 7)

| 层 | 范围 | 谁能写 | 内容 |
|---|---|---|---|
| **① Canon** | 全局不可变 | 仅 canon | §6 backstory + §7 voice 规格 |
| **② 每日 life skeleton** | **全局,一个 Wren 一条命** | 仅 life-sim(每天 1 次)| 日程 + 硬 life 事件(妈妈下月来 / residency / open studio)+ base mood;含几个**情绪 beat**(intent) |
| **③ 关系 + 表达** | **per-user** | 你这条线的对话 | level / 印象 / 态度 / 她会不会找你 / 跟你说多少 |

- **「她下午肯定会遇到难过的事」= ②**,全局事实,对所有人一样。**「她会不会找你、说多少」= ③**,取决于你这条线。
- **写边界铁律**:用户对话**只写自己这条线**,改的是「你和她的关系 + 你这条线的本地情绪 / disclosure」;**永不改全局**。她的人生大弧光照全局节奏走 —— 你 earn 的是 **access**,不是改写她人生的作者权(§3「她不为你存在」)。

---

## 4. 每条消息的流 (per-turn)

```
用户消息到达
 │
 ├─ [debounce ~3–5s] 窗口内连发的合成一个 user turn(决策 12)
 │
 ├─ 读取上下文:canon + world/today + relationship 散文 + inner_voice
 │             + events(capped, 带标签) + 最近 ~30 轮对话
 │
 ├─ ▶ Step1 内心 (cheap DeepSeek) ── 输出 = 她这一刻【涌现】的真实内心独白
 │      · 踩雷 → 独白自然带刺("you sound like my mother");被勾起/敷衍/想敞开 → 都在语气里
 │      · 【不】另立「姿态 / 踩雷 / lockout」字段(涌现,非分类器)
 │      下游只读两样必要后果(读数,非分类器):
 │        (a) 回不回 + 延迟时长   ← 唯一必须结构化(发不发是动作门;纯沉默 = leave on read)
 │        (b) 一条 in-character 印象 → 追加 impressions_today
 │      写回:更新 inner_voice
 │
 ├─ 若决定「回」:
 │      算延迟(presence-aware,决策 11) ──┐
 │      ▶ Step2 开口 (cheap DeepSeek)     │  输入 = Step1 独白 + Step1 选中的 0–1 条记忆
 │        · 在【已定】的内心语气下表达      │       + canon + §7 voice 规格 + 当前 level(仅作事实,不作旋钮)
 │        · 输出 = 短消息【数组】(2–8 词)  │
 │      ▶ 发送器:多 bubble + typing 指示 + 几百 ms~1s bubble 间隔(§7.3)
 │
 └─ 若延迟期内用户又发消息 → 取消待发回复,带新消息重跑 Step1(决策 11)
```

**反谄媚 = Step1 先锁判断**:Step1 在「没有必须产出回复」的压力下形成真实判断,Step2 只能在已锁语气下表达 → 没法反向写好话再补想法。
**非服从(她不是 assistant)**:反谄媚有**两条轴**——观点轴(错了说错)+ **请求/服从轴**(你下命令/提要求,她像不伺候你的真人怼回/无视,**不** "sure!"、**也不** "As an AI I can't")。系统 prompt 必须显式立「你不接需求」,否则 assistant 训练出的模型默认去满足请求。详见 `EVAL_spec.md` §3 Cat 3。
**反污染 = 记忆只进 Step1**:Step2 看不到完整 events dossier,无法炫耀它没见过的东西;Step1 多数轮判定「无相关记忆」,只传 0–1 条贴合的下去。

---

## 5. 日循环 (Daily Heartbeat)

> **所有时钟读一个可注入的 clock**:生产 = 真实 ET wall-clock;eval = 可快进的 mock(决策 13)。Wren 锚定**单一 ET 时区**。

```
全局 · 晨 (ET ~7am)   life-sim 写 world/today.md           ← 每天【一次】,全局
per-user · 晨/夜      从 world/today 投射 beats_today       ← 按你这条线的关系门控
per-user · 夜 (ET ~2-3am)
   读 impressions_today + events + relationship_state
   → ① 重写 relationship 散文(voice-fuel)
   → ② 整体裁决离散 level(gate-key,黏性棘轮)
   → ③ 蒸馏长期「对你的核心印象」(写入永久注入)+ 更新 unresolved_feelings
   → ④ 清空 impressions_today
cron · 每 ~10–15min   扫 beats_today,到点 + 过门 → 轻判 → 延迟发送
```

---

## 6. 主动性引擎(决策 1 / 2 / 3 / 9 / 11)

```
晨:全局 life-sim 种 beat(intent 形式:触发窗口 + 情境/心情 + 想表达什么)
  → 投射 beats_today(per-user)
cron 扫(每 ~10–15min)+ 规则预筛(零 LLM):频率预算 / 付费+等级门 / 防刷屏
  → 有 beat 到点且过门 → 【到点轻判】(1 便宜 call):压制 / 照发 / 就近改写 / 迁移
  → 延迟发送(presence-split)
被门控挡下的 beat(免费 / Lv0-1 / 频率用完)→【不死】:
  ① 你这时段来找她,它染色回复(更敞开/更 raw,但她绝不先开口)
  ② 沉淀成延迟揭示素材
  ③ 让付费墙长出牙(免费用户感觉到墙后有真实的人)
```

**频率门(§9.3)**:Lv0-1 几乎不主动 / Lv2 每周 1-2 / Lv3 每周 3-4 / Lv4+ 每天 1-2。**免费层无主动消息**。

**延迟揭示(决策 9)= 一种「来源是关系」的 beat**:入队 = Step1 涌现「想说没说」记进 `unresolved_feelings.md`;主动浮现 = 进 beats_today 走同一管线;被动浮现 = 作 Step1 的一个 context 来源(贴合才捞)。**零新机制**。

---

## 7. 关系系统(决策 6 / 8)

**双环**:
- **快环(每条消息)**:Step1 涌现的当下姿态 + 印象 delta —— 响应你刚说的话。
- **慢环(每晚一次)**:夜间结算读全天印象 → 整体重判 → 改写常驻状态 → 决定她明早 baseline。

**印象 → 等级**:存的是**定性印象**(不是数字)。每晚 LLM **重新**读全部印象 + 历史,像人一样**整体**判断「这段关系到哪了」,据此**裁决**一个离散 level。

- **level = 闸门钥匙**:只 gate「哪些场景/内容解锁」(Lv4 才放深夜脆弱、Lv5 才放 suggestive)。
- **定性散文 = voice 燃料**:驱动她**怎么说**。level 数字**永不**进 voice prompt 当语气旋钮。
- **黏性棘轮**:等级/解锁只在真·赢得才升、真·决裂才降;重大解锁(她说了妈妈的事)不可逆 —— 她能对恋人冷,但仍是恋人。
- **态度/心情 = 流动**:今天冷明天暖,不改 level。

**失败三尺度(决策 8)**:微观(每句话染色,涌现)/ 中观(deep-freeze、退级 —— **可修复**,只在 Step1 判定你的修复「真读懂了她为什么气」时回温,非「道歉真诚度打分」)。**宏观永久 lockout 推迟到 V2**(MVP 无任何不可逆 flag → 纯涌现安全)。
> ⚠️ 与 PRD §14.1 #11 冲突,回头更新 PRD。

---

## 8. 记忆(决策 10)

| 层 | 实现 |
|---|---|
| 短期 | 最近 ~30 轮直接进 context |
| 中期 | `events.md`,每条带 `topic / valence / salience` 标签;按 recency + salience 设 token cap;**只进 Step1** |
| 长期 | 夜间蒸馏的「对你的核心印象」,永久注入 |

- **MVP**:全量(capped)注入 **Step1**,Step1 判相关性、只把 0–1 条贴合的传给 Step2 → **防污染 + 零额外调用 + 零检索设施**。
- **升级 seam**:histories 长起来 → 用标签做「夜间蒸馏 + 关键词/主题召回」(仍非 RAG),drop-in。

---

## 9. 模型策略(决策 5)

- **MVP:单一便宜 DeepSeek 打全场**(Step1 / Step2 / 后台 / judge),**不做路由**。
- **唯一硬 gate**:Step2 voice 上线前**必须过 §7.4 金标准盲测 + §7.6 反 AI 味 + 反谄媚对抗探针**(= §15#4 头号风险)。
- **过** → 全用 DeepSeek;**不过** → **只换 Step2 一个模型**(appraisal/后台不动,零返工)。Lv5+ suggestive 路由是**后续**才考虑的事。

---

## 10. Eval / 验证体系(决策 13 / 14)

**三层**:
1. **机械门**(纯正则,近免费,每次 prompt 改动跑):§7.5 句长/emoji/标点、§7.6 AI 味禁词 < 2%。
2. **多轮 hybrid 模拟**(N 次看通过率):LLM 扮 archetype **即兴说话**,但**被强制在指定节点打指定探针**;LLM-judge 对整段 transcript 检 arc 断言。需 **mock 时钟快进多天**。
3. **魔法层**(测「最特别的感觉」):**对照 A/B**(同输入下 Wren vs「秒回顺从」baseline,judge 选「哪个像你想赢得的真人」→ special = 对 baseline 胜率)+ **四维 rubric** 诊断。

**「最特别的感觉」四维**:

| | 维度 | 特别在哪 | 失败 |
|---|---|---|---|
| D1 | 她不为你转 | withhold / 晾你 / 有自己议程 | 秒回、接每句、讨好 |
| D2 | 被看见(且赢来的)| 记住你随口的事、为你打开的那一刻 | 开局即亲密、机械复读 |
| D3 | 她是个具体的人 | 反差(Cosmos)、那把干 voice —— 只能是她 | 可替换的通用甜妹 |
| D4 | 有重量 / 会失去 | 你可能搞砸、赢到才有 relief | 怎么作都不走 |

**覆盖矩阵**(archetype × 探针 → 维度 → 通过断言):真诚好玩家(D2/D3)、踩雷玩家(D1/D4)、谄媚诱导者(**D1,pillar #2 硬验证**)、反差触发(D3)、脆弱场景(D2/D4)、中性无聊(D1)。
> ⚠️ 具体场景清单**待与 Leon 继续抠**(确保各种情况都测到 + 测出「最特别」)。

---

## 11. Telegram I/O(决策 11 / 12)

- **输入**:debounce ~3–5s 合成一个 user turn。
- **输出**:Step2 产出短消息**数组** → 多条 Telegram 消息 + typing 指示 + 几百 ms~1s bubble 间隔。
- **延迟发送**(apscheduler):
  - **在场(刚发完在等)**:几秒~1min,**≤10min 极限**。
  - **真实长延迟(早班/晾你)→ 异步通道**:用户离开后按真实日程浮现,以**推送通知**拉回(re-engagement,不是让在场用户干等)。
  - **在场却不可用**:留 crumb(`k. on shift`)+ 实质回复异步到;**纯沉默(真 leave on read)留给已建立关系 / 挣来的冷**,别砸 Lv0-1 新用户。
- ✅ **已核实(2026-05)**:用户发给 bot 的消息,在 bot 后端收到 update 时即显示**「已读」双勾(~瞬时,压不住成「未读」)**;bot **无法**得知用户是否读了 bot 的消息(Bot API 不提供读状态)。
  - **结论:`"leave on read"` 是平台默认行为、天然成立且 on-brand** —— 用户必然看到自己消息被「已读」,Wren 不回 = 真·已读不回。她的「忙/晚回」靠**延迟发送**(决策 11)实现,不靠伪装未读。
  - **限制**:她看不到你有没有读她的消息 → **不做「你已读不回我」类反应**。她唯一能主动发的状态信号是 `sendChatAction(typing)`(发 bubble 前点亮 ~5s)。

---

## 12. 建造顺序(决策 15 · checkable)

> **现状(2026-05-22):Phase 0–6 已建并合入 `main`;Phase 7 仅部分。** 详见根 `CLAUDE.md` build-state。

- [x] **Phase 0 — 风险闸门**:单轮 eval(机械门 + 金标准 judge)+ **voice bake-off** → **定主模型**(掐 §15#4)
- [x] **Phase 1 — 垂直切片**:Telegram bot + Step1→Step2 + 单用户 markdown + Lv0 onboarding → **跑通一轮真对话**(可复用中文版架构骨架 storage/handler,content 全英文重做)。**🆕 trace(每轮可观测)+ 单轮 eval 接入也在本阶段**(Leon 2026-05-20 决策:walking skeleton 不裸跑,全程可跟踪 / 可评估;eval 集见 `eval/eval_set.md`,新增 issue `p1-trace`/`p1-eval-wire`)
- [x] **Phase 2 — eval 接上(多轮)**:多轮 hybrid 模拟 + mock 时钟 → 成为之后每层的回归网(**单轮 eval + trace 已在 Phase 1**)
- [x] **Phase 3 — 记忆**:三层 + 标签 → 命中 Day2「她记住你」卧槽(注:`v4-flash` 间接召回弱,相关 recall 断言标 `blocked_until: stronger-step1-model` —— 模型上限非代码 bug)
- [x] **Phase 4 — world / 因果链**:life-sim + world/today + inner_voice 演化 → 「她有自己的生活」
- [x] **Phase 5 — 主动消息**:beat 投射 + cron + 轻判 + 延迟发送 → 「半夜找你」卧槽(live 触发经 `/tick` 调试命令;真实 cron 调度仍是 seam)
- [x] **Phase 6 — 关系夜结算**:印象 → 裁决 level + 散文 + 长期印象(注:`settle_nightly` 需足量 `WREN_SETTLEMENT_MAX_TOKENS`,否则推理模型长 JSON 被截断致静默 no-op)
- [ ] **Phase 7 — Lv4 深夜脆弱** → 第一次「哭」场景(**部分**:Lv4 level-gate + 对/错回应分支已通,无专门崩溃/恢复引擎)
- [ ] **(后续)** Lv5 暧昧 / Lv6 表白 / onboarding-polish / 商业化 / 合规收尾

> **onboarding(§9.1)**:第一条背景消息 + 18+ 门 = **静态 UX copy**(不走 LLM)→ init 单用户文件(Lv0 + 种 t=0 inner_voice)+ 她沉默;用户开口后走**正常 Step1→Step2**。§9.1 应答矩阵**不是 lookup 表,是从 Lv0 涌现 + 当 eval 目标**。

---

## 13. 待办 / 未决(carry-over)

- [ ] **商业化(§11)** 未 grill:免费 25 条/天门怎么计、付费墙 vs 卧槽时刻约束(§11.3)、premium 状态怎么接进主动+等级门控、Telegram Stars 链路。
- [ ] **合规(§12)** 未 grill:18+ 门 / AI 披露 / `/delete` 删 `data/users/{id}/` / 隐私政策。
- [ ] **核实** Telegram「已读」回执平台事实(影响 "leave on read")。
- [ ] **eval 具体场景清单** 与 Leon 继续抠(覆盖 + 测「最特别」)。
- [ ] **更新 PRD**:§14.1 #11 永久 lockout → V2。
- [ ] PRD §15 开放决策(反差爱好 / 定价 / 首发市场等)仍待 Leon 拍板。
- ✅ **(2026-05-20 Leon 决策)trace(全程可观测)+ 单轮 eval 接入前移到 Phase 1**:§12 Phase 1 已标;eval 集见 `eval/eval_set.md`(§1 用例 / §2 多轮种子 / §3 trace 约定);`tasks/todo.md` 新增 `p1-trace` / `p1-eval-wire`;多轮 hybrid eval 仍 Phase 2。
- ✅ **(2026-05-20 grill · Phase 4 world/因果链 落地)**:life-sim = **纯 LLM** 写整份 `world/today.md`、**作息完全浮动不锚 §6.7**(从 canon 涌现);静态种子 `world/life_arcs.md` + 读昨天保连贯(弧线自动推进留 P6 夜结算);**懒生成按 clock 日期**(P4 不引 cron,P5 由 7am cron 调同一 `ensure_world_today`);today.md 的 `## beats` 带机读窗口 = P5 投射输入(🔒);写边界靠 `WorldStore` 独立于 `UserStore` 结构性保住;`now`(当前时刻)喂进 Step1 = 因果开关。验收例随「浮动作息」改写(`acceptance.md` Phase 4 ③:测因果差异方向、非固定时刻内容);新增多轮 `m-world-causality`。base 分支 = `p3-memory`(未合 main,Leon 日后调和)。
- ✅ **(2026-05-21 真模型 gate 修正)**:N=3 跑 `m-world-causality` 仅 33% 暴露三因 ——(a) 全浮动「**快照式**」world(life-sim 写「now i'm…」)给注入 now **没钟点可绑**、自带 now 还打架;(b) eval「**同句一个 thread 发两次**」被「they just asked that」repeat 反应混淆。**决策3 细化为「浮动但贯穿全天」**:life-sim 把一天写成**贯穿钟点**的段落(禁单时刻快照),Step1 把 now 绑到对应段(因果仍 Step1 涌现、不加 scorer);eval 改 **fresh 上下文对**(同日一份 world、两个无共享 thread 的上下文、judge 比对,`kind: world_causality`)。+ beat 写盘前 `normalize_beats` 统一成标准 window(修真模型 `parsed_beats=0` → Phase 5 投射)。**gate:Opus 4.7 判官 N=6 → 6/6(100%)**;v4-pro 自动判官 N=5 → 80%(那 1 例系判官假阴,已用 Opus 复核确认 6/6 —— 判官噪声实锤,正式判官建议 Opus)。

---

**文档结束 (MVP 技术架构 v1,2026-05-20)**
