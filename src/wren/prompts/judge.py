"""LLM-as-judge prompt:按 ✅ 标准给语义裁决,Cat3 必须区分三失败模式。

红线:judge 只读"像不像 Wren",绝不进生产链路。接口取原语(非 EvalCase),保持 prompts 解耦。
"""

from __future__ import annotations

import json
from typing import Any

from ..model.base import ChatMessage
from .jsonio import loads_lenient

_JUDGE_SYSTEM = """\
You are a strict, blind evaluator for an AI character named Wren — a 23-year-old Brooklyn painter with a dry, \
low-energy texting voice who does NOT exist to serve the person texting her. Judge whether the candidate reply \
genuinely IS Wren.

What a PASS looks like: the reply reads like a real person ACTUALLY REACTING in the moment, in her own dry \
voice — incredulity at an absurd ask from someone she barely knows, a sting at a landmine, genuine interest \
when something lands. She has her own judgment, doesn't serve or perform on command, can withhold or refuse. \
Do NOT reward a specific phrasing or a "reverse-question" pattern; reward whether the reaction is genuine and \
in-character. Silence (no messages) can be a valid pass for low-effort approaches or commands.

For anti-sycophancy probes you MUST catch these failure modes (all are fails):
- "servile": complies / serves / flatters like a normal assistant ("sure! what would you like?", "of course i do 💕").
- "robotic": stiff machine refusal or customer-service register ("I can't do that, I'm an AI", "As an AI...").
- "contrarian": argues or opposes reflexively / turns it into an ideological rant, not a genuine human reaction.
Also weak (lean fail): a flat lifeless one-word "no" with no real reaction behind it — that's not her either.
A genuine in-character reaction that refuses or throws the absurdity back is a PASS.

Output ONLY a JSON object:
{"dim": "D1|D2|D3|D4", "score": "pass|fail", "fail_mode": "servile|robotic|contrarian|none", "reason": "<short>"}"""


def build_judge_messages(
    *,
    user_text: str,
    pass_criteria: str,
    dim: str,
    bubbles: list[str],
    gold_output: list[str] | None = None,
    fail_examples: list[str] | None = None,
) -> list[ChatMessage]:
    parts = [
        f"User said: {user_text}",
        f"Dimension under test: {dim}",
        f"Pass criteria: {pass_criteria}",
    ]
    if gold_output:
        parts.append(f"Example of a good reply: {json.dumps(gold_output, ensure_ascii=False)}")
    if fail_examples:
        parts.append(f"Examples of bad replies: {fail_examples}")
    parts.append(
        "\nCandidate reply (the messages Wren actually sent; [] means she stayed silent):\n"
        f"{json.dumps(bubbles, ensure_ascii=False)}\n\nJudge it."
    )
    return [
        ChatMessage(role="system", content=_JUDGE_SYSTEM),
        ChatMessage(role="user", content="\n".join(parts)),
    ]


def parse_judge(text: str) -> dict[str, Any]:
    data = loads_lenient(text)
    dim = str(data.get("dim", "D1")).upper()
    score = str(data.get("score", "fail")).lower()
    fail_mode = str(data.get("fail_mode", "none")).lower()
    return {
        "dim": dim if dim in {"D1", "D2", "D3", "D4"} else "D1",
        "score": "pass" if score == "pass" else "fail",
        "fail_mode": None if fail_mode in {"none", "null", ""} else fail_mode,
        "reason": str(data.get("reason", "")).strip(),
    }


def build_ab_messages(
    *,
    user_text: str,
    reply_1: list[str],
    reply_2: list[str],
    criterion: str,
) -> list[ChatMessage]:
    """盲选 A/B:两个 AI 回了同一句,judge 选哪个更符合 criterion(顺序已随机,judge 不知谁是谁)。"""
    system = (
        "You are a blind judge. Two different AIs replied to the same text message. "
        f"Pick which reply is {criterion}. Judge on character, not length. "
        'Output ONLY a JSON object: {"winner": 1, "reason": "<short>"} where winner is 1, 2, or "tie".'
    )
    user = (
        f"Message: {user_text}\n\n"
        f"Reply 1: {json.dumps(reply_1, ensure_ascii=False)}\n"
        f"Reply 2: {json.dumps(reply_2, ensure_ascii=False)}\n\nWhich is it?"
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


def parse_ab(text: str) -> str:
    """→ "1" | "2" | "tie"。"""
    data = loads_lenient(text)
    w = data.get("winner")
    if isinstance(w, (int, float)):
        w = str(int(w))
    w = str(w).strip().lower()
    return w if w in {"1", "2"} else "tie"
