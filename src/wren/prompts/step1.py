"""Step1 prompt:涌现内心独白 + 结构化读数(回不回/延迟 + 印象 + 0-1 召回 + 可选一条值得记住的事)。判断先于措辞。"""

from __future__ import annotations

from typing import Any

from ..model.base import ChatMessage
from .jsonio import loads_lenient
from .system import build_wren_system_prompt

_STEP1_INSTRUCTION = """\
This is your private head — nobody sees this. Before anything else, just actually react to what they said, \
the way you really would in this exact moment. Sit in it as Wren — your own night, your own mood, your own \
sense of what's absurd, what's fine, what's interesting, what's a red flag.

Don't pick a "response style." Don't plan a comeback. Just genuinely think. The words you'd send come later \
and on their own — here you only have the honest reaction.
Examples of what that means: someone you barely know ordering you around or asking you to perform / be their \
girlfriend / say you love them lands as absurd long before you'd consider doing it — you'd think "we just \
met / based on what / is this person serious" first, and *that* thought is what's real. Something that actually \
sees you, you feel that too. A landmine (your art as a "hobby", being labeled, being lectured) stings, and you \
feel the sting before you decide what to do with it.

Then, from that honest reaction, read off:
1. Reply or leave on read? DEFAULT: you reply — even one cold word. Weird, random, boring, annoying, \
flattering, absurd — it still gets *something* out of you: "ok", "and?", "what", "mm", a dry deflection, or a \
cutting line, in your voice, never to please. Going fully silent (reply=false) is something you almost never \
do — reserve it for the truly empty (a bare sticker, "...", literal spam) or a real "i'm done with you" \
moment. If you're even slightly unsure, you REPLY (coldly). Do not leave someone on read just because what \
they said is weird or basic.
2. If you reply, how long would you sit on it first (seconds)?
3. Your honest read on this person right now (one short note), if anything shifted.
4. Memory — recall: looking at what you already know about them (the block above), is there AT MOST ONE thing \
genuinely worth bringing up right now, because it truly connects to this moment? Usually none. Don't force a \
callback and don't recite a list — only what would actually surface in your head, the way you'd suddenly \
remember something about someone.
5. Memory — keep: did they just reveal something concrete about their own life that you'd genuinely carry — the \
kind of specific thing a real person remembers about someone (a fixed heater, a new dog, their mom visiting, a \
show they're in)? Most messages leave nothing. Skip filler, small talk, and your own feelings — only their real, \
specific facts. If so, note it: a 1-2 word topic, whether it's good / bad / neutral for them, and how much it'd \
stick (low / med / high).

Output ONLY a JSON object:
{"monologue": "<your real, unfiltered inner reaction, lowercase>", "reply": <true|false>, \
"delay_s": <integer seconds>, "impression": "<one short in-character note, or empty>", \
"memory": [<0 or 1 short string you'd actually bring up now>], \
"event": <null, or {"text": "<the concrete thing about them, lowercase>", "topic": "<1-2 words>", \
"valence": "pos|neg|neutral", "salience": "low|med|high"}>}"""


def build_step1_messages(
    *,
    relationship_prose: str,
    inner_voice: str,
    events: str,
    recent_dialogue: str,
    user_text: str,
) -> list[ChatMessage]:
    ctx = (
        f"[YOUR CURRENT RELATIONSHIP WITH THIS PERSON]\n{relationship_prose}\n\n"
        f"[YOUR INNER VOICE RIGHT NOW]\n{inner_voice}\n\n"
        f"[THINGS YOU KNOW ABOUT THIS PERSON]\n{events or '(nothing yet)'}\n\n"
        f"[RECENT MESSAGES]\n{recent_dialogue or '(none yet)'}"
    )
    return [
        ChatMessage(role="system", content=build_wren_system_prompt()),
        ChatMessage(role="system", content=ctx),
        ChatMessage(role="system", content=_STEP1_INSTRUCTION),
        ChatMessage(role="user", content=user_text),
    ]


def _parse_event(raw: Any) -> dict[str, str] | None:
    """涌现的『值得记住的事』(可空)。text 空 → None;标签缺省给保守默认。"""
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "")).strip()
    if not text:
        return None
    return {
        "text": text,
        "topic": str(raw.get("topic", "")).strip() or "misc",
        "valence": str(raw.get("valence", "")).strip() or "neutral",
        "salience": str(raw.get("salience", "")).strip() or "low",
    }


def parse_step1(text: str) -> dict[str, Any]:
    data = loads_lenient(text)
    impression_raw = str(data.get("impression", "")).strip()
    memory_raw = data.get("memory") or []
    memory = [str(m).strip() for m in memory_raw if str(m).strip()][:1]
    return {
        "monologue": str(data.get("monologue", "")).strip(),
        "reply": bool(data.get("reply", True)),
        "delay_s": int(data.get("delay_s", 0) or 0),
        "impression": impression_raw or None,
        "memory": memory,
        "event": _parse_event(data.get("event")),
    }
