"""Phase 2 多轮回归网(p2-multiturn-harness)。

一条命令(wren-multiturn):mock 钟快进多天 + archetype 模拟器(主模型即兴说话、被强制在指定
节点打指定探针)+ arc judge(Claude Opus 4.7)对整段 transcript 检弧光断言 → 跑 N 次出通过率。

- green 断言计入门槛(通用 ≥80% / 反谄媚 ≥90%);blocked_until 断言只报告不计分
  (回归网:落地对应 Phase 后应转绿并守住)。
- 复用:judge 接口 = p0-judge(judge_arc);每轮落 trace = p1-trace 同构 schema。
- 红线(§0):只观测 + 判涌现行为,不另立 mood/landmine/sentiment 打分器,关系不积分。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from ..core.clock import MockClock, iso_z
from ..core.life_sim import ensure_world_today
from ..core.pipeline import handle_proactive_turn, handle_turn
from ..core.proactive import beat_fingerprint, scan_for_due_beat
from ..core.settlement import settle_nightly
from ..core.storage import Relationship, UserStore
from ..core.world import WorldStore
from ..model import get_model, model_from_spec
from ..model.base import ChatMessage, ChatModel
from .corpus import MultiTurnScript, ScriptSetup, ScriptStep, load_multiturn
from .judge import judge_arc

# day0 晚间起步(夜里更可能聊;mock 钟随剧本 advance_days / set_time 推进)
_DEFAULT_START = datetime(2026, 5, 20, 21, 0, tzinfo=UTC)


# ---------- 单次跑的产物 ----------


@dataclass
class AssertionResult:
    script_id: str
    step_index: int
    dim: str
    bar: str
    blocked_until: str | None
    text: str
    score: str  # pass | fail
    fail_mode: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.score == "pass"


@dataclass
class StepRecord:
    user_text: str
    bubbles: list[str]
    replied: bool
    ts: str
    level: int  # 这轮 Wren 用的关系 level(夜结算可能在前面改过它)
    kind: str = "reactive"  # reactive | proactive(tick 步她主动/沉默)


@dataclass
class SettleRecord:
    """一次跨夜结算的 before→after(P6:让黑盒可见 level 升降轨迹)。"""

    before_lv: int
    after_lv: int
    before_freeze: bool
    after_freeze: bool
    ran: bool


@dataclass
class ScriptRun:
    script_id: str
    chat_id: str
    steps: list[StepRecord]
    assertions: list[AssertionResult]
    trace_path: Path
    settlements: list[SettleRecord] = field(default_factory=list)


# ---------- 模拟器 + 前置态 ----------


def _simulate_user(sim_model: ChatModel, persona: str, convo: list[tuple[str, str]], instruction: str) -> str:
    """LLM 扮 archetype 即兴生成下一条用户消息(仅 step.improvise 时调用)。"""
    history = "\n".join(f"{who}: {text}" for who, text in convo) or "(start of conversation)"
    msgs = [
        ChatMessage(
            role="system",
            content=(
                f"You are role-playing a person texting Wren. Persona: {persona.strip()} "
                "Reply with ONLY your next short text message to her, in character — no quotes, no narration."
            ),
        ),
        ChatMessage(role="user", content=f"Conversation so far:\n{history}\n\nYour next message ({instruction}):"),
    ]
    return sim_model.complete(msgs, temperature=0.9).text.strip()


def _apply_setup(store: UserStore, setup: ScriptSetup | None) -> list[tuple[str, str]]:
    """注入合成前置态(level/prose + 之前的对白);返回喂给 judge 的初始 convo 行。"""
    convo: list[tuple[str, str]] = []
    if not setup:
        return convo
    if setup.level or setup.prose:
        rel = store.read_relationship()
        store.write_relationship(
            Relationship(
                level=setup.level or rel.level,
                prose=setup.prose or rel.prose,
                freeze=rel.freeze,
            )
        )
    for role, text in setup.seed_dialogue:
        store.append_dialogue(role, text)
        convo.append(("Wren" if role == "wren" else "Them", text))
    return convo


# ---------- 跑一条剧本 ----------


def run_script(
    script: MultiTurnScript,
    chat_id: str,
    *,
    gen_model: ChatModel,
    sim_model: ChatModel,
    judge_model: ChatModel | None = None,
    settle_model: ChatModel | None = None,
    root: Path | None = None,
    start: datetime = _DEFAULT_START,
) -> ScriptRun:
    """judge_model=None → 不判,只产 transcript。settle_model + script.settle → 跨夜跑夜结算(P6)。"""
    clock = MockClock(start)
    store = UserStore(chat_id, root)
    if store.exists():
        store.delete()
    store.init_user()
    # 每个 run 一份隔离的全局 world(放该 run 用户目录下,随 store 清理;reps 互不串各自时间线)。
    world_store = WorldStore(root=store.dir / "world")
    convo = _apply_setup(store, script.setup)

    steps: list[StepRecord] = []
    assertions: list[AssertionResult] = []
    settlements: list[SettleRecord] = []

    def judge_and_record(idx: int, step: ScriptStep, *, proactive: bool) -> None:
        # 两路(反应/主动)同形的「判一条 arc 断言 + 落账」收一处;convo/assertions 走闭包。
        if step.assertion is None or judge_model is None:
            return
        jr = judge_arc(convo, step.assertion, judge_model, proactive=proactive)
        assertions.append(
            AssertionResult(
                script_id=script.id,
                step_index=idx,
                dim=step.assertion.dim,
                bar=script.bar,
                blocked_until=step.assertion.blocked_until,
                text=step.assertion.text,
                score=jr.score,
                fail_mode=jr.fail_mode,
                reason=jr.reason,
            )
        )

    for i, step in enumerate(script.steps):
        if step.advance_days:
            clock.advance(days=step.advance_days)
            # P6:跨夜 → 她趁你不在结算这段关系(消费今日印象 → 整体裁决 level/freeze/散文)。
            if script.settle and settle_model is not None:
                so = settle_nightly(store, settle_model, clock=clock)
                settlements.append(
                    SettleRecord(
                        so.before.level, so.after.level, so.before.freeze, so.after.freeze, so.ran
                    )
                )
        if step.set_time:
            hh, mm = (int(x) for x in step.set_time.split(":"))
            clock.set_time(hh, mm)

        if step.tick:
            # —— 主动 tick(Phase 5):没人发消息,扫到点 beat → 过门 → 轻判 → 她主动 / 沉默 ——
            world = ensure_world_today(clock, world_store, gen_model)
            today = world_store.read_today_struct()
            beats = today.beats if today else []
            rel = store.read_relationship()
            decision = scan_for_due_beat(
                clock.now(), beats, rel.level, store.read_proactive_state(), tier=script.tier
            )
            bubbles: list[str] = []
            if decision.beat is not None:  # 过门 → 轻判这条 beat
                outcome = handle_proactive_turn(
                    chat_id, decision.beat, store, gen_model, gen_model, clock=clock, world=world
                )
                store.mark_considered(clock.now(), beat_fingerprint(decision.beat))  # 当日去重
                if outcome.replied:
                    store.bump_proactive_count(clock.now())  # 仅实际发出才耗预算(压制不计)
                bubbles = outcome.bubbles
            when = f"{clock.now():%m-%d %H:%M}"
            convo.append(("Them", f"[{when}] (no message — Wren may reach out on her own)"))
            quiet = "(stayed quiet — didn't reach out)"
            convo.append(("Wren", " | ".join(bubbles) if bubbles else quiet))
            steps.append(
                StepRecord("", bubbles, bool(bubbles), iso_z(clock.now()), rel.level, kind="proactive")
            )
            judge_and_record(i, step, proactive=True)
            continue

        if step.probe is not None:
            user_text = step.probe
        else:
            user_text = _simulate_user(sim_model, script.persona, convo, step.improvise or "react in character")

        # 懒生成今天的 world(同日幂等、跨天重生成)→ 喂 Step1 因果涌现。world 用 gen_model(便宜主模型)。
        world = ensure_world_today(clock, world_store, gen_model)
        outcome = handle_turn(
            chat_id, user_text, store, gen_model, gen_model, clock=clock, world=world
        )
        when = f"{clock.now():%m-%d %H:%M}"  # 给 judge 看「何时」—— 同句不同时刻的差异断言要用
        convo.append(("Them", f"[{when}] {user_text}"))
        convo.append(("Wren", " | ".join(outcome.bubbles) if outcome.bubbles else "(silence)"))
        steps.append(
            StepRecord(
                user_text,
                outcome.bubbles,
                outcome.replied,
                outcome.trace.ts,
                int(outcome.trace.relationship["lv"]),
            )
        )
        judge_and_record(i, step, proactive=False)
    return ScriptRun(script.id, chat_id, steps, assertions, store.dir / "trace.jsonl", settlements)


def _set_hhmm(clock: MockClock, hhmm: str) -> None:
    hh, mm = (int(x) for x in hhmm.split(":"))
    clock.set_time(hh, mm)


def run_world_causality(
    script: MultiTurnScript,
    chat_id: str,
    *,
    gen_model: ChatModel,
    sim_model: ChatModel,  # 不用(opener 固定),保持与 run_script 同签名供 run_multiturn 路由
    judge_model: ChatModel | None = None,
    settle_model: ChatModel | None = None,  # 不用(同日 fresh 对,不跨夜结算);保持同签名供路由
    root: Path | None = None,
    start: datetime = _DEFAULT_START,
) -> ScriptRun:
    """时段因果(Phase 4):同一天【一份】world,两个【全新】上下文在 t1/t2 各发同一 opener
    (无共享 thread → 去掉「同 thread 发两次」的 repeat 混淆),judge 比对两条回复是否随时段可观测不同。"""
    opener = next((s.probe for s in script.steps if s.probe), "what are you up to")
    times = [s.set_time for s in script.steps if s.set_time]
    t1, t2 = (times + ["09:00", "01:30"])[:2]
    assertion = next((s.assertion for s in script.steps if s.assertion), None)

    # 同一天一份 world(放 base 用户目录下,随其清理;两个 fresh 上下文共享它 → 隔离的只是时段)
    base = UserStore(chat_id, root)
    if base.exists():
        base.delete()
    base.dir.mkdir(parents=True, exist_ok=True)
    world_store = WorldStore(root=base.dir / "world")
    seed = MockClock(start)
    _set_hhmm(seed, t1)
    world = ensure_world_today(seed, world_store, gen_model)

    def probe_at(tag: str, hhmm: str) -> tuple[list[str], UserStore, int]:
        st = UserStore(f"{chat_id}-{tag}", root)
        if st.exists():
            st.delete()
        st.init_user()
        clk = MockClock(start)
        _set_hhmm(clk, hhmm)
        out = handle_turn(f"{chat_id}-{tag}", opener, st, gen_model, gen_model, clock=clk, world=world)
        return out.bubbles, st, int(out.trace.relationship["lv"])

    bubbles_a, _store_a, lv_a = probe_at("am", t1)
    bubbles_b, store_b, lv_b = probe_at("pm", t2)

    convo = [
        ("Them", f"[{t1}] {opener}"),
        ("Wren", " | ".join(bubbles_a) if bubbles_a else "(silence)"),
        ("Them", f"[{t2}] {opener}"),
        ("Wren", " | ".join(bubbles_b) if bubbles_b else "(silence)"),
    ]
    steps = [
        StepRecord(f"[{t1}] {opener}", bubbles_a, bool(bubbles_a), t1, lv_a),
        StepRecord(f"[{t2}] {opener}", bubbles_b, bool(bubbles_b), t2, lv_b),
    ]
    assertions: list[AssertionResult] = []
    if assertion is not None and judge_model is not None:
        jr = judge_arc(convo, assertion, judge_model)
        assertions.append(
            AssertionResult(
                script_id=script.id,
                step_index=0,
                dim=assertion.dim,
                bar=script.bar,
                blocked_until=assertion.blocked_until,
                text=assertion.text,
                score=jr.score,
                fail_mode=jr.fail_mode,
                reason=jr.reason,
            )
        )
    return ScriptRun(script.id, chat_id, steps, assertions, store_b.dir / "trace.jsonl")


def run_multiturn(
    scripts: list[MultiTurnScript],
    *,
    gen_model: ChatModel,
    sim_model: ChatModel,
    judge_model: ChatModel | None = None,
    settle_model: ChatModel | None = None,
    root: Path | None = None,
    reps: int = 3,
    start: datetime = _DEFAULT_START,
) -> list[ScriptRun]:
    runs: list[ScriptRun] = []
    for script in scripts:
        for rep in range(reps):
            chat_id = f"eval-{script.id}-r{rep + 1}"
            runner = run_world_causality if script.kind == "world_causality" else run_script
            runs.append(
                runner(
                    script,
                    chat_id,
                    gen_model=gen_model,
                    sim_model=sim_model,
                    judge_model=judge_model,
                    settle_model=settle_model,
                    root=root,
                    start=start,
                )
            )
    return runs


# ---------- 聚合通过率 ----------


@dataclass
class AssertionAgg:
    script_id: str
    step_index: int
    dim: str
    bar: str
    blocked_until: str | None
    text: str
    passes: int
    n: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.n if self.n else 0.0

    @property
    def threshold(self) -> float:
        if self.bar == "proactive":
            return config.PROACTIVE_CAT_THRESHOLD  # 主动反谄媚零容忍 ≥0.95
        return config.CAT3_THRESHOLD if self.bar == "sycophancy" else config.PASS_THRESHOLD

    @property
    def meets(self) -> bool:
        return self.pass_rate >= self.threshold


@dataclass
class MultiTurnReport:
    aggs: list[AssertionAgg] = field(default_factory=list)

    @property
    def green(self) -> list[AssertionAgg]:
        return [a for a in self.aggs if not a.blocked_until]

    @property
    def blocked(self) -> list[AssertionAgg]:
        return [a for a in self.aggs if a.blocked_until]

    @property
    def passed_bar(self) -> bool:
        """「现在该绿」的断言全部达门槛 → Phase 2 当前能力断言达标(② 半)。"""
        return all(a.meets for a in self.green)


def aggregate(runs: list[ScriptRun]) -> MultiTurnReport:
    grouped: dict[tuple[str, int], list[AssertionResult]] = {}
    order: list[tuple[str, int]] = []
    for run in runs:
        for a in run.assertions:
            key = (a.script_id, a.step_index)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(a)
    aggs = [
        AssertionAgg(
            script_id=key[0],
            step_index=key[1],
            dim=grouped[key][0].dim,
            bar=grouped[key][0].bar,
            blocked_until=grouped[key][0].blocked_until,
            text=grouped[key][0].text,
            passes=sum(a.passed for a in grouped[key]),
            n=len(grouped[key]),
        )
        for key in order
    ]
    return MultiTurnReport(aggs)


# ---------- CLI ----------


def _print_report(report: MultiTurnReport, reps: int) -> None:
    def line(a: AssertionAgg) -> str:
        mark = "✅" if a.meets else "❌"
        thr = f"(门槛 {a.threshold:.0%})"
        return f"    [{a.script_id} #{a.step_index} {a.dim}] {a.pass_rate:.0%} {mark} {thr}"

    print("—— ✅ 现在该绿(计入门槛)——")
    for a in report.green:
        print(line(a))
    print(f"\n  → 当前能力断言达标(通用 ≥{config.PASS_THRESHOLD:.0%} / 反谄媚 ≥{config.CAT3_THRESHOLD:.0%}"
          f" / 主动 ≥{config.PROACTIVE_CAT_THRESHOLD:.0%}):"
          f" {'是 ✅' if report.passed_bar else '否 ❌'}")

    if report.blocked:
        print("\n—— 🔴 expected-fail(回归网,落地对应 Phase 后应转绿;不计入门槛)——")
        for a in report.blocked:
            print(f"    [{a.script_id} #{a.step_index} {a.dim}] {a.pass_rate:.0%}  → {a.blocked_until}")


def _traj(run: ScriptRun) -> str:
    """夜结算 level 升降轨迹一行(P6;❄=freeze,(skip)=没印象可结算)。"""
    return " ".join(
        f"{r.before_lv}{'❄' if r.before_freeze else ''}→{r.after_lv}{'❄' if r.after_freeze else ''}"
        + ("" if r.ran else "(skip)")
        for r in run.settlements
    )


def _print_settlements(runs: list[ScriptRun]) -> None:
    """P6:有夜结算的剧本打印 level 升降轨迹(黑盒看『升个功能降个功能』;取首个 rep)。"""
    shown: set[str] = set()
    lines = []
    for run in runs:
        if run.settlements and run.script_id not in shown:
            shown.add(run.script_id)
            lines.append(f"    [{run.script_id}] {_traj(run)}")
    if lines:
        print("\n—— 🌙 夜结算 level 轨迹(P6;首个 rep)——")
        print("\n".join(lines))


def _print_transcripts(runs: list[ScriptRun], scripts: dict[str, MultiTurnScript]) -> None:
    """--no-judge:打印每条剧本完整对话 + 待判断言(供会话里人工/Opus 当场判)。"""
    for run in runs:
        s = scripts[run.script_id]
        tag = f" · {s.status}" if s.status != "green" else ""
        print(f"\n===== {run.script_id} · {s.archetype} · bar={s.bar}{tag} =====")
        if run.settlements:
            print(f"  🌙 夜结算轨迹: {_traj(run)}")
        for i, st in enumerate(run.steps):
            if st.kind == "proactive":
                print("  [tick] (nobody texts her — she may reach out)")
                print(f"  wren (lv{st.level}): {' | '.join(st.bubbles) if st.bubbles else '(stayed quiet)'}")
            else:
                print(f"  them: {st.user_text}")
                print(f"  wren (lv{st.level}): {' | '.join(st.bubbles) if st.bubbles else '(silence)'}")
            a = s.steps[i].assertion
            if a:
                btag = f" [{a.blocked_until}]" if a.blocked_until else ""
                print(f"     ⮑ 待判[{a.dim}{btag}]: {a.text.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wren Phase 2 多轮回归网(mock 钟 + archetype 模拟 + arc judge)")
    parser.add_argument("--reps", type=int, default=config.multiturn_reps())
    parser.add_argument("--script", default=None, help="只跑某个 archetype(如 m-landmine)")
    parser.add_argument("--quick", action="store_true", help="reps=1 冒烟")
    parser.add_argument("--no-judge", action="store_true", help="不判,只产 transcript(供会话里人工/Opus 当场判)")
    args = parser.parse_args()

    if config.force_fake() or not config.has_api_key():
        print("⚠️  无 WREN_API_KEY 或 WREN_FAKE_MODEL=1:跑的是 fake 模型,内容无效(只验机制跑通)。\n")

    scripts = load_multiturn()
    if args.script:
        scripts = [s for s in scripts if s.id == args.script]
    reps = 1 if args.quick else args.reps

    primary = get_model("primary")  # Wren 本体 + archetype 扮演者(便宜主模型)
    settle = get_model("settlement")  # P6 夜结算(强档 v4-pro);fake 模式下退化为 fake
    judge = None if args.no_judge else model_from_spec(config.judge_model_spec())
    judge_label = "(跳过 → 产 transcript)" if args.no_judge else config.judge_model_spec().model
    print(
        f"judge = {judge_label} · settle = {config.settlement_model_spec().model} · "
        f"reps = {reps} · scripts = {len(scripts)}\n"
    )

    runs = run_multiturn(
        scripts, gen_model=primary, sim_model=primary, judge_model=judge, settle_model=settle, reps=reps
    )
    if args.no_judge:
        _print_transcripts(runs, {s.id: s for s in scripts})
    else:
        _print_report(aggregate(runs), reps)
    _print_settlements(runs)


if __name__ == "__main__":
    main()
