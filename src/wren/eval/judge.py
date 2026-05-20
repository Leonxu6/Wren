"""LLM-as-judge(语义层)。🔒接口:(case, 输出) → 结构化裁决,Phase 1/2 复用。"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.base import ChatModel
from ..prompts.judge import build_judge_messages, parse_judge
from .corpus import EvalCase


@dataclass(frozen=True)
class JudgeResult:
    dim: str
    score: str  # "pass" | "fail"
    fail_mode: str | None  # servile | robotic | contrarian | None
    reason: str = ""


def judge_case(case: EvalCase, bubbles: list[str], model: ChatModel) -> JudgeResult:
    msgs = build_judge_messages(
        user_text=case.input,
        pass_criteria=case.pass_criteria,
        dim=case.dim,
        bubbles=bubbles,
        gold_output=case.gold_output,
        fail_examples=case.fail_examples,
    )
    out = model.complete(msgs, temperature=0.0, response_format="json")
    d = parse_judge(out.text)
    return JudgeResult(dim=d["dim"], score=d["score"], fail_mode=d["fail_mode"], reason=d["reason"])
