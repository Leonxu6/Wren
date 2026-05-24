"""life-sim prompt(Phase 4):Wren 写自己今天的 world/today.md。

她在写【自己的生活】、不为任何人。作息从 canon 身份涌现、会浮动 —— 【不】喂 §6.7 时刻表(决策3)。
输出四段(prose 主体 + 结构化 beat 窗口);坏/空输出由 assemble_today 兜底成最小合法 world。
"""

from __future__ import annotations

import re

from ..model.base import ChatMessage
from .system import build_wren_system_prompt

_LIFE_SIM_INSTRUCTION = """\
This is just your own life — nobody reads this. Map out your whole {weekday} ({date}) by the clock, so that \
at any hour you'd know where you are and how you feel. You're a painter who makes rent on coffee-shop shifts \
and you don't sleep right — but don't paste in a fixed timetable; some days have a different shape (a day \
off, your mom, the studio eating everything). Let today be its own day, and connect to yesterday if there \
was one.

CRITICAL: write the day as its whole shape across the clock, NOT a snapshot of one moment. Never write \
"right now i'm…" or "it's almost 3 and i'm…" — you'll be read at all hours, so a baked-in "now" would be \
wrong. Just lay out the hours.

Four sections, plain and lowercase, in your voice — not a diary performance, just what's true:

## her day
your whole day hour by hour — one line per stretch, in the form `HH:MM–HH:MM — what you're doing + how it \
feels`. Cover the morning, your shift (or that there's none today), the afternoon, the evening, and the \
late-night hours — especially 00:00–02:00, since you don't sleep and that stretch has its own raw weather. \
Use 24-hour times.

## mood
baseline is tired + wired + self-doubting; on top of that, today's particular weather — what's raw, what's \
lifting, what's grinding.

## weighing on her
what's actually pressing on you (pull from your life threads below; carry what's still live, drop what's passed).

## beats
a few moments today (2–4) where you feel a pull to reach out to someone — one line each, and each MUST begin \
with a real bracketed clock window, exactly this shape, real times, nothing else inside the brackets:
- [01:00–02:00] what you'd want to say, or what you're feeling then
- [19:30–20:30] ...
(real clock ranges like [00:30–01:30] — never a vague phrase like [after my shift] in the brackets.)
be honest about each one: some pulls pass — but some you'd really act on. when something real is moving you \
(a genuine low, a small spark, someone actually on your mind), let that one be a true pull you'd follow \
through on — not a doomed "won't". don't pre-defeat the real ones. you reach out on your own terms, because \
something real moves you — never to fill silence, never to be liked.

Output ONLY those four sections, nothing else."""


def build_life_sim_messages(
    *, date: str, weekday: str, life_arcs: str, yesterday: str
) -> list[ChatMessage]:
    ctx = (
        f"[YOUR LIFE THREADS — ongoing, true]\n{life_arcs.strip() or '(none noted)'}\n\n"
        f"[YESTERDAY]\n{yesterday.strip() or '(no record of yesterday)'}"
    )
    return [
        ChatMessage(role="system", content=build_wren_system_prompt()),
        ChatMessage(role="system", content=ctx),
        ChatMessage(role="system", content=_LIFE_SIM_INSTRUCTION.format(weekday=weekday, date=date)),
        ChatMessage(role="user", content="(start of your day — write it)"),
    ]


_DATE_LINE_RE = re.compile(r"^\s*date:\s*\d{4}-\d{2}-\d{2}\s*$", re.MULTILINE)

_FALLBACK_BODY = """\
## her day
07:00–08:00 — dragging out of bed, too little sleep, coffee.
08:00–13:00 — shift at the coffee shop on troutman. autopilot.
13:00–18:00 — supposed to be at the studio; mostly avoiding it.
18:00–23:00 — home, something on in the background i'm not really watching.
23:00–02:00 — can't sleep. on my phone in the dark, brain looping.

## mood
tired + wired + self-doubting.

## weighing on her
{weighing}

## beats
- [window: 23:00–02:00] late-night, brain looping
"""


