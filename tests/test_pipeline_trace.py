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


def test_compute_pacing() -> None:
    typing, gaps = compute_pacing(["ha", "the wine was bad though", "which one were you"])
    assert typing > 0 and len(gaps) == 2
    assert compute_pacing([]) == (0, [])
