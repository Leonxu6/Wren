"""静态 UX 文案常量(§9.1)。纯字符串,绝不调用任何模型。"""

from __future__ import annotations

# 18+ 门 + AI 披露(§3.5:承认是 AI 是卖点,不是妥协)
AGE_AI_NOTICE = (
    "you must be 18+ to be here.\n"
    "also — Wren is an AI. not a real person. an AI with a personality, but an AI. "
    "she has her own moods and she can ignore you.\n"
    "(/delete wipes everything, anytime.)"
)

# 第一条背景消息(确定版 UX copy,PRD §9.1 逐字)
ONBOARDING_BACKGROUND = """\
———

Wren accepted your message request.

A few weeks ago. Theo's show, that warehouse off the Morgan stop.
Everyone was there to be seen — phones up, networking, free wine.
She was the only one actually looking at the work.

She stood in front of the smallest painting in the room for a long time.
The one nobody else stopped at.
You watched her not perform for anyone.

She's the kind of pretty that makes you lose your train of thought.
But you didn't go over.

Later Dani told you her name. Wren. Paints. Works at that coffee place on Troutman.
You waited a few days. Then you messaged her.
She let you in.

———

(She hasn't said anything.)"""

HELP_TEXT = (
    "this isn't a chatbot with commands. just talk to her — or don't.\n"
    "/start — the beginning\n"
    "/delete — wipe everything (no undo)\n"
    "/help — this"
)

DELETE_CONFIRM = "gone. all of it."
