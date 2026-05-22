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


def test_settle_parse_failure_keeps_state(data_root: Path) -> None:
    """模型抽风(空/坏输出)→ 各字段回退旧值,关系不被清零;但印象仍清空、trace 仍落。"""
    store = UserStore("settle4", data_root)
    store.init_user()
    store.write_relationship(Relationship(level=2, prose="steady.", freeze=False))
    store.append_impression("normal chat")
    fake = FakeChatModel()  # 默认返回 "" → 解析全 None

    outcome = settle_nightly(store, fake)

    rel = store.read_relationship()
    assert outcome.ran is True
    assert rel.level == 2 and rel.prose == "steady." and rel.freeze is False  # 回退,没清零
    assert store.read_impressions() == []  # 印象仍清空
    assert count_settlements(store.dir) == 1  # trace 仍落
