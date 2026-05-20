"""ChatModel 协议与数据类 —— 一次"对话补全"为单位,Step1/Step2/judge 都用它。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]
ResponseFormat = Literal["text", "json"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ChatResult:
    text: str  # 模型最终输出文本(Step1 独白 JSON / Step2 数组 JSON / judge JSON / 普通文本)
    model: str  # 实际用的 model 名(落 trace;绝不含密钥)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0


@runtime_checkable
class ChatModel(Protocol):
    """provider 无关的最薄接口。同步设计(eval 全同步;bot 用 asyncio.to_thread 包)。"""

    name: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: ResponseFormat = "text",
        seed: int | None = None,
    ) -> ChatResult: ...
