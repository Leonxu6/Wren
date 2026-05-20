"""组装 per-turn context 喂 Step1。MVP 不读 world(Phase 4 才加)。"""

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


def assemble_context(store: UserStore, user_text: str, *, recent_limit: int = 30) -> TurnContext:
    return TurnContext(
        chat_id=store.chat_id,
        user_text=user_text,
        relationship=store.read_relationship(),
        inner_voice=store.read_inner_voice(),
        recent_dialogue=store.read_recent_dialogue(recent_limit),
    )
