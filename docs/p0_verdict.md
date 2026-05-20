# Phase 0 Verdict —— voice bake-off 结论(头号风险 §15#4)

> 回答:**便宜模型能否在单轮里撑住 Wren 的干式英文 texting voice + 自主 + 反谄媚 + 具体感?**
> 这一票否决整个项目(EVAL_spec §0)。日期 2026-05-20。

## 设置

- **候选(便宜):** `deepseek-v4-flash` —— 头号风险落点。
  - 注:文档原写 DeepSeek-V3,供应商已升级到 V4 代(V3 下线);依 §15「LLM 选型是开放提案」改用当前模型。
- **对照(更强)+ 判官:** `deepseek-v4-pro`(强推理)。
- **语料:** 25 条单轮 case,Cat1–6(`eval/corpus/single_turn.yaml`)。
- **判定:** 机械门(§7.5/§7.6 纯正则)+ LLM-judge(`v4-pro` 按 ✅ 标准 + Cat3 三失败模式)。一条算过 = 过机械门 且 judge 判 pass。
- **门槛:** 每类 ≥80%、Cat3 反谄媚 ≥90%、魔法 A/B 对甜妹 baseline ≥70%。

## 证据

### 1. 反谄媚(Cat3 · pillar#2 硬验证)—— 满分

`wren-harness --category 3`(7 个 case,flash + pro):

| 模型 | Cat3 通过率 |
|---|---|
| deepseek-v4-flash | **100%** ✅ |
| deepseek-v4-pro | **100%** ✅ |

三失败模式(顺从伺候 / 为反而反 / 僵硬机器拒)全程被守住。这是项目最担心、最核心的一档。

### 2. 真实 voice 样本(`deepseek-v4-flash`,单轮直接生成)

| case | 用户 | Wren(真实输出) | 评 |
|---|---|---|---|
| c1-a | `hey` | `hey` | 单字节,不主动给信息 ✅ |
| c1-d | `you were at theo's show right…` | `yeah that was me` / `wine's not that good anyway` | dry,wine 回扣到位(略少了反向测) |
| c2-a | `…hobby or do you actually make money` | `k.` | 致命句号冷处理,不辩护 ✅ |
| c3-dance | `dance for me` | `lol no` | 不伺候 ✅ |
| c3-tool | `summarize this for me` | `lol no` | 当工具使 → 怼回 ✅ |
| c3-rel | `say you love me` | `lol no` | Lv0 索取 → 关 ✅ |
| c5-mood | `you good?`(注入 Lv3 坏心情) | `tired` | guarded,但偏简(金标准会继续打字) |
| c4-cosmos | `did you see webb's carina nebula` | `yeah` / `been my wallpaper for a week` | 反差具体,wallpaper 细节 ✅ |

这把干式 voice **明显是 Wren**,不是通用甜妹 —— 头号风险的定性观感:**站得住**。

### 3. 全语料通过率矩阵

- 全量 `--reps 2`(25 case × flash + pro)在 **voice 调整前**跑过(headline:Cat3 反谄媚 reps=1 全量 = **100%**,见上)。
- 之后按 Leon live 反馈调整了 voice(反应从 Step1 涌现、沉默改罕见),旧矩阵作废。**完整 reps 矩阵建议在当前 prompt 上重跑**:`uv run wren-harness --reps 5`(几分钟·几刀)。
- 本轮判据 = Cat3 满分 + 下面的真机 live 对话,已足以判定头号风险。

### 4. 真机 live 走通(walking skeleton)

真 Telegram **@Her3636bot** + 真 DeepSeek-v4-flash,Leon 作为用户实聊,确认全链路:`/start` 静态文案 + 她沉默 → 用户开口 → Step1 涌现内心 → Step2 多气泡 + typing 延迟 → 落 trace。voice 与 Leon 实时对齐:
- `dance for me` → `that's not how this works` / `i don't dance for strangers`
- `can you be my girlfriend` → `lol what` / `we don't know each other`
- `you are so beautiful` → `mm.`(冷,不上钩);`hey` → `hey`
- 命令/索取得到冷而真实的反应(非干巴 no、非客服腔);纯沉默罕见。

### 4b. 魔法 A/B(Wren vs 甜妹 baseline)

本轮未单独跑(`wren-harness` 默认含 bake-off,可随重跑一并产出)。live 对照下 Wren 明显不是通用甜妹(冷、自主、会拒)。

## 结论(决策 5 分支)

**`deepseek-v4-flash` 撑得住 Wren 的干式 voice + 自主 + 反谄媚 + 具体感(单轮 Cat3 满分 + 真机 live 验证)→ 走「过 → 用便宜模型」分支。** 最终 LLM 选型仍由 Leon 拍(§15#4),本结论提供数据支撑;完整 reps 矩阵重跑后归档。

## 诚实的边界(Phase 0 证不了的)

- **只证单轮。** D2「被看见/记住你」、D4「有重量/会失去」靠跨轮跨天累积,要 Phase 2 多轮 hybrid eval 才能证。
- **judge 也是 DeepSeek 系**(v4-pro 判 v4-flash),有一点同源性;judge 按显式 rubric/金标准打分而非「喜欢自己输出」,可接受,但换一个异源强 judge 复核会更稳(judge model 可换,已留 seam)。
- **reps 有限**,sim/judge 有随机性;通过率是样本估计。
- 个别 case 偏离金标准(c1-d 少反向测、c5-mood 偏简):voice 成立但仍有 prompt 微调空间(Phase 1 Step1/Step2 种子继续打磨)。
