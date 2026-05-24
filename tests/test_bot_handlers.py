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


# === #20:默认日志脱敏(让 /delete "wipe everything" 承诺成立)===


_SENSITIVE_USER_TEXT = "MY-VERY-PRIVATE-TEXT-12345"
_SENSITIVE_MONOLOGUE = "MY-PRIVATE-INNER-VOICE-XYZ"


async def _send_one_turn_with_sensitive_content(
    chat_id: int, data_root: Path
) -> None:
    """跑一轮,user_text + inner_voice 都带可识别 sentinel。"""
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {
                    "monologue": _SENSITIVE_MONOLOGUE,
                    "reply": True,
                    "delay_s": 3,
                    "impression": "",
                    "memory": [],
                }
            )
        ]
    )
    s2 = FakeChatModel(script=[json.dumps({"messages": ["ok"]})])
    await _handle_and_send(
        chat_id, _SENSITIVE_USER_TEXT, bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )


async def test_log_default_does_not_leak_user_text_or_inner_voice(
    data_root: Path, capsys: Any, monkeypatch: Any
) -> None:
    """默认(无 WREN_DEBUG_RAW_LOGS):stdout 必须不含 raw user_text / inner_voice /
    raw chat_id。否则 /delete 的 "wipe everything" 承诺站不住(#20)。
    """
    monkeypatch.delenv("WREN_DEBUG_RAW_LOGS", raising=False)
    await _send_one_turn_with_sensitive_content(888, data_root)
    captured = capsys.readouterr().out
    assert _SENSITIVE_USER_TEXT not in captured, "raw user_text 不应进默认日志"
    assert _SENSITIVE_MONOLOGUE not in captured, "raw inner_voice 不应进默认日志"
    assert "[888]" not in captured, "raw chat_id 不应进默认日志(用 chash 替代)"
    # 仍要有结构化指标可供运维 tail
    assert "user_len=" in captured
    assert "iv_len=" in captured
    assert "replied=True" in captured
    assert "bubbles=1" in captured


async def test_log_debug_mode_outputs_raw_content(
    data_root: Path, capsys: Any, monkeypatch: Any
) -> None:
    """WREN_DEBUG_RAW_LOGS=1 时,本地排障可看 raw 内容(只在显式开关下)。"""
    monkeypatch.setenv("WREN_DEBUG_RAW_LOGS", "1")
    await _send_one_turn_with_sensitive_content(889, data_root)
    captured = capsys.readouterr().out
    assert _SENSITIVE_USER_TEXT in captured
    assert _SENSITIVE_MONOLOGUE in captured
    assert "[889]" in captured  # debug 模式可见 raw chat_id
    assert "raw-logs(debug)" in captured  # 警示前缀


def test_log_chat_hash_is_stable_and_not_raw_id() -> None:
    """chash 跨调用稳定 + 8 hex 形态;不是 raw chat_id;独立于 metrics chat_hash
    (后者依赖 WREN_METRICS_SALT,缺 salt 会 raise —— 不能让 bot 因日志挂)。"""
    from wren.bot.handlers import _log_chat_hash

    h1 = _log_chat_hash(12345)
    h2 = _log_chat_hash(12345)
    h3 = _log_chat_hash(99999)
    assert h1 == h2  # 稳定
    assert h1 != h3  # 不同 id → 不同 hash
    assert len(h1) == 8 and all(c in "0123456789abcdef" for c in h1)  # 8 hex
    assert "12345" not in h1  # 不暴露 raw id
