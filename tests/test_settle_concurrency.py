"""#12:夜结算 race —— settle_all 必须在 `_chat_lock(cid)` 内跑,
与 on_message / proactive 共享同一把锁。否则结算窗口附近发生的 live turn
会和 settle 并发读写 impressions,settle 可能 clear 掉 live turn 刚 append 的印象。

测试用持锁 + asyncio 时序,直接证明:
- 任何 live turn 持锁时,settle_all 会阻塞;
- 锁释放后 settle 才真正跑(model 才被调);
- non-numeric 用户目录跳过(锁 key 是 int)。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from wren.bot.handlers import _chat_lock
from wren.bot.scheduler import settle_all
from wren.core.storage import UserStore
from wren.model.fake import FakeChatModel


def _verdict_json() -> str:
    return json.dumps(
        {"level": 1, "freeze": False, "prose": "warmed a touch.", "core": "ok.", "unresolved": []}
    )


async def test_settle_all_blocks_on_per_chat_lock(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """核心:持有同 chat 的 `_chat_lock` 时,`settle_all()` 必须阻塞(不调 settlement 模型)。

    Bug 现象:不上锁 → settle 在 live turn 之间挤进去 → live impression 被 clear 漏掉。
    修复后:settle 排在 live turn 之后,fake_model.calls 在锁释放前必须为空。
    """
    cid_str = "12345"
    cid = int(cid_str)
    store = UserStore(cid_str)
    store.init_user()
    store.append_impression("seed-impression")

    fake_model = FakeChatModel(script=[_verdict_json()])
    monkeypatch.setattr("wren.bot.scheduler.get_model", lambda role: fake_model)

    lock = _chat_lock(cid)
    async with lock:
        task = asyncio.create_task(settle_all())
        # 让出 event loop,给 task 机会跑(理论上它会停在 lock 上)
        await asyncio.sleep(0.05)
        # 关键断言:被锁住,模型一次都没被调
        assert not task.done(), (
            "settle_all 应该被 _chat_lock 阻塞 —— 若已完成,说明没拿锁(#12 race)"
        )
        assert fake_model.calls == [], (
            "settle_nightly 不该在 lock 释放前被调 —— 否则就是和 live turn 并发"
        )

    # 锁释放 → settle_all 应能完成
    count = await asyncio.wait_for(task, timeout=2.0)
    assert count == 1
    assert len(fake_model.calls) == 1  # 一次裁决调用


async def test_settle_all_sees_impression_appended_inside_lock(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端到端语义:live turn 在 lock 内 append 的 impression,settle 必须看到 + 结算。

    这是 issue #12 描述的真实危害——若 settle 不串行化,它可能在 live turn append
    之前就跑了,新 impression 没机会进 settlement.jsonl,被下一个 clear 抹掉。
    """
    from wren.core.trace import read_settlements

    cid_str = "23456"
    cid = int(cid_str)
    store = UserStore(cid_str)
    store.init_user()
    store.append_impression("seed-before-night")

    fake_model = FakeChatModel(script=[_verdict_json()])
    monkeypatch.setattr("wren.bot.scheduler.get_model", lambda role: fake_model)

    lock = _chat_lock(cid)
    async with lock:
        task = asyncio.create_task(settle_all())
        await asyncio.sleep(0.05)
        # live turn 在 lock 内追加新 impression(模拟用户在结算窗口附近发了消息)
        store.append_impression("live-turn-during-settle-window")

    # 释放锁 → settle 现在跑
    count = await asyncio.wait_for(task, timeout=2.0)
    assert count == 1
    rec = read_settlements(store.dir)[0]
    assert "seed-before-night" in rec["impressions"]
    # 关键:lock 内 append 的也进了 settlement(没被 race 漏掉)
    assert "live-turn-during-settle-window" in rec["impressions"]


async def test_settle_all_skips_non_numeric_chat_id(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """non-numeric 用户目录跳过(锁 key 是 int);numeric 目录正常结算。

    Issue 提醒:'保持 invalid user directory 的跳过逻辑,避免非 numeric 目录进入 lock key'。
    """
    # numeric:正常
    numeric = UserStore("99999")
    numeric.init_user()
    numeric.append_impression("real")
    # non-numeric:'.cache' / 'README' 之类的目录会出现
    bogus_dir = data_root / "not-a-chat-id"
    bogus_dir.mkdir()

    fake_model = FakeChatModel(script=[_verdict_json()])
    monkeypatch.setattr("wren.bot.scheduler.get_model", lambda role: fake_model)

    count = await settle_all()
    # 只有 numeric 那个真跑了
    assert count == 1
    assert len(fake_model.calls) == 1
