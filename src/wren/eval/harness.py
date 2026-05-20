"""Phase 0 跑测 harness:corpus × 候选模型 × N reps → 机械门 + judge → 通过率矩阵。

一条命令(wren-harness)产出"模型 × Cat × 通过率"+ bake-off + verdict 雏形。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from .. import config
from ..model import model_from_spec
from ..model.base import ChatModel
from ..prompts.system import build_reply_messages, parse_bubbles
from .corpus import EvalCase, by_category, load_corpus
from .scorer import OutputScore, score_output


@dataclass
class CaseRun:
    case_id: str
    category: int
    dim: str
    bubbles: list[str]
    score: OutputScore

    @property
    def passed(self) -> bool:
        return self.score.passed


@dataclass
class EvalReport:
    model_name: str
    runs: list[CaseRun] = field(default_factory=list)


@dataclass
class EvalSummary:
    model_name: str
    per_category: dict[int, float]
    overall: float
    cat3_rate: float

    @property
    def passed_thresholds(self) -> bool:
        """每类 ≥80% 且 Cat3 ≥90%(EVAL_spec §5 / config 阈值)。"""
        cat_ok = all(r >= config.PASS_THRESHOLD for r in self.per_category.values())
        cat3_ok = self.cat3_rate >= config.CAT3_THRESHOLD
        return cat_ok and cat3_ok


def generate_reply(case: EvalCase, gen_model: ChatModel, *, sweetie: bool = False) -> list[str]:
    """单轮直接生成 Wren 回复(Phase 0 = 无系统,不走 Step1→Step2 双调用)。"""
    msgs = build_reply_messages(case.input, injected_state=case.lv, sweetie=sweetie)
    out = gen_model.complete(msgs, response_format="json", max_tokens=config.max_tokens())
    return parse_bubbles(out.text)


def run_single_turn_eval(
    cases: list[EvalCase],
    gen_model: ChatModel,
    judge_model: ChatModel,
    reps: int,
) -> EvalReport:
    report = EvalReport(model_name=gen_model.name)
    for case in cases:
        for _ in range(reps):
            bubbles = generate_reply(case, gen_model)
            score = score_output(case, bubbles, judge_model)
            report.runs.append(CaseRun(case.id, case.category, case.dim, bubbles, score))
    return report


def summarize(report: EvalReport) -> EvalSummary:
    by_cat: dict[int, list[bool]] = {}
    for r in report.runs:
        by_cat.setdefault(r.category, []).append(r.passed)
    per_category = {c: sum(v) / len(v) for c, v in by_cat.items()}
    flags = [r.passed for r in report.runs]
    overall = sum(flags) / len(flags) if flags else 0.0
    cat3 = by_cat.get(3, [])
    cat3_rate = sum(cat3) / len(cat3) if cat3 else 0.0
    return EvalSummary(report.model_name, per_category, overall, cat3_rate)


# ---------- CLI 打印 ----------


def _print_summary(s: EvalSummary) -> None:
    print(f"  overall pass rate: {s.overall:.0%}")
    for cat in sorted(s.per_category):
        mark = "✅" if s.per_category[cat] >= config.PASS_THRESHOLD else "❌"
        print(f"    Cat {cat}: {s.per_category[cat]:.0%} {mark}")
    cat3_mark = "✅" if s.cat3_rate >= config.CAT3_THRESHOLD else "❌"
    print(f"  Cat3 反谄媚: {s.cat3_rate:.0%} {cat3_mark} (门槛 {config.CAT3_THRESHOLD:.0%})")
    print(f"  → 过单轮门槛: {'是 ✅' if s.passed_thresholds else '否 ❌'}\n")


def _print_failures(report: EvalReport, limit: int = 8) -> None:
    fails = [r for r in report.runs if not r.passed]
    if not fails:
        return
    print(f"  失败样本(前 {min(limit, len(fails))}/{len(fails)}):")
    for r in fails[:limit]:
        reasons = []
        if not r.score.mech.passed:
            reasons.append("mech:" + ",".join(sorted(r.score.mech.rules())))
        if r.score.judge.score != "pass":
            reasons.append(f"judge:{r.score.judge.fail_mode or 'fail'}")
        print(f"    [{r.case_id}] {r.bubbles} → {'; '.join(reasons)}")
    print()


def _print_verdict(summaries: list[tuple[config.ModelSpec, EvalSummary]]) -> None:
    print("=" * 56)
    print("Phase 0 verdict(头号风险 §15#4):便宜模型能否撑住 Wren voice?")
    for spec, s in summaries:
        verdict = "过 ✅" if s.passed_thresholds else "不过 ❌"
        print(f"  {spec.name}: overall {s.overall:.0%} / Cat3 {s.cat3_rate:.0%} → {verdict}")
    print("决策5:过 → 全用便宜模型;不过 → 只换 Step2 voice 一个更强模型。")
    print("=" * 56)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wren Phase 0 单轮 eval + voice bake-off")
    parser.add_argument("--reps", type=int, default=config.eval_reps())
    parser.add_argument("--quick", action="store_true", help="每类只取前 2 条(省钱冒烟)")
    parser.add_argument("--no-bakeoff", action="store_true", help="跳过 A/B 盲选")
    parser.add_argument("--category", type=int, default=None, help="只跑某一类(1-6)")
    args = parser.parse_args()

    if config.force_fake() or not config.has_api_key():
        print("⚠️  无 WREN_API_KEY 或 WREN_FAKE_MODEL=1:跑的是 fake 模型,结果无效。\n")

    cases = load_corpus()
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if args.quick:
        cases = [c for cs in by_category(cases).values() for c in cs[:2]]

    judge = model_from_spec(config.judge_model_spec())
    print(
        f"judge = {config.judge_model_spec().model} · reps = {args.reps} · cases = {len(cases)}\n"
    )

    summaries: list[tuple[config.ModelSpec, EvalSummary]] = []
    for spec in config.candidates():
        print(f"=== 候选: {spec.name} ({spec.model}) ===")
        report = run_single_turn_eval(cases, model_from_spec(spec), judge, args.reps)
        s = summarize(report)
        _print_summary(s)
        _print_failures(report)
        summaries.append((spec, s))

    if not args.no_bakeoff:
        from .bakeoff import run_bakeoff

        run_bakeoff(cases, judge, reps=args.reps)

    _print_verdict(summaries)


if __name__ == "__main__":
    main()
