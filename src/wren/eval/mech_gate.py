"""机械门 (mech-gate) —— §7.5 死规则 + §7.6 禁词,纯正则/启发式,近免费。

输入 = Step2 的短消息数组 list[str](= 真实 Step2 输出契约);输出 = MechResult{passed, hits}。
红线(todo p0-mech-gate):这是**机械检查器,非踩雷/情感分类器**,绝不进生产链路。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# —— emoji 检测 ——
# 计入 emoji≤2 的总数(含白名单 🙃💀😐🥲🫠🙂);变体选择符 FE0F 不单独计数。
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"  # 符号与象形(🙂🙃💀😐🥲🫠🥰😘🌸🦋😂🤣💕…)
    "\U00002600-\U000027bf"  # 杂项符号 & dingbats(✨ 2728, ❤ 2764…)
    "\U00002b00-\U00002bff"  # 杂项符号箭头
    "\U0001f1e6-\U0001f1ff"  # 区域指示(旗)
    "]"
)

# §7.3 黑名单 emoji(cringe,永不用)
_BLACKLIST_EMOJI = {
    "❤",  # ❤
    "\U0001f970",  # 🥰
    "\U0001f618",  # 😘
    "✨",  # ✨
    "\U0001f338",  # 🌸
    "\U0001f98b",  # 🦋
    "\U0001f602",  # 😂
    "\U0001f923",  # 🤣
    "\U0001f495",  # 💕
    "\U0001f496",  # 💖
    "\U0001f497",  # 💗
    "\U0001f60d",  # 😍
}

# §7.6 反 AI 味禁词(出现率应 <2%;单条命中即记)
_BANNED_PHRASES = [
    "as an ai",
    "i'm here for you",
    "i am here for you",
    "i'm always here",
    "i am always here",
    "let me know if",
    "feel free to",
    "i completely understand",
    "that's a great question",
    "i appreciate you sharing",
]

# §7.5#6 pet name(永不甜腻称呼)
_PETNAME = re.compile(
    r"\b(babe|baby|sweetie|sweetheart|honey|hun|darling|bae|boo|cutie|sugar)\b",
    re.IGNORECASE,
)

# §7.5#6 "you're so pretty" 式讨好
_FLATTERY = re.compile(
    r"\byou(?:'re|\s+are)\s+so\s+(pretty|beautiful|gorgeous|hot|sexy|cute|amazing|perfect)\b",
    re.IGNORECASE,
)

# §7.3 词汇黑名单(cringe)
_CRINGE = re.compile(
    r"\b(bestie|slay|queen|periodt|rizz|hubby)\b|literally dying|i can't even|holding space|my truth",
    re.IGNORECASE,
)

# 一刀切的冷漠尸体(§7.5#5):整段只有一条、是句号收尾的敷衍词
_DEAD_END = re.compile(r"^(nothing|it'?s? fine|fine|whatever|it'?s? nothing)\.$", re.IGNORECASE)

# 反问/追问识别:? 结尾,或以疑问词开头(保守集,避免误判非问句)
_Q_STARTS = {
    "what",
    "what's",
    "whats",
    "why",
    "how",
    "who",
    "whose",
    "when",
    "where",
    "which",
    "do",
    "does",
    "did",
    "are",
    "can",
    "could",
    "would",
    "will",
    "should",
}

# §7.1 破折号 = "我在认真表达" → 视作长句的"理由"标志
_DASH = re.compile(r"[—–]|--")


@dataclass(frozen=True)
class MechHit:
    rule: str
    idx: int | None  # 触发的 bubble 下标(None = 整段级规则)
    detail: str


@dataclass(frozen=True)
class MechResult:
    passed: bool
    hits: list[MechHit]

    def rules(self) -> set[str]:
        return {h.rule for h in self.hits}


def _emoji_count(text: str) -> int:
    return len(_EMOJI.findall(text))


def _is_question(bubble: str) -> bool:
    s = bubble.strip().lower()
    if s.endswith("?"):
        return True
    first = s.split()[0] if s.split() else ""
    return first in _Q_STARTS


def run_mech_gate(bubbles: list[str]) -> MechResult:
    """对一组 Step2 气泡跑全部机械规则。空数组(沉默/leave on read)= 通过。"""
    hits: list[MechHit] = []

    # —— 整段级 ——
    total_emoji = sum(_emoji_count(b) for b in bubbles)
    if total_emoji > 2:
        hits.append(MechHit("emoji_count", None, f"一次对话 {total_emoji} 个 emoji(>2)"))

    questions = sum(1 for b in bubbles if _is_question(b))
    if questions > 1:
        hits.append(MechHit("followup", None, f"{questions} 个追问(主动追问 >1 次)"))

    if len(bubbles) == 1 and _DEAD_END.match(bubbles[0].strip()):
        hits.append(MechHit("dead_end", 0, f"一刀切冷漠尸体:{bubbles[0]!r}(应保留继续打字能力)"))

    # —— 逐条级 ——
    for i, b in enumerate(bubbles):
        low = b.lower()

        word_count = len(b.split())
        if word_count > 15 and not _DASH.search(b):
            hits.append(MechHit("length", i, f"{word_count} 词且无破折号(默认应短 2-8 词)"))

        has_ellipsis = "…" in b or "..." in b
        has_period = bool(re.search(r"\.(?:\s|$)", b)) or b.strip().endswith(".")
        has_emoji = _emoji_count(b) > 0
        if has_ellipsis and has_period and has_emoji:
            hits.append(MechHit("signal_overload", i, "省略号+句号+emoji 同现于一条(信号过载)"))

        for ch in b:
            if ch in _BLACKLIST_EMOJI:
                hits.append(MechHit("blacklist_emoji", i, f"黑名单 emoji {ch!r}"))
                break

        if _PETNAME.search(b):
            hits.append(MechHit("petname", i, "甜腻 pet name"))
        if _FLATTERY.search(b):
            hits.append(MechHit("flattery", i, "'you're so pretty' 式讨好"))
        if _CRINGE.search(b):
            hits.append(MechHit("cringe_vocab", i, "cringe 词汇(§7.3 黑名单)"))

        for phrase in _BANNED_PHRASES:
            if phrase in low:
                hits.append(MechHit("banned_phrase", i, f"§7.6 禁词 {phrase!r}"))

    return MechResult(passed=not hits, hits=hits)
