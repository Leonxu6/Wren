"""组装 per-turn context 喂 Step1。Phase 4:加 world(今日 life skeleton)+ now(此刻时刻)。

world + now 让因果链在 Step1 涌现(在做什么→什么心情→怎么回你),不做独立 mood scorer(§0①)。
world 内容由 caller(bot / eval harness)经 life_sim.ensure_world_today 备好后传入(per-user 轮不写 world/)。
"""

from __future__ import annotations

from dataclasses import dataclass

from .storage import Relationship, UserStore


@dataclass
class TurnContext:
    chat_id: str
    user_text: str
    relationship: Relationship
    inner_voice: str
    recent_dialogue: str
    events: str  # 中期记忆(capped, tagged)— 只进 Step1(反污染 §4/§8)
    world: str = ""  # 今日 world/today.md(全局 life skeleton)— 整篇进 Step1,因果涌现(Phase 4)
    now: str = ""  # 她此刻在自己这天的哪儿(本地时刻)— 喂 Step1 定位因果(Phase 4)
    core_impression: str = ""  # 长期核心印象(夜结算蒸馏 → 永久注入;P6)
    unresolved: str = ""  # 她憋着没说的(夜结算更新)— 染色回复(P6),只进 Step1


def assemble_context(
    store: UserStore, user_text: str, *, world: str = "", now: str = "", recent_limit: int = 30
) -> TurnContext:
    return TurnContext(
        chat_id=store.chat_id,
        user_text=user_text,
        relationship=store.read_relationship(),
        inner_voice=store.read_inner_voice(),
        recent_dialogue=store.read_recent_dialogue(recent_limit),
        events=store.read_events(),
        world=world,
        now=now,
        core_impression=store.read_core_impression(),
        unresolved="\n".join(f"- {u}" for u in store.read_unresolved()),
    )
