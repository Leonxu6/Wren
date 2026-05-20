"""bot handler(p1-skeleton):mock update + fake model → 多气泡 + 落 trace;沉默不发;/delete 清目录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from wren.bot.handlers import _handle_and_send, cmd_delete
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.model.fake import FakeChatModel


async def _nosleep(_seconds: float) -> None:
    return None


def _bot() -> Any:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_chat_action = AsyncMock()
    return bot


async def test_handle_and_send_emits_bubbles_and_trace(data_root: Path) -> None:
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {
                    "monologue": "let's see",
                    "reply": True,
                    "delay_s": 6,
                    "impression": "",
                    "memory": [],
                }
            )
        ]
    )
    s2 = FakeChatModel(
        script=[json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})]
    )
    out = await _handle_and_send(
        555, "you were at theo's show right", bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )
    assert out.replied
    assert bot.send_message.await_count == 3  # 三个气泡
    assert bot.send_chat_action.await_count == 3  # 每条前 typing
    assert len(read_traces(UserStore("555", data_root).dir)) == 1  # 落了 trace


async def test_silence_sends_nothing_but_traces(data_root: Path) -> None:
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {"monologue": "ugh", "reply": False, "delay_s": 0, "impression": "", "memory": []}
            )
        ]
    )
    s2 = FakeChatModel(script=["unused"])
    out = await _handle_and_send(
        556, "hey gorgeous", bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )
    assert not out.replied
    assert bot.send_message.await_count == 0
    assert len(read_traces(UserStore("556", data_root).dir)) == 1  # 沉默轮也有 trace


async def test_delete_command_wipes(data_root: Path) -> None:
    UserStore("777", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 777
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    await cmd_delete(update, context)
    assert not UserStore("777", data_root).dir.exists()
