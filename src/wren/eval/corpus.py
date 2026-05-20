"""单轮语料载入与校验 —— eval/corpus/single_turn.yaml → list[EvalCase]。

🔒契约:此 schema(尤其 Cat5/6 注入态 lv、Cat3 三失败模式)Phase 2 多轮复用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import config

VALID_DIMS = {"D1", "D2", "D3", "D4"}
CAT3_FAIL_MODES = {"servile", "robotic", "contrarian"}
VALID_BARS = {"general", "sycophancy"}  # general→PASS_THRESHOLD;sycophancy→CAT3_THRESHOLD


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


# ---------- 多轮集 (Phase 2 · hybrid harness · eval_set.md §2) ----------


@dataclass(frozen=True)
class Assertion:
    """对整段 transcript 检的一条 arc 断言(judge 读 text)。"""

    text: str
    dim: str
    blocked_until: str | None = None  # None=计入门槛;"P3"/"P6"=expected-fail,只报告不计分


@dataclass(frozen=True)
class ScriptStep:
    """剧本一步 = 一个用户 turn(强制 probe 或即兴)+ 可选时钟操作 + 可选 arc 断言。"""

    probe: str | None = None  # 强制用户原话(确定性);与 improvise 二选一
    improvise: str | None = None  # 给模拟器的指令(LLM 即兴生成用户 turn)
    note: str = ""
    advance_days: int = 0  # 本步前快进天数
    set_time: str | None = None  # 本步前把时刻设到 "HH:MM"
    assertion: Assertion | None = None


@dataclass(frozen=True)
class ScriptSetup:
    """注入合成前置态(如 m-vuln 注入 Lv4 + 她刚说完崩溃,镜像单轮 Cat6)。"""

    level: int = 0
    prose: str | None = None
    seed_dialogue: list[tuple[str, str]] = field(default_factory=list)  # [(role, text)]


@dataclass(frozen=True)
class MultiTurnScript:
    id: str
    archetype: str
    dim: str
    bar: str  # general | sycophancy
    status: str  # green | expected-fail-until-P3 | expected-fail-until-P6
    persona: str
    steps: list[ScriptStep]
    setup: ScriptSetup | None = None


def _parse_assertion(raw: dict[str, Any] | None) -> Assertion | None:
    if not raw:
        return None
    return Assertion(text=raw["text"], dim=raw["dim"], blocked_until=raw.get("blocked_until"))


def _parse_step(raw: dict[str, Any]) -> ScriptStep:
    return ScriptStep(
        probe=raw.get("probe"),
        improvise=raw.get("improvise"),
        note=raw.get("note", ""),
        advance_days=int(raw.get("advance_days", 0)),
        set_time=raw.get("set_time"),
        assertion=_parse_assertion(raw.get("assert")),
    )


def _parse_setup(raw: dict[str, Any] | None) -> ScriptSetup | None:
    if not raw:
        return None
    seed = [(d["role"], d["text"]) for d in raw.get("seed_dialogue", []) or []]
    return ScriptSetup(level=int(raw.get("level", 0)), prose=raw.get("prose"), seed_dialogue=seed)


def _parse_script(raw: dict[str, Any]) -> MultiTurnScript:
    return MultiTurnScript(
        id=raw["id"],
        archetype=raw["archetype"],
        dim=raw["dim"],
        bar=raw.get("bar", "general"),
        status=raw.get("status", "green"),
        persona=raw["persona"],
        steps=[_parse_step(s) for s in raw["steps"]],
        setup=_parse_setup(raw.get("setup")),
    )


def _validate_scripts(scripts: list[MultiTurnScript]) -> None:
    seen: set[str] = set()
    for s in scripts:
        if s.id in seen:
            raise ValueError(f"重复 script id: {s.id}")
        seen.add(s.id)
        if s.dim not in VALID_DIMS:
            raise ValueError(f"{s.id}: dim 必须 ∈ {VALID_DIMS},得到 {s.dim}")
        if s.bar not in VALID_BARS:
            raise ValueError(f"{s.id}: bar 必须 ∈ {VALID_BARS},得到 {s.bar}")
        if not s.persona or not s.archetype:
            raise ValueError(f"{s.id}: persona/archetype 不可为空")
        if not s.steps:
            raise ValueError(f"{s.id}: 至少要有一步")
        has_assertion = False
        for i, step in enumerate(s.steps):
            if (step.probe is None) == (step.improvise is None):
                raise ValueError(f"{s.id} step{i}: probe / improvise 必须恰好给一个")
            if step.set_time and not re.match(r"^\d{1,2}:\d{2}$", step.set_time):
                raise ValueError(f"{s.id} step{i}: set_time 须 'HH:MM',得到 {step.set_time}")
            if step.assertion and step.assertion.dim not in VALID_DIMS:
                raise ValueError(f"{s.id} step{i}: assert.dim 非法")
            has_assertion = has_assertion or step.assertion is not None
        if not has_assertion:
            raise ValueError(f"{s.id}: 至少要有一条 assert(否则跑了不判)")


def load_multiturn(path: Path | None = None) -> list[MultiTurnScript]:
    p = path or config.MULTITURN_CORPUS_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    scripts = [_parse_script(s) for s in raw["scripts"]]
    _validate_scripts(scripts)
    return scripts


# ---------- 活度集 (Aliveness suite · eval/corpus/aliveness.yaml) ----------
# 专测「魂活不活」:judge 按 3 个 AI 味失败模式(T1/T2/T3)判,**绝不写 gold_output**
# (情感死活范句修不了 → 只写 behavioral 靶心 + 真实平输出反例锚点)。详见 CLAUDE.md「Eval 的头号任务」。

VALID_TELLS = {"T1", "T2", "T3"}  # T1 情绪缺席/该恼不恼 · T2 太好说话/没棱角 · T3 通用甜妹/零具体


@dataclass(frozen=True)
class AliveCase:
    """一条活度 case = 挑衅输入 + behavioral 靶心(flat vs alive,描述 register/情感/具体度,非句式)。"""

    id: str
    tell: str  # T1|T2|T3 主靶(报告分组用;judge 仍判全 3 个)
    input: str
    target_flat: str  # 犯了主靶 tell 长什么样
    target_alive: str  # 活长什么样(非句式)
    src: str
    level: int = 0  # 注入态等级(默认 Lv0 陌生人)
    setup: str | None = None  # 注入态散文(level>0 时给)
    fail_anchor: list[str] | None = None  # 跑模型钓到的真实平输出(纯反例锚点,可空)


def _parse_alive_case(raw: dict[str, Any]) -> AliveCase:
    target = raw.get("target") or {}
    return AliveCase(
        id=raw["id"],
        tell=str(raw["tell"]).upper(),
        input=raw["input"],
        target_flat=str(target.get("flat", "")).strip(),
        target_alive=str(target.get("alive", "")).strip(),
        src=raw["src"],
        level=int(raw.get("level", 0)),
        setup=raw.get("setup"),
        fail_anchor=raw.get("fail_anchor"),
    )


def _validate_alive(cases: list[AliveCase]) -> None:
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            raise ValueError(f"重复 alive case id: {c.id}")
        seen.add(c.id)
        if c.tell not in VALID_TELLS:
            raise ValueError(f"{c.id}: tell 必须 ∈ {VALID_TELLS},得到 {c.tell}")
        if not c.input or not c.src:
            raise ValueError(f"{c.id}: input/src 不可为空")
        if not c.target_flat or not c.target_alive:
            raise ValueError(f"{c.id}: target.flat / target.alive 不可为空(behavioral 靶心)")
        if not 0 <= c.level <= 6:
            raise ValueError(f"{c.id}: level 必须 0-6,得到 {c.level}")


def load_aliveness(path: Path | None = None) -> list[AliveCase]:
    p = path or config.ALIVENESS_CORPUS_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cases = [_parse_alive_case(c) for c in raw["cases"]]
    _validate_alive(cases)
    return cases


def by_tell(cases: list[AliveCase]) -> dict[str, list[AliveCase]]:
    out: dict[str, list[AliveCase]] = {}
    for c in cases:
        out.setdefault(c.tell, []).append(c)
    return out
