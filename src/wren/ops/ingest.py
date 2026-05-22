"""增量幂等 ETL:per-user trace.jsonl + settlement.jsonl + source.md → DuckDB(W6)。

幂等靠 turn_id/settlement_id 主键 + ON CONFLICT DO NOTHING(重跑零新增、零变更)。
增量靠 ingest_state 记的行数偏移(只解析新增行;文件变短=/delete 重建 → 偏移归零重灌)。
**只写指标+维度,绝不写原文**(见 db.py 铁律);chat_id 一律哈希。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .. import config
from ..core.trace import settlement_path, trace_path
from .db import chat_hash, connect, create_schema

_TURN_COLS = 22
_SETTLE_COLS = 13


def _qs(n: int) -> str:
    return ",".join(["?"] * n)


def _loads(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _hashed_id(raw_id: str, chat_id: str, chash: str) -> str:
    """把 id 里的原始 chat_id 前缀换成 chat_hash(turn_id/settlement_id 都 = chat_id + 后缀)。"""
    return chash + raw_id[len(chat_id) :] if raw_id.startswith(chat_id) else f"{chash}-{raw_id}"


def _turn_row(rec: dict[str, Any], chat_id: str, chash: str) -> tuple[Any, ...] | None:
    tid = rec.get("turn_id")
    if not tid:
        return None
    ts = _parse_ts(rec.get("ts"))
    s1 = rec.get("step1") or {}
    s2 = rec.get("step2")
    sent = rec.get("sent")
    rel = rec.get("relationship") or {}
    ut = rec.get("user_turn")
    return (
        _hashed_id(str(tid), chat_id, chash),
        chash,
        ts,
        ts.date() if ts else None,
        rec.get("kind", "reactive"),
        ut is not None,
        len(ut) if isinstance(ut, str) else None,
        rel.get("lv"),
        bool(rel.get("freeze")),
        s1.get("reply"),
        s1.get("delay_s"),
        bool(s1.get("impression")),
        bool(s1.get("selected_memory")),
        s1.get("event_stored") is not None,
        s1.get("tokens"),
        s1.get("latency_ms"),
        s1.get("model"),
        s2.get("tokens") if isinstance(s2, dict) else None,
        s2.get("latency_ms") if isinstance(s2, dict) else None,
        s2.get("model") if isinstance(s2, dict) else None,
        len(sent.get("bubbles") or []) if isinstance(sent, dict) else 0,
        sent.get("typing_ms") if isinstance(sent, dict) else None,
    )


def _settle_row(rec: dict[str, Any], chat_id: str, chash: str) -> tuple[Any, ...] | None:
    sid = rec.get("settlement_id")
    if not sid:
        return None
    ts = _parse_ts(rec.get("ts"))
    before = rec.get("before") or {}
    after = rec.get("after") or {}
    judge = rec.get("judge") or {}
    lvb, lva = before.get("lv"), after.get("lv")
    return (
        _hashed_id(str(sid), chat_id, chash),
        chash,
        ts,
        ts.date() if ts else None,
        lvb,
        lva,
        bool(before.get("freeze")),
        bool(after.get("freeze")),
        (lva - lvb) if isinstance(lva, int) and isinstance(lvb, int) else None,
        len(rec.get("impressions") or []),
        judge.get("tokens"),
        judge.get("model"),
        bool(judge.get("raw_out")) and lva is not None,
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _read_source(d: Path) -> str:
    p = d / "source.md"
    if not p.exists():
        return ""
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            return ln
    return ""


def _offset(con: duckdb.DuckDBPyConnection, chash: str, col: str) -> int:
    row = con.execute(f"SELECT {col} FROM ingest_state WHERE chat_hash=?", [chash]).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def ingest(*, db_path: str | Path | None = None, data_root: str | Path | None = None) -> dict[str, int]:
    """跑一遍 ETL,返回各表总行数。幂等可重复跑。"""
    root = Path(data_root) if data_root else config.data_root()
    if not os.getenv("WREN_METRICS_SALT"):
        print("⚠️  [metrics] WREN_METRICS_SALT 未设 → 用源码默认盐(chat_hash 可被反推);公开发布前务必设。", flush=True)
    con = connect(db_path)
    try:
        create_schema(con)
        sources: dict[str, str] = {}
        for d in sorted(root.iterdir()) if root.exists() else []:
            if not d.is_dir():
                continue
            chat_id = d.name
            chash = chat_hash(chat_id)

            tlines = _lines(trace_path(d))
            tprev = _offset(con, chash, "trace_lines")
            if len(tlines) < tprev:
                tprev = 0  # 文件变短(/delete 重建)→ 重灌
            trows = [
                row
                for ln in tlines[tprev:]
                if (rec := _loads(ln)) is not None and (row := _turn_row(rec, chat_id, chash))
            ]
            if trows:
                con.executemany(
                    f"INSERT INTO turns VALUES ({_qs(_TURN_COLS)}) ON CONFLICT (turn_id) DO NOTHING",
                    trows,
                )

            slines = _lines(settlement_path(d))
            sprev = _offset(con, chash, "settle_lines")
            if len(slines) < sprev:
                sprev = 0
            srows = [
                row
                for ln in slines[sprev:]
                if (rec := _loads(ln)) is not None and (row := _settle_row(rec, chat_id, chash))
            ]
            if srows:
                con.executemany(
                    f"INSERT INTO settlements VALUES ({_qs(_SETTLE_COLS)}) "
                    "ON CONFLICT (settlement_id) DO NOTHING",
                    srows,
                )

            con.execute(
                "INSERT INTO ingest_state (chat_hash, trace_lines, settle_lines, last_run_ts) "
                "VALUES (?,?,?,?) ON CONFLICT (chat_hash) DO UPDATE SET "
                "trace_lines=excluded.trace_lines, settle_lines=excluded.settle_lines, "
                "last_run_ts=excluded.last_run_ts",
                [chash, len(tlines), len(slines), datetime.now(UTC).replace(tzinfo=None)],
            )
            src = _read_source(d)
            if src:
                sources[chash] = src

        # users 维:从 turns 聚合 first/last_seen + 首条用户消息;source 单独覆盖。
        con.execute(
            "INSERT INTO users (chat_hash, first_seen, last_seen, first_user_msg_ts) "
            "SELECT chat_hash, min(ts), max(ts), min(CASE WHEN is_user_turn THEN ts END) "
            "FROM turns GROUP BY chat_hash "
            "ON CONFLICT (chat_hash) DO UPDATE SET first_seen=excluded.first_seen, "
            "last_seen=excluded.last_seen, first_user_msg_ts=excluded.first_user_msg_ts"
        )
        for chash, src in sources.items():  # 含「只 /start 没发消息」的用户(无 turns)
            con.execute(
                "INSERT INTO users (chat_hash, source) VALUES (?,?) "
                "ON CONFLICT (chat_hash) DO UPDATE SET source=excluded.source",
                [chash, src],
            )

        return {
            "turns": _scalar(con, "SELECT count(*) FROM turns"),
            "settlements": _scalar(con, "SELECT count(*) FROM settlements"),
            "users": _scalar(con, "SELECT count(*) FROM users"),
        }
    finally:
        con.close()


def forget(chat_id: str, *, db_path: str | Path | None = None) -> None:
    """硬删某用户在监测库的所有行(GDPR/对齐 /delete;按 chat_hash)。"""
    chash = chat_hash(chat_id)
    con = connect(db_path)
    try:
        create_schema(con)
        for tbl in ("turns", "settlements", "users", "ingest_state"):
            con.execute(f"DELETE FROM {tbl} WHERE chat_hash=?", [chash])
    finally:
        con.close()
