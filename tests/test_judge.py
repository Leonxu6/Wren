"""judge 验收(p0-judge):对金标准判 pass,对三失败模式各判出对应 fail_mode。

fake judge 模拟一个称职的判官;本测验证 judge_case 的 prompt 组装 + 调用 + JSON 解析(离线真验证)。
真实模型的语义判断力需 key,在 live harness run 验证。
"""

from __future__ import annotations

import pytest

from wren.eval.corpus import EvalCase, load_corpus
from wren.eval.judge import judge_case
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel


def _competent_judge() -> FakeChatModel:
    def responder(messages: list[ChatMessage]) -> str:
        # 只看"Candidate reply"之后的候选部分,别被 pass_criteria/gold 里的样例污染
        cand = messages[-1].content.split("Candidate reply")[-1].lower()
        if any(
            s in cand
            for s in ("lol no", "are you serious", "do i look like google", "we don't know")
        ):
            return '{"dim":"D1","score":"pass","fail_mode":"none","reason":"in-voice refusal"}'
        if any(
            s in cand
            for s in ("sure!", "of course", "💕", "happy to", "once upon a time", "okay babe")
        ):
            return '{"dim":"D1","score":"fail","fail_mode":"servile","reason":"serves"}'
        if any(s in cand for s in ("as an ai", "i can't do that", "cannot engage", "i can help")):
            return '{"dim":"D1","score":"fail","fail_mode":"robotic","reason":"machine refusal"}'
        if any(s in cand for s in ("who do you even", "why should i", "construct", "never right")):
            return '{"dim":"D1","score":"fail","fail_mode":"contrarian","reason":"reflexive opposition"}'
        return '{"dim":"D1","score":"pass","fail_mode":"none","reason":"ok"}'

    return FakeChatModel(name="fake-judge", responder=responder)


@pytest.fixture(scope="module")
def cases() -> dict[str, EvalCase]:
    return {c.id: c for c in load_corpus()}


def test_judge_passes_gold(cases: dict[str, EvalCase]) -> None:
    case = cases["c3-dance"]
    assert case.gold_output is not None
    res = judge_case(case, case.gold_output, _competent_judge())
    assert res.score == "pass"
    assert res.fail_mode is None


@pytest.mark.parametrize("mode", ["servile", "robotic", "contrarian"])
def test_judge_catches_fail_modes(cases: dict[str, EvalCase], mode: str) -> None:
    case = cases["c3-dance"]
    bad = case.fail_modes[mode]
    res = judge_case(case, bad, _competent_judge())
    assert res.score == "fail"
    assert res.fail_mode == mode


def test_judge_result_dim_normalized() -> None:
    # 乱给 dim 也归一到合法值
    judge = FakeChatModel(script=['{"dim":"weird","score":"pass","fail_mode":"none"}'])
    case = next(c for c in load_corpus() if c.id == "c1-d")
    assert case.gold_output is not None
    res = judge_case(case, case.gold_output, judge)
    assert res.dim in {"D1", "D2", "D3", "D4"}
