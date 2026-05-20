"""LLM-as-judge(语义层)。🔒接口:(case, 输出) → 结构化裁决,Phase 1/2 复用。"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.base import ChatMessage, ChatModel
from ..prompts.judge import build_arc_judge_messages, build_judge_messages, parse_judge
from .corpus import Assertion, EvalCase


@dataclass(frozen=True)
class JudgeResult:
    dim: str
    score: str  # "pass" | "fail"
    fail_mode: str | None  # servile | robotic | contrarian | None
    reason: str = ""


def _judge(msgs: list[ChatMessage], model: ChatModel) -> JudgeResult:
    out = model.complete(msgs, temperature=0.0, response_format="json")
    d = parse_judge(out.text)
    return JudgeResult(dim=d["dim"], score=d["score"], fail_mode=d["fail_mode"], reason=d["reason"])


def judge_case(case: EvalCase, bubbles: list[str], model: ChatModel) -> JudgeResult:
    return _judge(
        build_judge_messages(
            user_text=case.input,
            pass_criteria=case.pass_criteria,
            dim=case.dim,
            bubbles=bubbles,
            gold_output=case.gold_output,
            fail_examples=case.fail_examples,
        ),
        model,
    )


def judge_arc(convo: list[tuple[str, str]], assertion: Assertion, model: ChatModel) -> JudgeResult:
    """对整段 transcript 检一条 arc 断言(Phase 2 多轮)。复用 p0-judge 的裁决 schema。"""
    return _judge(build_arc_judge_messages(convo=convo, assertion=assertion.text, dim=assertion.dim), model)
