"""Telegram handlers:/start(静态,不走 LLM)/help /delete + on_message(debounce→pipeline→多气泡)。

红线:onboarding 静态、她不主动破冰;应答从 Lv0 经真实 Step1→Step2 涌现(非 lookup 表)。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .. import config
from ..core.clock import Clock
from ..core.pipeline import TurnOutcome, handle_turn
from ..core.storage import UserStore
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
    outcome = await asyncio.to_thread(
        handle_turn, str(chat_id), user_text, store, s1, s2, clock=clock
    )
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
