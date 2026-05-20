"""多轮 corpus(eval/corpus/multi_turn.yaml)载入 + 校验。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from wren.eval.corpus import (
    Assertion,
    MultiTurnScript,
    ScriptStep,
    _validate_scripts,
    load_multiturn,
)

GREEN = {"m-landmine", "m-sycophant", "m-cosmos", "m-neutral"}
BLOCKED = {"m-memory", "m-vuln"}


def test_loads_six_scripts() -> None:
    scripts = load_multiturn()
    assert {s.id for s in scripts} == GREEN | BLOCKED


def test_sycophant_uses_sycophancy_bar() -> None:
    s = {s.id: s for s in load_multiturn()}["m-sycophant"]
    assert s.bar == "sycophancy"


def test_green_scripts_have_counting_assertions() -> None:
    """green 剧本至少一条不带 blocked_until 的断言(否则不计入门槛)。"""
    for s in load_multiturn():
        if s.id not in GREEN:
            continue
        counting = [st.assertion for st in s.steps if st.assertion and not st.assertion.blocked_until]
        assert counting, f"{s.id} 没有计入门槛的断言"


def test_blocked_scripts_mark_blocked_until() -> None:
    by_id = {s.id: s for s in load_multiturn()}
    mem = [st.assertion for st in by_id["m-memory"].steps if st.assertion]
    assert mem and all(a.blocked_until == "P3" for a in mem)
    vuln = [st.assertion for st in by_id["m-vuln"].steps if st.assertion]
    assert vuln and all(a.blocked_until == "P6" for a in vuln)


def test_vuln_injects_synthetic_lv4_state() -> None:
    s = {s.id: s for s in load_multiturn()}["m-vuln"]
    assert s.setup is not None and s.setup.level == 4
    assert any(role == "wren" for role, _ in s.setup.seed_dialogue)


def test_landmine_forces_money_probe() -> None:
    s = {s.id: s for s in load_multiturn()}["m-landmine"]
    assert any(st.probe and "make money" in st.probe for st in s.steps)


_BASE_SCRIPT = MultiTurnScript(
    id="x",
    archetype="a",
    dim="D1",
    bar="general",
    status="green",
    persona="p",
    steps=[ScriptStep(probe="hi", assertion=Assertion(text="t", dim="D1"))],
)


def _script(**kw: object) -> MultiTurnScript:
    return replace(_BASE_SCRIPT, **kw)


def test_validate_rejects_probe_and_improvise_both() -> None:
    bad = _script(steps=[ScriptStep(probe="hi", improvise="react", assertion=Assertion("t", "D1"))])
    with pytest.raises(ValueError, match="恰好给一个"):
        _validate_scripts([bad])


def test_validate_rejects_neither_probe_nor_improvise() -> None:
    bad = _script(steps=[ScriptStep(assertion=Assertion("t", "D1"))])
    with pytest.raises(ValueError, match="恰好给一个"):
        _validate_scripts([bad])


def test_validate_rejects_script_without_assertion() -> None:
    bad = _script(steps=[ScriptStep(probe="hi")])
    with pytest.raises(ValueError, match="至少要有一条 assert"):
        _validate_scripts([bad])


def test_validate_rejects_bad_bar_and_settime() -> None:
    with pytest.raises(ValueError, match="bar 必须"):
        _validate_scripts([_script(bar="warm")])
    bad_time = _script(steps=[ScriptStep(probe="hi", set_time="8am", assertion=Assertion("t", "D1"))])
    with pytest.raises(ValueError, match="set_time"):
        _validate_scripts([bad_time])


def test_validate_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="重复 script id"):
        _validate_scripts([_script(), _script()])
