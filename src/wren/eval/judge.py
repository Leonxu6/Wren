"""LLM-as-judge(语义层)。🔒接口:(case, 输出) → 结构化裁决,Phase 1/2 复用。"""

from __future__ import annotations

from dataclasses import dataclass

from ..model.base import ChatMessage, ChatModel
from ..prompts.judge import (
    build_alive_judge_messages,
    build_arc_judge_messages,
    build_judge_messages,
    parse_alive_judge,
    parse_judge,
)
from .corpus import AliveCase, Assertion, EvalCase


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


# ---------- 活度判分(aliveness suite)----------


@dataclass(frozen=True)
class AliveJudgeResult:
    """活度判:3 个 AI 味失败模式各 present/absent + 整体 alive/flat。present(True)= 该失败犯了。"""

    t1: bool  # 情绪缺席/该恼不恼
    t2: bool  # 太好说话/没棱角
    t3: bool  # 通用甜妹/零具体
    alive: bool  # judge 整体判读(headline,与「无 tell 犯」通常一致)
    reason: str = ""

    @property
    def fired(self) -> list[str]:
        return [t for t, v in (("T1", self.t1), ("T2", self.t2), ("T3", self.t3)) if v]

    @property
    def passed(self) -> bool:
        """pass = 3 个 tell 都没犯(plan 决策7;机械门在 runner 侧另判)。"""
        return not (self.t1 or self.t2 or self.t3)


def judge_alive(case: AliveCase, bubbles: list[str], model: ChatModel) -> AliveJudgeResult:
    out = model.complete(
        build_alive_judge_messages(
            user_text=case.input,
            bubbles=bubbles,
            tell=case.tell,
            target_flat=case.target_flat,
            target_alive=case.target_alive,
            level=case.level,
            setup=case.setup,
            fail_anchor=case.fail_anchor,
        ),
        temperature=0.0,
        response_format="json",
    )
    d = parse_alive_judge(out.text)
    return AliveJudgeResult(t1=d["t1"], t2=d["t2"], t3=d["t3"], alive=d["alive"], reason=d["reason"])
