"""可注入时钟 seam(§5)。MVP 只用真实 UTC;p2-mock-clock 再加 FrozenClock 快进。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def iso_z(dt: datetime) -> str:
    """→ '2026-05-20T06:15:00Z'(trace ts 格式)。"""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
