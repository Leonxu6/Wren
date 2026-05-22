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
    user_turn: str | None  # None = 主动轮(没人发消息,她自己开口/沉默)
    relationship: dict[str, Any]  # {lv, freeze}
    step1: dict[str, Any]
    step2: dict[str, Any] | None  # None = 纯沉默 / leave on read
    sent: dict[str, Any] | None  # None = 没发任何消息
    eval: dict[str, Any] | None = None  # 离线回填
    kind: str = "reactive"  # reactive(被动回) | proactive(她主动找,Phase 5)


@dataclass
class SettlementTrace:
    """夜结算一条 trace(Phase 6)。落独立 settlement.jsonl,不混进 trace.jsonl
    (后者被 count_traces 用来编 turn_id,混入会污染计数)。"""

    settlement_id: str
    chat_id: str
    ts: str
    before: dict[str, Any]  # {lv, freeze}
    after: dict[str, Any]  # {lv, freeze}
    impressions: list[str]  # 本次消费的今日印象
    judge: dict[str, Any]  # {model, raw_out, tokens, latency_ms, …}


def trace_path(store_dir: Path) -> Path:
    return store_dir / "trace.jsonl"


def settlement_path(store_dir: Path) -> Path:
    return store_dir / "settlement.jsonl"


def write_trace(store_dir: Path, trace: TurnTrace) -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    path = trace_path(store_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读 JSONL,跳过空行与坏行(掉电极端下尾行可能不全;不让一行坏掉整份读取)。"""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def read_traces(store_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(trace_path(store_dir))


def count_traces(store_dir: Path) -> int:
    return len(read_traces(store_dir))


def write_settlement_trace(store_dir: Path, trace: SettlementTrace) -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    path = settlement_path(store_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")
    return path


def read_settlements(store_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(settlement_path(store_dir))


def count_settlements(store_dir: Path) -> int:
    return len(read_settlements(store_dir))
