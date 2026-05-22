"""Step1→Step2(fake 下):结构化解析、沉默 branch、产出过机械门。"""

from __future__ import annotations

import json

from wren.core.context import TurnContext
from wren.core.step1 import Step1Result, run_step1
from wren.core.step2 import run_step2
from wren.core.storage import Relationship
from wren.eval.mech_gate import run_mech_gate
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel
from wren.prompts.step1 import parse_step1


def _ctx(user_text: str, level: int = 0) -> TurnContext:
    return TurnContext(
        chat_id="c",
        user_text=user_text,
        relationship=Relationship(level=level, prose="x", freeze=False),
        inner_voice="y",
        recent_dialogue="",
        events="",
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
        event_to_store=None,
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


def test_step1_parses_event_three_states() -> None:
    # 有 event:解析出 text + 标签
    d = parse_step1(
        json.dumps(
            {
                "monologue": "m",
                "reply": True,
                "delay_s": 0,
                "event": {
                    "text": "landlord fixed the heat",
                    "topic": "heat",
                    "valence": "neutral",
                    "salience": "low",
                },
            }
        )
    )
    assert d["event"]["text"] == "landlord fixed the heat" and d["event"]["salience"] == "low"
    # event=null → None
    assert parse_step1(json.dumps({"monologue": "m", "reply": True, "event": None}))["event"] is None
    # 缺省 → None
    assert parse_step1(json.dumps({"monologue": "m", "reply": True}))["event"] is None
    # 坏形(text 空 / 非 dict)→ None
    assert parse_step1(json.dumps({"monologue": "m", "event": {"topic": "x"}}))["event"] is None
    assert parse_step1(json.dumps({"monologue": "m", "event": "oops"}))["event"] is None


def test_step2_gets_thread_but_not_events_dossier() -> None:
    """Step2 接对话线程(接得住话、不再 thread-blind),但【不】接 events dossier(反污染 §4/§8 红线)。"""
    captured: dict[str, str] = {}

    def responder(messages: list[ChatMessage]) -> str:
        captured["blob"] = "\n".join(m.content for m in messages)
        return json.dumps({"messages": ["the big one", "still not done"]})

    s1 = Step1Result(
        monologue="i can say a little about it",
        reply=True,
        delay_s=0,
        impression=None,
        selected_memory=[],
        event_to_store=None,
        raw="",
        model="fake",
        tokens=0,
        latency_ms=0,
    )
    ctx = TurnContext(
        chat_id="c",
        user_text="the painting!",
        relationship=Relationship(level=0, prose="x", freeze=False),
        inner_voice="y",
        recent_dialogue="user: you were at the show\nwren: yeah\nuser: the painting!",
        events="- [grief|neg|high] their dad died last month",
    )
    run_step2(s1, ctx, FakeChatModel(responder=responder))
    assert "you were at the show" in captured["blob"]  # 线程进了 Step2 → 接得住话
    assert "their dad died" not in captured["blob"]  # events dossier 没进 Step2 → 反污染保住
