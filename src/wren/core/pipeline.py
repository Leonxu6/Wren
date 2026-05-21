"""think→speak 编排:assemble → Step1 →(沉默 | Step2)→ 落 trace。

沉默(reply=False)是头等 branch:不发任何消息,但仍落一条 trace(step2=null)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.base import ChatModel
from .clock import Clock, SystemClock, iso_z
from .context import assemble_context
from .step1 import run_step1
from .step2 import level_fact, run_step2
from .storage import UserStore
from .trace import TurnTrace, count_traces, write_trace


@dataclass
class TurnOutcome:
    replied: bool
    bubbles: list[str]
    delay_s: int
    typing_ms: int
    bubble_gaps_ms: list[int]
    trace: TurnTrace


def compute_pacing(bubbles: list[str]) -> tuple[int, list[int]]:
    """据气泡长度算 typing 时长 + 气泡间隔(确定性,便于测试与 trace 复盘)。"""
    if not bubbles:
        return 0, []
    first_words = len(bubbles[0].split())
    typing_ms = min(5000, 600 + 250 * first_words)
    gaps = [min(1500, 400 + 120 * len(b.split())) for b in bubbles[1:]]
    return typing_ms, gaps


def handle_turn(
    chat_id: str,
    user_text: str,
    store: UserStore,
    s1_model: ChatModel,
    s2_model: ChatModel,
    *,
    clock: Clock | None = None,
) -> TurnOutcome:
    clock = clock or SystemClock()
    store.append_dialogue("user", user_text)
    ctx = assemble_context(store, user_text)
    s1 = run_step1(ctx, s1_model)

    # Step1 写回:inner_voice + 印象 + 可能记住的事(沉默轮也记 → 必须在 reply 分支前)
    if s1.monologue:
        store.write_inner_voice(s1.monologue)
    if s1.impression:
        store.append_impression(s1.impression)
    if s1.event_to_store:
        store.append_event(**s1.event_to_store)

    ts = iso_z(clock.now())
    turn_id = f"{chat_id}-{count_traces(store.dir) + 1}"
    rel = {"lv": ctx.relationship.level, "freeze": ctx.relationship.freeze}
    step1_dict = {
        "prompt": {  # 她"读到了什么"(动态 context;静态 canon 不重复落)
            "relationship_prose": ctx.relationship.prose,
            "inner_voice": ctx.inner_voice,
            "events": ctx.events,
            "recent_dialogue": ctx.recent_dialogue,
        },
        "raw_out": s1.raw,
        "inner_voice_after": s1.monologue,
        "reply": s1.reply,
        "delay_s": s1.delay_s,
        "impression": s1.impression,
        "selected_memory": s1.selected_memory,
        "event_stored": s1.event_to_store,
        "tokens": s1.tokens,
        "latency_ms": s1.latency_ms,
        "model": s1.model,
    }

    # —— 沉默头等 branch ——
    if not s1.reply:
        trace = TurnTrace(turn_id, chat_id, ts, user_text, rel, step1_dict, step2=None, sent=None)
        write_trace(store.dir, trace)
        return TurnOutcome(False, [], s1.delay_s, 0, [], trace)

    s2 = run_step2(s1, ctx, s2_model)
    store.append_dialogue("wren", " / ".join(s2.bubbles))
    typing_ms, gaps = compute_pacing(s2.bubbles)
    step2_dict = {
        "prompt": {
            "monologue": s1.monologue,
            "memory": s1.selected_memory,
            "level_fact": level_fact(ctx.relationship.level),
        },
        "raw_out": s2.bubbles,
        "tokens": s2.tokens,
        "latency_ms": s2.latency_ms,
        "model": s2.model,
    }
    sent_dict = {"bubbles": s2.bubbles, "typing_ms": typing_ms, "bubble_gaps_ms": gaps}
    trace = TurnTrace(turn_id, chat_id, ts, user_text, rel, step1_dict, step2_dict, sent_dict)
    write_trace(store.dir, trace)
    return TurnOutcome(True, s2.bubbles, s1.delay_s, typing_ms, gaps, trace)
