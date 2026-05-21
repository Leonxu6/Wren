"""主动消息「规则预筛」(Phase 5,§6 决策):零-LLM 决定『此刻这条 beat 该不该进到点轻判』。

ARCHITECTURE §6:cron 扫 beats_today + 规则预筛(零 LLM:频率预算 / 付费+等级门 / 防刷屏)→ 有 beat
到点且过门 → 到点轻判(1 便宜 call)。本模块只做【过门】这一半(纯函数、无副作用、不调 LLM、不写盘);
轻判 = pipeline.handle_proactive_turn,Step1 同形涌现(§0① 不做独立调度器)。

定时来自 life-sim 的 beat 窗口(world/today.md `## beats`,已涌现、有来处);本模块只管「一共能发几条」
+「这条今天判过没有」。真实 scheduler(每 ~10-15min 调一次)留 bot/ seam。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .. import config
from .storage import ProactiveState
from .world import Beat


@dataclass(frozen=True)
class ProactiveDecision:
    """过门结果:beat 非空 = 该走轻判;reason 机读,落 trace / 调试用。"""

    beat: Beat | None
    reason: str  # fired | no_beat_in_window | already_considered | budget_exhausted | level_floor | free_tier


def beat_fingerprint(beat: Beat) -> str:
    """当日去重指纹:窗口起点 + intent 前缀(同一 beat 一天只判一次)。"""
    return f"{beat.window_start}|{beat.intent[:24]}"


def _to_minutes(hm: str) -> int:
    """'H:MM' / 'HH:MM' → 当日分钟数(life-sim 窗口允许 1-2 位时,不能按字符串比)。"""
    h, _, m = hm.partition(":")
    return int(h) * 60 + int(m)


def _in_window(now: datetime, start: str, end: str) -> bool:
    """now 的时刻是否落在 [start, end](含跨午夜:end < start 时如 23:30–00:30)。"""
    t = now.hour * 60 + now.minute
    s, e = _to_minutes(start), _to_minutes(end)
    return s <= t <= e if s <= e else (t >= s or t <= e)


def scan_for_due_beat(
    now: datetime,
    beats: list[Beat],
    level: int,
    state: ProactiveState,
    *,
    tier: str = "premium",
) -> ProactiveDecision:
    """零-LLM 过门:tier → 等级地板 → 预算 → 到点窗口 → 当日去重。命中返回该 beat,否则 None+原因。"""
    if tier == "free":
        return ProactiveDecision(None, "free_tier")  # 免费层无主动消息(§11.2)

    weekly, daily = config.proactive_caps(level)
    cap = weekly if weekly is not None else daily  # 该等级适用的上限维度
    if not cap:  # Lv0-1(上限 0)或未知等级 → 几乎不主动
        return ProactiveDecision(None, "level_floor")

    state = state.rolled(now)  # 跨周/日先重置,保证看的是当周/当日真实计数
    count = state.week_count if weekly is not None else state.day_count
    if count >= cap:
        return ProactiveDecision(None, "budget_exhausted")

    saw_considered = False
    for beat in beats:
        if not _in_window(now, beat.window_start, beat.window_end):
            continue
        if beat_fingerprint(beat) in state.considered_today:
            saw_considered = True  # 这条今天判过了,看还有没有别的到点 beat
            continue
        return ProactiveDecision(beat, "fired")
    return ProactiveDecision(None, "already_considered" if saw_considered else "no_beat_in_window")
