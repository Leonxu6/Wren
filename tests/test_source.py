"""W3 深链来源归因:/start 解析 ?start=<payload> → source.md(首触一次、净化、幂等)。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from wren.bot.handlers import cmd_start
from wren.core.storage import UserStore


async def test_start_records_deeplink_source(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    update, context = make_tg(chat_id=42)
    context.args = ["instagram_xmas"]
    await cmd_start(update, context)
    assert UserStore("42").read_source() == "instagram_xmas"


async def test_start_source_idempotent(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    u1, c1 = make_tg(chat_id=42)
    c1.args = ["first_source"]
    await cmd_start(u1, c1)
    u2, c2 = make_tg(chat_id=42)
    c2.args = ["second_source"]
    await cmd_start(u2, c2)
    assert UserStore("42").read_source() == "first_source"  # 不覆盖首触来源


async def test_start_no_payload_no_source(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    update, context = make_tg(chat_id=42)
    context.args = []
    await cmd_start(update, context)
    assert UserStore("42").read_source() == ""


async def test_start_mock_args_not_treated_as_source(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    # make_tg 的 context.args 是 MagicMock(非 list)→ 不当作来源(否则会把 Mock repr 写进去)
    update, context = make_tg(chat_id=42)
    await cmd_start(update, context)
    assert UserStore("42").read_source() == ""


async def test_start_source_sanitized(
    data_root: Path, make_tg: Callable[..., tuple[Any, Any]]
) -> None:
    update, context = make_tg(chat_id=42)
    context.args = ["promo/../x!! 2026-q1"]
    await cmd_start(update, context)
    src = UserStore("42").read_source()
    assert src and all(c.isalnum() or c in "_-" for c in src)  # 只剩安全字符
