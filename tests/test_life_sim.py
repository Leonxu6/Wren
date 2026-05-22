"""life-sim + ensure_world_today 验收(p4-world):懒/幂等、生成含必需段、坏输出兜底、
world+now 进 Step1 与 trace、用户轮永不写 world/(写边界铁律)。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from wren.core.clock import MockClock
from wren.core.life_sim import ensure_world_today, run_life_sim
from wren.core.pipeline import handle_turn
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.core.world import WorldStore, parse_beats, parse_today
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel
from wren.prompts.life_sim import assemble_today, normalize_beats
from wren.prompts.step1 import build_step1_messages

_DAY0 = datetime(2026, 5, 20, 9, 0, tzinfo=UTC)

_GOOD_WORLD = """\
## her day
cafe open, then studio.

## mood
tired + wired + self-doubting.

## weighing on her
mom's visit, open studio soon.

## beats
- [window: 01:00–02:00] can't sleep, want to say something
"""


def _world_responder(_msgs: list[ChatMessage]) -> str:
    return _GOOD_WORLD


def _s1(reply: bool) -> FakeChatModel:
    return FakeChatModel(
        script=[json.dumps({"monologue": "ok", "reply": reply, "delay_s": 0, "impression": "", "memory": []})]
    )


def test_ensure_generates_when_missing(world_root: Path) -> None:
    content = ensure_world_today(MockClock(_DAY0), WorldStore(), FakeChatModel(responder=_world_responder))
    t = parse_today(content)
    assert t is not None and t.date == "2026-05-20"
    assert "## her day" in content and len(t.beats) == 1


def test_ensure_idempotent_same_day(world_root: Path) -> None:
    w = WorldStore()
    clock = MockClock(_DAY0)
    model = FakeChatModel(responder=_world_responder)
    ensure_world_today(clock, w, model)
    n = len(model.calls)
    clock.set_time(1, 30)  # 同一天不同时刻
    ensure_world_today(clock, w, model)
    assert len(model.calls) == n  # 同日 → 不再调用模型(幂等、零额外调用)


def test_ensure_regenerates_next_day(world_root: Path) -> None:
    w = WorldStore()
    clock = MockClock(_DAY0)
    model = FakeChatModel(responder=_world_responder)
    ensure_world_today(clock, w, model)
    clock.advance(days=1)
    ensure_world_today(clock, w, model)
    assert len(model.calls) == 2  # 跨天 → 重新生成
    assert "## her day" in w.read_yesterday()  # 旧 today 轮换成 yesterday(连贯输入)


def test_bad_output_falls_back_to_minimal_world(world_root: Path) -> None:
    # 默认 fake 返回 "" → assemble_today 兜底成最小合法 world(pipeline 绝不因此崩)
    content = run_life_sim(MockClock(_DAY0), WorldStore(), FakeChatModel())
    t = parse_today(content)
    assert t is not None and t.date == "2026-05-20"
    assert "## her day" in content


def test_build_step1_includes_world_and_now() -> None:
    msgs = build_step1_messages(
        relationship_prose="r",
        inner_voice="iv",
        events="",
        recent_dialogue="",
        user_text="hi",
        world="date: 2026-05-20\n## her day\nstudio all day",
        now="Wednesday 01:30",
    )
    blob = "\n".join(m.content for m in msgs)
    assert "studio all day" in blob and "01:30" in blob


def test_world_and_now_logged_in_trace(data_root: Path, world_root: Path) -> None:
    s = UserStore("w1", data_root)
    s.init_user()
    clock = MockClock(_DAY0)
    world = ensure_world_today(clock, WorldStore(), FakeChatModel(responder=_world_responder))
    handle_turn("w1", "what are you up to", s, _s1(True), FakeChatModel(script=[json.dumps({"messages": ["mm"]})]), clock=clock, world=world)
    prompt = read_traces(s.dir)[0]["step1"]["prompt"]
    assert "## her day" in prompt["world"]  # world 进了 Step1 input(落 trace)
    assert prompt["now"] == "Wednesday 09:00"  # now 也落了(本地墙钟)


def test_user_turn_never_writes_world(data_root: Path, world_root: Path) -> None:
    """写边界铁律:一轮 handle_turn(用户线)绝不创建/改动 world/(只有 WorldStore/life-sim 写)。"""
    s = UserStore("w2", data_root)
    s.init_user()
    handle_turn("w2", "hey", s, _s1(False), FakeChatModel(script=["unused"]), world="date: 2026-05-20\n\n## her day\nx")
    assert not (world_root / "today.md").exists()  # handle_turn 没碰 world/


def test_normalize_beats_messy_formats() -> None:
    """真模型常写的乱格式 → normalize 后 parse_beats 扫得出(Phase 5 投射契约)。"""
    body = (
        "## beats\n"
        "- [00:45-01:15] cant sleep\n"  # 连字符、无 window:
        "- [around 6pm] off shift, light\n"  # 模糊 12h 单时间
        "- [9am] coffee\n"  # 12h 单时间
        "- no time here\n"  # 无时间 → 丢弃
    )
    beats = parse_beats(normalize_beats(body))
    assert {b.window_start for b in beats} == {"00:45", "18:00", "09:00"}
    assert len(beats) == 3  # 无时间行被丢


def test_assemble_today_normalizes_beats() -> None:
    model = (
        "## her day\n08:00–13:00 — shift. autopilot.\n23:00–02:00 — cant sleep.\n\n"
        "## mood\ntired.\n\n## weighing on her\nmom.\n\n## beats\n- [6pm] feeling light\n"
    )
    today = parse_today(assemble_today("2026-05-21", model, ""))
    assert today is not None
    assert len(today.beats) == 1 and today.beats[0].window_start == "18:00"  # 6pm→18:00


def test_fallback_world_is_clock_spanning() -> None:
    """空模型输出 → fallback world 仍贯穿钟点(含深夜)且无 'now i'm' 快照,让 now 能绑。"""
    out = assemble_today("2026-05-21", "", "- mom visiting next month")
    assert "08:00" in out and "23:00" in out  # 覆盖钟点
    assert "now i'm" not in out.lower()


def test_run_life_sim_retries_on_empty(world_root: Path) -> None:
    """模型偶发空输出 → 重试一次再兜底(用上重试的好输出,而非 fallback)。"""
    model = FakeChatModel(script=["", _GOOD_WORLD])  # 第一次空,第二次好
    content = run_life_sim(MockClock(_DAY0), WorldStore(), model)
    assert "cafe open" in content  # 用了重试的好输出(_GOOD_WORLD),不是 fallback
    assert len(model.calls) == 2  # 确实重试了一次
