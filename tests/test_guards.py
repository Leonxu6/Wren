"""W1 公开发布护栏:调试命令 owner 鉴权 + 每用户限流 + 全局每日成本天花板。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from wren.bot import limits
from wren.bot.handlers import cmd_setlevel, cmd_tick
from wren.core.storage import UserStore


# ---- 调试命令 owner 鉴权(公开发布:非 owner 一句话跳 Lv6 = 绕过整个产品魂)----
async def test_setlevel_silent_for_non_owner(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WREN_OWNER_CHAT_IDS", "999")  # owner 是 999
    update, context = make_tg(chat_id=555)  # 555 非 owner
    context.args = ["6"]
    await cmd_setlevel(update, context)
    context.bot.send_message.assert_not_called()  # 静默:不暴露命令存在
    assert not UserStore("555").exists()  # 没建/没改 → 没跳级


async def test_setlevel_works_for_owner(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WREN_OWNER_CHAT_IDS", "555")
    update, context = make_tg(chat_id=555)
    context.args = ["6"]
    await cmd_setlevel(update, context)
    assert UserStore("555").read_relationship().level == 6


async def test_tick_silent_for_non_owner(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WREN_OWNER_CHAT_IDS", "")  # 空 = 谁都不行(公开默认)
    update, context = make_tg(chat_id=555)
    await cmd_tick(update, context)
    context.bot.send_message.assert_not_called()


# ---- 每用户限流 ----
def test_rate_limit_blocks_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_RATE_LIMIT_PER_MIN", "3")
    limits._msg_times.clear()
    t = 1000.0
    assert not limits.rate_limited(7, now=t)
    assert not limits.rate_limited(7, now=t)
    assert not limits.rate_limited(7, now=t)
    assert limits.rate_limited(7, now=t)  # 第 4 条同窗 → 丢
    assert not limits.rate_limited(7, now=t + 61)  # 窗口滑过 → 放行


def test_rate_limit_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_RATE_LIMIT_PER_MIN", "0")
    limits._msg_times.clear()
    assert all(not limits.rate_limited(7, now=1000.0) for _ in range(50))


def test_rate_limit_isolated_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_RATE_LIMIT_PER_MIN", "1")
    limits._msg_times.clear()
    assert not limits.rate_limited(1, now=1000.0)
    assert not limits.rate_limited(2, now=1000.0)  # 不同用户互不影响
    assert limits.rate_limited(1, now=1000.0)


# ---- 全局每日成本天花板 ----
def test_daily_cap_hard_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_DAILY_TURN_CAP", "2")
    monkeypatch.setenv("WREN_DAILY_CAP_HARD", "1")
    limits._turn_day, limits._turn_count = "", 0
    now = datetime(2026, 5, 22, tzinfo=UTC)
    assert not limits.turn_blocked(now=now)  # 1
    assert not limits.turn_blocked(now=now)  # 2(达上限那条仍跑)
    assert limits.turn_blocked(now=now)  # 3 → 硬停


def test_daily_cap_alert_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_DAILY_TURN_CAP", "1")
    monkeypatch.delenv("WREN_DAILY_CAP_HARD", raising=False)  # 非硬停
    limits._turn_day, limits._turn_count = "", 0
    now = datetime(2026, 5, 22, tzinfo=UTC)
    assert not limits.turn_blocked(now=now)
    assert not limits.turn_blocked(now=now)  # 超了也只告警、继续服务


def test_daily_cap_rolls_over_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WREN_DAILY_TURN_CAP", "1")
    monkeypatch.setenv("WREN_DAILY_CAP_HARD", "1")
    limits._turn_day, limits._turn_count = "", 0
    d1 = datetime(2026, 5, 22, tzinfo=UTC)
    d2 = datetime(2026, 5, 23, tzinfo=UTC)
    assert not limits.turn_blocked(now=d1)
    assert limits.turn_blocked(now=d1)  # 同日超限
    assert not limits.turn_blocked(now=d2)  # 跨日重置
