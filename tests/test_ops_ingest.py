"""W6 监测库:增量幂等 ingest + 指标正确 + 隐私(无原文)+ 全命名查询可跑 + forget/diagnose。

满足 D2.1(完整捕获→可一键拉旅程)、D2.2(看板信号)、隐私铁律(只存指标维度)。离线、确定性。
"""

from __future__ import annotations

from pathlib import Path

from wren.core.storage import UserStore
from wren.core.trace import (
    SettlementTrace,
    TurnTrace,
    write_settlement_trace,
    write_trace,
)
from wren.ops.db import connect
from wren.ops.diagnose import diagnose
from wren.ops.ingest import forget, ingest
from wren.ops.queries import NAMED_QUERIES, run_named

_FLASH = "deepseek-v4-flash"

# 含「内容」的真实形 step1(prompt/raw_out/inner_voice/user_turn)—— 用来验证这些绝不进库。
SECRETS = ["SECRET_PROSE", "SECRET_IV", "SECRET_RAW", "SECRET_USERMSG"]


def _reactive(chat_id: str, n: int, *, reply: bool, hour: int) -> TurnTrace:
    step1 = {
        "prompt": {"relationship_prose": "SECRET_PROSE", "inner_voice": "SECRET_IV"},
        "raw_out": "SECRET_RAW",
        "inner_voice_after": "SECRET_IV",
        "reply": reply,
        "delay_s": 3,
        "impression": "noticing them",
        "selected_memory": [],
        "event_stored": None,
        "tokens": 50,
        "latency_ms": 120,
        "model": _FLASH,
    }
    step2 = {"tokens": 30, "latency_ms": 80, "model": _FLASH} if reply else None
    sent = {"bubbles": ["hi", "there"], "typing_ms": 600, "bubble_gaps_ms": [400]} if reply else None
    return TurnTrace(
        f"{chat_id}-{n}", chat_id, f"2026-05-22T{hour:02d}:00:00Z", "SECRET_USERMSG",
        {"lv": 0, "freeze": False}, step1, step2, sent,
    )


def _proactive(chat_id: str, n: int, *, reply: bool, hour: int) -> TurnTrace:
    step1 = {"reply": reply, "delay_s": 0, "impression": "", "selected_memory": [],
             "event_stored": None, "tokens": 40, "latency_ms": 90, "model": _FLASH}
    step2 = {"tokens": 20, "latency_ms": 70, "model": _FLASH} if reply else None
    sent = {"bubbles": ["hey"], "typing_ms": 600, "bubble_gaps_ms": []} if reply else None
    return TurnTrace(
        f"{chat_id}-{n}", chat_id, f"2026-05-22T{hour:02d}:30:00Z", None,
        {"lv": 2, "freeze": False}, step1, step2, sent, kind="proactive",
    )


def _seed(data_root: Path) -> Path:
    """用户 alice:2 回 + 1 沉默 + 1 主动发 + 1 主动压 + 一次结算 lv0→2 + 来源 instagram。"""
    cid = "12345"
    d = data_root / cid
    write_trace(d, _reactive(cid, 1, reply=True, hour=10))
    write_trace(d, _reactive(cid, 2, reply=True, hour=11))
    write_trace(d, _reactive(cid, 3, reply=False, hour=12))
    write_trace(d, _proactive(cid, 4, reply=True, hour=13))
    write_trace(d, _proactive(cid, 5, reply=False, hour=14))
    write_settlement_trace(
        d,
        SettlementTrace(
            f"{cid}-settle-1", cid, "2026-05-23T02:30:00Z",
            {"lv": 0, "freeze": False}, {"lv": 2, "freeze": False},
            ["impr"], {"model": "deepseek-v4-pro", "raw_out": "OK", "tokens": 500, "latency_ms": 2000},
        ),
    )
    UserStore(cid).write_source_once("instagram_xmas")
    return data_root


def test_ingest_idempotent(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    c1 = ingest(db_path=db, data_root=data_root)
    c2 = ingest(db_path=db, data_root=data_root)
    assert c1 == c2  # 重跑零新增
    assert c1["turns"] == 5 and c1["settlements"] == 1 and c1["users"] == 1


def test_ingest_incremental(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    write_trace(data_root / "12345", _reactive("12345", 6, reply=True, hour=15))
    c = ingest(db_path=db, data_root=data_root)
    assert c["turns"] == 6  # 只多了 1 行


def test_ingest_truncation_guard(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    UserStore("12345").delete()  # /delete 重建场景:文件没了
    write_trace(data_root / "12345", _reactive("12345", 1, reply=True, hour=10))
    c = ingest(db_path=db, data_root=data_root)  # 偏移归零重灌,不崩
    assert c["turns"] >= 1


def test_metrics_correct(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    con = connect(db, read_only=True)
    try:
        # 沉默率:reactive 3 条,1 沉默 → 33.3%
        _, eng = run_named(con, "engagement_daily")
        assert eng[0][1] == 3 and eng[0][2] == 33.3
        # 主动:2 条,1 发 1 压 → fire 50%
        _, pro = run_named(con, "proactive_daily")
        assert pro[0][1] == 2 and pro[0][2] == 1 and pro[0][4] == 50.0
        # 等级分布:最近结算 lv_after=2 → lv2 一人
        _, dist = run_named(con, "level_distribution")
        assert dist == [(2, 1)]
        # 升级:lv0→2 → 1 promotion
        _, trans = run_named(con, "level_transitions")
        assert trans[0][1] == 1
    finally:
        con.close()


def test_all_named_queries_run(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    con = connect(db, read_only=True)
    try:
        for name in NAMED_QUERIES:  # 全 13 条 SQL 都能跑(校验 DuckDB 方言)
            run_named(con, name)
    finally:
        con.close()


def test_privacy_no_raw_content_in_db(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    con = connect(db, read_only=True)
    try:
        blob = ""
        for tbl in ("users", "turns", "settlements", "ingest_state"):
            for row in con.execute(f"SELECT * FROM {tbl}").fetchall():
                blob += " ".join("" if v is None else str(v) for v in row)
        for secret in SECRETS:
            assert secret not in blob, f"原文泄漏进库:{secret}"
        assert "12345" not in blob  # 原始 chat_id 也不该出现(已哈希)
    finally:
        con.close()


def test_forget(data_root: Path, tmp_path: Path) -> None:
    _seed(data_root)
    db = tmp_path / "m.duckdb"
    ingest(db_path=db, data_root=data_root)
    forget("12345", db_path=db)
    con = connect(db, read_only=True)
    try:
        for tbl in ("turns", "settlements", "users", "ingest_state"):
            assert con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0] == 0
    finally:
        con.close()


def test_diagnose_reconstructs_journey(data_root: Path) -> None:
    _seed(data_root)
    report = diagnose("12345", data_root=data_root)
    assert "5 轮" in report and "1 次夜结算" in report
    assert "SECRET_USERMSG" in report  # diagnose 读原始 trace(在机器上,供人工深挖)
    assert "lv 0→2" in report  # 结算可见
