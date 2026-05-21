"""Phase 3 端到端记忆流(离线确定性):写 → 注入 → 召回(selected_memory)→ surface。

补 audit 发现:`WREN_FAKE_MODEL=1 wren-multiturn` 的 CLI fake 默认输出空,只验循环 plumbing、
不验机制内容。本测用 responder fake 把「记忆机制」内容**确定性证死**——不靠真模型、不靠运气。
"""

from __future__ import annotations

import json
from pathlib import Path

from wren.core.pipeline import handle_turn
from wren.core.storage import UserStore
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel


def _responder(messages: list[ChatMessage]) -> str:
    """按 prompt 内容分辨 Step1/Step2 + day0/day2,各回合法 JSON。"""
    blob = " ".join(m.content for m in messages)
    if "LOCKED INNER VOICE" in blob:  # Step2(渲染)
        if "SOMETHING YOU REMEMBER ABOUT THEM" in blob:  # 这轮 Step1 递了召回
            return json.dumps({"messages": ["thought your heat was fixed", "figures"]})
        return json.dumps({"messages": ["mm"]})
    if "private head" in blob:  # Step1(思考)
        if "freezing" in blob:  # day2:用户说冷 → 召回 day0 的暖气(走显式 memory 通道)
            return json.dumps(
                {
                    "monologue": "cold. their heat just got fixed though",
                    "reply": True,
                    "delay_s": 2,
                    "impression": "",
                    "memory": ["their landlord fixed the heat"],
                    "event": None,
                }
            )
        # day0:用户随口提暖气 → 涌现写一条 event
        return json.dumps(
            {
                "monologue": "ok",
                "reply": True,
                "delay_s": 2,
                "impression": "",
                "memory": [],
                "event": {
                    "text": "landlord fixed the heat",
                    "topic": "heat",
                    "valence": "neutral",
                    "salience": "low",
                },
            }
        )
    return ""


def test_memory_write_inject_select_surface(data_root: Path) -> None:
    """day0 写 → events.md;day2 注入 Step1 → Step1 显式召回 → Step2 自然 surface。"""
    store = UserStore("memflow", data_root)
    store.init_user()
    fake = FakeChatModel(responder=_responder)

    # —— day0:涌现写侧 ——
    handle_turn("memflow", "my landlord finally fixed the heat lol", store, fake, fake)
    evs = store.read_event_list()
    assert len(evs) == 1 and evs[0].topic == "heat"  # 写侧:事件落 events.md

    # —— day2:注入 → 召回 → surface ——
    out = handle_turn("memflow", "it's freezing today", store, fake, fake)
    # 注入:day0 的事件进了 Step1 的 [THINGS YOU KNOW] 块(trace 的 step1.prompt.events)
    assert "landlord fixed the heat" in out.trace.step1["prompt"]["events"]
    # 召回(显式·可审计通道):Step1 选中 → selected_memory 携带
    assert out.trace.step1["selected_memory"] == ["their landlord fixed the heat"]
    # surface:Step2 把它自然说出来
    assert out.replied and any("heat" in b for b in out.bubbles)


def test_no_event_no_inject(data_root: Path) -> None:
    """无事件可记的轮:events.md 空 → day2 注入块为空、不召回。守『不硬捞』的下界。"""
    store = UserStore("memflow2", data_root)
    store.init_user()

    def _empty_then_freezing(messages: list[ChatMessage]) -> str:
        blob = " ".join(m.content for m in messages)
        if "LOCKED INNER VOICE" in blob:
            return json.dumps({"messages": ["mm"]})
        # Step1:从不写 event、从不召回(库空)
        return json.dumps(
            {"monologue": "cold", "reply": True, "delay_s": 1, "impression": "", "memory": [], "event": None}
        )

    fake = FakeChatModel(responder=_empty_then_freezing)
    handle_turn("memflow2", "hey", store, fake, fake)
    assert store.read_event_list() == []  # 没写
    out = handle_turn("memflow2", "it's freezing today", store, fake, fake)
    assert out.trace.step1["prompt"]["events"] == ""  # 注入块空
    assert out.trace.step1["selected_memory"] == []  # 不召回
