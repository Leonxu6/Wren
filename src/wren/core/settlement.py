"""Phase 6 夜结算编排:per-user 每晚整体裁决这段关系。

读 relationship + 今日印象 + events + 长期印象 + 未了情绪 → settlement 模型整体裁决
→ 写 relationship(level/freeze/散文)+ 长期印象 + 未了情绪 → 清空今日印象 → 落 settlement trace。
与 `pipeline.handle_turn` 并列;clock 可注入(SystemClock 生产 / MockClock eval)。

红线:这是关系**唯一**改 level/freeze 的地方;不积分(整体裁决,§0①);用户线只写自己目录。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..model.base import ChatModel
from ..prompts.settlement import build_settlement_messages, parse_settlement
from .clock import Clock, SystemClock, iso_z
from .storage import Relationship, UserStore
from .trace import SettlementTrace, count_settlements, write_settlement_trace


@dataclass
class SettlementOutcome:
    ran: bool  # False = 没今日印象可结算,跳过(关系态原样保留)
    before: Relationship
    after: Relationship
    impressions: list[str]  # 本次消费的今日印象
    trace: SettlementTrace | None


def settle_nightly(
    store: UserStore,
    settle_model: ChatModel,
    *,
    clock: Clock | None = None,
) -> SettlementOutcome:
    clock = clock or SystemClock()
    before = store.read_relationship()
    impressions = store.read_impressions()

    # 没有今日印象 → 她今天没和你互动,没东西可结算 → 跳过,关系态不动。
    if not impressions:
        return SettlementOutcome(False, before, before, [], None)

    core_before = store.read_core_impression()
    unresolved_before = store.read_unresolved()

    msgs = build_settlement_messages(
        level=before.level,
        prose=before.prose,
        impressions=impressions,
        events=store.read_events(),
        core_impression=core_before,
        unresolved=unresolved_before,
        recent_dialogue=store.read_recent_dialogue(),
    )
    out = settle_model.complete(
        msgs, temperature=0.7, max_tokens=config.settlement_max_tokens(), response_format="json"
    )
    parsed = parse_settlement(out.text)

    # 缺字段 / 解析失败 → 回退旧值(防一次模型抽风把关系清零)。
    after = Relationship(
        level=parsed["level"] if parsed["level"] is not None else before.level,
        prose=parsed["prose"] or before.prose,
        freeze=parsed["freeze"] if parsed["freeze"] is not None else before.freeze,
    )
    new_core = parsed["core"] if parsed["core"] is not None else core_before
    new_unresolved = (
        parsed["unresolved"] if parsed["unresolved"] is not None else unresolved_before
    )

    store.write_relationship(after)
    store.write_core_impression(new_core)
    store.write_unresolved(new_unresolved)
    store.clear_impressions()

    trace = SettlementTrace(
        settlement_id=f"{store.chat_id}-settle-{count_settlements(store.dir) + 1}",
        chat_id=store.chat_id,
        ts=iso_z(clock.now()),
        before={"lv": before.level, "freeze": before.freeze},
        after={"lv": after.level, "freeze": after.freeze},
        impressions=impressions,
        judge={
            "raw_out": out.text,
            "model": out.model,
            "tokens": out.completion_tokens,
            "latency_ms": out.latency_ms,
            "core": new_core,
            "unresolved": new_unresolved,
        },
    )
    write_settlement_trace(store.dir, trace)
    return SettlementOutcome(True, before, after, impressions, trace)
