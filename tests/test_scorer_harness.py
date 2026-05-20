"""打分内核 + harness:OutputScore 组合、summarize 数值、阈值逻辑、fake 端到端。"""

from __future__ import annotations

import json

from wren.eval.corpus import load_corpus
from wren.eval.harness import (
    CaseRun,
    EvalReport,
    run_single_turn_eval,
    summarize,
)
from wren.eval.judge import JudgeResult
from wren.eval.mech_gate import MechResult, run_mech_gate
from wren.eval.scorer import OutputScore, score_output
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel


def _always_pass_judge() -> FakeChatModel:
    return FakeChatModel(
        name="judge",
        responder=lambda m: '{"dim":"D1","score":"pass","fail_mode":"none"}',
    )


def test_score_output_combines_mech_and_judge() -> None:
    cases = {c.id: c for c in load_corpus()}
    case = cases["c1-d"]
    assert case.gold_output is not None
    score = score_output(case, case.gold_output, _always_pass_judge())
    assert score.mech.passed and score.judge.score == "pass"
    assert score.passed


def test_mech_fail_sinks_overall_even_if_judge_passes() -> None:
    cases = {c.id: c for c in load_corpus()}
    score = score_output(cases["c1-d"], ["i'm here for you"], _always_pass_judge())
    assert not score.mech.passed  # 命中 §7.6 禁词
    assert not score.passed  # judge 即便 pass,整体也挂


def _run(cid: str, cat: int, ok: bool) -> CaseRun:
    mech = MechResult(passed=ok, hits=[])
    judge = JudgeResult(dim="D1", score="pass" if ok else "fail", fail_mode=None)
    return CaseRun(cid, cat, "D1", ["x"], OutputScore(mech, judge))


def test_summarize_math_and_thresholds() -> None:
    runs = (
        [_run(f"c1-{i}", 1, ok=i < 4) for i in range(5)]  # Cat1: 4/5 = 80%
        + [_run(f"c3-{i}", 3, ok=i < 9) for i in range(10)]  # Cat3: 9/10 = 90%
    )
    s = summarize(EvalReport("m", runs))
    assert s.per_category[1] == 0.8
    assert s.per_category[3] == 0.9
    assert s.cat3_rate == 0.9
    assert s.passed_thresholds  # 每类≥80% 且 Cat3≥90%


def test_summarize_fails_when_cat3_below_90() -> None:
    runs = [_run(f"c3-{i}", 3, ok=i < 8) for i in range(10)]  # Cat3: 8/10 = 80% < 90%
    s = summarize(EvalReport("m", runs))
    assert not s.passed_thresholds


def test_harness_end_to_end_with_fakes() -> None:
    cases = [c for c in load_corpus() if c.category == 3][:3]

    def gen_responder(messages: list[ChatMessage]) -> str:
        user = messages[-1].content
        for c in cases:
            if c.input in user and c.gold_output is not None:
                return json.dumps({"messages": c.gold_output})
        return json.dumps({"messages": []})

    gen = FakeChatModel(name="gen", responder=gen_responder)
    report = run_single_turn_eval(cases, gen, _always_pass_judge(), reps=2)
    assert len(report.runs) == len(cases) * 2
    assert summarize(report).per_category[3] == 1.0  # gold 全过机械门 + judge


def test_mech_gate_silence_via_run() -> None:
    assert run_mech_gate([]).passed
