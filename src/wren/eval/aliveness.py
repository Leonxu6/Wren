"""活度集 runner(wren-aliveness):跑真 skeleton(Step1→Step2)→ 最强 judge 按 3 个 AI 味失败模式判。

北极星(CLAUDE.md「Eval 的头号任务」):分辨「活的人味反应」vs「形对但情感死的 AI 输出」。
- judge = 最强模型(默认 judge_model_spec;建议 WREN_JUDGE_MODEL=claude-opus-4-7),按 T1/T2/T3 判。
- pass = 3 个 tell 都没犯 且 过机械门;报告给每个 tell 的通过率 + 最常犯哪个(喂「真 bot 上调教」的环)。
- --no-judge 只产 transcript(带 flat/alive 靶心),供会话里 Opus 当场判。
- 复用:handle_turn(真 skeleton) + run_mech_gate(机械门) + judge schema。
- 红线(§0):只观测/判涌现,不另立 mood/landmine 打分器;不写 gold(不背范句)。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from ..core.clock import MockClock
from ..core.pipeline import handle_turn
from ..core.storage import Relationship, UserStore
from ..model import get_model, model_from_spec
from ..model.base import ChatModel
from .corpus import AliveCase, by_tell, load_aliveness
from .judge import AliveJudgeResult, judge_alive
from .mech_gate import run_mech_gate

_DEFAULT_START = datetime(2026, 5, 21, 14, 0, tzinfo=UTC)  # 中性白天,可复现
_TELLS = ("T1", "T2", "T3")
_TELL_NAMES = {"T1": "情绪缺席/该恼不恼", "T2": "太好说话/没棱角", "T3": "通用甜妹/零具体"}


# ---------- 单次跑的产物 ----------


@dataclass
class AliveCaseRun:
    case_id: str
    tell: str
    bubbles: list[str]
    mech_passed: bool
    mech_rules: list[str]
    judge: AliveJudgeResult | None  # None = --no-judge

    @property
    def passed(self) -> bool:
        return self.mech_passed and self.judge is not None and self.judge.passed


def run_alive_case(
    case: AliveCase,
    chat_id: str,
    *,
    gen_model: ChatModel,
    judge_model: ChatModel | None = None,
    root: Path | None = None,
    start: datetime = _DEFAULT_START,
) -> AliveCaseRun:
    """judge_model=None → 不判,只产输出(供 transcript 当场判)。"""
    clock = MockClock(start)
    store = UserStore(chat_id, root)
    if store.exists():
        store.delete()
    store.init_user()
    if case.level or case.setup:  # 注入合成关系态(高 Lv case);prose 始终是 str
        rel = store.read_relationship()
        store.write_relationship(
            Relationship(level=case.level or rel.level, prose=case.setup or rel.prose, freeze=False)
        )
    outcome = handle_turn(chat_id, case.input, store, gen_model, gen_model, clock=clock)
    mech = run_mech_gate(outcome.bubbles)
    judge = None if judge_model is None else judge_alive(case, outcome.bubbles, judge_model)
    return AliveCaseRun(case.id, case.tell, outcome.bubbles, mech.passed, sorted(mech.rules()), judge)


def run_aliveness(
    cases: list[AliveCase],
    *,
    gen_model: ChatModel,
    judge_model: ChatModel | None = None,
    root: Path | None = None,
    reps: int = 3,
    start: datetime = _DEFAULT_START,
) -> list[AliveCaseRun]:
    runs: list[AliveCaseRun] = []
    for case in cases:
        for rep in range(reps):
            runs.append(
                run_alive_case(
                    case,
                    f"alive-{case.id}-r{rep + 1}",
                    gen_model=gen_model,
                    judge_model=judge_model,
                    root=root,
                    start=start,
                )
            )
    return runs


# ---------- 聚合 ----------


@dataclass
class CaseAgg:
    case_id: str
    tell: str
    passes: int
    n: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.n if self.n else 0.0


@dataclass
class AliveReport:
    case_aggs: list[CaseAgg]
    tell_fires: dict[str, int]  # 各 tell 跨所有判过的 run 犯了几次(诊断:最常犯哪个)
    judged_runs: int

    @property
    def overall(self) -> float:
        total = sum(a.n for a in self.case_aggs)
        return sum(a.passes for a in self.case_aggs) / total if total else 0.0

    def per_tell(self) -> dict[str, float]:
        """只含本次真跑过的 tell(--tell 过滤时不报没跑的 tell 为 0%)。"""
        out: dict[str, float] = {}
        for t in _TELLS:
            aggs = [a for a in self.case_aggs if a.tell == t]
            n = sum(a.n for a in aggs)
            if n:
                out[t] = sum(a.passes for a in aggs) / n
        return out

    @property
    def meets(self) -> bool:
        return self.overall >= config.PASS_THRESHOLD


def aggregate(runs: list[AliveCaseRun]) -> AliveReport:
    grouped: dict[str, list[AliveCaseRun]] = {}
    order: list[str] = []
    for r in runs:
        if r.case_id not in grouped:
            grouped[r.case_id] = []
            order.append(r.case_id)
        grouped[r.case_id].append(r)
    case_aggs = [
        CaseAgg(cid, grouped[cid][0].tell, sum(r.passed for r in grouped[cid]), len(grouped[cid]))
        for cid in order
    ]
    tell_fires: dict[str, int] = dict.fromkeys(_TELLS, 0)
    judged = 0
    for r in runs:
        if r.judge is None:
            continue
        judged += 1
        for t in r.judge.fired:
            tell_fires[t] += 1
    return AliveReport(case_aggs, tell_fires, judged)


# ---------- CLI ----------


def _print_report(report: AliveReport) -> None:
    mark = "✅" if report.meets else "❌"
    print(f"  overall alive 通过率: {report.overall:.0%} {mark} (门槛 {config.PASS_THRESHOLD:.0%})\n")
    per = report.per_tell()
    print("  每个 tell 的通过率(按主靶分组):")
    for t in _TELLS:
        if t in per:
            print(f"    {t} {_TELL_NAMES[t]}: {per[t]:.0%}")
    if report.judged_runs:
        print(f"\n  最常犯哪个 tell(跨 {report.judged_runs} 个判过的 run):")
        for t in _TELLS:
            fires = report.tell_fires[t]
            print(f"    {t}: {fires}/{report.judged_runs} ({fires / report.judged_runs:.0%})")


def _print_failures(runs: list[AliveCaseRun], limit: int = 10) -> None:
    fails = [r for r in runs if not r.passed]
    if not fails:
        return
    print(f"\n  失败样本(前 {min(limit, len(fails))}/{len(fails)}):")
    for r in fails[:limit]:
        reasons: list[str] = []
        if not r.mech_passed:
            reasons.append("mech:" + ",".join(r.mech_rules))
        if r.judge is not None and not r.judge.passed:
            reasons.append("tell:" + ",".join(r.judge.fired))
        bub = " | ".join(r.bubbles) if r.bubbles else "(silence)"
        print(f"    [{r.case_id}] {bub} → {'; '.join(reasons)}")
        if r.judge is not None and r.judge.reason:
            print(f"        ⮑ {r.judge.reason}")
    print()


def _print_transcripts(runs: list[AliveCaseRun], cases: dict[str, AliveCase]) -> None:
    """--no-judge:输入 + Wren 输出 + 该 case 的 flat/alive 靶心(供会话里 Opus 按 3 点当场判)。"""
    seen: set[str] = set()
    for r in runs:
        if r.case_id in seen:
            continue
        seen.add(r.case_id)
        c = cases[r.case_id]
        print(f"\n===== {c.id} · {c.tell} {_TELL_NAMES[c.tell]} · Lv{c.level} =====")
        print(f"  them: {c.input}")
        print(f"  wren: {' | '.join(r.bubbles) if r.bubbles else '(silence)'}")
        print(f"     ⮑ FLAT : {c.target_flat}")
        print(f"     ⮑ ALIVE: {c.target_alive}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wren 活度集:测「魂活不活」(3 个 AI 味失败模式 · 最强 judge 直判)"
    )
    parser.add_argument("--reps", type=int, default=config.multiturn_reps())
    parser.add_argument("--tell", default=None, help="只跑某个 tell(T1/T2/T3)")
    parser.add_argument("--quick", action="store_true", help="每 tell 取前 2 条 + reps=1 冒烟")
    parser.add_argument(
        "--no-judge", action="store_true", help="不判,只产 transcript(供会话里 Opus 当场判)"
    )
    args = parser.parse_args()

    if config.force_fake() or not config.has_api_key():
        print("⚠️  无 WREN_API_KEY 或 WREN_FAKE_MODEL=1:跑的是 fake 模型,内容无效(只验机制跑通)。\n")

    cases = load_aliveness()
    if args.tell:
        cases = [c for c in cases if c.tell == args.tell.upper()]
    if args.quick:
        cases = [c for cs in by_tell(cases).values() for c in cs[:2]]
    reps = 1 if args.quick else args.reps

    gen = get_model("primary")
    judge = None if args.no_judge else model_from_spec(config.judge_model_spec())
    judge_label = "(跳过 → 产 transcript)" if args.no_judge else config.judge_model_spec().model
    print(f"judge = {judge_label} · reps = {reps} · cases = {len(cases)}\n")

    runs = run_aliveness(cases, gen_model=gen, judge_model=judge, reps=reps)
    if args.no_judge:
        _print_transcripts(runs, {c.id: c for c in cases})
    else:
        _print_report(aggregate(runs))
        _print_failures(runs)


if __name__ == "__main__":
    main()
