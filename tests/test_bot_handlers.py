"""bot handler(p1-skeleton):mock update + fake model → 多气泡 + 落 trace;沉默不发;/delete 清目录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from wren.bot.handlers import _handle_and_send, cmd_delete
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.model.fake import FakeChatModel


async def _nosleep(_seconds: float) -> None:
    return None


def _bot() -> Any:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_chat_action = AsyncMock()
    return bot


async def test_handle_and_send_emits_bubbles_and_trace(data_root: Path) -> None:
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {
                    "monologue": "let's see",
                    "reply": True,
                    "delay_s": 6,
                    "impression": "",
                    "memory": [],
                }
            )
        ]
    )
    s2 = FakeChatModel(
        script=[json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})]
    )
    out = await _handle_and_send(
        555, "you were at theo's show right", bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )
    assert out.replied
    assert bot.send_message.await_count == 3  # 三个气泡
    assert bot.send_chat_action.await_count == 3  # 每条前 typing
    assert len(read_traces(UserStore("555", data_root).dir)) == 1  # 落了 trace


async def test_silence_sends_nothing_but_traces(data_root: Path) -> None:
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {"monologue": "ugh", "reply": False, "delay_s": 0, "impression": "", "memory": []}
            )
        ]
    )
    s2 = FakeChatModel(script=["unused"])
    out = await _handle_and_send(
        556, "hey gorgeous", bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )
    assert not out.replied
    assert bot.send_message.await_count == 0
    assert len(read_traces(UserStore("556", data_root).dir)) == 1  # 沉默轮也有 trace


async def test_delete_command_wipes(data_root: Path) -> None:
    UserStore("777", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 777
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}
    await cmd_delete(update, context)
    assert not UserStore("777", data_root).dir.exists()


# === #20:默认日志脱敏(让 /delete "wipe everything" 承诺成立)===


_SENSITIVE_USER_TEXT = "MY-VERY-PRIVATE-TEXT-12345"
_SENSITIVE_MONOLOGUE = "MY-PRIVATE-INNER-VOICE-XYZ"


async def _send_one_turn_with_sensitive_content(
    chat_id: int, data_root: Path
) -> None:
    """跑一轮,user_text + inner_voice 都带可识别 sentinel。"""
    bot = _bot()
    s1 = FakeChatModel(
        script=[
            json.dumps(
                {
                    "monologue": _SENSITIVE_MONOLOGUE,
                    "reply": True,
                    "delay_s": 3,
                    "impression": "",
                    "memory": [],
                }
            )
        ]
    )
    s2 = FakeChatModel(script=[json.dumps({"messages": ["ok"]})])
    await _handle_and_send(
        chat_id, _SENSITIVE_USER_TEXT, bot, s1_model=s1, s2_model=s2, sleeper=_nosleep
    )


async def test_log_default_does_not_leak_user_text_or_inner_voice(
    data_root: Path, capsys: Any, monkeypatch: Any
) -> None:
    """默认(无 WREN_DEBUG_RAW_LOGS):stdout 必须不含 raw user_text / inner_voice /
    raw chat_id。否则 /delete 的 "wipe everything" 承诺站不住(#20)。
    """
    monkeypatch.delenv("WREN_DEBUG_RAW_LOGS", raising=False)
    await _send_one_turn_with_sensitive_content(888, data_root)
    captured = capsys.readouterr().out
    assert _SENSITIVE_USER_TEXT not in captured, "raw user_text 不应进默认日志"
    assert _SENSITIVE_MONOLOGUE not in captured, "raw inner_voice 不应进默认日志"
    assert "[888]" not in captured, "raw chat_id 不应进默认日志(用 chash 替代)"
    # 仍要有结构化指标可供运维 tail
    assert "user_len=" in captured
    assert "iv_len=" in captured
    assert "replied=True" in captured
    assert "bubbles=1" in captured


async def test_log_debug_mode_outputs_raw_content(
    data_root: Path, capsys: Any, monkeypatch: Any
) -> None:
    """WREN_DEBUG_RAW_LOGS=1 时,本地排障可看 raw 内容(只在显式开关下)。"""
    monkeypatch.setenv("WREN_DEBUG_RAW_LOGS", "1")
    await _send_one_turn_with_sensitive_content(889, data_root)
    captured = capsys.readouterr().out
    assert _SENSITIVE_USER_TEXT in captured
    assert _SENSITIVE_MONOLOGUE in captured
    assert "[889]" in captured  # debug 模式可见 raw chat_id
    assert "raw-logs(debug)" in captured  # 警示前缀


def test_log_chat_hash_is_stable_and_not_raw_id() -> None:
    """chash 跨调用稳定 + 8 hex 形态;不是 raw chat_id;独立于 metrics chat_hash
    (后者依赖 WREN_METRICS_SALT,缺 salt 会 raise —— 不能让 bot 因日志挂)。"""
    from wren.bot.handlers import _log_chat_hash

    h1 = _log_chat_hash(12345)
    h2 = _log_chat_hash(12345)
    h3 = _log_chat_hash(99999)
    assert h1 == h2  # 稳定
    assert h1 != h3  # 不同 id → 不同 hash
    assert len(h1) == 8 and all(c in "0123456789abcdef" for c in h1)  # 8 hex
    assert "12345" not in h1  # 不暴露 raw id


async def test_delete_cancels_pending_debounce_job(data_root: Path) -> None:
    """#34:cmd_delete 必须先取消同 chat 的 debounce job —— 否则旧 buffer 会被 flush
    成新 turn,在 store.init_user() 时**重建**刚被删的目录,wipe 失败。"""
    UserStore("888", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 888
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    fake_job = MagicMock()
    fake_job.schedule_removal = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[fake_job])
    context.chat_data = {"buffer": ["old message that should not survive"]}

    await cmd_delete(update, context)

    context.job_queue.get_jobs_by_name.assert_called_with("debounce-888")
    fake_job.schedule_removal.assert_called_once()
    assert context.chat_data["buffer"] == []  # 旧消息清掉
    assert not UserStore("888", data_root).dir.exists()


async def test_delete_holds_chat_lock_until_done(data_root: Path) -> None:
    """#34:cmd_delete 必须进 `_chat_lock(chat_id)`,与 in-flight turn 串行。
    否则 in-flight `_handle_and_send` 的 `store.init_user()` 会与 delete 同跑,
    产生半状态(目录被删 + trace 又被写)。"""
    import asyncio

    from wren.bot.handlers import _chat_lock

    UserStore("999", data_root).init_user()
    update = MagicMock()
    update.effective_chat.id = 999
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}

    lock = _chat_lock(999)
    async with lock:
        # in-flight turn 抢先持锁;启动 cmd_delete 应被阻塞
        task = asyncio.create_task(cmd_delete(update, context))
        await asyncio.sleep(0.05)
        assert not task.done(), "cmd_delete 应被 _chat_lock 阻塞(#34 race)"
        assert UserStore("999", data_root).dir.exists(), "锁释放前不该删"
        assert context.bot.send_message.call_count == 0, "锁释放前不该发 confirmation"

    # 锁释放 → cmd_delete 应完成
    await asyncio.wait_for(task, timeout=2.0)
    assert not UserStore("999", data_root).dir.exists()
    context.bot.send_message.assert_called_once()


async def test_delete_also_clears_metrics_rows(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#35:cmd_delete 端到端必须同步清 metrics DB 的对应 hashed rows,
    而不是只删 data/users/<id>/。文档曾要求 ops 另跑 wren-metrics forget,
    但用户触发的 /delete 不会执行它。"""
    from wren.core.trace import (
        SettlementTrace,
        TurnTrace,
        write_settlement_trace,
        write_trace,
    )
    from wren.ops.db import connect
    from wren.ops.ingest import ingest

    cid = "55555"
    # 1) seed: 写 trace + settle,跑 ingest 让 metrics DB 有这个用户的行
    UserStore(cid, data_root).init_user()
    write_trace(
        data_root / cid,
        TurnTrace(
            f"{cid}-1", cid, "2026-05-22T10:00:00Z", "hi",
            {"lv": 0, "freeze": False},
            {"reply": True, "delay_s": 3, "impression": "", "selected_memory": [],
             "event_stored": None, "tokens": 50, "latency_ms": 120, "model": "fake"},
            {"tokens": 30, "latency_ms": 80, "model": "fake"},
            {"bubbles": ["hi"], "typing_ms": 600, "bubble_gaps_ms": []},
        ),
    )
    write_settlement_trace(
        data_root / cid,
        SettlementTrace(
            f"{cid}-s1", cid, "2026-05-23T02:30:00Z",
            {"lv": 0, "freeze": False}, {"lv": 1, "freeze": False},
            ["impr"], {"model": "fake", "raw_out": "OK", "tokens": 100, "latency_ms": 500},
        ),
    )
    db = tmp_path / "m.duckdb"
    monkeypatch.setenv("WREN_METRICS_DB", str(db))
    ingest(db_path=db, data_root=data_root)
    # 确认 metrics 真的有该用户的行
    con = connect(db, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM users").fetchone()[0] > 0
        assert con.execute("SELECT count(*) FROM turns").fetchone()[0] > 0
    finally:
        con.close()

    # 2) 用户 /delete
    update = MagicMock()
    update.effective_chat.id = int(cid)
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}
    await cmd_delete(update, context)

    # 3) user dir 删了 (#34) **且** metrics rows 也清了 (#35)
    assert not UserStore(cid, data_root).dir.exists()
    con = connect(db, read_only=True)
    try:
        for tbl in ("turns", "settlements", "users", "ingest_state"):
            n = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            assert n == 0, f"{tbl} 应被 cmd_delete 清空(#35),实际 {n}"
    finally:
        con.close()


async def test_delete_does_not_fail_when_metrics_db_missing(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#35:本地开发还没跑过 ingest → metrics DB 不存在;cmd_delete 仍应成功
    (不主动 create 空 DB,不让 bot 因 metrics 缺失而失败)。"""
    cid = "44444"
    UserStore(cid, data_root).init_user()
    nonexistent = tmp_path / "no-such.duckdb"
    monkeypatch.setenv("WREN_METRICS_DB", str(nonexistent))

    update = MagicMock()
    update.effective_chat.id = int(cid)
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    context.chat_data = {}
    await cmd_delete(update, context)  # 不应抛

    assert not UserStore(cid, data_root).dir.exists()
    assert not nonexistent.exists(), "metrics DB 不存在时不该被意外 create"
    context.bot.send_message.assert_called_once()
