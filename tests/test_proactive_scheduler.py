"""W2 主动消息 live scheduler(P5 缺的触发器):到点过门 → 发;新近度护栏让路;注册接线。

满足验收 D3.3(主动调度器对 Lv2+ 用户实际触发)。models/clock 注入 → 确定性、离线。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from wren.bot.scheduler import _recently_active, proactive_tick, register_proactive
from wren.core.clock import MockClock, iso_z
from wren.core.storage import Relationship, UserStore
from wren.core.trace import read_traces, trace_path
from wren.model.fake import FakeChatModel

_NOW = datetime(2026, 5, 22, 15, 30, tzinfo=UTC)  # 15:30,落在下面 beat 窗口内
_TODAY_MD = (
    "date: 2026-05-22\n\n## her day\nrestless, paint everywhere.\n\n"
    "## beats\n- [window: 15:00–16:00] wants to share a small thing\n"
)


def _seed_world(world_root: Path) -> None:
    world_root.mkdir(parents=True, exist_ok=True)
    (world_root / "today.md").write_text(_TODAY_MD, encoding="utf-8")


def _lv3_user(uid: str = "12345") -> UserStore:
    store = UserStore(uid)
    store.init_user()
    store.write_relationship(Relationship(level=3, prose="warm", freeze=False))  # Lv3 → 日 cap=1
    return store


def _ctx(*, pending_debounce: bool = False) -> MagicMock:
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(
        return_value=[object()] if pending_debounce else []
    )
    return context


def _models() -> dict[str, FakeChatModel]:
    return {
        "s1_model": FakeChatModel(
            script=[json.dumps({"monologue": "thinking of them", "reply": True, "delay_s": 0})]
        ),
        "s2_model": FakeChatModel(script=[json.dumps({"messages": ["hey", "saw something dumb"]})]),
        "world_model": FakeChatModel(script=["unused — today.md 已是当天,走快路径"]),
    }


async def test_proactive_tick_fires_for_due_beat(data_root: Path, world_root: Path) -> None:
    _seed_world(world_root)
    store = _lv3_user()
    n = await proactive_tick(_ctx(), clock=MockClock(_NOW), **_models())
    assert n == 1  # 到点 + 过门 + 无近期对话 → 发
    assert any(t.get("kind") == "proactive" for t in read_traces(store.dir))
    assert store.read_proactive_state().day_count == 1  # 预算 +1


async def test_proactive_tick_skips_recently_active(data_root: Path, world_root: Path) -> None:
    _seed_world(world_root)
    store = _lv3_user()
    # 2 分钟前刚有一轮 → 对话中,主动消息让路
    with trace_path(store.dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"chat_id": "12345", "ts": iso_z(_NOW)}) + "\n")
    n = await proactive_tick(_ctx(), clock=MockClock(_NOW), **_models())
    assert n == 0


async def test_proactive_tick_skips_pending_debounce(data_root: Path, world_root: Path) -> None:
    _seed_world(world_root)
    _lv3_user()
    n = await proactive_tick(_ctx(pending_debounce=True), clock=MockClock(_NOW), **_models())
    assert n == 0  # 有 pending debounce(用户正在打字)→ 不插嘴


async def test_proactive_tick_skips_lv0(data_root: Path, world_root: Path) -> None:
    _seed_world(world_root)
    UserStore("12345").init_user()  # Lv0:cap=0,地板,不主动
    n = await proactive_tick(_ctx(), clock=MockClock(_NOW), **_models())
    assert n == 0


def test_recently_active(data_root: Path) -> None:
    store = UserStore("u")
    store.init_user()
    assert _recently_active(store, _NOW) is False  # 无 trace
    with trace_path(store.dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": iso_z(_NOW)}) + "\n")
    assert _recently_active(store, _NOW) is True  # 刚刚
    later = _NOW.replace(hour=_NOW.hour + 1)  # 1 小时后 → 不算近期
    assert _recently_active(store, later) is False


def test_register_proactive() -> None:
    app = MagicMock()
    assert register_proactive(app) is True
    app.job_queue.run_repeating.assert_called_once()


def test_register_proactive_no_jobqueue() -> None:
    app = MagicMock()
    app.job_queue = None
    assert register_proactive(app) is False
