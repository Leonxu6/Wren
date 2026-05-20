"""openai 兼容真实适配器(DeepSeek 等)。base_url/api_key/model 由 config 注入。

注:DeepSeek V4 是推理模型(usage 含 reasoning_tokens),max_tokens 要留足。
最终答案读 message.content;思维链(若有)在 reasoning_content,我们不消费。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from openai import OpenAI

from .base import ChatMessage, ChatResult, ResponseFormat

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class OpenAICompatModel:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        default_max_tokens: int = 2048,
    ) -> None:
        self.name = name
        self.model = model
        self._default_max_tokens = default_max_tokens
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: ResponseFormat = "text",
        seed: int | None = None,
    ) -> ChatResult:
        oai_messages = cast(
            "list[ChatCompletionMessageParam]",
            [{"role": m.role, "content": m.content} for m in messages],
        )
        # 只在需要时带 response_format/seed,避开 SDK 重载里 NotGiven/Omit 的版本差异
        extra: dict[str, Any] = {}
        if response_format == "json":
            extra["response_format"] = {"type": "json_object"}
        if seed is not None:
            extra["seed"] = seed
        start = time.monotonic()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            temperature=temperature,
            max_tokens=max_tokens or self._default_max_tokens,
            **extra,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return ChatResult(
            text=text,
            model=self.model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )
