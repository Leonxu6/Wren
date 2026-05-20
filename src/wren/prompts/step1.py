"""Step1 prompt:涌现内心独白 + 唯一两结构化读数(回不回/延迟 + 印象)。判断先于措辞。"""

from __future__ import annotations

from typing import Any

from ..model.base import ChatMessage
from .jsonio import loads_lenient
from .system import build_wren_system_prompt

_STEP1_INSTRUCTION = """\
This is your private head — nobody sees this. Think first, before any wording.
Read the situation as Wren and decide, in this order:
1. Do you even reply? Silence (leaving it on read) is a real, first-class choice — pick it when that's what \
you'd actually do (low-effort approaches, being told what to do, nothing worth answering).
2. If you reply, how long would you realistically wait first (seconds)?
3. Your honest in-character read on this person right now (one short note), if anything shifted.
4. At most ONE thing from memory worth surfacing when you speak. Usually none.

Output ONLY a JSON object:
{"monologue": "<your private inner voice, lowercase>", "reply": <true|false>, \
"delay_s": <integer seconds>, "impression": "<one short in-character note, or empty>", \
"memory": [<0 or 1 short string>]}"""


def build_step1_messages(
    *,
    relationship_prose: str,
    inner_voice: str,
    recent_dialogue: str,
    user_text: str,
) -> list[ChatMessage]:
    ctx = (
        f"[YOUR CURRENT RELATIONSHIP WITH THIS PERSON]\n{relationship_prose}\n\n"
        f"[YOUR INNER VOICE RIGHT NOW]\n{inner_voice}\n\n"
        f"[RECENT MESSAGES]\n{recent_dialogue or '(none yet)'}"
    )
    return [
        ChatMessage(role="system", content=build_wren_system_prompt()),
        ChatMessage(role="system", content=ctx),
        ChatMessage(role="system", content=_STEP1_INSTRUCTION),
        ChatMessage(role="user", content=user_text),
    ]


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
    }
