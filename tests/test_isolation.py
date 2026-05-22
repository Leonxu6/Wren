"""W4 数据完整性 / 会话隔离(验收 D1):
- D1.1 N 用户并发跑 handle_turn → 各自目录零跨用户污染。
- D1.2 原子写:写到一半崩(os.replace 抛错)→ 正本不动、无半截、无遗留 .tmp。
- D1.3 共享 world/ 并发触发 ensure_world_today → 单飞(只生成一次)。
- D1.4 /delete 全清:目录与 exists() 都没了。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from wren.core.atomicio import atomic_write_text
from wren.core.pipeline import handle_turn
from wren.core.storage import Relationship, UserStore
from wren.core.trace import count_traces, read_traces
from wren.model.fake import FakeChatModel


# ---- D1.1 跨用户隔离(并发)----
async def test_cross_user_isolation_concurrent(data_root: Path) -> None:
    uids = [f"u{i}" for i in range(6)]

    def run(uid: str) -> None:
        store = UserStore(uid)
        store.init_user()
        s1 = FakeChatModel(
            script=[json.dumps({"monologue": f"think-{uid}", "reply": True, "delay_s": 0})]
        )
        s2 = FakeChatModel(script=[json.dumps({"messages": [f"reply-to-{uid}"]})])
        handle_turn(uid, f"msg-from-{uid}", store, s1, s2)

    await asyncio.gather(*[asyncio.to_thread(run, uid) for uid in uids])

    for uid in uids:
        store = UserStore(uid)
        convo = store.read_recent_dialogue()
        assert f"msg-from-{uid}" in convo and f"reply-to-{uid}" in convo
        for other in uids:
            if other != uid:  # 别人的任何文本都不该出现在我的目录
                assert f"msg-from-{other}" not in convo
                assert f"reply-to-{other}" not in convo
        assert count_traces(store.dir) == 1
        assert read_traces(store.dir)[0]["chat_id"] == uid


# ---- D1.2 原子写:崩在中途不留半截 ----
def test_atomic_write_intact_on_crash(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = UserStore("crashtest")
    store.init_user()
    assert store.read_relationship().level == 0

    import wren.core.atomicio as aio

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("rename failed mid-write")

    monkeypatch.setattr(aio.os, "replace", boom)
    with pytest.raises(OSError):
        store.write_relationship(Relationship(level=5, prose="x", freeze=False))

    assert store.read_relationship().level == 0  # 正本没变成 5、没半截
    assert list(store.dir.glob(".relationship_state.md.*.tmp")) == []  # 临时文件已清


def test_atomic_write_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "x.md"  # 父目录不存在也应自动建
    atomic_write_text(p, "hello\n")
    assert p.read_text(encoding="utf-8") == "hello\n"
    atomic_write_text(p, "world\n")  # 覆盖
    assert p.read_text(encoding="utf-8") == "world\n"


# ---- D1.3 共享 world/ 并发单飞 ----
async def test_world_regen_single_flight(world_root: Path) -> None:
    from wren.core.clock import SystemClock
    from wren.core.life_sim import ensure_world_today
    from wren.core.world import WorldStore

    calls = {"n": 0}

    def responder(_messages: object) -> str:
        calls["n"] += 1
        return "## her day\ntired, paint everywhere.\n\n## beats\n- [window: 09:00–10:00] coffee, alone"

    model = FakeChatModel(responder=responder)
    clock = SystemClock()
    store = WorldStore()
    await asyncio.gather(
        *[asyncio.to_thread(ensure_world_today, clock, store, model) for _ in range(10)]
    )
    assert calls["n"] == 1  # 单飞:10 个并发触发只生成一次


# ---- D1.4 /delete 全清 ----
def test_delete_wipes_everything(data_root: Path) -> None:
    store = UserStore("delme")
    store.init_user()
    store.append_dialogue("user", "hi")
    assert store.exists() and store.dir.exists()
    store.delete()
    assert not store.dir.exists()
    assert not store.exists()
