"""life-sim(Phase 4):每天一次,Wren 写自己的 world/today.md(纯 LLM,§0① 涌现)。

决策(2026-05-20 grill):
- 纯 LLM 生成整份 today.md(含作息),不用代码模板;作息从 canon 身份涌现、会浮动(不锚 §6.7)。
- 静态种子 world/life_arcs.md + 读昨天 → 跨天连贯(弧线自动推进留 Phase 6 夜结算 seam)。
- 触发 = 懒生成、按 clock 日期:ensure_world_today 只在 today.md 缺失/过期时跑(同日幂等、零额外调用)。
  Phase 4 不引 cron;同一函数 Phase 5 由 7am cron 调(让 world 在用户开口前/为主动就绪)。
- 用 primary 便宜模型(决策5,后台不路由)。空/坏输出由 assemble_today 兜底成最小合法 world。
"""

from __future__ import annotations

import threading

from .. import config
from ..model.base import ChatModel
from ..prompts.life_sim import assemble_today, build_life_sim_messages
from .clock import Clock
from .world import WorldStore


def run_life_sim(clock: Clock, world_store: WorldStore, model: ChatModel) -> str:
    """生成并写入今天的 world/today.md,返回其内容。读 life_arcs + 昨天 → 一次 LLM call。

    推理模型偶发空/截断输出 → 重试一次,再让 assemble_today 兜底(降低 fallback 频率)。
    #28:模型抛异常时也 retry 一次,仍失败 → fallback(空文本) → assemble_today fallback,
    确保 turn 不整批崩。failure 路径写 stdout 让 ops 看见,不上抛。
    """
    now = clock.now()
    date = f"{now:%Y-%m-%d}"
    arcs = world_store.read_life_arcs()
    msgs = build_life_sim_messages(
        date=date, weekday=f"{now:%A}", life_arcs=arcs, yesterday=world_store.read_yesterday()
    )
    # 第 1 次调用(带异常 retry)
    raw_text = ""
    try:
        out = model.complete(msgs, temperature=0.9, max_tokens=config.max_tokens())
        raw_text = out.text
    except Exception as e:  # noqa: BLE001 — life-sim 失败不能拖崩 reactive turn
        print(f"⚠️  [life-sim] 模型抛异常,retry 一次:{type(e).__name__}: {e}", flush=True)
    # 若第 1 次没拿到合法 body(异常 / 缺 her day) → retry
    if "## her day" not in raw_text.lower():
        try:
            out = model.complete(msgs, temperature=0.9, max_tokens=config.max_tokens())
            raw_text = out.text
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  [life-sim] retry 也抛异常,走 fallback world:{type(e).__name__}: {e}",
                  flush=True)
            raw_text = ""
    # assemble_today 内已含 validate_today + fallback,raw_text='' 也安全
    content = assemble_today(date, raw_text, arcs)
    world_store.write_today(content)
    return content


# 全局单飞锁:world/ 是「一个 Wren 一条命」的共享一份,多用户的轮可能并发触发重生成。
# 双检锁保证同一天只生成一次(省掉重复 LLM call + 防并发 rotate/写竞态)。单进程内有效(部署单实例 D3.5)。
_world_lock = threading.Lock()


def ensure_world_today(clock: Clock, world_store: WorldStore, model: ChatModel) -> str:
    """懒触发:today.md 是今天的 → 原样返回(零调用);否则旧档转 yesterday 再重生成。

    共享 world/ 下多用户并发安全:双检锁 —— 拿锁后再查一次,别的线程刚生成好就直接用。
    """
    date = f"{clock.now():%Y-%m-%d}"
    cur = world_store.read_today_struct()
    if cur is not None and cur.date == date:
        return cur.raw  # 同日幂等,不调用模型(无锁快路径)
    with _world_lock:
        cur = world_store.read_today_struct()  # 双检:可能别的线程已生成
        if cur is not None and cur.date == date:
            return cur.raw
        if cur is not None:
            world_store.rotate_to_yesterday()  # 跨天:旧 today → yesterday(连贯输入)
        return run_life_sim(clock, world_store, model)
