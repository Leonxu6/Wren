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
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}
    await cmd_delete(update, context)
    assert not UserStore("777", data_root).dir.exists()


async def test_delete_cancels_pending_debounce_job(data_root: Path) -> None:
    """#34:cmd_delete 必须先取消同 chat 的 debounce job —— 否则旧 buffer 会被 flush
    成新 turn,在 store.init_user() 时**重建**刚被删的目录,wipe 失败。"""
    UserStore("888", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 888
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    fake_job = MagicMock()
    fake_job.schedule_removal = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[fake_job])
    context.chat_data = {"buffer": ["old message that should not survive"]}

    await cmd_delete(update, context)

    context.job_queue.get_jobs_by_name.assert_called_with("debounce-888")
    fake_job.schedule_removal.assert_called_once()
    assert context.chat_data["buffer"] == []  # 旧消息清掉
    assert not UserStore("888", data_root).dir.exists()


async def test_delete_holds_chat_lock_until_done(data_root: Path) -> None:
    """#34:cmd_delete 必须进 `_chat_lock(chat_id)`,与 in-flight turn 串行。
    否则 in-flight `_handle_and_send` 的 `store.init_user()` 会与 delete 同跑,
    产生半状态(目录被删 + trace 又被写)。"""
    import asyncio

    from wren.bot.handlers import _chat_lock

    UserStore("999", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 999
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}

    lock = _chat_lock(999)
    async with lock:
        # in-flight turn 抢先持锁;启动 cmd_delete 应被阻塞
        task = asyncio.create_task(cmd_delete(update, context))
        await asyncio.sleep(0.05)
        assert not task.done(), "cmd_delete 应被 _chat_lock 阻塞(#34 race)"
        assert UserStore("999", data_root).dir.exists(), "锁释放前不该删"
        assert context.bot.send_message.call_count == 0, "锁释放前不该发 confirmation"

    # 锁释放 → cmd_delete 应完成
    await asyncio.wait_for(task, timeout=2.0)
    assert not UserStore("999", data_root).dir.exists()
    context.bot.send_message.assert_called_once()
