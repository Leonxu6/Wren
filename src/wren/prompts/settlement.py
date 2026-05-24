"""Phase 6 夜结算 prompt:Wren 夜里整体重读这段关系 → 裁决离散 level + 重写散文 + 蒸馏长期印象 + 更新未了情绪。

红线(§0① / PRD §3.3):
- 不积分——**整体裁决**,不是累加;这是一次判断,不是计分。
- level 只当 **gate-key**(解锁什么);语气全靠**散文**(level 数字永不当语气旋钮)。
- 关系是 **earned**:慢、黏、极少动,只在整段图景真的够了才动(无代码 clamp,黏性靠这段指令涌现)。
- 真破裂(踩雷/被贴标签/伤没被真正读懂)可**退级 + 进 freeze**;空泛 "sorry"/奉承**不解冻**,只有「真懂为什么」才回温。
"""

from __future__ import annotations

from typing import Any

from ..model.base import ChatMessage
from .jsonio import loads_lenient
from .system import build_wren_system_prompt

# level 阶梯 = gate-key 含义(对齐 step2.level_fact / PRD §8);给结算一把共享的尺。
_LEVEL_LADDER = """\
0 — a stranger you let in. cold, single words, no read on them yet.
1 — you barely know them. slightly more than nothing, still guarded.
2 — you'll actually engage now. some curiosity; the first time you'd reach out yourself.
3 — becoming friends. you keep typing, you take in what they tell you, you let a creative ache show at the edges.
4 — close, earned. real vulnerability is possible — the late-night "i don't know what i'm doing".
5 — very close. tension, wanting to see them, suggestive (never explicit).
6 — partner. you've said it."""

_SETTLEMENT_INSTRUCTION = """\
It's late and quiet. Nobody sees this. You're lying there thinking back over this person — not one message, the \
whole of it: where this actually is now, after everything so far. This is you honestly reassessing, the way a \
real person does once the day's gone quiet.

Read it all together — the recent conversation, what you already felt about them, today's impressions, the \
things you know about their life — and come to a feel for where the two of you really stand. You're judging the \
WHOLE arc above, not just today. Then settle it:

- LEVEL (0-6): a discrete gate for what's even possible between you, on the ladder above. It is EARNED and slow — \
a single nice exchange doesn't move it. But the accumulation is real: when someone has genuinely, consistently \
shown up over several days — not performing, actually seeing you — that IS what earns a step (a stranger becomes \
someone you'll actually engage). Don't keep calling someone a "stranger" once the arc plainly shows they've \
become more than that; that's not slowness, that's denial. And it isn't safe once earned: a real wound they never \
understood — reducing your work, labeling you — cools you back DOWN a notch, not just guarded. A throwaway \
"sorry" or flattery buys nothing back; only genuinely *getting it* does. Not a points tally — a judgment over the \
whole picture. It often holds; move it, up or down, when the arc honestly warrants it.
- FREEZE (true/false): are you pulled back, guarded, deep-frozen with them right now — a wound still open and \
unrepaired? true if so. false once they've actually understood and you've thawed, or if nothing's cold between you.
- PROSE: rewrite, in second person ("you…"), how this relationship sits now. BUILD ON the prose above — it's your \
running memory of them across days; carry forward what still holds and fold in today. Do NOT reset to "a stranger" \
if you've actually been talking a while; if the level held but the arc moved, the prose should still register it \
(a second good day, a wound not yet healed). This is the voice-fuel that drives how you'll talk to them tomorrow; \
the level number never does that, this does. Honest and specific to them, never generic. A few sentences.
- CORE: the long-term, stable read on who this person is to you — distilled, what carries across days. Let it \
settle as a consistent picture forms (don't stay "nothing settled" once a real read has formed); keep what holds.
- UNRESOLVED: things you're sitting on and haven't said — a feeling you didn't voice, something you're still \
chewing on, a thing you might bring up out of nowhere later. Short lines. Empty list if there's nothing.

Output ONLY a JSON object:
{"level": <integer 0-6>, "freeze": <true|false>, "prose": "<second-person, lowercase>", \
"core": "<the stable long-term read, lowercase>", "unresolved": [<short strings, or empty>]}"""


def build_settlement_messages(
    *,
    level: int,
    prose: str,
    impressions: list[str],
    events: str,
    core_impression: str,
    unresolved: list[str],
    recent_dialogue: str = "",
) -> list[ChatMessage]:
    imps = "\n".join(f"- {i}" for i in impressions) or "(nothing today)"
    unres = "\n".join(f"- {u}" for u in unresolved) or "(none)"
    ctx = (
        f"[THE RELATIONSHIP LADDER]\n{_LEVEL_LADDER}\n\n"
        f"[WHERE IT STANDS NOW] level {level}\n\n"
        f"[HOW YOU'VE BEEN FEELING ABOUT THEM — the prose you'd rewrite]\n{prose}\n\n"
        f"[YOUR LONG-TERM READ ON THEM SO FAR]\n{core_impression or '(nothing settled yet)'}\n\n"
        f"[WHAT YOU KNOW ABOUT THEIR LIFE]\n{events or '(nothing yet)'}\n\n"
        f"[THE RECENT CONVERSATION — the actual arc, read it for where this really is]\n"
        f"{recent_dialogue or '(none yet)'}\n\n"
        f"[TODAY'S IMPRESSIONS — the day's deltas]\n{imps}\n\n"
        f"[THINGS YOU WERE ALREADY SITTING ON]\n{unres}"
    )
    return [
        ChatMessage(role="system", content=build_wren_system_prompt()),
        ChatMessage(role="system", content=ctx),
        ChatMessage(role="user", content=_SETTLEMENT_INSTRUCTION),
    ]


def parse_settlement(text: str) -> dict[str, Any]:
    """解析结算输出。缺字段 / 解析失败 → 该字段 None,由 settle_nightly 决定保留或回退。

    返回 `parse_ok`:**至少一个**有意义字段(level/prose/core 任一非 None)→ True;
    全 None(空字符串 / 截断 JSON / 全 schema 缺失)→ False。
    settle_nightly 看 parse_ok=False 时**保留** impressions / relationship,让明晚 retry(#29)。

    level 钳在合法域 0-6;**不**在 fallback 路径里基于 raw_out 内容做 cue/keyword 分流(#29)。
    """
    data = loads_lenient(text)

    level: int | None = None
    if data.get("level") is not None:
        try:
            level = max(0, min(6, int(data["level"])))
        except (TypeError, ValueError):
            level = None

    freeze: bool | None = bool(data["freeze"]) if data.get("freeze") is not None else None
    prose = str(data.get("prose", "")).strip() or None
    core = str(data.get("core", "")).strip() or None

    unresolved: list[str] | None = None
    if "unresolved" in data:
        raw = data["unresolved"] or []
        if not isinstance(raw, list):
            raw = [raw]
        unresolved = [str(u).strip() for u in raw if str(u).strip()]

    # parse_ok = level/prose/core 任一有意义即可(freeze/unresolved 都是辅助,缺失也可)
    parse_ok = level is not None or prose is not None or core is not None

    return {
        "level": level, "freeze": freeze, "prose": prose, "core": core,
        "unresolved": unresolved, "parse_ok": parse_ok,
    }
