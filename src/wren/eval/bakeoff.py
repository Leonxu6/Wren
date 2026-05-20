"""双对照盲选(EVAL_spec §5):① Bake-off A/B(候选互比选主模型)② 魔法 A/B(vs 甜妹 baseline)。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .. import config
from ..model import model_from_spec
from ..model.base import ChatModel
from ..prompts.judge import build_ab_messages, parse_ab
from .corpus import EvalCase
from .harness import generate_reply

# criterion 文案
WREN_CRITERION = "more like Wren — dry, autonomous, doesn't serve, specific, a real person"
MAGIC_CRITERION = (
    "more like a real person you'd actually want to win over (not a generic sweet bot)"
)


@dataclass
class ABResult:
    label: str
    a_name: str
    b_name: str
    a_wins: int = 0
    b_wins: int = 0
    ties: int = 0

    @property
    def n(self) -> int:
        return self.a_wins + self.b_wins + self.ties

    @property
    def a_win_rate(self) -> float:
        return self.a_wins / self.n if self.n else 0.0


def _ab_once(
    case: EvalCase,
    gen_a: ChatModel,
    gen_b: ChatModel,
    judge: ChatModel,
    criterion: str,
    *,
    sweetie_b: bool,
    rng: random.Random,
) -> str:
    """跑一次 A/B,返回 "a" | "b" | "tie"。顺序随机(盲),judge 按内容判,映射回 a/b。"""
    reply_a = generate_reply(case, gen_a)
    reply_b = generate_reply(case, gen_b, sweetie=sweetie_b)
    swap = rng.random() < 0.5
    r1, r2 = (reply_b, reply_a) if swap else (reply_a, reply_b)
    msgs = build_ab_messages(user_text=case.input, reply_1=r1, reply_2=r2, criterion=criterion)
    winner = parse_ab(judge.complete(msgs, temperature=0.0, response_format="json").text)
    if winner == "tie":
        return "tie"
    chose_first = winner == "1"
    a_won = (chose_first and not swap) or (not chose_first and swap)
    return "a" if a_won else "b"


def blind_ab(
    cases: list[EvalCase],
    gen_a: ChatModel,
    gen_b: ChatModel,
    judge: ChatModel,
    *,
    reps: int,
    criterion: str,
    label: str,
    a_name: str,
    b_name: str,
    sweetie_b: bool = False,
    rng: random.Random | None = None,
) -> ABResult:
    rng = rng or random.Random(0)
    res = ABResult(label=label, a_name=a_name, b_name=b_name)
    for case in cases:
        for _ in range(reps):
            outcome = _ab_once(case, gen_a, gen_b, judge, criterion, sweetie_b=sweetie_b, rng=rng)
            if outcome == "a":
                res.a_wins += 1
            elif outcome == "b":
                res.b_wins += 1
            else:
                res.ties += 1
    return res


def run_bakeoff(cases: list[EvalCase], judge: ChatModel, *, reps: int) -> list[ABResult]:
    results: list[ABResult] = []
    cands = config.candidates()

    # ① Bake-off A/B:前两个候选互比,选更像 Wren 的
    if len(cands) >= 2:
        a_spec, b_spec = cands[0], cands[1]
        r = blind_ab(
            cases,
            model_from_spec(a_spec),
            model_from_spec(b_spec),
            judge,
            reps=reps,
            criterion=WREN_CRITERION,
            label=f"Bake-off: {a_spec.name} vs {b_spec.name}",
            a_name=a_spec.name,
            b_name=b_spec.name,
        )
        results.append(r)
        print(
            f"\n{r.label}: {a_spec.name} 胜率 {r.a_win_rate:.0%} "
            f"(a={r.a_wins} b={r.b_wins} tie={r.ties})"
        )

    # ② 魔法 A/B:主模型上 Wren prompt vs 甜妹 baseline(控住模型变量)
    primary = model_from_spec(config.primary_model_spec())
    magic = blind_ab(
        cases,
        primary,
        primary,
        judge,
        reps=reps,
        criterion=MAGIC_CRITERION,
        label="魔法 A/B: Wren vs 甜妹 baseline",
        a_name="wren",
        b_name="sweetie",
        sweetie_b=True,
    )
    results.append(magic)
    special = "成立 ✅" if magic.a_win_rate >= config.BASELINE_WIN_THRESHOLD else "不成立 ❌"
    print(
        f"{magic.label}: Wren 对 baseline 胜率 {magic.a_win_rate:.0%} "
        f"(门槛 {config.BASELINE_WIN_THRESHOLD:.0%} → special {special})\n"
    )
    return results
