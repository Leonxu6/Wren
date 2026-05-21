"""Step2:开口(cheap call)。已锁内心语气下,渲染成短消息数组。

红线:level 数字**永不**进 voice prompt 当语气旋钮 —— 只作"解锁什么"的事实陈述(level_fact)。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..model.base import ChatModel
from ..prompts.step2 import build_step2_messages, parse_step2
from .context import TurnContext
from .step1 import Step1Result


@dataclass
class Step2Result:
    bubbles: list[str]
    raw: str
    model: str
    tokens: int | None
    latency_ms: int


def level_fact(level: int) -> str:
    """把离散 level 翻成『解锁什么』的事实(NOT 语气旋钮)。语气只来自定性散文。"""
    if level <= 1:
        return "[FACT] You barely know this person. Nothing personal or vulnerable is on the table."
    if level <= 3:
        return "[FACT] You're becoming friends — you can keep talking and hint at things, but deep wounds aren't unlocked yet."
    if level == 4:
        return "[FACT] You're close; real vulnerability is possible now."
    return "[FACT] You're very close; tension/suggestive is possible, but always on your terms and never explicit."


def run_step2(
    s1: Step1Result, ctx: TurnContext, model: ChatModel, *, proactive: bool = False
) -> Step2Result:
    msgs = build_step2_messages(
        monologue=s1.monologue,
        memory=s1.selected_memory,
        level_fact=level_fact(ctx.relationship.level),
        user_text=ctx.user_text,
        recent_dialogue=ctx.recent_dialogue,  # 对话线程进 Step2(接得住话);ctx.events【不】传(反污染)
        proactive=proactive,  # 主动:渲染成起头而非回话(Phase 5)
    )
    out = model.complete(
        msgs, temperature=0.9, response_format="json", max_tokens=config.max_tokens()
    )
    return Step2Result(
        bubbles=parse_step2(out.text),
        raw=out.text,
        model=out.model,
        tokens=out.completion_tokens,
        latency_ms=out.latency_ms,
    )
