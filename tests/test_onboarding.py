"""onboarding(p1-skeleton 一部分):/start 是静态文案,绝不走 LLM。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from wren.bot.handlers import cmd_start


async def test_start_sends_static_copy(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    update, context = make_tg()
    await cmd_start(update, context)
    sent = [c.kwargs["text"] for c in context.bot.send_message.call_args_list]
    assert any("Wren accepted your message request" in t for t in sent)
    assert any("18+" in t for t in sent)  # 年龄门
    assert any("(She hasn't said anything.)" in t for t in sent)  # 她沉默


async def test_start_does_not_call_model(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("/start 不应调用任何 LLM")

    monkeypatch.setattr("wren.bot.handlers.get_model", boom)
    update, context = make_tg()
    await cmd_start(update, context)  # 不抛错 = 证明 onboarding 不走模型
