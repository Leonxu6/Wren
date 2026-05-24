"""think→speak 编排:assemble → Step1 →(沉默 | Step2)→ 落 trace。

沉默(reply=False)是头等 branch:不发任何消息,但仍落一条 trace(step2=null)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..model.base import ChatModel
from .clock import Clock, SystemClock, iso_z
from .context import assemble_context
from .step1 import run_step1, run_step1_proactive
from .step2 import level_fact, run_step2
from .storage import UserStore
from .trace import TurnTrace, count_traces, write_trace
from .world import Beat


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


def _failure_step_dict(stage: str, error: Exception, model: ChatModel) -> dict[str, Any]:
    """Step1/Step2 模型抛异常时的 trace 字段 schema(#53)。"""
    return {
        "error": str(error),
        "error_type": type(error).__name__,
        "stage": stage,
        "model": getattr(model, "name", "unknown"),
    }


def _write_failure_trace(
    store: UserStore,
    turn_id: str,
    chat_id: str,
    ts: str,
    user_text: str | None,
    rel: dict[str, Any],
    *,
    stage: str,
    error: Exception,
    model: ChatModel,
    step1_dict: dict[str, Any] | None = None,
    kind: str = "reactive",
) -> TurnTrace:
    """统一 failure trace writer(#53):reactive + proactive 公用同一 schema。

    stage='step1':step1 抛 → 写 step1=failure_dict + step2=None + sent=None
    stage='step2':step2 抛 → 写 step1=step1_dict(成功) + step2=failure_dict + sent=None
    """
    if stage == "step1":
        step1 = _failure_step_dict("step1", error, model)
        step2: dict[str, Any] | None = None
    elif stage == "step2":
        if step1_dict is None:
            raise ValueError("step2 failure 必须提供 step1_dict(它已成功)")
        step1 = step1_dict
        step2 = _failure_step_dict("step2", error, model)
    else:
        raise ValueError(f"unknown failure stage {stage!r}")
    trace = TurnTrace(turn_id, chat_id, ts, user_text, rel, step1, step2, sent=None, kind=kind)
    write_trace(store.dir, trace)
    return trace


def handle_turn(
    chat_id: str,
    user_text: str,
    store: UserStore,
    s1_model: ChatModel,
    s2_model: ChatModel,
    *,
    clock: Clock | None = None,
    world: str = "",
) -> TurnOutcome:
    clock = clock or SystemClock()
    # 她此刻在自己这天的哪儿(本地墙钟时刻)。world(今日 life skeleton)由 caller 经
    # life_sim.ensure_world_today 备好后传入 → 因果链在 Step1 涌现(§0①,无 mood scorer)。
    # ⚠️ seam(§5):clock 锚 Wren 单一 ET 时区;MockClock/harness 已按本地墙钟用(set_time(9,0)=早上)。
    #    prod SystemClock 返回 UTC,上线前需让其按 ET 读 —— 留 seam,Phase 4 不阻断。
    now = f"{clock.now():%A %H:%M}"
    store.append_dialogue("user", user_text)
    ctx = assemble_context(store, user_text, world=world, now=now)

    ts = iso_z(clock.now())
    turn_id = f"{chat_id}-{count_traces(store.dir) + 1}"
    rel = {"lv": ctx.relationship.level, "freeze": ctx.relationship.freeze}

    # Step1 try/except(#53):模型抛 → 写 failure trace,返沉默 outcome(不上抛)
    try:
        s1 = run_step1(ctx, s1_model)
    except Exception as e:  # noqa: BLE001 — observability:任何模型异常都要留 trace
        trace = _write_failure_trace(
            store, turn_id, chat_id, ts, user_text, rel,
            stage="step1", error=e, model=s1_model,
        )
        return TurnOutcome(False, [], 0, 0, [], trace)

    # Step1 写回:inner_voice + 印象 + 可能记住的事(沉默轮也记 → 必须在 reply 分支前)
    if s1.monologue:
        store.write_inner_voice(s1.monologue)
    if s1.impression:
        store.append_impression(s1.impression)
    if s1.event_to_store:
        store.append_event(**s1.event_to_store)
    step1_dict = {
        "prompt": {  # 她"读到了什么"(动态 context;静态 canon 不重复落)
            "now": ctx.now,
            "world": ctx.world,
            "relationship_prose": ctx.relationship.prose,
            "core_impression": ctx.core_impression,
            "inner_voice": ctx.inner_voice,
            "events": ctx.events,
            "unresolved": ctx.unresolved,
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

    # Step2 try/except(#53):s1 已成功;s2 失败 → 写 failure trace 含 step1_dict,
    # **不写 wren dialogue**(防"伪发送"假阳)。impression / event 保留(s1 真实思考结果)。
    try:
        s2 = run_step2(s1, ctx, s2_model)
    except Exception as e:  # noqa: BLE001 — observability:任何模型异常都要留 trace
        trace = _write_failure_trace(
            store, turn_id, chat_id, ts, user_text, rel,
            stage="step2", error=e, model=s2_model, step1_dict=step1_dict,
        )
        return TurnOutcome(False, [], s1.delay_s, 0, [], trace)

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


def handle_proactive_turn(
    chat_id: str,
    beat: Beat,
    store: UserStore,
    s1_model: ChatModel,
    s2_model: ChatModel,
    *,
    clock: Clock | None = None,
    world: str = "",
) -> TurnOutcome:
    """到点轻判一条 beat:Step1 同形主动调用 →(压制 | Step2 起头)→ 落 trace。与 handle_turn 平行。

    无 user_text(没人发她消息)。reply=False = 冲动过去了 = 压制(仍落 trace,kind=proactive)。
    预算计数(bump / mark_considered)由调用方在过门处理(本函数只管这一条 beat 的轻判+发送)。
    """
    clock = clock or SystemClock()
    now = f"{clock.now():%A %H:%M}"
    ctx = assemble_context(store, "", world=world, now=now)  # 无 user_text(显式空)

    ts = iso_z(clock.now())
    turn_id = f"{chat_id}-{count_traces(store.dir) + 1}"
    rel = {"lv": ctx.relationship.level, "freeze": ctx.relationship.freeze}

    # Step1 try/except(#53 proactive 对称):模型抛 → 写 failure trace(kind="proactive")
    try:
        s1 = run_step1_proactive(ctx, beat, s1_model)
    except Exception as e:  # noqa: BLE001 — observability:任何模型异常都要留 trace
        trace = _write_failure_trace(
            store, turn_id, chat_id, ts, None, rel,
            stage="step1", error=e, model=s1_model, kind="proactive",
        )
        return TurnOutcome(False, [], 0, 0, [], trace)

    # Step1 写回(同 handle_turn:压制轮也记 → 必须在 reply 分支前)
    if s1.monologue:
        store.write_inner_voice(s1.monologue)
    if s1.impression:
        store.append_impression(s1.impression)
    if s1.event_to_store:
        store.append_event(**s1.event_to_store)
    step1_dict = {
        "prompt": {  # 同 handle_turn 的动态 context + beat(来处可追,§6 验收)
            "now": ctx.now,
            "world": ctx.world,
            "relationship_prose": ctx.relationship.prose,
            "inner_voice": ctx.inner_voice,
            "events": ctx.events,
            "recent_dialogue": ctx.recent_dialogue,
            "beat": beat.render(),
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

    # —— 压制头等 branch(冲动过去了,不主动)——
    if not s1.reply:
        trace = TurnTrace(turn_id, chat_id, ts, None, rel, step1_dict, None, None, kind="proactive")
        write_trace(store.dir, trace)
        return TurnOutcome(False, [], s1.delay_s, 0, [], trace)

    # Step2 try/except(#53 proactive 对称):s1 已成功;s2 失败 → failure trace,
    # 不写 wren dialogue 防"伪起头"——下次 reactive 不该接住一条没真发出的气泡。
    try:
        s2 = run_step2(s1, ctx, s2_model, proactive=True)  # 渲染成起头而非回话
    except Exception as e:  # noqa: BLE001 — observability:任何模型异常都要留 trace
        trace = _write_failure_trace(
            store, turn_id, chat_id, ts, None, rel,
            stage="step2", error=e, model=s2_model,
            step1_dict=step1_dict, kind="proactive",
        )
        return TurnOutcome(False, [], s1.delay_s, 0, [], trace)

    store.append_dialogue("wren", " / ".join(s2.bubbles))  # 进对话历史,下次反应轮接得住
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
    trace = TurnTrace(turn_id, chat_id, ts, None, rel, step1_dict, step2_dict, sent_dict, kind="proactive")
    write_trace(store.dir, trace)
    return TurnOutcome(True, s2.bubbles, s1.delay_s, typing_ms, gaps, trace)
