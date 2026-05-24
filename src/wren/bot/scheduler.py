"""Phase 6:每晚 ~2:30 ET 对所有活跃用户跑夜结算(后台调度器,复用 PTB JobQueue)。

ARCHITECTURE §5 日循环的「per-user · 夜」那一格。settle_nightly 本身 clock 可注入 + 同步,
这里用 PTB 的 run_daily 触发 + asyncio.to_thread 包同步调用,不阻塞 event loop。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .. import config
from ..core.clock import Clock, runtime_clock
from ..core.life_sim import ensure_world_today
from ..core.pipeline import handle_proactive_turn
from ..core.proactive import beat_fingerprint, scan_for_due_beat
from ..core.settlement import settle_nightly
from ..core.storage import UserStore
from ..core.trace import read_traces
from ..core.world import WorldStore
from ..model.base import ChatModel
from ..model.registry import get_model
from .handlers import _chat_lock, _log_turn  # 复用 on_message 同一把 per-chat 锁,不与之竞态
from .limits import turn_blocked
from .sender import send_bubbles

_ET = ZoneInfo("America/New_York")
_SETTLE_TIME = time(hour=2, minute=30, tzinfo=_ET)


def active_chat_ids() -> list[str]:
    """data/users/ 下的所有用户目录名。"""
    root = config.data_root()
    if not root.exists():
        return []
    return [p.name for p in sorted(root.iterdir()) if p.is_dir()]


async def _settle_one_locked(cid: int, chat_id: str, model: ChatModel) -> int:
    """单个用户的 settlement:在 `_chat_lock(cid)` 内跑,与 on_message / proactive 串行(#12)。

    若 live turn 正在同 chat 处理(持有同一把锁),settlement 会等到 lock 释放才进;
    避免读 impressions 后 → live turn 追加新 impression → settle clear 把新的也清掉的竞态。

    返回 1 if 真跑了 settle,0 if 不存在/未到结算窗口/失败。"""
    try:
        store = UserStore(chat_id)
        if not store.exists():
            return 0
        async with _chat_lock(cid):
            outcome = await asyncio.to_thread(settle_nightly, store, model)
    except Exception as e:  # noqa: BLE001 — 批处理鲁棒性优先(单用户失败不拖垮整批)
        print(f"[settle] {chat_id} 失败:{e}", flush=True)
        return 0
    if outcome.ran:
        print(
            f"[settle] {chat_id}: lv {outcome.before.level}→{outcome.after.level} · "
            f"freeze {outcome.before.freeze}→{outcome.after.freeze}",
            flush=True,
        )
        return 1
    return 0


async def settle_all(_context: Any = None) -> int:
    """对所有活跃用户跑一次结算;单个用户失败不拖垮整批。返回实际结算的人数。

    每个用户走 `_chat_lock(cid)`(与 on_message / proactive 共享同一把锁),避免与
    live turn 在结算窗口附近争 impressions(#12)。non-numeric 目录跳过——锁 key 是 int。"""
    model = get_model("settlement")
    ran = 0
    for chat_id in active_chat_ids():
        try:
            cid = int(chat_id)
        except ValueError:
            continue  # 与 proactive_tick 一致:只对数字 chat_id 上锁
        ran += await _settle_one_locked(cid, chat_id, model)
    return ran


def register_nightly(app: Any) -> bool:
    """把夜结算挂到 app 的 JobQueue;无 JobQueue(没装 [job-queue])则告警跳过。返回是否挂上。"""
    jq = getattr(app, "job_queue", None)
    if jq is None:
        print("⚠️  无 JobQueue —— 装 python-telegram-bot[job-queue] 才有夜结算。", flush=True)
        return False
    jq.run_daily(settle_all, time=_SETTLE_TIME, name="nightly-settlement")
    print(f"✓ 夜结算已挂:每日 {_SETTLE_TIME.strftime('%H:%M')} ET", flush=True)
    return True


# ---- Phase 5:主动消息 live scheduler(W2;P5 缺的就是这个触发器)----
_PROACTIVE_INTERVAL_S = 600.0  # ~10min 扫一次
_PROACTIVE_FIRST_S = 60.0  # 启动 1min 后首次
_RECENCY_SKIP_S = 25 * 60.0  # 最近 25min 有过 trace 的用户:对话中,主动消息先让路(机械计时,非分类器)


def _recently_active(store: UserStore, now: datetime, window_s: float = _RECENCY_SKIP_S) -> bool:
    """最近一条 trace 在 window 内 → 视作对话中。纯计时护栏(§0:不是分类器)。"""
    traces = read_traces(store.dir)
    if not traces:
        return False
    try:
        last = datetime.fromisoformat(str(traces[-1].get("ts", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now - last).total_seconds() < window_s


async def proactive_tick(
    context: Any,
    *,
    clock: Clock | None = None,
    s1_model: ChatModel | None = None,
    s2_model: ChatModel | None = None,
    world_model: ChatModel | None = None,
) -> int:
    """~10min 扫所有活跃用户:到点且过门的 beat → 轻判 →(发 | 压制)。返回实际发出的人数。

    P5 缺的「live 触发器」。判断/渲染早建好(handle_proactive_turn);这里只管定时驱动 + 新近度护栏
    (别在用户对话中插嘴)+ 复用同一把 per-chat 锁(气泡不交错)。models/clock 可注入(测试确定性)。
    """
    clk = clock or runtime_clock()
    now = clk.now()
    s1 = s1_model or get_model("step1")
    s2 = s2_model or get_model("step2")
    primary = world_model or get_model("primary")
    await asyncio.to_thread(ensure_world_today, clk, WorldStore(), primary)
    world = WorldStore().read_today()
    today = WorldStore().read_today_struct()
    beats = today.beats if today else []
    if not beats:
        return 0

    jq = getattr(context, "job_queue", None)
    sent = 0
    for chat_id in active_chat_ids():
        try:
            cid = int(chat_id)
        except ValueError:
            continue  # 主动消息只发给真实数字 chat_id
        try:
            store = UserStore(chat_id)
            if not store.exists():
                continue
            # 护栏 1(pre-lock 快筛):用户正在对话 / 最近活跃 → 跳过整个 chat,
            # 省下进 lock + 重新 read store 的开销
            if jq is not None and jq.get_jobs_by_name(f"debounce-{chat_id}"):
                continue
            if _recently_active(store, now):
                continue
            level = store.read_relationship().level
            decision = scan_for_due_beat(
                now, beats, level, store.read_proactive_state(), tier=store.read_tier()
            )
            beat = decision.beat
            if beat is None:
                continue
            # 护栏 2(inside-lock 再确认,#49):pre-lock 检查与 lock 获取之间,
            # 若 reactive turn 抢先持锁 + 触新 debounce job + 写 trace → 此时
            # **同 chat 实际正在对话**,proactive 还按 stale 状态发就是"插嘴"。
            # 进锁后重新 read store + jq,任一新护栏 fire → 退出,不发不 mark/不 bump cap。
            async with _chat_lock(cid):
                if jq is not None and jq.get_jobs_by_name(f"debounce-{chat_id}"):
                    continue  # reactive turn 刚进 debounce → 让路
                fresh_now = clk.now()
                if _recently_active(store, fresh_now):
                    continue  # reactive turn 刚 flush 写了 trace → 让路
                # 重读 proactive_state + relationship + 重判 due beat(都可能在 gap 中变)
                fresh_level = store.read_relationship().level
                fresh_decision = scan_for_due_beat(
                    fresh_now, beats, fresh_level,
                    store.read_proactive_state(), tier=store.read_tier(),
                )
                if fresh_decision.beat is None:
                    continue  # gap 中 beat 已被别的路径 mark 或 budget 用尽
                # cost cap(#49 reviewer 指出):必须在所有 inside-lock skip 路径**之后**才 bump,
                # 否则 race-skip 也会消耗每日 cap,虽然没发气泡/没写 trace。
                if turn_blocked():
                    break
                beat = fresh_decision.beat
                outcome = await asyncio.to_thread(
                    handle_proactive_turn, chat_id, beat, store, s1, s2, clock=clk, world=world
                )
                store.mark_considered(fresh_now, beat_fingerprint(beat))
                _log_turn(cid, f"[proactive] {beat.intent}", outcome)
                if outcome.replied and outcome.bubbles:
                    store.bump_proactive_count(fresh_now)
                    await send_bubbles(
                        context.bot, cid, outcome.bubbles, outcome.typing_ms, outcome.bubble_gaps_ms
                    )
                    sent += 1
        except Exception as e:  # noqa: BLE001 — 批处理鲁棒性优先(单用户失败不拖垮整批)
            print(f"[proactive] {chat_id} 失败:{e}", flush=True)
            continue
    return sent


def register_proactive(app: Any) -> bool:
    """把主动消息扫描挂到 JobQueue(run_repeating ~10min)。无 JobQueue 则告警跳过。"""
    jq = getattr(app, "job_queue", None)
    if jq is None:
        print("⚠️  无 JobQueue —— 装 python-telegram-bot[job-queue] 才有主动消息调度。", flush=True)
        return False
    jq.run_repeating(
        proactive_tick, interval=_PROACTIVE_INTERVAL_S, first=_PROACTIVE_FIRST_S, name="proactive-scan"
    )
    print(f"✓ 主动消息调度已挂:每 {int(_PROACTIVE_INTERVAL_S / 60)}min 扫一次", flush=True)
    return True
