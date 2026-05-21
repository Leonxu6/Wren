"""per-user markdown 存储(ARCHITECTURE §2)+ 写边界铁律。

🔒契约 / 红线:
- relationship_state.md = 离散 level(gate-key)+ 定性散文 + freeze,**绝不存积分**。
- 用户线只写 data/users/{chat_id}/,**永不碰 world/ 或 canon/**(类里根本没有那种方法)。
- /delete 清整个目录(含 trace)。
- events.md = 中期记忆(每条带 topic/valence/salience 标签);Step1 涌现写入,注入回 Step1 供召回。
- **反污染**:events 只进 Step1,Step2 永不接收完整 dossier(§4/§8)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .. import config

_CHAT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# events.md 行:- [topic|valence|salience] text
_EVENT_RE = re.compile(r"^- \[([^|\]]*)\|([^|\]]*)\|([^|\]]*)\]\s*(.*)$")
_SALIENCE_RANK = {"high": 2, "med": 1, "low": 0}

# t=0 初始内心(PRD §9.1)
_INITIAL_INNER_VOICE = """\
dani mentioned this one.
…theo's show. the guy who didn't film anything.
think he was the one just standing there.

let them in.
let's see what they've got."""

_INITIAL_PROSE = """\
A stranger Dani vouched for — they were at Theo's show, the one who actually looked at the work \
instead of filming the wine. You let them into your messages. That's all. No read on them yet; \
they have to earn everything from zero."""

_STUB_EVENTS = """\
# Events (中期记忆 · 只进 Step1 · 非 RAG)
# 预留标签字段(Phase 3 用):每条 - [topic|valence|salience] <event>
"""


@dataclass
class Relationship:
    level: int  # 离散 Lv0-6,gate-key
    prose: str  # 定性散文,驱动语气
    freeze: bool = False  # 中观失败 deep-freeze(可修复)
    # ↑ 故意没有 points/score 字段(§0① 非积分制)


@dataclass(frozen=True)
class Event:
    """中期记忆一条:关于对方生活的具体事 + 标签(涌现自 Step1,非全量记录)。"""

    topic: str
    valence: str  # pos | neg | neutral
    salience: str  # low | med | high
    text: str

    def render(self) -> str:
        return f"- [{self.topic}|{self.valence}|{self.salience}] {self.text}"


class UserStore:
    def __init__(self, chat_id: str, root: Path | None = None) -> None:
        if not _CHAT_ID_RE.match(chat_id):
            raise ValueError(f"非法 chat_id: {chat_id!r}(只允许字母数字 _ -)")
        self.chat_id = chat_id
        self.root = root or config.data_root()
        self.dir = self.root / chat_id

    # ---- 文件路径(全部锚定在 self.dir 内)----
    @property
    def _relationship(self) -> Path:
        return self.dir / "relationship_state.md"

    @property
    def _inner_voice(self) -> Path:
        return self.dir / "inner_voice.md"

    @property
    def _impressions(self) -> Path:
        return self.dir / "impressions_today.md"

    @property
    def _events(self) -> Path:
        return self.dir / "events.md"

    @property
    def _conversation(self) -> Path:
        return self.dir / "conversation.md"

    # ---- 生命周期 ----
    def exists(self) -> bool:
        return self._relationship.exists()

    def init_user(self) -> None:
        """建文件树 + 写 Lv0 relationship + 种 t=0 inner_voice。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.write_relationship(Relationship(level=0, prose=_INITIAL_PROSE, freeze=False))
        self.write_inner_voice(_INITIAL_INNER_VOICE)
        self._impressions.write_text("# Impressions today\n", encoding="utf-8")
        self._events.write_text(_STUB_EVENTS, encoding="utf-8")
        self._conversation.write_text("", encoding="utf-8")

    def delete(self) -> None:
        """/delete:清整个用户目录(含 trace.jsonl)。"""
        if self.dir.exists():
            for p in sorted(self.dir.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            self.dir.rmdir()

    # ---- relationship(离散 level + 散文 + freeze)----
    def read_relationship(self) -> Relationship:
        text = self._relationship.read_text(encoding="utf-8")
        level = 0
        freeze = False
        prose_lines: list[str] = []
        in_prose = False
        for line in text.splitlines():
            if line.startswith("## prose"):
                in_prose = True
                continue
            if in_prose:
                prose_lines.append(line)
            elif line.startswith("level:"):
                level = int(line.split(":", 1)[1].strip())
            elif line.startswith("freeze:"):
                freeze = line.split(":", 1)[1].strip().lower() == "true"
        return Relationship(level=level, prose="\n".join(prose_lines).strip(), freeze=freeze)

    def write_relationship(self, r: Relationship) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._relationship.write_text(
            f"# Relationship State (离散 level = gate-key;非积分)\n\n"
            f"level: {r.level}\n"
            f"freeze: {str(r.freeze).lower()}\n\n"
            f"## prose\n\n{r.prose}\n",
            encoding="utf-8",
        )

    # ---- inner_voice ----
    def read_inner_voice(self) -> str:
        return self._inner_voice.read_text(encoding="utf-8").strip()

    def write_inner_voice(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._inner_voice.write_text(text.strip() + "\n", encoding="utf-8")

    # ---- impressions(Step1 产出,夜结算消费)----
    def append_impression(self, text: str) -> None:
        with self._impressions.open("a", encoding="utf-8") as f:
            f.write(f"- {text.strip()}\n")

    # ---- events(中期记忆;Step1 涌现写入 + 注入 Step1 召回;只进 Step1,反污染)----
    @staticmethod
    def _clean_field(s: str) -> str:
        return str(s).replace("|", "/").replace("]", ")").replace("\n", " ").strip()

    def append_event(self, text: str, topic: str, valence: str, salience: str) -> None:
        ev = Event(
            topic=self._clean_field(topic),
            valence=self._clean_field(valence),
            salience=self._clean_field(salience),
            text=self._clean_field(text),
        )
        if not ev.text:
            return
        with self._events.open("a", encoding="utf-8") as f:
            f.write(ev.render() + "\n")

    def read_event_list(self, cap: int | None = None) -> list[Event]:
        """解析 events.md;超 cap 先逐出最旧的低 salience(高 salience/近期多留),返回时间序。"""
        if not self._events.exists():
            return []
        evs: list[Event] = []
        for ln in self._events.read_text(encoding="utf-8").splitlines():
            m = _EVENT_RE.match(ln.strip())
            if m:
                evs.append(
                    Event(m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
                )
        cap = config.events_cap() if cap is None else cap
        if 0 <= cap < len(evs):
            ranked = sorted(
                enumerate(evs),
                key=lambda it: (_SALIENCE_RANK.get(it[1].salience, 0), it[0]),
                reverse=True,
            )[:cap]
            evs = [e for _, e in sorted(ranked, key=lambda it: it[0])]
        return evs

    def read_events(self, cap: int | None = None) -> str:
        """注入 Step1 的中期记忆块(capped, 时间序);无则空串。"""
        return "\n".join(e.render() for e in self.read_event_list(cap))

    # ---- conversation(最近对话,喂 Step1 context)----
    def append_dialogue(self, role: str, text: str) -> None:
        with self._conversation.open("a", encoding="utf-8") as f:
            f.write(f"{role}: {text}\n")

    def read_recent_dialogue(self, limit: int = 30) -> str:
        if not self._conversation.exists():
            return ""
        lines = [
            ln for ln in self._conversation.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        return "\n".join(lines[-limit:])
