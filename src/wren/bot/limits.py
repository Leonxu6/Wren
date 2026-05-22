"""轻量运行期护栏(公开发布):每用户限流 + 全局每日成本天花板。纯内存、无新服务(§0②)。

限流防单用户刷屏(debounce 已合并连发,这里防持续刷);每日 turn 计数是成本告警 —— 开放链接
= 花费暴露。重启清零 = 可接受(告警/护栏用途,非账务)。两者都可经 env 关/调。
"""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime

from .. import config

# ---- 每用户限流(60s 滑动窗) ----
_msg_times: dict[int, deque[float]] = {}


def rate_limited(chat_id: int, *, now: float | None = None) -> bool:
    """每用户 60s 滑动窗;超过 WREN_RATE_LIMIT_PER_MIN 返回 True(本条该丢)。0 = 不限。

    now 仅供测试注入(默认 time.monotonic —— 用单调钟,免受系统时间回拨影响)。
    """
    cap = config.rate_limit_per_min()
    if cap <= 0:
        return False
    t = time.monotonic() if now is None else now
    dq = _msg_times.setdefault(chat_id, deque())
    cutoff = t - 60.0
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= cap:
        return True
    dq.append(t)
    return False


# ---- 全局每日 turn 成本天花板 ----
_turn_day: str = ""
_turn_count: int = 0


def turn_blocked(*, now: datetime | None = None) -> bool:
    """每个 turn(LLM 调用)前调一次。达 WREN_DAILY_TURN_CAP:到点告警;
    仅 WREN_DAILY_CAP_HARD=1 才返回 True(硬停本 turn),否则只告警、继续服务。0 = 不限。

    now 仅供测试注入(默认 UTC now;按 UTC 日重置)。
    """
    global _turn_day, _turn_count
    day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
    if day != _turn_day:
        _turn_day, _turn_count = day, 0
    cap = config.daily_turn_cap()
    if cap > 0 and _turn_count >= cap and config.daily_cap_hard():
        return True
    _turn_count += 1
    if cap > 0 and _turn_count == cap:
        mode = "硬停后续 turn" if config.daily_cap_hard() else "仅告警,继续服务"
        print(f"⚠️  [cost] 今日 turn 已达上限 {cap}(UTC {day});{mode}", flush=True)
    return False
