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
