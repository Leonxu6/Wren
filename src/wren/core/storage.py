"""per-user markdown 存储(ARCHITECTURE §2)+ 写边界铁律。

🔒契约 / 红线:
- relationship_state.md = 离散 level(gate-key)+ 定性散文 + freeze,**绝不存积分**。
- 用户线只写 data/users/{chat_id}/,**永不碰 world/ 或 canon/**(类里根本没有那种方法)。
- /delete 清整个目录(含 trace)。
- events.md 预留 topic/valence/salience 标签字段(Phase 3 用),MVP 仅 stub。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .. import config

_CHAT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

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
