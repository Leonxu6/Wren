"""全局 world 存储(ARCHITECTURE §2/§3②):一个 Wren 一条命的每日 life skeleton。

§3 写边界铁律:用户对话【永不】碰 world/。WorldStore 是【唯一】能写 world/ 的类
(对照 storage.py:UserStore 故意没有 world 方法)—— 边界靠「写 world/ 的代码路径只此一处」
结构性保住,不靠自觉。

🔒契约(todo.md L155):today.md 的 `## beats` 段是 Phase 5 投射 beats 的输入源 —— 每条 beat
带机读触发窗口 `[window: HH:MM–HH:MM]`,让 Phase 5 cron 零-LLM 扫「到点」。
作息/心情/在压着的事是 prose,只供 Step1 整篇读、因果涌现(§0①,不做独立 mood scorer)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

# `- [window: 01:00–02:00] intent…` 或 `- [01:00–02:00] intent…`(window: 前缀可选 + – — - 三种破折号)。
# 宽松解析(同 jsonio 哲学):真实便宜模型 temp 0.9 常丢 `window:`,parser 不能只认严格式,
# 否则 0 beat 解析 → 主动永不发火(E2E 实测踩过)。括号内非「时:分–时:分」的自由句(如
# `[just after the shift, 13:15]`)不匹配 → 跳过(无可机读窗口,本就不该当 beat)。
# 注:写盘前 life_sim.normalize_beats 已把乱格式(12h/单时间)统一成标准式;这里再宽松一层兜底。
_BEAT_RE = re.compile(r"^- \[(?:window:\s*)?(\d{1,2}:\d{2})\s*[–—-]\s*(\d{1,2}:\d{2})\]\s*(.*)$")
_DATE_RE = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)


@dataclass(frozen=True)
class Beat:
    """今日一个情绪 beat(intent,非脚本):触发窗口 + 想表达/感受什么。Phase 5 投射用。"""

    window_start: str  # "HH:MM"
    window_end: str  # "HH:MM"
    intent: str

    def render(self) -> str:
        return f"- [window: {self.window_start}–{self.window_end}] {self.intent}"


@dataclass
class Today:
    """解析后的 world/today.md:date(判新旧)+ beats(Phase 5 契约)+ raw(整篇喂 Step1)。"""

    date: str
    beats: list[Beat] = field(default_factory=list)
    raw: str = ""


def parse_beats(text: str) -> list[Beat]:
    out: list[Beat] = []
    for ln in text.splitlines():
        m = _BEAT_RE.match(ln.strip())
        if m:
            out.append(Beat(m.group(1), m.group(2), m.group(3).strip()))
    return out


def parse_today(text: str) -> Today | None:
    """解析 today.md;无 date 头 → None(视作缺失/坏档,触发重生成)。"""
    m = _DATE_RE.search(text)
    if not m:
        return None
    return Today(date=m.group(1), beats=parse_beats(text), raw=text)


class WorldStore:
    """全局 world/ I/O。root 默认 config.world_root();life_arcs 退回版本化的 canonical seed。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config.world_root()

    @property
    def _today(self) -> Path:
        return self.root / "today.md"

    @property
    def _yesterday(self) -> Path:
        return self.root / "yesterday.md"

    @property
    def _life_arcs(self) -> Path:
        """静态种子:优先本 root 的(测试可覆盖),否则版本化的 world/life_arcs.md。"""
        local = self.root / "life_arcs.md"
        return local if local.exists() else config.WORLD_DIR / "life_arcs.md"

    # ---- 读 ----
    def read_today(self) -> str:
        """喂 Step1 的整篇今日 world(prose + beats)。无则空串。"""
        return self._today.read_text(encoding="utf-8") if self._today.exists() else ""

    def read_today_struct(self) -> Today | None:
        text = self.read_today()
        return parse_today(text) if text else None

    def read_yesterday(self) -> str:
        return self._yesterday.read_text(encoding="utf-8") if self._yesterday.exists() else ""

    def read_life_arcs(self) -> str:
        p = self._life_arcs
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ---- 写(唯一能写 world/ 的地方)----
    def write_today(self, content: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._today.write_text(content.rstrip() + "\n", encoding="utf-8")

    def rotate_to_yesterday(self) -> None:
        """重生成前把旧 today 落成 yesterday(跨天连贯的输入)。无旧档则无操作。"""
        if self._today.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self._yesterday.write_text(self._today.read_text(encoding="utf-8"), encoding="utf-8")
