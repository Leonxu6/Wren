"""轻量运行期护栏(公开发布):每用户限流 + 全局每日 LLM-call 成本天花板。

限流防单用户刷屏(debounce 已合并连发,这里防持续刷);每日 model-call 计数是成本告警 —— 开放链接
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


# ---- 全局每日 model-call 成本天花板 ----
_model_call_day: str = ""
_model_call_count: int = 0


def _roll_model_call_day(now: datetime | None = None) -> tuple[str, int]:
    global _model_call_day, _model_call_count
    day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
    if day != _model_call_day:
        _model_call_day, _model_call_count = day, 0
    return day, _model_call_count


def model_call_exhausted(*, now: datetime | None = None) -> bool:
    """硬停模式下,是否已经不能再发起新的 LLM complete()。不递增计数。"""
    _day, count = _roll_model_call_day(now)
    cap = config.daily_turn_cap()
    return cap > 0 and count >= cap and config.daily_cap_hard()


def register_model_call(*, now: datetime | None = None) -> bool:
    """每个 ChatModel.complete() 前调一次。True = blocked, caller 不得发起模型调用。

    达 WREN_DAILY_TURN_CAP:到点告警;仅 WREN_DAILY_CAP_HARD=1 才硬停后续 model call,
    否则只告警、继续服务。0 = 不限。

    now 仅供测试注入(默认 UTC now;按 UTC 日重置)。
    """
    global _model_call_count
    day, count = _roll_model_call_day(now)
    cap = config.daily_turn_cap()
    if cap > 0 and count >= cap and config.daily_cap_hard():
        return True
    _model_call_count += 1
    if cap > 0 and _model_call_count == cap:
        mode = "硬停后续 model call" if config.daily_cap_hard() else "仅告警,继续服务"
        print(f"⚠️  [cost] 今日 model call 已达上限 {cap}(UTC {day});{mode}", flush=True)
    return False


def turn_blocked(*, now: datetime | None = None) -> bool:
    """Backward-compatible alias: the daily cost cap is now counted per model call."""
    return register_model_call(now=now)
