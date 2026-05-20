"""机械门验收(p0-mech-gate):喂金标准全过 / 喂反例逐项标红。"""

from __future__ import annotations

import pytest

from wren.eval.corpus import EvalCase, load_corpus
from wren.eval.mech_gate import run_mech_gate

SIGNATURE_GOLDENS = ["c1-d", "c2-a", "c5-mood"]  # §7.4 逐字金标准(todo p0-mech-gate 验收点名)


@pytest.fixture(scope="module")
def cases() -> dict[str, EvalCase]:
    return {c.id: c for c in load_corpus()}


def test_signature_goldens_pass(cases: dict[str, EvalCase]) -> None:
    for cid in SIGNATURE_GOLDENS:
        gold = cases[cid].gold_output
        assert gold is not None
        res = run_mech_gate(gold)
        assert res.passed, f"{cid} 金标准应过机械门,却命中 {res.hits}"


def test_all_gold_outputs_pass(cases: dict[str, EvalCase]) -> None:
    """不变量:语料里所有金标准 + also_acceptable 都必须过机械门。"""
    for c in cases.values():
        candidates = [c.gold_output, *c.also_acceptable]
        for out in candidates:
            if out is None:
                continue
            res = run_mech_gate(out)
            assert res.passed, f"{c.id} 输出 {out} 应过门,命中 {[h.rule for h in res.hits]}"


@pytest.mark.parametrize(
    "bubbles,rule",
    [
        (["i'm here for you", "let me know if you need anything"], "banned_phrase"),
        (["lol", "🙂", "🙃", "💀"], "emoji_count"),
        (["nothing."], "dead_end"),
        (["aww", "🥰"], "blacklist_emoji"),
        (
            [
                "this message keeps going on and on well past the fifteen word ceiling for absolutely no good reason"
            ],
            "length",
        ),
        (["mm… fineee 🙂."], "signal_overload"),
        (["how was your day", "what did you eat", "did you sleep ok"], "followup"),
        (["hey babe"], "petname"),
        (["you're so pretty"], "flattery"),
        (["slay queen"], "cringe_vocab"),
    ],
)
def test_violation_flagged(bubbles: list[str], rule: str) -> None:
    res = run_mech_gate(bubbles)
    assert not res.passed
    assert rule in res.rules(), f"期望命中 {rule},实际 {res.rules()}"


def test_silence_passes() -> None:
    assert run_mech_gate([]).passed


def test_long_with_dash_is_allowed() -> None:
    """>15 词但有破折号(§7.1『我在认真表达』的理由标志)→ 不判 length。"""
    bubbles = [
        "i don't know — it's the kind of thing where you sink years into it and still feel like a fraud somehow"
    ]
    assert "length" not in run_mech_gate(bubbles).rules()
