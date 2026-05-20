"""单轮语料载入与校验 —— eval/corpus/single_turn.yaml → list[EvalCase]。

🔒契约:此 schema(尤其 Cat5/6 注入态 lv、Cat3 三失败模式)Phase 2 多轮复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import config

VALID_DIMS = {"D1", "D2", "D3", "D4"}
CAT3_FAIL_MODES = {"servile", "robotic", "contrarian"}


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: int
    dim: str
    input: str
    pass_criteria: str
    src: str
    lv: str | None = None
    gold_output: list[str] | None = None
    also_acceptable: list[list[str]] = field(default_factory=list)
    fail_examples: list[str] = field(default_factory=list)
    fail_modes: dict[str, list[str]] = field(default_factory=dict)  # Cat3:三失败模式各一例
    axis: str | None = None  # Cat3:request / opinion
    mech: dict[str, Any] = field(default_factory=dict)  # 自由备注/期望


def _parse_case(raw: dict[str, Any]) -> EvalCase:
    return EvalCase(
        id=raw["id"],
        category=int(raw["category"]),
        dim=raw["dim"],
        input=raw["input"],
        pass_criteria=raw["pass_criteria"],
        src=raw["src"],
        lv=raw.get("lv"),
        gold_output=raw.get("gold_output"),
        also_acceptable=raw.get("also_acceptable", []) or [],
        fail_examples=raw.get("fail_examples", []) or [],
        fail_modes=raw.get("fail_modes", {}) or {},
        axis=raw.get("axis"),
        mech=raw.get("mech", {}) or {},
    )


def _validate(cases: list[EvalCase]) -> None:
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            raise ValueError(f"重复 case id: {c.id}")
        seen.add(c.id)
        if not 1 <= c.category <= 6:
            raise ValueError(f"{c.id}: category 必须 1-6,得到 {c.category}")
        if c.dim not in VALID_DIMS:
            raise ValueError(f"{c.id}: dim 必须 ∈ {VALID_DIMS},得到 {c.dim}")
        if not c.input or not c.pass_criteria or not c.src:
            raise ValueError(f"{c.id}: input/pass_criteria/src 不可为空")
        if c.category == 3:
            # Cat3 必须带三失败模式各一例(供 judge 区分);供 p0-judge 验收
            missing = CAT3_FAIL_MODES - set(c.fail_modes)
            if missing:
                raise ValueError(f"{c.id}: Cat3 缺失败模式 {missing}")


def load_corpus(path: Path | None = None) -> list[EvalCase]:
    p = path or config.CORPUS_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cases = [_parse_case(c) for c in raw["cases"]]
    _validate(cases)
    return cases


def by_category(cases: list[EvalCase]) -> dict[int, list[EvalCase]]:
    out: dict[int, list[EvalCase]] = {}
    for c in cases:
        out.setdefault(c.category, []).append(c)
    return out
