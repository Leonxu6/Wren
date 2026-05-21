"""per-user markdown 存储(ARCHITECTURE §2)+ 写边界铁律。

🔒契约 / 红线:
- relationship_state.md = 离散 level(gate-key)+ 定性散文 + freeze,**绝不存积分**。
- 用户线只写 data/users/{chat_id}/,**永不碰 world/ 或 canon/**(类里根本没有那种方法)。
- /delete 清整个目录(含 trace)。
- events.md = 中期记忆(每条带 topic/valence/salience 标签);Step1 涌现写入,注入回 Step1 供召回。
- **反污染**:events 只进 Step1,Step2 永不接收完整 dossier(§4/§8)。
- impressions_today.md = Step1 每轮产出的印象 delta;**夜结算(Phase 6)消费后清空**。
- core_impression.md = 夜结算蒸馏的长期核心印象(永久注入 Step1,只被结算重写,不随每轮变)。
- unresolved_feelings.md = 她憋着没说的(夜结算更新);染色 Step1,供 P5 延迟揭示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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

_STUB_IMPRESSIONS = "# Impressions today\n"

_STUB_CORE = "# Core impression (长期蒸馏 · 永久注入 Step1 · 只被夜结算重写)\n"

_STUB_UNRESOLVED = "# Unresolved feelings (她憋着没说的 · 夜结算更新 · 染色 Step1 / 供 P5)\n"


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


@dataclass
class ProactiveState:
    """主动消息预算计数器(Phase 5;频率天花板,§0① 非积分关系)。

    anchor 用于跨周/跨日惰性重置:读出来后由 `.rolled(now)` 把过期计数清零(纯函数,不持久化),
    所以 scan/bump 永远看的是「当周/当日」的真实计数。considered_today = 今日已判过的 beat 指纹,
    防真实 cron(每 ~10-15min 扫一次)在同一窗口反复触发同一条 beat。
    """

    week_anchor: str = ""  # 当周周一 ISO(YYYY-MM-DD)
    week_count: int = 0
    day_anchor: str = ""  # 当天 ISO(YYYY-MM-DD)
    day_count: int = 0
    considered_today: list[str] = field(default_factory=list)

    def rolled(self, now: datetime) -> ProactiveState:
        """跨周/跨日则把对应计数 + 去重清零(纯函数,返回新实例,不写盘)。"""
        monday = (now.date() - timedelta(days=now.weekday())).isoformat()
        today = now.date().isoformat()
        same_day = self.day_anchor == today
        return ProactiveState(
            week_anchor=monday,
            week_count=self.week_count if self.week_anchor == monday else 0,
            day_anchor=today,
            day_count=self.day_count if same_day else 0,
            considered_today=list(self.considered_today) if same_day else [],
        )


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

    @property
    def _proactive_state(self) -> Path:
        return self.dir / "proactive_state.md"

    @property
    def _core_impression(self) -> Path:
        return self.dir / "core_impression.md"

    @property
    def _unresolved(self) -> Path:
        return self.dir / "unresolved_feelings.md"

    # ---- 生命周期 ----
    def exists(self) -> bool:
        return self._relationship.exists()

    def init_user(self) -> None:
        """建文件树 + 写 Lv0 relationship + 种 t=0 inner_voice。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.write_relationship(Relationship(level=0, prose=_INITIAL_PROSE, freeze=False))
        self.write_inner_voice(_INITIAL_INNER_VOICE)
        self._impressions.write_text(_STUB_IMPRESSIONS, encoding="utf-8")
        self._events.write_text(_STUB_EVENTS, encoding="utf-8")
        self._core_impression.write_text(_STUB_CORE, encoding="utf-8")
        self._unresolved.write_text(_STUB_UNRESOLVED, encoding="utf-8")
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
    @staticmethod
    def _read_bullets(path: Path) -> list[str]:
        """读 '- <text>' 列表(去前缀,跳过表头/注释);无文件则空。"""
        if not path.exists():
            return []
        items = [
            ln.strip()[2:].strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("- ")
        ]
        return [s for s in items if s]

    def append_impression(self, text: str) -> None:
        with self._impressions.open("a", encoding="utf-8") as f:
            f.write(f"- {text.strip()}\n")

    def read_impressions(self) -> list[str]:
        """夜结算消费:今日所有印象条目(去 '- ' 前缀);无则空。"""
        return self._read_bullets(self._impressions)

    def clear_impressions(self) -> None:
        """夜结算后清空(留表头),为下一日重新累积。"""
        self._impressions.write_text(_STUB_IMPRESSIONS, encoding="utf-8")

    # ---- core_impression(夜结算蒸馏的长期核心印象;永久注入 Step1,只被结算重写)----
    def read_core_impression(self) -> str:
        if not self._core_impression.exists():
            return ""
        lines = [
            ln
            for ln in self._core_impression.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        ]
        return "\n".join(lines).strip()

    def write_core_impression(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        body = text.strip()
        self._core_impression.write_text(
            _STUB_CORE + (f"\n{body}\n" if body else ""), encoding="utf-8"
        )

    # ---- unresolved_feelings(她憋着没说的;夜结算更新;染色 Step1 / 供 P5)----
    def read_unresolved(self) -> list[str]:
        return self._read_bullets(self._unresolved)

    def write_unresolved(self, items: list[str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        body = "".join(f"- {it.strip()}\n" for it in items if it.strip())
        self._unresolved.write_text(_STUB_UNRESOLVED + body, encoding="utf-8")

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

    # ---- proactive 预算计数器(Phase 5;频率天花板,非积分)----
    def read_proactive_state(self) -> ProactiveState:
        """读预算计数器;无文件 → 初始零态。惰性重置交给 ProactiveState.rolled(now)。"""
        if not self._proactive_state.exists():
            return ProactiveState()
        s = ProactiveState()
        # considered 指纹每条独占一行(指纹含 ':'/'|',故不可用单行分隔存;partition 只切首个 ':')。
        for line in self._proactive_state.read_text(encoding="utf-8").splitlines():
            if ":" not in line or line.startswith("#"):
                continue
            key, _, val = line.partition(":")
            val = val.strip()
            if key == "week_anchor":
                s.week_anchor = val
            elif key == "week_count":
                s.week_count = int(val or 0)
            elif key == "day_anchor":
                s.day_anchor = val
            elif key == "day_count":
                s.day_count = int(val or 0)
            elif key == "considered" and val:
                s.considered_today.append(val)
        return s

    def write_proactive_state(self, s: ProactiveState) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Proactive State (主动消息预算计数器 · 频率天花板,非积分关系)",
            f"week_anchor: {s.week_anchor}",
            f"week_count: {s.week_count}",
            f"day_anchor: {s.day_anchor}",
            f"day_count: {s.day_count}",
            *(f"considered: {fp}" for fp in s.considered_today),
        ]
        self._proactive_state.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def bump_proactive_count(self, now: datetime) -> None:
        """实际发出一条主动消息后调用(跨周/日先重置再 +1)。压制(reply=False)【不】调用。"""
        s = self.read_proactive_state().rolled(now)
        s.week_count += 1
        s.day_count += 1
        self.write_proactive_state(s)

    def mark_considered(self, now: datetime, fingerprint: str) -> None:
        """记下「这条 beat 今天已判过」(无论发/压制),防真实 cron 在同窗口重复触发。"""
        s = self.read_proactive_state().rolled(now)
        if fingerprint not in s.considered_today:
            s.considered_today.append(fingerprint)
        self.write_proactive_state(s)
