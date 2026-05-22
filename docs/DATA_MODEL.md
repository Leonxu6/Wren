# 数据模型(per-user 隔离 · 真相源)

**一个 `chat_id` = 一段持续关系 = 一条完整、隔离、可下钻的记录。** 真相源是 per-user markdown +
两条 JSONL;分析层是单独的 DuckDB(见 [监测](#监测-duckdb-分析层),内容不出机器)。

## 写边界铁律(D1.3)
- 用户线**只写** `data/users/{chat_id}/`(`UserStore` 类里根本没有写 `world/`/`canon/` 的方法)。
- `world/` 是「一个 Wren 一条命」的**共享一份**,**唯一**能写它的是 `WorldStore`;并发触发由
  `life_sim.ensure_world_today` 的单飞锁保证同日只生成一次(D1.3)。
- 所有「整篇覆盖」写都走 `core/atomicio.atomic_write_text`(temp→fsync→`os.replace`):崩在中途
  不留半截、不损坏正本(D1.2)。JSONL 追加走单次整行 write,读侧 `_read_jsonl` 跳坏行(双保险)。

## per-user 目录 `data/users/{chat_id}/`
| 文件 | 内容 | 写者 | 读者 |
|---|---|---|---|
| `relationship_state.md` | 离散 level(Lv0-6,gate-key)+ 散文 + freeze;**绝不存积分** | init / 夜结算 / `/setlevel`(owner) | 每轮 Step1、Step2 level_fact |
| `inner_voice.md` | 当前内心独白(每轮 Step1 覆盖) | 每轮 Step1 | 下一轮 Step1 |
| `conversation.md` | 追加式对话历史(`role: text`) | 每轮(user + wren) | Step1/Step2 近窗 |
| `events.md` | 中期记忆,每条 `- [topic\|valence\|salience] text` | Step1 涌现写 | 注入 Step1 召回(**只进 Step1,反污染**) |
| `impressions_today.md` | 当日印象 delta(`- text`) | 每轮 Step1 | 夜结算消费后清空 |
| `core_impression.md` | 夜结算蒸馏的长期核心印象 | 夜结算 | 永久注入 Step1 |
| `unresolved_feelings.md` | 她憋着没说的(`- text`) | 夜结算 | 染色 Step1 / 供 P5 |
| `proactive_state.md` | 主动消息预算计数器(周/日 + 当日已判 beat 指纹) | P5 过门 | P5 过门 |
| `source.md` | 深链来源归因(首次 `/start` 写,幂等不覆盖;W3) | `/start` | 监测归因 |
| `trace.jsonl` | 每轮一条结构化 trace(见下) | 每轮 | 复盘 / eval 回放 / 监测 ingest |
| `settlement.jsonl` | 每晚一条夜结算 trace | 夜结算 | 监测 ingest |

## `trace.jsonl`(每轮一行;`core/trace.py:TurnTrace`)
`turn_id`(`{chat_id}-{n}`)、`chat_id`、`ts`(ISO-8601 Z UTC)、`user_turn`(主动轮为 null)、
`relationship{lv,freeze}`、`step1{prompt{...}, raw_out, inner_voice_after, reply, delay_s,
impression, selected_memory, event_stored, tokens, latency_ms, model}`、`step2|null`(null=沉默)、
`sent|null`(`{bubbles, typing_ms, bubble_gaps_ms}`)、`eval|null`(离线回填 seam)、
`kind`(`reactive`|`proactive`)。
⚠️ `tokens` 只记 completion(成本估算为下界);trace 无 error 字段。

## `settlement.jsonl`(每晚一行;`SettlementTrace`)
`settlement_id`(`{chat_id}-settle-{n}`)、`chat_id`、`ts`、`before{lv,freeze}`、`after{lv,freeze}`、
`impressions[]`(本次消费的今日印象)、`judge{model, raw_out, tokens, latency_ms, …}`。

## `world/`(共享;`config.world_root()`)
`today.md`(今日 life skeleton:prose + `## beats` 机读窗口,喂 Step1 + P5 扫描)、
`yesterday.md`(跨天连贯)、`life_arcs.md`(版本化静态种子,不忽略)。`today.md`/`yesterday.md` gitignored。

## /delete(D1.4)
`UserStore.delete()` 清整个 `data/users/{chat_id}/`(含两条 jsonl);监测 DB 的对应行由
`wren-metrics forget`(W6)按 `chat_hash` 删除。

## 监测 DuckDB 分析层
只读消费 trace/settlement → `data/metrics.duckdb`(只存指标+维度,**绝不存原文**;`chat_id` 哈希存)。
schema 与查询见 W6 / `src/wren/ops/`。
