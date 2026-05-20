"""公共测试夹具。默认强制 fake 模式 —— 测试绝不真调外部 API。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from wren.model.base import ChatMessage


@pytest.fixture(autouse=True)
def _force_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试默认离线 fake;删掉 .env 注入的真实 key,避免误调 API。"""
    monkeypatch.setenv("WREN_FAKE_MODEL", "1")
    monkeypatch.delenv("WREN_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "users"
    monkeypatch.setenv("WREN_DATA_ROOT", str(root))
    return root


@pytest.fixture
def last_user_text() -> Callable[[list[ChatMessage]], str]:
    """从一组 messages 里取最后一条 user 内容(写 responder 用)。"""

    def _get(messages: list[ChatMessage]) -> str:
        for m in reversed(messages):
            if m.role == "user":
                return m.content
        return ""

    return _get


@pytest.fixture
def make_tg() -> Callable[..., tuple[Any, Any]]:
    """造 mock Telegram (update, context);不连真服务器。"""

    def _make(text: str = "hi", chat_id: int = 555) -> tuple[Any, Any]:
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.message.text = text
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot.send_chat_action = AsyncMock()
        context.chat_data = {}
        context.job_queue = None  # 降级:on_message 直接处理
        return update, context

    return _make
