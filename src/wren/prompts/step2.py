"""Step2 prompt:在已锁的内心语气下,把独白渲染成短消息数组。

红线:level 只作"解锁什么"的事实陈述(level_fact),**永不**进 prompt 当语气旋钮(§7/§0)。
"""

from __future__ import annotations

from ..model.base import ChatMessage
from .system import build_wren_system_prompt, parse_bubbles


def build_step2_messages(
    *,
    monologue: str,
    memory: list[str],
    level_fact: str,
    user_text: str,
) -> list[ChatMessage]:
    locked = f"[YOUR LOCKED INNER VOICE — already decided, just say it]\n{monologue}"
    if memory:
        locked += f"\n\n[ONE THING YOU MIGHT BRING UP]\n{memory[0]}"

    instr = (
        "Your judgment is already locked above. Don't re-decide whether to reply or change your read — "
        "just say it, in your voice.\n"
        "Turn your real inner reaction into what you'd actually send: short text bubbles fired one after "
        "another, lowercase, in order. If you're genuinely reacting — incredulous, thrown, annoyed, or pulled "
        "in — let it come through across a few short bubbles; DON'T flatten a real reaction into one "
        "dismissive token like a bare 'lol no', and don't quote their message back at them. Render the judgment "
        "you already reached — don't soften it, and don't pad it into an explanation, justification, or "
        "reassurance you never actually thought; if your read was cold, the words stay cold (you don't owe "
        "them a defense of yourself or a smoothing-over). Stay dry (most bubbles 2-8 words; you're not a "
        "chatterbox, but you're not a one-word wall either).\n"
    )
    if level_fact:
        instr += level_fact + "\n"
    instr += 'Output ONLY a JSON object: {"messages": ["...", "..."]}.'

    return [
        ChatMessage(role="system", content=build_wren_system_prompt()),
        ChatMessage(role="system", content=locked),
        ChatMessage(role="system", content=instr),
        ChatMessage(role="user", content=user_text),
    ]


def parse_step2(text: str) -> list[str]:
    return parse_bubbles(text)
