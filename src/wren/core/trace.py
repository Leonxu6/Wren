"""每轮一条结构化 JSONL trace(schema = eval_set.md §3)。

红线(§0②):轻量优先 —— 一轮一行 JSONL,写入收口在 write_trace 单点,seam 留给 Langfuse/OTel。
落 data/users/{chat_id}/(运行期,已 gitignore),随 /delete 清除。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class TurnTrace:
    turn_id: str
    chat_id: str
    ts: str
    user_turn: str
    relationship: dict[str, Any]  # {lv, freeze}
    step1: dict[str, Any]
    step2: dict[str, Any] | None  # None = 纯沉默 / leave on read
    sent: dict[str, Any] | None  # None = 没发任何消息
    eval: dict[str, Any] | None = None  # 离线回填


def trace_path(store_dir: Path) -> Path:
    return store_dir / "trace.jsonl"


def write_trace(store_dir: Path, trace: TurnTrace) -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    path = trace_path(store_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")
    return path


def read_traces(store_dir: Path) -> list[dict[str, Any]]:
    path = trace_path(store_dir)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def count_traces(store_dir: Path) -> int:
    return len(read_traces(store_dir))
