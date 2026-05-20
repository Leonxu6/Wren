"""多气泡发送:typing 指示 + 气泡间隔。sleeper 可注入,便于测试不真睡。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

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
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        wait_ms = typing_ms if i == 0 else bubble_gaps_ms[i - 1]
        await sleeper(wait_ms / 1000)
        await bot.send_message(chat_id=chat_id, text=bubble)
