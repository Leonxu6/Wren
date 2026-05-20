"""storage 验收(p1-storage):init/读回 + 写边界铁律 + 无积分。"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from wren.core.storage import Relationship, UserStore


def test_init_and_read(data_root: Path) -> None:
    s = UserStore("12345", data_root)
    s.init_user()
    assert s.exists()
    r = s.read_relationship()
    assert r.level == 0 and not r.freeze and r.prose
    assert "dani" in s.read_inner_voice().lower()  # t=0 inner voice 已种


def test_relationship_has_no_points_field() -> None:
    names = {f.name for f in fields(Relationship)}
    assert names == {"level", "prose", "freeze"}
    assert "points" not in names and "score" not in names  # §0① 非积分制


def test_no_world_or_canon_write_api() -> None:
    """写边界铁律靠『代码路径不存在』保证。"""
    api = [m for m in dir(UserStore) if not m.startswith("__")]
    assert not any("world" in m or "canon" in m for m in api)


def test_chat_id_traversal_rejected(data_root: Path) -> None:
    with pytest.raises(ValueError):
        UserStore("../evil", data_root)
    with pytest.raises(ValueError):
        UserStore("a/b", data_root)


def test_dir_is_confined_under_root(data_root: Path) -> None:
    s = UserStore("42", data_root)
    assert data_root in s.dir.parents


def test_round_trip_relationship(data_root: Path) -> None:
    s = UserStore("3", data_root)
    s.init_user()
    s.write_relationship(Relationship(level=3, prose="friends now", freeze=True))
    r = s.read_relationship()
    assert r.level == 3 and r.prose == "friends now" and r.freeze is True


def test_dialogue_and_impressions(data_root: Path) -> None:
    s = UserStore("7", data_root)
    s.init_user()
    s.append_dialogue("user", "hey")
    s.append_dialogue("wren", "hey")
    s.append_impression("noticed the small painting")
    assert "user: hey" in s.read_recent_dialogue()


def test_delete_wipes_everything(data_root: Path) -> None:
    s = UserStore("99", data_root)
    s.init_user()
    s.append_dialogue("user", "x")
    assert s.dir.exists()
    s.delete()
    assert not s.dir.exists()


# ---- events(中期记忆 · Phase 3)----


def test_event_round_trip(data_root: Path) -> None:
    s = UserStore("ev1", data_root)
    s.init_user()
    s.append_event("landlord fixed the heat", topic="heat", valence="neutral", salience="low")
    s.append_event("mom coming to the city", topic="mom", valence="neg", salience="high")
    evs = s.read_event_list()
    assert [e.text for e in evs] == ["landlord fixed the heat", "mom coming to the city"]
    assert evs[1].topic == "mom" and evs[1].salience == "high"
    block = s.read_events()
    assert "[heat|neutral|low] landlord fixed the heat" in block
    assert "[mom|neg|high] mom coming to the city" in block


def test_events_empty_when_none(data_root: Path) -> None:
    s = UserStore("ev2", data_root)
    s.init_user()
    assert s.read_events() == ""  # stub 头不含事件行
    assert s.read_event_list() == []


def test_append_event_sanitizes_separators(data_root: Path) -> None:
    s = UserStore("ev3", data_root)
    s.init_user()
    s.append_event("got a raise | finally]", topic="work|life", valence="pos", salience="med")
    evs = s.read_event_list()
    assert len(evs) == 1  # 分隔符被清理,行仍可解析
    assert "|" not in evs[0].text and "]" not in evs[0].text


def test_append_event_skips_empty_text(data_root: Path) -> None:
    s = UserStore("ev4", data_root)
    s.init_user()
    s.append_event("   ", topic="x", valence="neutral", salience="low")
    assert s.read_event_list() == []


def test_event_cap_keeps_salient_and_recent(data_root: Path) -> None:
    s = UserStore("ev5", data_root)
    s.init_user()
    s.append_event("keeper", topic="big", valence="neg", salience="high")  # 最旧,但高 salience
    for i in range(1, 6):
        s.append_event(f"x{i}", topic="t", valence="neutral", salience="low")
    texts = [e.text for e in s.read_event_list(cap=3)]
    # 高 salience 即便最旧也留;低 salience 先逐出最旧的(x1-x3);近期低(x4,x5)留;时间序输出
    assert texts == ["keeper", "x4", "x5"]
