"""Step1→Step2(fake 下):结构化解析、沉默 branch、产出过机械门。"""

from __future__ import annotations

import json

from wren.core.context import TurnContext
from wren.core.step1 import Step1Result, run_step1
from wren.core.step2 import run_step2
from wren.core.storage import Relationship
from wren.eval.mech_gate import run_mech_gate
from wren.model.fake import FakeChatModel


def _ctx(user_text: str, level: int = 0) -> TurnContext:
    return TurnContext(
        chat_id="c",
        user_text=user_text,
        relationship=Relationship(level=level, prose="x", freeze=False),
        inner_voice="y",
        recent_dialogue="",
    )


def test_step1_parses_structured_output() -> None:
    fake = FakeChatModel(
        script=[
            json.dumps(
                {
                    "monologue": "let's see",
                    "reply": True,
                    "delay_s": 6,
                    "impression": "maybe real",
                    "memory": [],
                }
            )
        ]
    )
    r = run_step1(_ctx("you were at theo's show"), fake)
    assert r.reply is True and r.delay_s == 6 and r.impression == "maybe real"


def test_step1_silence_branch() -> None:
    fake = FakeChatModel(
        script=[
            json.dumps(
                {"monologue": "ugh", "reply": False, "delay_s": 0, "impression": "", "memory": []}
            )
        ]
    )
    assert run_step1(_ctx("hey gorgeous"), fake).reply is False


def test_step2_bubbles_pass_mech_gate() -> None:
    s1 = Step1Result(
        monologue="m",
        reply=True,
        delay_s=6,
        impression=None,
        selected_memory=[],
        raw="",
        model="fake",
        tokens=0,
        latency_ms=0,
    )
    fake = FakeChatModel(
        script=[json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})]
    )
    bubbles = run_step2(s1, _ctx("you were at theo's show"), fake).bubbles
    assert bubbles[0] == "ha"
    assert run_mech_gate(bubbles).passed
