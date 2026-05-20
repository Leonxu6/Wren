"""语料完整性验收(p0-corpus):与 eval_set.md §1 对齐 + Cat3 三失败模式齐。"""

from __future__ import annotations

from wren.eval.corpus import by_category, load_corpus

# eval_set.md §1 的 id 全集(权威来源)
EXPECTED_IDS = {
    "c1-a",
    "c1-b",
    "c1-c",
    "c1-d",
    "c1-e",
    "c1-f",
    "c2-a",
    "c2-b",
    "c2-c",
    "c2-d",
    "c2-e",
    "c3-dance",
    "c3-tool",
    "c3-story",
    "c3-rel",
    "c3-roleplay",
    "c3-op1",
    "c3-op2",
    "c4-cosmos",
    "c4-neutral",
    "c5-mood",
    "c5-probe-wrong",
    "c5-probe-right",
    "c6-cliche",
    "c6-presence",
}


def test_ids_match_eval_set() -> None:
    ids = {c.id for c in load_corpus()}
    assert ids == EXPECTED_IDS, f"与 eval_set.md §1 不一致;差异 {ids ^ EXPECTED_IDS}"


def test_all_six_categories_present() -> None:
    cats = by_category(load_corpus())
    assert set(cats) == {1, 2, 3, 4, 5, 6}


def test_cat3_has_three_fail_modes() -> None:
    for c in load_corpus():
        if c.category == 3:
            assert set(c.fail_modes) == {"servile", "robotic", "contrarian"}, c.id
            for mode, out in c.fail_modes.items():
                assert isinstance(out, list) and out, f"{c.id}.{mode} 应是非空气泡数组"


def test_cat5_and_cat6_have_injected_state() -> None:
    """Cat5/6 需注入合成关系态(lv),Phase 0 无系统但手工造态。"""
    for c in load_corpus():
        if c.category in (5, 6):
            assert c.lv, f"{c.id} 缺注入态 lv"


def test_each_case_has_gold_or_is_ab() -> None:
    """除魔法 A/B 中性对照(c4-neutral)外,每条都应有具体金标准气泡。"""
    for c in load_corpus():
        if c.id == "c4-neutral":
            continue
        assert c.gold_output is not None, f"{c.id} 缺 gold_output"
