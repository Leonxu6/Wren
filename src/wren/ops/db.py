"""DuckDB 连接 + schema + chat_id 哈希(W6 监测库)。

隐私铁律:**只存指标 + 维度,绝不存原文**(user_turn / inner_voice / prose / raw_out / impressions 文本)。
唯一 PII 是 chat_id → 一律哈希存(chat_hash);turn_id/settlement_id 里的 chat_id 前缀也换成 chat_hash。
原始 transcript 留在机器上的 trace.jsonl(供 diagnose 人工深挖),不进库、不出机器。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import duckdb

from .. import config

# 22 列 turns / 13 列 settlements / 5 列 users —— 全是计数/维度,无任何原文。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_hash TEXT PRIMARY KEY,
    source TEXT,                    -- 深链来源(campaign tag,非隐私内容)
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    first_user_msg_ts TIMESTAMP     -- 首条真实用户消息(激活判定;只 /start 没发 → NULL)
);
CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,       -- {chat_hash}-{n}(原始 chat_id 前缀已换哈希)
    chat_hash TEXT, ts TIMESTAMP, turn_day DATE, kind TEXT,   -- day 是 DuckDB datepart 关键字,改 turn_day
    is_user_turn BOOLEAN, user_turn_len INTEGER,   -- 长度,非文本
    lv INTEGER, frozen BOOLEAN,                     -- freeze 是 DuckDB 保留词,改 frozen
    replied BOOLEAN, delay_s INTEGER,
    has_impression BOOLEAN, has_memory BOOLEAN, event_stored BOOLEAN,
    s1_tokens INTEGER, s1_latency_ms INTEGER, s1_model TEXT,
    s2_tokens INTEGER, s2_latency_ms INTEGER, s2_model TEXT,
    bubble_count INTEGER, typing_ms INTEGER
);
CREATE TABLE IF NOT EXISTS settlements (
    settlement_id TEXT PRIMARY KEY,
    chat_hash TEXT, ts TIMESTAMP, night DATE,
    lv_before INTEGER, lv_after INTEGER,
    freeze_before BOOLEAN, freeze_after BOOLEAN, lv_delta INTEGER,
    impressions_n INTEGER, settle_tokens INTEGER, settle_model TEXT,
    parse_ok BOOLEAN                -- 启发:judge 有输出且 after.lv 非空(查静默回落 bug)
);
CREATE TABLE IF NOT EXISTS ingest_state (
    chat_hash TEXT PRIMARY KEY,
    trace_lines BIGINT DEFAULT 0,
    settle_lines BIGINT DEFAULT 0,
    last_run_ts TIMESTAMP
);
"""


def metrics_db_path() -> Path:
    """默认 data/metrics.duckdb(data_root 同级);WREN_METRICS_DB 可覆盖。"""
    override = os.getenv("WREN_METRICS_DB", "").strip()
    if override and not override.startswith("#"):
        return Path(override)
    return config.data_root().parent / "metrics.duckdb"


def connect(path: str | Path | None = None, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    p = Path(path) if path else metrics_db_path()
    if not read_only:
        p.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(p), read_only=read_only)


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_SCHEMA)  # DuckDB 解析多语句脚本 + 正确忽略 -- 注释(勿在 Python 端按 ; 裸切)


def chat_hash(chat_id: str) -> str:
    """sha256(salt + chat_id) 前 16 hex。salt 走 WREN_METRICS_SALT(勿提交);默认 dev salt 仅本地。"""
    salt = os.getenv("WREN_METRICS_SALT", "wren-dev-salt")
    return hashlib.sha256(f"{salt}:{chat_id}".encode()).hexdigest()[:16]
