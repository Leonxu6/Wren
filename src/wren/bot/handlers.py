"""Telegram handlers:/start(静态,不走 LLM)/help /delete + on_message(debounce→pipeline→多气泡)。

红线:onboarding 静态、她不主动破冰;应答从 Lv0 经真实 Step1→Step2 涌现(非 lookup 表)。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from typing import Any

from .. import config
from ..core.clock import Clock, runtime_clock
from ..core.life_sim import ensure_world_today
from ..core.pipeline import (
    TurnOutcome,
    handle_proactive_turn,
    handle_turn,
    persist_delivered_reply,
    write_delivery_failure_trace,
)
from ..core.proactive import beat_fingerprint, scan_for_due_beat
from ..core.storage import Relationship, UserStore
from ..core.world import Beat, WorldStore
from ..model.base import ChatModel
from ..model.registry import get_model
from ..onboarding import static_copy
from .limits import model_call_exhausted, rate_limited
from .sender import Sleeper, send_bubbles


async def _handle_and_send(
    chat_id: int,
    user_text: str,
    bot: Any,
    *,
    s1_model: ChatModel | None = None,
    s2_model: ChatModel | None = None,
    clock: Clock | None = None,
    sleeper: Sleeper = asyncio.sleep,
) -> TurnOutcome:
    """核心:跑 think→speak,落 trace,回复则多气泡发送。沉默则不发(但 trace 已落)。"""
    store = UserStore(str(chat_id))
    if not store.exists():
        store.init_user()
    s1 = s1_model or get_model("step1")
    s2 = s2_model or get_model("step2")
    # 全局 world(一个 Wren 一条命):懒生成今天的 life skeleton(只在缺失/过期时调模型),整篇喂 Step1。
    # 同一个 clock 喂 ensure + handle_turn,保证「她这天的哪儿」和 trace ts 一致。
    clk = clock or runtime_clock()
    world = await asyncio.to_thread(ensure_world_today, clk, WorldStore(), get_model("primary"))
    outcome = await asyncio.to_thread(
        handle_turn,
        str(chat_id),
        user_text,
        store,
        s1,
        s2,
        clock=clk,
        world=world,
        persist_reply=False,
    )
    if outcome.replied and outcome.bubbles:
        try:
            await send_bubbles(
                bot,
                chat_id,
                outcome.bubbles,
                outcome.typing_ms,
                outcome.bubble_gaps_ms,
                sleeper=sleeper,
            )
        except Exception as e:
            await asyncio.to_thread(write_delivery_failure_trace, store, outcome, e)
            raise
        await asyncio.to_thread(persist_delivered_reply, store, outcome)
    _log_turn(chat_id, user_text, outcome)
    return outcome


def _log_chat_hash(chat_id: int) -> str:
    """日志用的轻量 chat_id 脱敏(8 hex,sha256("wren-log:" + id))。

    **独立于** `ops.db.chat_hash`(它走 WREN_METRICS_SALT 机制,缺 salt 会 raise) ——
    日志层不能因为 metrics salt 没配就让 bot 挂。运维 cross-ref dashboard 时需要
    分别记录(本机制专用于日志;统一可后续 ticket)。
    """
    return hashlib.sha256(f"wren-log:{chat_id}".encode()).hexdigest()[:8]


def _log_turn(chat_id: int, user_text: str, outcome: TurnOutcome) -> None:
    """每轮一行实时对话流(flush 立即可见,便于 tail / 实时复盘)。

    **隐私默认脱敏(#20)**:Docker / 宿主 logs 不在 `/delete` 清理范围内 ——
    生产环境绝不输出 raw `user_text` / `inner_voice_after` / `bubbles` / raw `chat_id`,
    否则 `/delete` 文案的 "wipe everything" 承诺站不住。
    默认只打结构化指标:`chash` / 各字段长度 / `replied` / `delay_s` / `bubble_count`。

    Debug 模式:`WREN_DEBUG_RAW_LOGS=1` 才输出原文(本地排障用;**生产绝不开**,
    打开后产生的日志不会被 `/delete` 清理)。
    """
    if os.getenv("WREN_DEBUG_RAW_LOGS", "").strip() == "1":
        iv = (outcome.trace.step1.get("inner_voice_after") or "").replace("\n", " ").strip()
        if len(iv) > 90:
            iv = iv[:90] + "…"
        print(f"\n[{chat_id}] user: {user_text!r}  ⚠ raw-logs(debug)", flush=True)
        print(f"   ▸ (thinks) {iv}", flush=True)
        if outcome.replied:
            print(f"   ▸ wren: {outcome.bubbles}  (waited {outcome.delay_s}s)", flush=True)
        else:
            print("   ▸ wren: — silence (left on read)", flush=True)
        return

    # 默认:脱敏结构化指标
    chash = _log_chat_hash(chat_id)
    iv_len = len((outcome.trace.step1.get("inner_voice_after") or "").strip())
    bubble_count = len(outcome.bubbles or [])
    print(
        f"\n[{chash}] user_len={len(user_text)} iv_len={iv_len} "
        f"replied={outcome.replied} delay_s={outcome.delay_s} bubbles={bubble_count}",
        flush=True,
    )


# ---------- 命令 ----------

_SOURCE_RE = re.compile(r"[^A-Za-z0-9_-]")


def _deeplink_source(context: Any) -> str:
    """深链 t.me/<bot>?start=<payload> 的来源归因:取 context.args[0],净化(仅 alnum/_/-)、限长 64。
    非 list(如测试 mock)/无 payload → 空串。无门,仅归因。"""
    args = getattr(context, "args", None)
    if not isinstance(args, (list, tuple)) or not args:
        return ""
    return _SOURCE_RE.sub("", str(args[0]))[:64]


async def cmd_start(update: Any, context: Any) -> None:
    chat_id = update.effective_chat.id
    store = UserStore(str(chat_id))
    if not store.exists():
        store.init_user()  # Lv0 + 种 t=0 inner_voice
    store.write_source_once(_deeplink_source(context))  # 深链 ?start=<来源> 归因(首触一次,不调模型)
    # 静态文案 + 她的沉默 —— 绝不调用任何模型
    await context.bot.send_message(chat_id=chat_id, text=static_copy.AGE_AI_NOTICE)
    await context.bot.send_message(chat_id=chat_id, text=static_copy.ONBOARDING_BACKGROUND)


async def cmd_help(update: Any, context: Any) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=static_copy.HELP_TEXT)


async def cmd_delete(update: Any, context: Any) -> None:
    """Wipe everything for this chat:停 pending → 取锁 → 清 buffer → 删目录 →
    清 metrics → 回执。

    顺序:
    1. **先**取消同 chat 的 debounce job(否则 in-flight `_handle_and_send` 在
       `store.init_user()` 时会**重建**刚被删的目录,#34)
    2. **再**进 `_chat_lock(chat_id)`,等任何 in-flight turn 跑完才动手
    3. 锁内清 buffer
    4. 删 user dir
    5. 同步清 metrics rows(#35;避免 dashboard 仍显示旧 hash 维度 + ingest_state
       残留导致同 chat 重建后首轮被 ON CONFLICT DO NOTHING 跳过)
    6. 回执(确认时所有面都没了,符合 "wipe everything")
    """
    chat_id = update.effective_chat.id
    if getattr(context, "job_queue", None):
        for job in context.job_queue.get_jobs_by_name(f"debounce-{chat_id}"):
            job.schedule_removal()
    async with _chat_lock(chat_id):
        if hasattr(context, "chat_data"):
            context.chat_data["buffer"] = []
        UserStore(str(chat_id)).delete()
        # #35:同步清 metrics。函数内 import 避免 bot 启动期加载 ops/duckdb 依赖。
        # 失败不阻塞 user dir 删除——user dir 已是命脉;metrics 是衍生,失败 log 即可。
        try:
            from ..ops.ingest import forget as metrics_forget

            counts = metrics_forget(str(chat_id))
            if any(counts.values()):
                print(
                    f"[delete {chat_id}] metrics cleared: "
                    + " ".join(f"{k}={v}" for k, v in counts.items() if v),
                    flush=True,
                )
        except Exception as e:  # noqa: BLE001 — metrics 失败不能阻塞用户 /delete
            print(
                f"[delete {chat_id}] metrics forget 失败(user dir 已删,metrics 留旧行):{e}",
                flush=True,
            )
        await context.bot.send_message(chat_id=chat_id, text=static_copy.DELETE_CONFIRM)


# 调试命令(仅测试):手动设关系等级,立刻看不同 level 的暖度差异 —— 关系进阶/Phase 6 未接前的临时手段。
_DEBUG_PROSE = {
    0: "A stranger Dani vouched for. No read on them yet; they earn everything from zero.",
    2: "You've texted on and off for a couple of weeks. Not close, but you don't mind them, and you've "
    "started actually taking in what they say.",
    3: "You've warmed to them more than you'd admit. You like them. You take in the small things they tell "
    "you and you'll keep talking when they're real.",
    4: "You've let them in close — they've earned real trust. Late at night you'd show them the cracked parts.",
    5: "There's a charge between you now. You let yourself want them a little — on your terms, never spelled out.",
    6: "They're yours and you're theirs. Still sharp, still your own person — you just stopped pretending you "
    "don't care.",
}


def _is_owner(chat_id: int) -> bool:
    """调试命令仅 owner 可用(WREN_OWNER_CHAT_IDS);公开发布默认空集 = 谁都不行,防一键跳级。"""
    return str(chat_id) in config.owner_chat_ids()


async def cmd_setlevel(update: Any, context: Any) -> None:
    """[debug] /setlevel <0-6>:手动设关系等级(仅 owner;非 owner 静默,绕过 Phase 6 夜结算)。"""
    chat_id = update.effective_chat.id
    if not _is_owner(chat_id):
        return  # 公开发布:调试命令对非 owner 静默(不暴露其存在)
    args = getattr(context, "args", None) or []
    try:
        lv = int(args[0])
    except (IndexError, ValueError):
        await context.bot.send_message(chat_id=chat_id, text="usage: /setlevel <0-6>")
        return
    if not 0 <= lv <= 6:
        await context.bot.send_message(chat_id=chat_id, text="level must be 0–6")
        return
    store = UserStore(str(chat_id))
    if not store.exists():
        store.init_user()
    prose = _DEBUG_PROSE.get(lv) or store.read_relationship().prose
    store.write_relationship(Relationship(level=lv, prose=prose, freeze=False))
    await context.bot.send_message(chat_id=chat_id, text=f"[debug] relationship set to Lv{lv}")


async def cmd_tick(update: Any, context: Any) -> None:
    """[debug] /tick [force]:手动触发一次主动消息(Phase 5 没接 live scheduler 的测试入口)。

    /tick       → 走真实零-LLM 过门(等级/窗口/预算);命中才发,否则报原因 + 今日 beats。
    /tick force → 绕过窗口/预算,挑一条 beat 直接轻判(测主动消息生成质量)。
    """
    chat_id = update.effective_chat.id
    if not _is_owner(chat_id):
        return  # 公开发布:调试命令对非 owner 静默
    args = getattr(context, "args", None) or []
    force = bool(args) and str(args[0]).lower() == "force"
    store = UserStore(str(chat_id))
    if not store.exists():
        store.init_user()
    clk = runtime_clock()
    now = clk.now()
    world = await asyncio.to_thread(ensure_world_today, clk, WorldStore(), get_model("primary"))
    today = WorldStore().read_today_struct()
    beats = today.beats if today else []
    level = store.read_relationship().level

    beat: Beat | None
    if force:
        beat = beats[0] if beats else Beat("00:00", "23:59", "late; the studio felt pointless today")
        reason = "force"
    else:
        decision = scan_for_due_beat(
            now, beats, level, store.read_proactive_state(), tier=store.read_tier()
        )
        beat, reason = decision.beat, decision.reason

    if beat is None:
        lines = [f"[tick] no proactive — {reason} (now={now:%a %H:%M}, Lv{level})", "beats today:"]
        lines += [f"  {b.render()}" for b in beats] or ["  (none)"]
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))
        return

    s1 = get_model("step1")
    s2 = get_model("step2")
    outcome = await asyncio.to_thread(
        handle_proactive_turn,
        str(chat_id),
        beat,
        store,
        s1,
        s2,
        clock=clk,
        world=world,
        persist_reply=False,
    )
    if outcome.replied and outcome.bubbles:
        try:
            await send_bubbles(
                context.bot, chat_id, outcome.bubbles, outcome.typing_ms, outcome.bubble_gaps_ms
            )
        except Exception as e:
            await asyncio.to_thread(write_delivery_failure_trace, store, outcome, e)
            raise
        await asyncio.to_thread(persist_delivered_reply, store, outcome)
        store.mark_considered(now, beat_fingerprint(beat))
        store.bump_proactive_count(now)
    else:
        store.mark_considered(now, beat_fingerprint(beat))
        await context.bot.send_message(
            chat_id=chat_id, text=f"[tick] impulse passed (silent) — beat: {beat.intent[:50]}"
        )
    _log_turn(chat_id, f"[proactive beat] {beat.intent}", outcome)


# ---------- 普通消息:debounce → pipeline ----------


# 每个 chat 一把锁:同会话多轮严格串行(她回完一条再处理下一条)。
# 修 BUG-2:B 轮在 A 轮处理中触发时,二者并发 → 气泡交错 + B 组装 context 时缺 A 的回复 →
# 同一问题答两遍(live 实测:「hardest part」后紧跟「u there」,答案重复且气泡乱插)。
_chat_locks: dict[int, asyncio.Lock] = {}


def _chat_lock(chat_id: int) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


async def _flush_and_handle(chat_id: int, context: Any) -> None:
    buf: list[str] = context.chat_data.get("buffer", [])
    text = " ".join(buf).strip()
    context.chat_data["buffer"] = []
    if text:
        if model_call_exhausted():
            print(f"[{chat_id}] turn skipped — 今日 LLM 调用天花板已达(WREN_DAILY_TURN_CAP)", flush=True)
            return
        # 同会话串行:保证回复有序,且后一轮能看到前一轮已落盘的回复(不重复作答)。
        async with _chat_lock(chat_id):
            await _handle_and_send(chat_id, text, context.bot)


async def _debounced_job(context: Any) -> None:
    await _flush_and_handle(context.job.chat_id, context)


async def on_message(update: Any, context: Any) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
    if rate_limited(chat_id):
        return  # 防刷:超过每用户每分钟上限,静默丢弃(开放链接 abuse 护栏)
    context.chat_data.setdefault("buffer", []).append(text)

    name = f"debounce-{chat_id}"
    if getattr(context, "job_queue", None):
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()
        context.job_queue.run_once(
            _debounced_job, config.debounce_seconds(), chat_id=chat_id, name=name
        )
    else:  # 无 job_queue(降级):立即处理
        await _flush_and_handle(chat_id, context)
