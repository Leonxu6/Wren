"""Prompt 种子 —— Phase 0 harness 确立,Phase 1 Step1/Step2 复用同一 Wren system prompt。

🔒契约:build_wren_system_prompt() 显式立住反谄媚两轴(『你不是 assistant、不接需求、
对命令像真人反应』)+ §3 红线 + AI 披露。这是 §3.1「她不为你存在」在 prompt 层的落点。
"""

from .judge import build_judge_messages, parse_judge
from .step1 import build_step1_messages, parse_step1
from .step2 import build_step2_messages, parse_step2
from .system import (
    build_reply_messages,
    build_sweetie_baseline_prompt,
    build_wren_system_prompt,
    parse_bubbles,
)

__all__ = [
    "build_judge_messages",
    "build_reply_messages",
    "build_step1_messages",
    "build_step2_messages",
    "build_sweetie_baseline_prompt",
    "build_wren_system_prompt",
    "parse_bubbles",
    "parse_judge",
    "parse_step1",
    "parse_step2",
]
