"""pipeline + trace(p1-trace):回复轮落完整 trace、沉默轮 step2=null、inner_voice 更新。"""

from __future__ import annotations

import json
from pathlib import Path

from wren.core.pipeline import compute_pacing, handle_turn
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.model.fake import FakeChatModel

_S1_REPLY = json.dumps(
    {
        "monologue": "let's see what they've got",
        "reply": True,
        "delay_s": 6,
        "impression": "noticed the small painting",
        "memory": [],
    }
)
_S1_SILENT = json.dumps(
    {"monologue": "ugh", "reply": False, "delay_s": 0, "impression": "", "memory": []}
)
_S2 = json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})
_S1_REPLY_EVENT = json.dumps(
    {
        "monologue": "ok the heat thing",
        "reply": True,
        "delay_s": 4,
        "impression": "",
        "memory": [],
        "event": {"text": "landlord fixed the heat", "topic": "heat", "valence": "neutral", "salience": "low"},
    }
)
_S1_SILENT_EVENT = json.dumps(
    {
        "monologue": "spam, ignore",
        "reply": False,
        "delay_s": 0,
        "impression": "",
        "memory": [],
        "event": {"text": "their sister is visiting", "topic": "sister", "valence": "neutral", "salience": "med"},
    }
)


def test_reply_turn_writes_full_trace(data_root: Path) -> None:
    s = UserStore("100", data_root)
    s.init_user()
    out = handle_turn(
        "100",
        "you were at theo's show right",
        s,
        FakeChatModel(script=[_S1_REPLY]),
        FakeChatModel(script=[_S2]),
    )
    assert out.replied and out.bubbles[0] == "ha"
    traces = read_traces(s.dir)
    assert len(traces) == 1
    t = traces[0]
    assert t["step2"] is not None
    assert t["sent"]["bubbles"] == out.bubbles
    assert t["step1"]["reply"] is True
    assert t["relationship"]["lv"] == 0
    assert t["turn_id"] == "100-1"


def test_silence_turn_writes_trace_with_null_step2(data_root: Path) -> None:
    s = UserStore("101", data_root)
    s.init_user()
    out = handle_turn(
        "101", "hey gorgeous", s, FakeChatModel(script=[_S1_SILENT]), FakeChatModel(script=[_S2])
    )
    assert not out.replied and out.bubbles == []
    t = read_traces(s.dir)[0]
    assert t["step2"] is None and t["sent"] is None
    assert t["step1"]["reply"] is False


def test_inner_voice_updated_after_turn(data_root: Path) -> None:
    s = UserStore("102", data_root)
    s.init_user()
    handle_turn("102", "hi", s, FakeChatModel(script=[_S1_REPLY]), FakeChatModel(script=[_S2]))
    assert "let's see what they've got" in s.read_inner_voice()


def test_event_persisted_and_traced(data_root: Path) -> None:
    s = UserStore("103", data_root)
    s.init_user()
    handle_turn(
        "103", "landlord finally fixed the heat", s,
        FakeChatModel(script=[_S1_REPLY_EVENT]), FakeChatModel(script=[_S2]),
    )
    evs = s.read_event_list()
    assert len(evs) == 1 and evs[0].topic == "heat"
    t = read_traces(s.dir)[0]
    assert t["step1"]["event_stored"]["text"] == "landlord fixed the heat"
    assert "events" in t["step1"]["prompt"]  # 注入的中期记忆进了 trace


def test_no_event_means_no_write(data_root: Path) -> None:
    s = UserStore("104", data_root)
    s.init_user()
    handle_turn("104", "hi", s, FakeChatModel(script=[_S1_REPLY]), FakeChatModel(script=[_S2]))
    assert s.read_event_list() == []  # event 缺省 → 不写
    assert read_traces(s.dir)[0]["step1"]["event_stored"] is None


def test_silence_turn_still_records_event(data_root: Path) -> None:
    s = UserStore("105", data_root)
    s.init_user()
    out = handle_turn(
        "105", "...", s, FakeChatModel(script=[_S1_SILENT_EVENT]), FakeChatModel(script=[_S2])
    )
    assert not out.replied  # 沉默(leave on read)
    evs = s.read_event_list()
    assert len(evs) == 1 and evs[0].topic == "sister"  # 沉默轮也记住了 → 写在 reply 分支前


def test_compute_pacing() -> None:
    typing, gaps = compute_pacing(["ha", "the wine was bad though", "which one were you"])
    assert typing > 0 and len(gaps) == 2
    assert compute_pacing([]) == (0, [])
