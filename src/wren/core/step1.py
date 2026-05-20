"""Step1:涌现内心(cheap call)。结构化读数 = 回不回/延迟 + 印象 + 0-1 召回 + 可选一条值得记住的事(中期记忆)。

红线:不另立姿态/踩雷/lockout 字段(踩雷活在独白里涌现);记忆涌现自同一 call、非全量记录(§0①);判断先于措辞;沉默是头等 branch。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..model.base import ChatModel
from ..prompts.step1 import build_step1_messages, parse_step1
from .context import TurnContext


@dataclass
class Step1Result:
    monologue: str
    reply: bool  # False = leave on read(头等 branch)
    delay_s: int
    impression: str | None
    selected_memory: list[str]  # 0-1 条传给 Step2(反污染)
    event_to_store: dict[str, str] | None  # 涌现的「值得记住的事」→ events.md(可空)
    raw: str
    model: str
    tokens: int | None
    latency_ms: int


def run_step1(ctx: TurnContext, model: ChatModel) -> Step1Result:
    msgs = build_step1_messages(
        relationship_prose=ctx.relationship.prose,
        inner_voice=ctx.inner_voice,
        events=ctx.events,
        recent_dialogue=ctx.recent_dialogue,
        user_text=ctx.user_text,
    )
    out = model.complete(
        msgs, temperature=0.8, response_format="json", max_tokens=config.max_tokens()
    )
    d = parse_step1(out.text)
    return Step1Result(
        monologue=d["monologue"],
        reply=d["reply"],
        delay_s=d["delay_s"],
        impression=d["impression"],
        selected_memory=d["memory"],
        event_to_store=d["event"],
        raw=out.text,
        model=out.model,
        tokens=out.completion_tokens,
        latency_ms=out.latency_ms,
    )
