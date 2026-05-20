"""eval-wire(p1-eval-wire):同一把尺 + trace 回放 + 活 skeleton 打分。"""

from __future__ import annotations

import json
from pathlib import Path

from wren.core.pipeline import handle_turn
from wren.core.storage import UserStore
from wren.core.trace import trace_path
from wren.eval.corpus import load_corpus
from wren.eval.replay import (
    replay_trace_file,
    score_live_output,
    score_pipeline_on_corpus,
)
from wren.eval.scorer import score_output
from wren.model.fake import FakeChatModel

_C1D_INPUT = (
    "you were at theo's show right. the corner one actually looking at the "
    "paintings instead of filming the free wine"
)
_PASS_JUDGE = '{"dim":"D1","score":"pass","fail_mode":"none"}'


def _judge() -> FakeChatModel:
    return FakeChatModel(name="judge", responder=lambda m: _PASS_JUDGE)


def test_score_live_output_is_same_ruler() -> None:
    assert score_live_output is score_output  # 线上线下同一把尺


def test_replay_trace_file_matches_corpus(data_root: Path) -> None:
    s = UserStore("200", data_root)
    s.init_user()
    handle_turn(
        "200",
        _C1D_INPUT,
        s,
        FakeChatModel(
            script=[
                json.dumps(
                    {"monologue": "m", "reply": True, "delay_s": 6, "impression": "", "memory": []}
                )
            ]
        ),
        FakeChatModel(
            script=[
                json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})
            ]
        ),
    )
    report = replay_trace_file(trace_path(s.dir), _judge())
    assert len(report.rows) == 1
    assert report.rows[0].bubbles[0] == "ha"
    assert report.pass_rate == 1.0


def test_score_pipeline_on_corpus(data_root: Path, tmp_path: Path) -> None:
    cases = [c for c in load_corpus() if c.id == "c1-d"]
    s1 = FakeChatModel(
        name="s1",
        responder=lambda m: json.dumps(
            {"monologue": "let's see", "reply": True, "delay_s": 6, "impression": "", "memory": []}
        ),
    )
    s2 = FakeChatModel(
        name="s2",
        responder=lambda m: json.dumps(
            {"messages": ["ha", "the wine was bad though", "which one were you"]}
        ),
    )
    report = score_pipeline_on_corpus(cases, s1, s2, _judge(), root=tmp_path / "pl")
    assert report.pass_rate == 1.0
