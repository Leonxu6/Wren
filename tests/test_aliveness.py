"""活度集(aliveness suite)fake 模式离线契约验证 —— loader/schema、judge schema、
真 skeleton 端到端跑通、聚合(每 tell 通过率 + 最常犯哪个)。内容由 fake 脚本提供,只验机制。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from wren.eval.aliveness import (
    AliveCaseRun,
    aggregate,
    run_alive_case,
    run_aliveness,
)
from wren.eval.corpus import AliveCase, by_tell, load_aliveness
from wren.eval.judge import AliveJudgeResult, judge_alive
from wren.model.fake import FakeChatModel
from wren.prompts.judge import parse_alive_judge

_S1 = json.dumps({"monologue": "whatever", "reply": True, "delay_s": 2, "impression": "", "memory": []})
_S2 = json.dumps({"messages": ["mm"]})


def _responder(messages: list) -> str:
    """分辨 step1 / step2 / alive-judge,各回合法输出。alive judge 先于通用 judge 判(其 prompt 含两者标记)。"""
    blob = " ".join(m.content for m in messages)
    if "deadness of an AI" in blob:  # alive judge(唯一标记)
        return json.dumps({"t1": False, "t2": False, "t3": False, "alive": True, "reason": "ok"})
    if "LOCKED INNER VOICE" in blob:  # step2
        return _S2
    if "private head" in blob:  # step1
        return _S1
    return ""


def _fake() -> FakeChatModel:
    return FakeChatModel(responder=_responder)


# ---------- loader / schema ----------


def test_load_aliveness_validates_real_corpus() -> None:
    cases = load_aliveness()
    assert len(cases) >= 12
    for c in cases:
        assert c.tell in {"T1", "T2", "T3"}
        assert c.input and c.src
        assert c.target_flat and c.target_alive  # behavioral 靶心非空
        assert 0 <= c.level <= 6


def test_alive_case_carries_no_gold_output() -> None:
    """🔒原则:活度集绝不写 gold_output(不背范句)。"""
    names = {f.name for f in fields(AliveCase)}
    assert "gold_output" not in names
    assert {"target_flat", "target_alive", "fail_anchor"} <= names


def test_by_tell_groups_all_three() -> None:
    grouped = by_tell(load_aliveness())
    assert set(grouped) == {"T1", "T2", "T3"}
    assert all(grouped[t] for t in ("T1", "T2", "T3"))


def test_validation_rejects_bad_tell_and_empty_target(tmp_path: Path) -> None:
    from wren.eval.corpus import load_aliveness as _load

    bad_tell = tmp_path / "bad_tell.yaml"
    bad_tell.write_text(
        'cases:\n  - id: x\n    tell: T9\n    input: "hi"\n    target: {flat: "a", alive: "b"}\n    src: "s"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tell"):
        _load(bad_tell)

    empty_target = tmp_path / "empty_target.yaml"
    empty_target.write_text(
        'cases:\n  - id: y\n    tell: T1\n    input: "hi"\n    target: {flat: "", alive: ""}\n    src: "s"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="target"):
        _load(empty_target)


# ---------- judge schema(纯函数)----------


def test_parse_alive_judge_handles_bools_strings_and_defaults() -> None:
    d = parse_alive_judge('{"t1": true, "t2": "false", "t3": "yes", "alive": false, "reason": " r "}')
    assert d == {"t1": True, "t2": False, "t3": True, "alive": False, "reason": "r"}
    # 缺字段 → 安全默认(不崩),全 absent
    d2 = parse_alive_judge("not json at all")
    assert d2["t1"] is False and d2["alive"] is False


def test_alive_judge_result_passed_and_fired() -> None:
    clean = AliveJudgeResult(t1=False, t2=False, t3=False, alive=True)
    assert clean.passed and clean.fired == []
    flat = AliveJudgeResult(t1=True, t2=False, t3=True, alive=False)
    assert not flat.passed and flat.fired == ["T1", "T3"]


# ---------- 端到端(真 skeleton,fake 模型)----------


def test_run_alive_case_runs_skeleton_and_judges(data_root: Path) -> None:
    case = load_aliveness()[0]
    run = run_alive_case(case, "alive-t", gen_model=_fake(), judge_model=_fake(), root=data_root)
    assert run.bubbles == ["mm"]  # step1→step2 真跑通
    assert run.mech_passed and run.judge is not None and run.judge.passed
    assert run.passed


def test_no_judge_skips_judging_but_still_runs(data_root: Path) -> None:
    case = load_aliveness()[0]
    run = run_alive_case(case, "alive-nj", gen_model=_fake(), judge_model=None, root=data_root)
    assert run.judge is None
    assert run.bubbles == ["mm"]
    assert not run.passed  # 没判 → 不算过


def test_setup_injects_level_prose_into_step1(data_root: Path) -> None:
    case = next(c for c in load_aliveness() if c.level > 0 and c.setup)
    fake = _fake()
    run_alive_case(case, "alive-setup", gen_model=fake, judge_model=None, root=data_root)
    step1_blobs = [
        " ".join(m.content for m in c) for c in fake.calls if any("private head" in m.content for m in c)
    ]
    assert step1_blobs and any(case.setup.split()[0] in b for b in step1_blobs)


def test_judge_alive_builds_request_with_targets(data_root: Path) -> None:
    case = load_aliveness()[0]
    fake = _fake()
    judge_alive(case, ["mm"], fake)
    blob = " ".join(m.content for c in fake.calls for m in c)
    assert "deadness of an AI" in blob  # 用了活度 rubric
    assert case.target_flat[:6] in blob and case.target_alive[:6] in blob  # 靶心进了 prompt


# ---------- 聚合(每 tell 通过率 + 最常犯哪个)----------


def test_run_aliveness_reps_and_aggregate(data_root: Path) -> None:
    cases = by_tell(load_aliveness())
    subset = [cases["T1"][0], cases["T2"][0], cases["T3"][0]]
    runs = run_aliveness(subset, gen_model=_fake(), judge_model=_fake(), root=data_root, reps=2)
    assert len(runs) == 6  # 3 cases × 2 reps
    report = aggregate(runs)
    assert report.overall == 1.0 and report.meets  # fake judge 全 alive
    assert set(report.per_tell()) == {"T1", "T2", "T3"}
    assert all(v == 1.0 for v in report.per_tell().values())
    assert report.judged_runs == 6
    assert report.tell_fires == {"T1": 0, "T2": 0, "T3": 0}


def test_aggregate_counts_tell_fires_and_per_tell_rate() -> None:
    """纯函数:T1 case 一过一犯 → T1 通过率 0.5、T1 fire 计 1。"""
    j_pass = AliveJudgeResult(t1=False, t2=False, t3=False, alive=True)
    j_t1 = AliveJudgeResult(t1=True, t2=False, t3=False, alive=False)
    runs = [
        AliveCaseRun("a-t1-x", "T1", ["mm"], True, [], j_pass),
        AliveCaseRun("a-t1-x", "T1", [], True, [], j_t1),
        AliveCaseRun("a-t3-y", "T3", ["studio"], True, [], j_pass),
    ]
    report = aggregate(runs)
    per = report.per_tell()
    assert per["T1"] == 0.5 and per["T3"] == 1.0
    assert report.tell_fires["T1"] == 1 and report.tell_fires["T3"] == 0
    assert report.judged_runs == 3
