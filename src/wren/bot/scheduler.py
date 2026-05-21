"""Phase 6:每晚 ~2:30 ET 对所有活跃用户跑夜结算(后台调度器,复用 PTB JobQueue)。

ARCHITECTURE §5 日循环的「per-user · 夜」那一格。settle_nightly 本身 clock 可注入 + 同步,
这里用 PTB 的 run_daily 触发 + asyncio.to_thread 包同步调用,不阻塞 event loop。
"""

from __future__ import annotations

import asyncio
from datetime import time
from typing import Any
from zoneinfo import ZoneInfo

from .. import config
from ..core.settlement import settle_nightly
from ..core.storage import UserStore
from ..model.registry import get_model

_ET = ZoneInfo("America/New_York")
_SETTLE_TIME = time(hour=2, minute=30, tzinfo=_ET)


def active_chat_ids() -> list[str]:
    """data/users/ 下的所有用户目录名。"""
    root = config.data_root()
    if not root.exists():
        return []
    return [p.name for p in sorted(root.iterdir()) if p.is_dir()]


async def settle_all(_context: Any = None) -> int:
    """对所有活跃用户跑一次结算;单个用户失败不拖垮整批。返回实际结算的人数。"""
    model = get_model("settlement")
    ran = 0
    for chat_id in active_chat_ids():
        try:
            store = UserStore(chat_id)
            if not store.exists():
                continue
            outcome = await asyncio.to_thread(settle_nightly, store, model)
        except Exception as e:  # noqa: BLE001 — 批处理鲁棒性优先
            print(f"[settle] {chat_id} 失败:{e}", flush=True)
            continue
        if outcome.ran:
            ran += 1
            print(
                f"[settle] {chat_id}: lv {outcome.before.level}→{outcome.after.level} · "
                f"freeze {outcome.before.freeze}→{outcome.after.freeze}",
                flush=True,
            )
    return ran


def register_nightly(app: Any) -> bool:
    """把夜结算挂到 app 的 JobQueue;无 JobQueue(没装 [job-queue])则告警跳过。返回是否挂上。"""
    jq = getattr(app, "job_queue", None)
    if jq is None:
        print("⚠️  无 JobQueue —— 装 python-telegram-bot[job-queue] 才有夜结算。", flush=True)
        return False
    jq.run_daily(settle_all, time=_SETTLE_TIME, name="nightly-settlement")
    print(f"✓ 夜结算已挂:每日 {_SETTLE_TIME.strftime('%H:%M')} ET", flush=True)
    return True
