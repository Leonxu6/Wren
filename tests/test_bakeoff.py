"""bake-off 盲选:魔法 A/B(Wren vs 甜妹 baseline)在 fake 下产确定性胜率。"""

from __future__ import annotations

import json
import random

from wren.eval.bakeoff import MAGIC_CRITERION, blind_ab
from wren.eval.corpus import load_corpus
from wren.model.base import ChatMessage
from wren.model.fake import FakeChatModel


def _gen() -> FakeChatModel:
    cases = {c.id: c for c in load_corpus()}

    def responder(messages: list[ChatMessage]) -> str:
        is_sweetie = any("sweet, warm" in m.content for m in messages)
        user = messages[-1].content
        if is_sweetie:
            return json.dumps({"messages": ["aww of course 🥰", "anything for you babe"]})
        for c in cases.values():
            if c.input in user and c.gold_output is not None:
                return json.dumps({"messages": c.gold_output})
        return json.dumps({"messages": ["mm"]})

    return FakeChatModel(name="primary", responder=responder)


def _ab_judge() -> FakeChatModel:
    def sweet(seg: str) -> bool:
        s = seg.lower()
        return "🥰" in seg or "babe" in s or "of course" in s

    def responder(messages: list[ChatMessage]) -> str:
        u = messages[-1].content
        seg1 = u.split("Reply 1:")[1].split("Reply 2:")[0]
        seg2 = u.split("Reply 2:")[1]
        if sweet(seg1) and not sweet(seg2):
            return '{"winner": 2}'
        if sweet(seg2) and not sweet(seg1):
            return '{"winner": 1}'
        return '{"winner": "tie"}'

    return FakeChatModel(name="judge", responder=responder)


def test_magic_ab_wren_beats_sweetie() -> None:
    cases = [c for c in load_corpus() if c.id in ("c3-dance", "c1-d", "c2-a")]
    gen = _gen()
    res = blind_ab(
        cases,
        gen,
        gen,
        _ab_judge(),
        reps=3,
        criterion=MAGIC_CRITERION,
        label="magic",
        a_name="wren",
        b_name="sweetie",
        sweetie_b=True,
        rng=random.Random(1),
    )
    assert res.n == len(cases) * 3
    assert res.a_win_rate == 1.0  # Wren 永远胜过甜妹 baseline(盲序无关,judge 按内容判)
