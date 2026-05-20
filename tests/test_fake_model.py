"""FakeChatModel:确定性 / 脚本化 / 调用计数。"""

from __future__ import annotations

import pytest

from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel


def _msgs(text: str) -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def test_script_returns_in_order() -> None:
    m = FakeChatModel(script=["a", "b", "c"])
    assert [m.complete(_msgs("x")).text for _ in range(3)] == ["a", "b", "c"]


def test_script_exhaustion_raises() -> None:
    m = FakeChatModel(script=["only"])
    m.complete(_msgs("x"))
    with pytest.raises(IndexError):
        m.complete(_msgs("x"))


def test_responder_sees_messages() -> None:
    m = FakeChatModel(responder=lambda msgs: msgs[-1].content.upper())
    assert m.complete(_msgs("hi")).text == "HI"


def test_calls_are_recorded() -> None:
    m = FakeChatModel(script=["1", "2"])
    m.complete(_msgs("first"))
    m.complete(_msgs("second"))
    assert len(m.calls) == 2
    assert m.calls[0][-1].content == "first"


def test_result_carries_model_name() -> None:
    m = FakeChatModel(name="fake-judge", script=["ok"])
    res = m.complete(_msgs("x"))
    assert res.model == "fake-judge"
    assert res.latency_ms == 0
