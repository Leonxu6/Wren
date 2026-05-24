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


# === #32:SystemClock 必须是 ET wall-clock(Wren 锚定 Brooklyn / America/New_York)===


def test_system_clock_returns_et_not_utc() -> None:
    """#32 核心:SystemClock.now() 必须返回 America/New_York 的 tz-aware datetime,
    不是 UTC。否则 Step1 `now` / world date / proactive 窗口都按 UTC 偏 4-5h。"""
    from zoneinfo import ZoneInfo

    now = SystemClock().now()
    assert now.tzinfo is not None, "必须 tz-aware"
    assert now.tzinfo == ZoneInfo("America/New_York"), (
        f"SystemClock 必须返 ET,实际 {now.tzinfo}(#32)"
    )
    # ET 偏移 -4h(DST)或 -5h(EST);**绝不是 0**(UTC)
    offset = now.utcoffset()
    assert offset is not None
    assert offset.total_seconds() != 0, "SystemClock 不该是 UTC(offset=0)"
    assert offset.total_seconds() in (-4 * 3600, -5 * 3600), (
        f"ET 偏移应为 -4h(DST)或 -5h(EST),实际 {offset}"
    )


def test_iso_z_still_normalizes_et_to_utc() -> None:
    """回归:`iso_z()` 应仍把 ET 时间转 UTC 后写成 `Z` 格式(trace 时间面不变)。

    DST 期间:2026-05-20 ET 22:00 = UTC 02:00 次日 → `2026-05-21T02:00:00Z`。
    """
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    dt_et = datetime(2026, 5, 20, 22, 0, tzinfo=et)
    assert iso_z(dt_et) == "2026-05-21T02:00:00Z"


def test_system_clock_and_utc_now_same_instant() -> None:
    """sanity:ET 和 UTC 是同一瞬间,只是 tzinfo 不同。`astimezone(UTC)` 后必须
    与 `datetime.now(UTC)` 在几秒内吻合(防 SystemClock 偷偷拿了别的 wall-clock)。"""
    sys_now = SystemClock().now()
    utc_now = datetime.now(UTC)
    diff_s = abs((sys_now.astimezone(UTC) - utc_now).total_seconds())
    assert diff_s < 5, f"SystemClock 与 UTC now 同瞬间(astimezone 后),实际差 {diff_s}s"
