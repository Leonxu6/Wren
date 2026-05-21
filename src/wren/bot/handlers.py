"""Telegram handlers:/start(静态,不走 LLM)/help /delete + on_message(debounce→pipeline→多气泡)。

红线:onboarding 静态、她不主动破冰;应答从 Lv0 经真实 Step1→Step2 涌现(非 lookup 表)。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .. import config
from ..core.clock import Clock, SystemClock
from ..core.life_sim import ensure_world_today
from ..core.pipeline import TurnOutcome, handle_turn
from ..core.storage import Relationship, UserStore
from ..core.world import WorldStore
from ..model.base import ChatModel
from ..model.registry import get_model
from ..onboarding import static_copy
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
    clk = clock or SystemClock()
    world = await asyncio.to_thread(ensure_world_today, clk, WorldStore(), get_model("primary"))
    outcome = await asyncio.to_thread(
        handle_turn, str(chat_id), user_text, store, s1, s2, clock=clk, world=world
    )
    _log_turn(chat_id, user_text, outcome)
    if outcome.replied and outcome.bubbles:
        await send_bubbles(
            bot,
            chat_id,
            outcome.bubbles,
            outcome.typing_ms,
            outcome.bubble_gaps_ms,
            sleeper=sleeper,
        )
    return outcome


def _log_turn(chat_id: int, user_text: str, outcome: TurnOutcome) -> None:
    """每轮一行实时对话流(flush 立即可见,便于 tail / 实时复盘)。"""
    iv = (outcome.trace.step1.get("inner_voice_after") or "").replace("\n", " ").strip()
    if len(iv) > 90:
        iv = iv[:90] + "…"
    print(f"\n[{chat_id}] user: {user_text!r}", flush=True)
    print(f"   ▸ (thinks) {iv}", flush=True)
    if outcome.replied:
        print(f"   ▸ wren: {outcome.bubbles}  (waited {outcome.delay_s}s)", flush=True)
    else:
        print("   ▸ wren: — silence (left on read)", flush=True)


# ---------- 命令 ----------


async def cmd_start(update: Any, context: Any) -> None:
    chat_id = update.effective_chat.id
    store = UserStore(str(chat_id))
    if not store.exists():
        store.init_user()  # Lv0 + 种 t=0 inner_voice
    # 静态文案 + 她的沉默 —— 绝不调用任何模型
    await context.bot.send_message(chat_id=chat_id, text=static_copy.AGE_AI_NOTICE)
    await context.bot.send_message(chat_id=chat_id, text=static_copy.ONBOARDING_BACKGROUND)


async def cmd_help(update: Any, context: Any) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=static_copy.HELP_TEXT)


async def cmd_delete(update: Any, context: Any) -> None:
    UserStore(str(update.effective_chat.id)).delete()
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=static_copy.DELETE_CONFIRM
    )


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


async def cmd_setlevel(update: Any, context: Any) -> None:
    """[debug] /setlevel <0-6>:手动设关系等级 + 对应散文(仅测试,绕过 Phase 6 夜结算)。"""
    chat_id = update.effective_chat.id
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


# ---------- 普通消息:debounce → pipeline ----------


async def _flush_and_handle(chat_id: int, context: Any) -> None:
    buf: list[str] = context.chat_data.get("buffer", [])
    text = " ".join(buf).strip()
    context.chat_data["buffer"] = []
    if text:
        await _handle_and_send(chat_id, text, context.bot)


async def _debounced_job(context: Any) -> None:
    await _flush_and_handle(context.job.chat_id, context)


async def on_message(update: Any, context: Any) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
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
