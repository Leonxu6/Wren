"""registry —— 按 env 决定真实还是 fake。这是"零改代码即 live"的唯一开关。

有 WREN_API_KEY 且非 WREN_FAKE_MODEL=1 → 真实 OpenAICompatModel;否则 FakeChatModel。
"""

from __future__ import annotations

from typing import Literal

from .. import config
from .base import ChatModel
from .fake import FakeChatModel
from .openai_compat import OpenAICompatModel

Role = Literal["primary", "step1", "step2", "judge", "baseline", "background"]


def _spec_for(role: Role) -> config.ModelSpec:
    if role == "judge":
        return config.judge_model_spec()
    if role == "baseline":
        return config.baseline_model_spec()
    return config.primary_model_spec()


def model_from_spec(spec: config.ModelSpec) -> ChatModel:
    """据一个 ModelSpec 造模型;无 key/强制 fake 时退化为同名 fake。"""
    if config.force_fake() or not spec.api_key:
        return FakeChatModel(name=f"fake-{spec.name}")
    return OpenAICompatModel(
        name=spec.name,
        base_url=spec.base_url,
        api_key=spec.api_key,
        model=spec.model,
        default_max_tokens=config.max_tokens(),
    )


def get_model(role: Role = "primary") -> ChatModel:
    """生产/eval 取模型的统一入口。"""
    if config.force_fake() or not config.has_api_key():
        return FakeChatModel(name=f"fake-{role}")
    return model_from_spec(_spec_for(role))


def list_candidates() -> list[config.ModelSpec]:
    """bake-off 候选清单(DeepSeek 系必含)。"""
    return config.candidates()
