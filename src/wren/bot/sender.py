"""多气泡发送:typing 指示 + 气泡间隔。sleeper 可注入,便于测试不真睡。

健壮性(live bot · 网络抖动):typing 指示纯属拟真,是【尽力而为】—— 它对 Telegram 的调用
超时/失败【绝不能】拖垮真正的回复。否则一次 typing 超时 = 整条回复被吞(p4-world live 测教训)。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from telegram.error import TelegramError

Sleeper = Callable[[float], Awaitable[None]]


async def send_bubbles(
    bot: Any,
    chat_id: int,
    bubbles: list[str],
    typing_ms: int,
    bubble_gaps_ms: list[int],
    *,
    sleeper: Sleeper = asyncio.sleep,
) -> None:
    for i, bubble in enumerate(bubbles):
        # typing 仅为拟真,尽力而为:超时/失败也绝不挡住真正的 bubble(关键路径是 send_message)。
        with contextlib.suppress(TelegramError):
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        wait_ms = typing_ms if i == 0 else bubble_gaps_ms[i - 1]
        await sleeper(wait_ms / 1000)
        await bot.send_message(chat_id=chat_id, text=bubble)
