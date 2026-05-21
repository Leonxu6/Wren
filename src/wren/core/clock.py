"""可注入时钟 seam(§5)。生产用 SystemClock(真实 UTC);eval 用 MockClock 快进。"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class MockClock:
    """可注入的假时钟(p2-mock-clock):把时间钉死、快进多天、跨午夜,全可复现。

    让「早班 08:00 vs 失眠窗 02:00」「day0→夜结算→day2」在 eval 里确定性重放(§5)。
    🔒契约:实现 Clock 协议,Phase 4/5/6 日循环都注入它;trace 的 `ts` 读它。
    """

    def __init__(self, start: datetime) -> None:
        self._now = start if start.tzinfo is not None else start.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> None:
        """快进(可跨午夜/跨天)。"""
        self._now += timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    def set_time(self, hour: int, minute: int = 0) -> None:
        """把当天时刻设到 HH:MM(不动日期),用于「设到早班/失眠窗」。"""
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"非法时刻 {hour}:{minute}")
        self._now = self._now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def iso_z(dt: datetime) -> str:
    """→ '2026-05-20T06:15:00Z'(trace ts 格式)。"""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def runtime_clock() -> Clock:
    """live/debug 时钟:WREN_CLOCK_OVERRIDE=<ISO8601> → 钉死的 MockClock(P4 时段因果 / P5 时间窗手测可时间旅行),
    否则 SystemClock(真实时间)。仅调试/测试路径用;prod 不设该 env → 走 SystemClock。"""
    raw = os.getenv("WREN_CLOCK_OVERRIDE", "").strip()
    if not raw:
        return SystemClock()
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return SystemClock()
    return MockClock(dt)
