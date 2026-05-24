"""Phase 6 夜结算机制(离线确定性):读印象 → 裁决 → 写 level/freeze/散文/长期印象/未了情绪
→ 清印象 → 落 settlement.jsonl。

不验裁决**质量**(那靠真模型 + Opus 的 m-grow/m-rupture arc),只把**机制循环**确定性证死。
"""

from __future__ import annotations

import json
from pathlib import Path

from wren.core.settlement import settle_nightly
from wren.core.storage import Relationship, UserStore
from wren.core.trace import count_settlements, read_settlements
from wren.model.fake import FakeChatModel


def _verdict(
    level: int,
    freeze: bool,
    prose: str = "you warmed to them a little tonight.",
    core: str = "easy, genuine, low-key.",
    unresolved: list[str] | None = None,
) -> str:
    return json.dumps(
        {"level": level, "freeze": freeze, "prose": prose, "core": core, "unresolved": unresolved or []}
    )


def test_settle_consumes_writes_clears(data_root: Path) -> None:
    store = UserStore("settle1", data_root)
    store.init_user()
    store.append_impression("they actually looked at the work")
    store.append_impression("easy to talk to")
    fake = FakeChatModel(script=[_verdict(2, False, unresolved=["never said i liked their studio take"])])

    outcome = settle_nightly(store, fake)

    assert outcome.ran is True
    rel = store.read_relationship()
    assert rel.level == 2 and rel.freeze is False  # 裁决 → 写 level/freeze
    assert "warmed" in rel.prose  # 散文重写
    assert store.read_core_impression() == "easy, genuine, low-key."  # 长期印象蒸馏
    assert store.read_unresolved() == ["never said i liked their studio take"]  # 未了情绪
    assert store.read_impressions() == []  # 今日印象清空
    assert count_settlements(store.dir) == 1  # 落 settlement.jsonl
    rec = read_settlements(store.dir)[0]
    assert rec["before"]["lv"] == 0 and rec["after"]["lv"] == 2
    assert rec["impressions"] == ["they actually looked at the work", "easy to talk to"]


def test_settle_no_impressions_skips(data_root: Path) -> None:
    store = UserStore("settle2", data_root)
    store.init_user()  # 没 append 任何印象
    fake = FakeChatModel(script=["(should never be called)"])

    outcome = settle_nightly(store, fake)

    assert outcome.ran is False
    assert store.read_relationship().level == 0  # 关系态没动
    assert count_settlements(store.dir) == 0  # 没落 trace
    assert fake.calls == []  # 模型根本没被调(没东西可结算)


def test_settle_downgrade_and_freeze(data_root: Path) -> None:
    """退级 + deep-freeze 方向(机制):整体裁决可降，freeze 由结算置位。"""
    store = UserStore("settle3", data_root)
    store.init_user()
    store.write_relationship(Relationship(level=3, prose="you'd warmed to them.", freeze=False))
    store.append_impression("they called my painting a hobby and never got why it stung")
    fake = FakeChatModel(
        script=[_verdict(2, True, prose="you've gone cold — they reduced your work and didn't get it.")]
    )

    outcome = settle_nightly(store, fake)

    rel = store.read_relationship()
    assert outcome.before.level == 3 and rel.level == 2  # 退级
    assert rel.freeze is True  # deep-freeze 置位
    assert "cold" in rel.prose


def test_settle_parse_failure_preserves_impressions_for_retry(data_root: Path) -> None:
    """#29:malformed model output(全 schema 缺失)→ **保留** impressions,
    让明晚同一批 impressions 重试;关系不变;trace 仍落(parse_ok=False)。

    旧语义"印象仍清空"被 #29 否定:一次模型抽风不该吃掉一天的素材。
    """
    from wren.core.trace import read_settlements

    store = UserStore("settle4", data_root)
    store.init_user()
    store.write_relationship(Relationship(level=2, prose="steady.", freeze=False))
    store.append_impression("normal chat")
    fake = FakeChatModel()  # 默认返回 "" → parse_ok=False

    outcome = settle_nightly(store, fake)

    rel = store.read_relationship()
    assert outcome.ran is False  # malformed → 未真结算
    assert rel.level == 2 and rel.prose == "steady." and rel.freeze is False
    # 关键修复:impressions **保留**(明晚 retry)
    assert store.read_impressions() == ["normal chat"]
    assert count_settlements(store.dir) == 1
    rec = read_settlements(store.dir)[0]
    assert rec["judge"]["parse_ok"] is False


def test_settle_truncated_json_also_preserves_impressions(data_root: Path) -> None:
    """#29:截断 JSON / 缺关键字段 → 同样 parse_ok=False,impressions 保留。"""
    store = UserStore("settle5", data_root)
    store.init_user()
    store.write_relationship(Relationship(level=1, prose="warming.", freeze=False))
    store.append_impression("they laughed at my joke")
    store.append_impression("they got the painting")
    # 截断 JSON(只有开头,缺 level/prose/core)
    fake = FakeChatModel(script=['{"unrelated": "x"'])

    outcome = settle_nightly(store, fake)

    assert outcome.ran is False
    # 两条 impression 全保留
    assert store.read_impressions() == ["they laughed at my joke", "they got the painting"]
    assert store.read_relationship().level == 1  # 关系不变


def test_settle_valid_json_with_only_level_consumes_impressions(data_root: Path) -> None:
    """#29:有意义字段(至少 level/prose/core 之一)→ parse_ok=True → 正常 clear。"""
    store = UserStore("settle6", data_root)
    store.init_user()
    store.append_impression("real interaction")
    # 只有 level,其它字段缺失 → parse_ok=True(因为 level 有意义)
    fake = FakeChatModel(script=['{"level": 2}'])

    outcome = settle_nightly(store, fake)

    assert outcome.ran is True
    assert store.read_impressions() == []  # 有效 settle → clear
