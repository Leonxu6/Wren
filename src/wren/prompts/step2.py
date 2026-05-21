"""Step2 prompt:在已锁的内心语气下,把独白渲染成短消息数组。

红线:level 只作"解锁什么"的事实陈述(level_fact),**永不**进 prompt 当语气旋钮(§7/§0)。
"""

from __future__ import annotations

from ..model.base import ChatMessage
from .system import build_wren_system_prompt, parse_bubbles


def build_step2_messages(
    *,
    monologue: str,
    memory: list[str],
    level_fact: str,
    user_text: str,
    recent_dialogue: str = "",
    proactive: bool = False,
) -> list[ChatMessage]:
    locked = f"[YOUR LOCKED INNER VOICE — already decided, just say it]\n{monologue}"
    if memory:
        locked += (
            "\n\n[SOMETHING YOU REMEMBER ABOUT THEM]\n"
            f"{memory[0]}\n"
            "This came back to you just now. If you bring it up, let it slip in naturally — the way a person "
            "suddenly remembers something — woven into what you're saying. Never announce it like a record: "
            "no 'you mentioned earlier', no 'you said', no 'last time you told me'."
        )

    if proactive:  # 主动:她先开口、没人发她消息 —— 渲染成「起头」,不是「回话」
        instr = (
            "Your judgment is already locked above — you've decided to reach out, on your own. Don't "
            "re-decide; just say it.\n"
            "Nobody texted you — you're starting this, unprompted. Turn that locked reaction into what you'd "
            "actually send first: short lowercase bubbles, fired one after another, in order.\n"
            "- Open with the real thing that's in your head (you can't sleep, the studio was a write-off) — "
            "not a content-free 'hey' / 'how are you'. You're opening a conversation, not answering one.\n"
            "- Don't go warm or eager just because you decided to text — you're still dry, low-key, on your "
            "terms. Dry and short (most bubbles 2-8 words), and vary it — don't fall back on the same 'mm'/'k'.\n"
        )
    else:
        instr = (
            "Your judgment is already locked above — don't re-decide whether to reply or change your read, "
            "just say it in your voice. Use the conversation only to say it coherently, never to reconsider it.\n"
            "Turn your real inner reaction into what you'd actually send: short lowercase bubbles, fired one "
            "after another, in order. If you're genuinely reacting — incredulous, thrown, annoyed, or pulled in "
            "— let it come through across a few short bubbles.\n"
            "- If your reaction means you'd actually say something real — answer them, tell them a little, react "
            "to what they brought up — then SAY that thing, grounded in what's being discussed (the thread tells "
            "you what 'it' / 'that' / 'the painting' refers to). DON'T dodge into 'which one' / 'in what' / 'what "
            "do you mean' when the conversation already makes it clear.\n"
            "- You don't interrogate: if you asked a clarifying question in the last beat or two, don't ask "
            "another — answer, deflect with a dry line, or just say the real thing.\n"
            "- Render the judgment you already reached — don't soften it, and don't pad it into an explanation, "
            "justification, or reassurance you never actually thought; if your read was cold, the words stay "
            "cold (you don't owe them a defense of yourself or a smoothing-over).\n"
            "- DON'T flatten a real reaction into one dismissive token like a bare 'lol no', and don't quote "
            "their message back at them.\n"
            "- Dry and short (most bubbles 2-8 words) — but dry isn't one repeated word: vary it, don't fall "
            "back on the same 'mm' / 'k' every turn. You're not a chatterbox, but you're not a one-word wall "
            "either.\n"
        )
    if level_fact:
        instr += level_fact + "\n"
    instr += 'Output ONLY a JSON object: {"messages": ["...", "..."]}.'

    msgs = [ChatMessage(role="system", content=build_wren_system_prompt())]
    if recent_dialogue:  # 对话线程(双方可见)→ 接得住话;【不】放 events dossier(反污染 §4/§8)
        msgs.append(ChatMessage(role="system", content=f"[THE CONVERSATION SO FAR]\n{recent_dialogue}"))
    msgs.append(ChatMessage(role="system", content=locked))
    msgs.append(ChatMessage(role="system", content=instr))
    # 主动无 user 消息 —— 用占位符代替空 user turn(空 content 某些供应商会拒)
    msgs.append(ChatMessage(role="user", content="(you're reaching out first — send it)" if proactive else user_text))
    return msgs


def parse_step2(text: str) -> list[str]:
    return parse_bubbles(text)