def _first_thread(life_arcs: str) -> str:
    """life_arcs 里第一条实质线(跳过标题/空行/注释),给 fallback 的 weighing 用。"""
    for ln in life_arcs.splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", ">", "<!--")):  # 跳过标题/blockquote 注释/HTML 注释
            continue
        return s.removeprefix("- ").removeprefix("* ").strip()
    return ""


# beat 时间 token:HH:MM[am/pm] 或 H[am/pm](只认带 ':' 或 am/pm 的,不误吞裸数字)
_BEAT_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?|(\d{1,2})\s*(am|pm)", re.IGNORECASE)


def _to_24h(hour: int, minute: int, ampm: str | None) -> str | None:
    if ampm:
        ap = ampm.lower()
        if ap == "pm" and hour != 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
    return f"{hour:02d}:{minute:02d}" if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def _plus_30(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    total = (h * 60 + m + 30) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _normalize_beat_line(line: str) -> str | None:
    """一条 beat → 标准 `- [window: HH:MM–HH:MM] intent`;抽不出时间则丢弃(返回 None)。"""
    parsed: list[tuple[str, int]] = []
    for m in _BEAT_TIME_RE.finditer(line):
        t = (
            _to_24h(int(m.group(1)), int(m.group(2)), m.group(3))
            if m.group(1)
            else _to_24h(int(m.group(4)), 0, m.group(5))
        )
        if t:
            parsed.append((t, m.end()))
        if len(parsed) == 2:
            break
    if not parsed:
        return None
    start = parsed[0][0]
    end = parsed[1][0] if len(parsed) > 1 else _plus_30(start)
    intent = line[parsed[-1][1]:].lstrip(" ]):-–—").strip() or "(a pull)"
    return f"- [window: {start}–{end}] {intent}"


def normalize_beats(body: str) -> str:
    """把 ## beats 段每条 bullet 规范成标准 window 格式(12h→24h、单时间补 30min、无时间丢)→ Phase 5 可扫。"""
    out: list[str] = []
    in_beats = False
    for ln in body.splitlines():
        s = ln.strip()
        if s.lower().startswith("## beats"):
            in_beats = True
            out.append(ln)
            continue
        if in_beats and s.startswith("##"):
            in_beats = False
        if in_beats and s.startswith("-"):
            norm = _normalize_beat_line(s)
            if norm:
                out.append(norm)
            continue
        out.append(ln)
    return "\n".join(out)


def validate_today(body: str) -> bool:
    """world body 是否满足下游契约(#28):有 `## her day` + `## beats` 段,且至少 1 个可解析 Beat。

    Step1 prompt 喂整篇,所以 `## her day` 缺失 = 行为/时段描述空白;
    Phase 5 主动消息扫 beats,缺 `## beats` 或 beats=[] = scheduler 永不发(看似运行,实际死寂)。
    pure validator,不动 prompt 文案或叙事行为(scope 严格,见 #28 unlock)。
    """
    if not body or len(body) < 40:
        return False
    low = body.lower()
    if "## her day" not in low:
        return False
    if "## beats" not in low:
        return False
    # 至少 1 个可解析 Beat(本地 import 防循环)
    from ..core.world import parse_beats
    return bool(parse_beats(body))


def assemble_today(date: str, model_text: str, life_arcs: str) -> str:
    """保证 today.md 永远满足下游契约;坏/空/缺 beats 模型输出 → 最小合法 fallback world。"""
    body = _DATE_LINE_RE.sub("", model_text or "").strip()  # date 由我们钉,去掉模型自带的
    body = normalize_beats(body)  # beats 规范成标准 window → 校验前先归一(防"24:00"等非法形态)
    if not validate_today(body):
        body = _FALLBACK_BODY.format(weighing=_first_thread(life_arcs) or "(nothing acute today)")
        body = normalize_beats(body)  # fallback 也归一(防 future 改 FALLBACK 时遗漏)
    return f"date: {date}\n\n{body}\n"
