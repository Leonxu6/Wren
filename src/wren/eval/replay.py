"""p1-eval-wire:把 Phase 0 打分内核接到活 skeleton + trace 回放(线上线下同一把尺)。

红线:eval 不进生产决策链路(只观测/打分,绝不反向改 Step1 判断)。
🔒契约:复用 scorer.score_output,不另起一套。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.pipeline import handle_turn
from ..core.storage import Relationship, UserStore
from ..model.base import ChatModel
from .corpus import EvalCase, load_corpus
from .scorer import OutputScore, score_output

# 同一把尺(线上 Step2 输出 / 离线 case 共用)
score_live_output = score_output

_GENERIC_CRITERIA = (
    "in Wren's voice — dry, autonomous, doesn't serve, can refuse; not a sycophant, not a chatbot"
)


@dataclass
class ReplayRow:
    turn_id: str
    user_turn: str
    bubbles: list[str]
    score: OutputScore

    @property
    def passed(self) -> bool:
        return self.score.passed


@dataclass
class ReplayReport:
    rows: list[ReplayRow] = field(default_factory=list)
    silent_turns: int = 0

    @property
    def pass_rate(self) -> float:
        scored = [r.passed for r in self.rows]
        return sum(scored) / len(scored) if scored else 0.0


def _case_from_trace(t: dict[str, Any], corpus_by_input: dict[str, EvalCase]) -> EvalCase:
    user_turn = t["user_turn"]
    if user_turn in corpus_by_input:
        return corpus_by_input[user_turn]  # 命中语料 → 用其丰富判定标准
    rel = t.get("relationship") or {}
    return EvalCase(
        id=str(t.get("turn_id", "trace")),
        category=1,
        dim="D1",
        input=user_turn,
        pass_criteria=_GENERIC_CRITERIA,
        src="trace-replay",
        lv=str(rel.get("lv")) if rel.get("lv") is not None else None,
    )


def replay_trace_file(jsonl_path: Path, judge_model: ChatModel) -> ReplayReport:
    """读历史 trace,把 {user_turn + 注入态 + step2 输出} 当 case 离线打分。"""
    traces = [
        json.loads(ln) for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    corpus_by_input = {c.input: c for c in load_corpus()}
    report = ReplayReport()
    for t in traces:
        step2 = t.get("step2")
        if step2 is None:  # 沉默轮:无 step2,跳过打分(沉默本身合法)
            report.silent_turns += 1
            continue
        bubbles = list(step2.get("raw_out", []))
        case = _case_from_trace(t, corpus_by_input)
        report.rows.append(
            ReplayRow(
                str(t.get("turn_id", "")),
                t["user_turn"],
                bubbles,
                score_output(case, bubbles, judge_model),
            )
        )
    return report


def _level_for(case: EvalCase) -> int:
    if case.category == 6:
        return 4
    if case.category == 5:
        return 3
    return 0


def score_pipeline_on_corpus(
    cases: list[EvalCase],
    s1_model: ChatModel,
    s2_model: ChatModel,
    judge_model: ChatModel,
    *,
    root: Path,
) -> ReplayReport:
    """对活 skeleton(真实 Step1→Step2)跑语料,给真实 Step2 输出打分。"""
    report = ReplayReport()
    for case in cases:
        store = UserStore(case.id, root)
        store.init_user()
        if case.lv:  # 注入合成关系态(Cat5/6)
            store.write_relationship(
                Relationship(level=_level_for(case), prose=case.lv, freeze=False)
            )
        outcome = handle_turn(case.id, case.input, store, s1_model, s2_model)
        if not outcome.replied:
            report.silent_turns += 1
            continue
        report.rows.append(
            ReplayRow(
                outcome.trace.turn_id,
                case.input,
                outcome.bubbles,
                score_output(case, outcome.bubbles, judge_model),
            )
        )
    return report
