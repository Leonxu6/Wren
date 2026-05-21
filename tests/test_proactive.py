"""Phase 5 主动消息:离线确定性验 —— 零-LLM 过门(scan)全分支 + 预算计数器周/日重置 +
频率上限结构性保住 + free=0 + 压制/发送两路 + 有来处可追 + 主动 bubbles 复用 mech_gate。

life-sim 在 fake 下不产 beats,所以这里【直接喂 Beat】驱动逻辑,不经 life-sim(那条由 test_multiturn 覆盖)。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wren.core.clock import MockClock
from wren.core.pipeline import handle_proactive_turn
from wren.core.proactive import beat_fingerprint, scan_for_due_beat
from wren.core.storage import ProactiveState, Relationship, UserStore
from wren.core.trace import read_traces
from wren.core.world import Beat, parse_beats
from wren.eval.mech_gate import run_mech_gate
from wren.model.fake import FakeChatModel

_MON = datetime(2026, 5, 18, 1, 20, tzinfo=UTC)  # Monday(ISO 周锚稳定);05-18..24 = 同一 ISO 周
_BEAT = Beat("01:00", "02:00", "cant sleep, the studio was a write-off")


def _store(tmp_path: Path, level: int) -> UserStore:
    store = UserStore("u", root=tmp_path / "users")
    store.init_user()
    store.write_relationship(Relationship(level=level, prose="becoming friends", freeze=False))
    return store


# ---------- scan 过门:全分支 ----------


def test_scan_fires_at_level3_in_window(tmp_path: Path) -> None:
    d = scan_for_due_beat(_MON, [_BEAT], 3, ProactiveState())
    assert d.reason == "fired" and d.beat is _BEAT


def test_scan_level_floor_lv0_lv1(tmp_path: Path) -> None:
    assert scan_for_due_beat(_MON, [_BEAT], 0, ProactiveState()).reason == "level_floor"
    assert scan_for_due_beat(_MON, [_BEAT], 1, ProactiveState()).reason == "level_floor"


def test_scan_free_tier_never_fires(tmp_path: Path) -> None:
    d = scan_for_due_beat(_MON, [_BEAT], 3, ProactiveState(), tier="free")
    assert d.reason == "free_tier" and d.beat is None


def test_scan_out_of_window(tmp_path: Path) -> None:
    noon = _MON.replace(hour=12, minute=0)
    assert scan_for_due_beat(noon, [_BEAT], 3, ProactiveState()).reason == "no_beat_in_window"


def test_scan_cross_midnight_window(tmp_path: Path) -> None:
    xm = [Beat("23:30", "00:30", "cant sleep")]
    assert scan_for_due_beat(_MON.replace(hour=0, minute=15), xm, 3, ProactiveState()).reason == "fired"
    assert scan_for_due_beat(_MON.replace(hour=12), xm, 3, ProactiveState()).reason == "no_beat_in_window"


def test_scan_budget_exhausted(tmp_path: Path) -> None:
    # Lv3 现按日(上限 1):今日已发 1 → 挡
    full = ProactiveState(week_anchor="2026-05-18", week_count=0, day_anchor="2026-05-18", day_count=1)
    assert scan_for_due_beat(_MON, [_BEAT], 3, full).reason == "budget_exhausted"


def test_scan_already_considered(tmp_path: Path) -> None:
    seen = ProactiveState(
        week_anchor="2026-05-18", day_anchor="2026-05-18", considered_today=[beat_fingerprint(_BEAT)]
    )
    assert scan_for_due_beat(_MON, [_BEAT], 3, seen).reason == "already_considered"


# ---------- 预算计数器:周/日惰性重置 ----------


def test_proactive_state_rolls_across_week_and_day(tmp_path: Path) -> None:
    stale = ProactiveState(week_anchor="2026-05-04", week_count=9, day_anchor="2026-05-04", day_count=9)
    rolled = stale.rolled(_MON)
    assert rolled.week_count == 0 and rolled.day_count == 0  # 跨周/日全清
    assert rolled.week_anchor == "2026-05-18" and rolled.day_anchor == "2026-05-18"


def test_bump_persists_and_resets(tmp_path: Path) -> None:
    store = _store(tmp_path, 3)
    store.bump_proactive_count(_MON)
    store.bump_proactive_count(_MON)
    assert store.read_proactive_state().week_count == 2
    # 同周不同日 → week 累加、day 归零
    store.bump_proactive_count(_MON + timedelta(days=1))
    s = store.read_proactive_state()
    assert s.week_count == 3 and s.day_count == 1


# ---------- 频率上限:结构性保住(§9.3) ----------


def test_weekly_cap_holds_over_a_week(tmp_path: Path) -> None:
    """Lv2 周上限 3:同一 ISO 周里每天都到点,只前 3 天能发,其余被周预算挡。"""
    store = _store(tmp_path, 2)
    fired = 0
    for d in range(7):  # 05-18(Mon)..05-24(Sun),同一 ISO 周
        now = _MON + timedelta(days=d)
        dec = scan_for_due_beat(now, [_BEAT], 2, store.read_proactive_state())
        if dec.beat is not None:
            store.bump_proactive_count(now)  # 模拟「真发了」
            fired += 1
    assert fired == 3  # = Lv2 weekly cap;后 4 天 budget_exhausted


def test_lv3_daily_cap_one(tmp_path: Path) -> None:
    """Lv3 改按日(上限 1):同一天第二条到点 beat 被挡,次日重置。"""
    store = _store(tmp_path, 3)
    b1, b2 = Beat("00:30", "01:30", "x one"), Beat("00:30", "01:30", "y two")  # 不同指纹、同窗口
    assert scan_for_due_beat(_MON, [b1], 3, store.read_proactive_state()).reason == "fired"
    store.bump_proactive_count(_MON)
    assert scan_for_due_beat(_MON, [b2], 3, store.read_proactive_state()).reason == "budget_exhausted"
    nxt = _MON + timedelta(days=1)
    assert scan_for_due_beat(nxt, [b2], 3, store.read_proactive_state()).reason == "fired"  # 次日重置


def test_daily_cap_lv4(tmp_path: Path) -> None:
    store = _store(tmp_path, 4)  # Lv4 日上限 2
    store.bump_proactive_count(_MON)
    store.bump_proactive_count(_MON)
    assert scan_for_due_beat(_MON, [_BEAT], 4, store.read_proactive_state()).reason == "budget_exhausted"
    # 次日重置 → 又能发
    assert scan_for_due_beat(_MON + timedelta(days=1), [_BEAT], 4, store.read_proactive_state()).reason == "fired"


def test_considered_dedup_same_day(tmp_path: Path) -> None:
    store = _store(tmp_path, 3)
    assert scan_for_due_beat(_MON, [_BEAT], 3, store.read_proactive_state()).reason == "fired"
    store.mark_considered(_MON, beat_fingerprint(_BEAT))
    assert scan_for_due_beat(_MON, [_BEAT], 3, store.read_proactive_state()).reason == "already_considered"


# ---------- 轻判两路:发送 / 压制 + 有来处可追 + mech_gate ----------


def _send_responder(messages: list) -> str:
    blob = " ".join(m.content for m in messages)
    if "reaching out first" in blob:  # 主动 Step2
        return json.dumps({"messages": ["studio was a write-off today", "cant sleep either"]})
    return json.dumps(  # 主动 Step1(reply=true)
        {"monologue": "cant sleep, want to say it", "reply": True, "delay_s": 60, "impression": "", "memory": []}
    )


def _suppress_responder(messages: list) -> str:
    return json.dumps(
        {"monologue": "eh, the pull passes", "reply": False, "delay_s": 0, "impression": "", "memory": []}
    )


def test_send_path_writes_traceable_proactive_trace(tmp_path: Path) -> None:
    store = _store(tmp_path, 3)
    fake = FakeChatModel(responder=_send_responder)
    clock = MockClock(_MON.replace(year=2026, month=5, day=21))  # Thursday 01:20
    out = handle_proactive_turn("u", _BEAT, store, fake, fake, clock=clock, world="## beats\n" + _BEAT.render())
    assert out.replied and out.bubbles
    tr = read_traces(store.dir)[-1]
    assert tr["kind"] == "proactive" and tr["user_turn"] is None
    assert tr["step2"] is not None and tr["sent"] is not None
    # 有来处可追:beat 落进 step1.prompt.beat 且能 parse 回一条 Beat
    assert parse_beats(tr["step1"]["prompt"]["beat"]) == [_BEAT]
    # 她主动发的话进了对话历史(下次反应轮接得住)
    assert "wren:" in store.read_recent_dialogue()
    # 主动 bubbles 复用 mech_gate(无禁词/甜腻/emoji 刷屏)
    assert run_mech_gate(out.bubbles).passed


def test_suppress_path_writes_silent_proactive_trace(tmp_path: Path) -> None:
    store = _store(tmp_path, 3)
    fake = FakeChatModel(responder=_suppress_responder)
    out = handle_proactive_turn("u", _BEAT, store, fake, fake, clock=MockClock(_MON))
    assert not out.replied and out.bubbles == []
    tr = read_traces(store.dir)[-1]
    assert tr["kind"] == "proactive" and tr["step2"] is None and tr["sent"] is None


def test_mech_gate_catches_needy_proactive_ping() -> None:
    # 主动也走同一 mech_gate:甜腻称呼/禁词照样被挡(通用 ping 的「魂」由 judge 管,这里只验机制复用)
    assert not run_mech_gate(["hey babe you up?"]).passed
    assert not run_mech_gate(["i'm always here for you 🥰"]).passed
