"""registry —— 按 env 决定真实还是 fake。这是"零改代码即 live"的唯一开关。

有 WREN_API_KEY 且非 WREN_FAKE_MODEL=1 → 真实 OpenAICompatModel;否则 FakeChatModel。
"""

from __future__ import annotations

from typing import Literal

from .. import config
from .base import ChatMessage, ChatModel, ChatResult, ResponseFormat
from .fake import FakeChatModel
from .openai_compat import OpenAICompatModel

Role = Literal["primary", "step1", "step2", "judge", "settlement", "baseline", "background"]


class DailyCapModel:
    """Thin runtime wrapper that enforces the global daily model-call cap."""

    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner
        self.name = inner.name

    @property
    def inner(self) -> ChatModel:
        return self._inner

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: ResponseFormat = "text",
        seed: int | None = None,
    ) -> ChatResult:
        from ..bot.limits import register_model_call

        if register_model_call():
            raise RuntimeError("daily LLM call cap reached (WREN_DAILY_TURN_CAP)")
        return self._inner.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed,
        )


def _with_daily_cap(model: ChatModel) -> ChatModel:
    return DailyCapModel(model)


def _spec_for(role: Role) -> config.ModelSpec:
    if role == "judge":
        return config.judge_model_spec()
    if role == "settlement":
        return config.settlement_model_spec()
    if role == "baseline":
        return config.baseline_model_spec()
    return config.primary_model_spec()


def model_from_spec(spec: config.ModelSpec) -> ChatModel:
    """据一个 ModelSpec 造模型;无 key/强制 fake 时退化为同名 fake。"""
    if config.force_fake() or not spec.api_key:
        return _with_daily_cap(FakeChatModel(name=f"fake-{spec.name}"))
    return _with_daily_cap(
        OpenAICompatModel(
            name=spec.name,
            base_url=spec.base_url,
            api_key=spec.api_key,
            model=spec.model,
            default_max_tokens=config.max_tokens(),
        )
    )


def get_model(role: Role = "primary") -> ChatModel:
    """生产/eval 取模型的统一入口。"""
    if config.force_fake() or not config.has_api_key():
        return _with_daily_cap(FakeChatModel(name=f"fake-{role}"))
    return model_from_spec(_spec_for(role))


def list_candidates() -> list[config.ModelSpec]:
    """bake-off 候选清单(DeepSeek 系必含)。"""
    return config.candidates()
