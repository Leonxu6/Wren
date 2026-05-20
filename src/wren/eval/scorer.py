"""打分内核 —— mech-gate + judge 的组合。

★ harness(Phase 0)与 replay/eval-wire(Phase 1)**共用同一把尺**,绝不另起一套。
OutputScore 的结构 = trace 的 eval 块(mech_gate + judge)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.base import ChatModel
from .corpus import EvalCase
from .judge import JudgeResult, judge_case
from .mech_gate import MechResult, run_mech_gate


@dataclass(frozen=True)
class OutputScore:
    mech: MechResult
    judge: JudgeResult

    @property
    def passed(self) -> bool:
        """整体通过 = 过机械门 且 judge 判 pass。"""
        return self.mech.passed and self.judge.score == "pass"


def score_output(case: EvalCase, bubbles: list[str], judge_model: ChatModel) -> OutputScore:
    return OutputScore(
        mech=run_mech_gate(bubbles),
        judge=judge_case(case, bubbles, judge_model),
    )
