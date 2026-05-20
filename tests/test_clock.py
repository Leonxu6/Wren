"""p2-mock-clock:MockClock 可设/可快进/跨午夜,且能注入 handle_turn 让 trace ts 读它。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from wren.core.clock import MockClock, SystemClock, iso_z
from wren.core.pipeline import handle_turn
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.model.fake import FakeChatModel

_S1 = json.dumps(
    {"monologue": "mm", "reply": True, "delay_s": 3, "impression": "", "memory": []}
)
_S2 = json.dumps({"messages": ["mm"]})


def test_mock_and_system_satisfy_contract() -> None:
    # 都暴露 now() → tz-aware datetime(Clock 协议;handle_turn 注入点凭它收口)
    for clk in (MockClock(datetime(2026, 5, 20, tzinfo=UTC)), SystemClock()):
        assert clk.now().tzinfo is not None


def test_set_time_morning_vs_insomnia() -> None:
    c = MockClock(datetime(2026, 5, 20, 12, 0, tzinfo=UTC))
    c.set_time(8, 0)
    assert iso_z(c.now()) == "2026-05-20T08:00:00Z"
    c.set_time(2, 0)
    assert iso_z(c.now()) == "2026-05-20T02:00:00Z"


def test_advance_crosses_midnight_and_days() -> None:
    c = MockClock(datetime(2026, 5, 20, 23, 30, tzinfo=UTC))
    c.advance(hours=2)  # 跨午夜
    assert iso_z(c.now()) == "2026-05-21T01:30:00Z"
    c.advance(days=2)
    assert c.now().date() == datetime(2026, 5, 23).date()


def test_naive_start_assumed_utc() -> None:
    assert MockClock(datetime(2026, 5, 20, 9, 0)).now().tzinfo is UTC


def test_injected_clock_drives_trace_ts(data_root: Path) -> None:
    s = UserStore("clk1", data_root)
    s.init_user()
    clock = MockClock(datetime(2026, 5, 20, 2, 15, tzinfo=UTC))
    handle_turn("clk1", "you up", s, FakeChatModel(script=[_S1]), FakeChatModel(script=[_S2]), clock=clock)
    assert read_traces(s.dir)[0]["ts"] == "2026-05-20T02:15:00Z"
