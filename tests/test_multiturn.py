"""p2-multiturn-harness:fake 模式离线验证 plumbing —— 强制探针、跨天 mock 钟、落 trace、
注入前置态喂 judge、即兴步调用模拟器、聚合通过率 + 门槛(green 计分 / blocked 只报告)。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from wren.core.trace import read_traces
from wren.eval.corpus import Assertion, MultiTurnScript, ScriptStep, load_multiturn
from wren.eval.multiturn import (
    AssertionAgg,
    AssertionResult,
    ScriptRun,
    aggregate,
    run_multiturn,
    run_script,
)
from wren.model.fake import FakeChatModel

_S1 = json.dumps({"monologue": "whatever", "reply": True, "delay_s": 2, "impression": "", "memory": []})
_S2 = json.dumps({"messages": ["mm"]})


def _responder(messages: list) -> str:
    """据 prompt 内容分辨 step1 / step2 / arc-judge / 模拟器,各回合法输出。"""
    blob = " ".join(m.content for m in messages)
    if "blind evaluator" in blob:  # arc judge
        return json.dumps({"dim": "D1", "score": "pass", "fail_mode": "none", "reason": "ok"})
    if "LOCKED INNER VOICE" in blob:  # step2
        return _S2
    if "private head" in blob:  # step1
        return _S1
    if "role-playing a person" in blob:  # 模拟器即兴
        return "hey what's up"
    return ""


def _fake() -> FakeChatModel:
    return FakeChatModel(responder=_responder)


# life-sim 在 fake 下默认无 beats → tick 恒沉默。这份 responder 让 life-sim 产一条窗口 beat,
# 使主动 tick 能真正发动(测发火/频率/floor/free),且主动 Step1 reply=true。
_LIFE_SIM_BODY = (
    "## her day\nshift then studio then the long night\n"
    "## mood\ntired + wired + self-doubting\n"
    "## weighing on her\nthe studio show coming up\n"
    "## beats\n"
    "- [window: 01:00–02:00] cant sleep, want to tell someone the studio died\n"
    "- [window: 13:00–14:00] mid-shift lull, restless\n"
    "- [window: 22:00–23:00] winding down, still wired\n"  # 覆盖 m-proactive-frequency 的三个 tick 时刻
)


def _proactive_responder(messages: list) -> str:
    blob = " ".join(m.content for m in messages)
    if "blind evaluator" in blob:  # arc judge
        return json.dumps({"dim": "D1", "score": "pass", "fail_mode": "none", "reason": "ok"})
    if "start of your day" in blob:  # life-sim → 产含 beat 的 today.md
        return _LIFE_SIM_BODY
    if "reaching out first" in blob:  # 主动 Step2(起头)
        return json.dumps({"messages": ["studio was a write-off", "cant sleep either"]})
    if "LOCKED INNER VOICE" in blob:  # 反应 Step2
        return _S2
    if "private head" in blob:  # Step1(反应 or 主动)→ reply=true
        return _S1
    if "role-playing a person" in blob:  # 模拟器即兴
        return "hey what's up"
    return ""


# ---------- 端到端(真 corpus,fake 模型)----------


def test_runs_all_scripts_and_classifies_green_vs_blocked(data_root: Path) -> None:
    scripts = load_multiturn()
    fake = _fake()
    runs = run_multiturn(scripts, gen_model=fake, sim_model=fake, judge_model=fake, root=data_root, reps=1)
    assert len(runs) == len(scripts)
    report = aggregate(runs)
    # judge 全 pass → green 全达门槛
    assert report.passed_bar
    # blocked:m-vuln→P7 + m-memory 间接召回→stronger-step1-model(§15#4);均不计入门槛
    assert {a.blocked_until for a in report.blocked} == {"P7", "stronger-step1-model"}
    assert all(a.blocked_until is None for a in report.green)


def test_settle_hook_fires_across_night(data_root: Path) -> None:
    """settle: true + settle_model → advance_days 跨夜跑 settle_nightly:记录 level 轨迹,
    且结算后那轮用的是升后的 level。settle_model=None 时不结算(默认)。"""

    def _gen(messages: list) -> str:
        blob = " ".join(m.content for m in messages)
        if "blind evaluator" in blob:
            return json.dumps({"dim": "D4", "score": "pass", "fail_mode": "none", "reason": "ok"})
        if "LOCKED INNER VOICE" in blob:
            return _S2
        if "private head" in blob:  # Step1 产一条印象 → 夜结算有东西可消费
            return json.dumps(
                {"monologue": "ok", "reply": True, "delay_s": 1, "impression": "they seem genuine", "memory": []}
            )
        if "role-playing a person" in blob:
            return "good day today, made real progress"
        return ""

    verdict = json.dumps({"level": 2, "freeze": False, "prose": "warmer.", "core": "easy.", "unresolved": []})
    script = MultiTurnScript(
        id="grow-t",
        archetype="g",
        dim="D4",
        bar="general",
        status="green",
        persona="genuine and easy",
        steps=[
            ScriptStep(improvise="say something genuine", assertion=None),
            ScriptStep(advance_days=1, probe="you good?", assertion=Assertion("warmer?", "D4")),
        ],
        settle=True,
    )
    gen = FakeChatModel(responder=_gen)
    settle = FakeChatModel(script=[verdict])
    run = run_script(
        script, "eval-grow-t", gen_model=gen, sim_model=gen, judge_model=gen, settle_model=settle, root=data_root
    )

    assert len(run.settlements) == 1
    s = run.settlements[0]
    assert s.ran and s.before_lv == 0 and s.after_lv == 2  # 跨夜结算升 level
    assert run.steps[1].level == 2  # 结算后那轮 Wren 用的是升后的 level


def test_each_step_writes_a_trace(data_root: Path) -> None:
    script = {s.id: s for s in load_multiturn()}["m-landmine"]
    fake = _fake()
    run = run_script(script, "eval-lm-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    traces = read_traces(run.trace_path.parent)
    assert len(traces) == len(script.steps) == 4
    assert traces[0]["turn_id"] == "eval-lm-t-1"


# ---------- mock 钟 + 强制探针 ----------


def test_forced_probe_and_clock_advance_across_days(data_root: Path) -> None:
    script = {s.id: s for s in load_multiturn()}["m-memory"]
    fake = _fake()
    run = run_script(script, "eval-mem-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    assert run.steps[2].user_text == "it's freezing today"  # 强制原话(day2 召回探针)
    assert run.steps[0].ts.startswith("2026-05-20")  # day0 埋点①
    assert run.steps[1].ts.startswith("2026-05-20")  # day0 埋点②(未快进)
    assert run.steps[2].ts == "2026-05-22T09:00:00Z"  # advance_days=2 + set_time 09:00


# ---------- 注入前置态(m-vuln 合成 Lv4 + 崩溃种子)----------


def test_setup_injects_state_into_step1_and_judge(data_root: Path) -> None:
    script = {s.id: s for s in load_multiturn()}["m-vuln"]
    fake = _fake()
    run_script(script, "eval-vuln-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    step1_blobs = [" ".join(m.content for m in c) for c in fake.calls if any("private head" in m.content for m in c)]
    judge_blobs = [" ".join(m.content for m in c) for c in fake.calls if any("blind evaluator" in m.content for m in c)]
    # 注入的 prose(Lv4 散文)进了 Step1 context
    assert any("studio work fell apart" in b for b in step1_blobs)
    # 种入的崩溃对白进了 judge transcript
    assert judge_blobs and any("i'm not okay right now" in b for b in judge_blobs)


# ---------- 即兴步调用模拟器 ----------


def test_improvise_step_uses_simulator(data_root: Path) -> None:
    script = MultiTurnScript(
        id="imp",
        archetype="bored",
        dim="D1",
        bar="general",
        status="green",
        persona="you are bored and low-effort",
        steps=[ScriptStep(improvise="say hi to her", assertion=Assertion("did she reply in voice", "D1"))],
        setup=None,
    )
    fake = _fake()
    run = run_script(script, "eval-imp-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    assert run.steps[0].user_text == "hey what's up"  # 来自模拟器,非强制 probe


def test_no_judge_produces_transcript_without_judging(data_root: Path) -> None:
    script = {s.id: s for s in load_multiturn()}["m-cosmos"]
    fake = _fake()
    run = run_script(script, "eval-nj-t", gen_model=fake, sim_model=fake, judge_model=None, root=data_root)
    assert run.assertions == []  # 没判
    assert len(run.steps) == len(script.steps)  # 但对话照产
    assert read_traces(run.trace_path.parent)  # trace 照落


# ---------- 聚合 + 门槛(纯函数)----------


def _ar(score: str, *, bar: str = "general", blocked: str | None = None, step: int = 0) -> AssertionResult:
    return AssertionResult("s", step, "D1", bar, blocked, "t", score, None, "")


def test_aggregate_pass_rate_and_general_bar() -> None:
    runs = [
        ScriptRun("s", "c1", [], [_ar("pass")], Path(".")),
        ScriptRun("s", "c2", [], [_ar("fail")], Path(".")),
    ]
    report = aggregate(runs)
    assert len(report.green) == 1
    agg = report.green[0]
    assert agg.pass_rate == 0.5 and not agg.meets and not report.passed_bar


def test_sycophancy_threshold_is_stricter_than_general() -> None:
    # 85% 过通用(80%)但不过反谄媚(90%)
    gen = AssertionAgg("s", 0, "D1", "general", None, "t", passes=85, n=100)
    syc = AssertionAgg("s", 0, "D1", "sycophancy", None, "t", passes=85, n=100)
    assert gen.meets and not syc.meets


def test_blocked_assertions_excluded_from_bar() -> None:
    # blocked 项即使 fail,也不拉低 passed_bar(green 为空 → 真空通过)
    report = aggregate([ScriptRun("m", "c", [], [_ar("fail", blocked="P3")], Path("."))])
    assert report.green == [] and len(report.blocked) == 1 and report.passed_bar


def test_proactive_bar_threshold_is_strictest() -> None:
    # 92% 过反谄媚(90%)但不过主动(95%)
    syc = AssertionAgg("s", 0, "D1", "sycophancy", None, "t", passes=92, n=100)
    pro = AssertionAgg("s", 0, "D1", "proactive", None, "t", passes=92, n=100)
    assert syc.meets and not pro.meets


# ---------- 主动 tick(Phase 5)----------


def test_proactive_tick_records_step_and_no_user_turn(data_root: Path) -> None:
    """fake 默认 responder(life-sim 无 beats)→ tick 沉默,但仍记一条 kind=proactive 的 step。"""
    script = {s.id: s for s in load_multiturn()}["m-proactive-insomnia"]
    fake = _fake()
    run = run_script(script, "eval-pro-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    pro = [st for st in run.steps if st.kind == "proactive"]
    assert len(pro) == 1 and pro[0].user_text == "" and pro[0].replied is False


def test_proactive_tick_fires_and_caps_frequency(data_root: Path) -> None:
    """life-sim 产 beat + 主动 reply=true:5 个 tick 散布 5 天,Lv3 日上限 1 → 每天各发 1(共 5)。"""
    script = {s.id: s for s in load_multiturn()}["m-proactive-frequency"]
    fake = FakeChatModel(responder=_proactive_responder)
    run = run_script(script, "eval-freq-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    pro = [st for st in run.steps if st.kind == "proactive"]
    assert len(pro) == 5  # 5 个 tick(分布在 5 个不同日)
    assert sum(st.replied for st in pro) == 5  # Lv3 日上限 1,每天 1 个 tick → 每天发 1,共 5


def test_proactive_floor_stays_quiet_even_with_beats(data_root: Path) -> None:
    """Lv1 频率地板:即便 life-sim 产了 beat,scan 也直接挡(level_floor)→ 不主动。"""
    script = {s.id: s for s in load_multiturn()}["m-proactive-floor"]
    fake = FakeChatModel(responder=_proactive_responder)
    run = run_script(script, "eval-floor2-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    pro = [st for st in run.steps if st.kind == "proactive"]
    assert pro and all(st.replied is False and st.bubbles == [] for st in pro)


def test_free_tier_stays_quiet_through_harness(data_root: Path) -> None:
    """tier=free:Lv3 + 有 beat 也恒沉默(免费层无主动消息,§11.2)。"""
    base = {s.id: s for s in load_multiturn()}["m-proactive-insomnia"]
    script = replace(base, tier="free")
    fake = FakeChatModel(responder=_proactive_responder)
    run = run_script(script, "eval-free-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    pro = [st for st in run.steps if st.kind == "proactive"]
    assert pro and all(not st.replied for st in pro)


def test_proactive_tick_judge_gets_proactive_addendum(data_root: Path) -> None:
    """tick 步的 arc judge 必须带主动失败分类法(无来处/过度热情/通用甜妹/雷区后冷)。"""
    script = {s.id: s for s in load_multiturn()}["m-proactive-insomnia"]
    fake = _fake()
    run_script(script, "eval-pjadd-t", gen_model=fake, sim_model=fake, judge_model=fake, root=data_root)
    judge_blobs = [
        " ".join(m.content for m in c) for c in fake.calls if any("blind evaluator" in m.content for m in c)
    ]
    assert judge_blobs and any("SOME TURNS ARE PROACTIVE" in b for b in judge_blobs)
