"""FakeChatModel —— 确定性、可脚本化、可计数的假模型。

离线 /go 与全部确定性测试的引擎。它的"智能"全在测试夹具传入的 responder/script 里;
生产代码对它与真实模型一视同仁。

二选一:
- responder: 看 messages 内容决定回什么(最灵活;judge/Step1/Step2 用)。
- script:    按调用顺序逐条返回(最简单;harness "同输入跑 N 次"用)。
"""

from __future__ import annotations

from collections.abc import Callable

from .base import ChatMessage, ChatResult, ResponseFormat

Responder = Callable[[list[ChatMessage]], str]


class FakeChatModel:
    def __init__(
        self,
        name: str = "fake",
        *,
        responder: Responder | None = None,
        script: list[str] | None = None,
    ) -> None:
        self.name = name
        self._responder = responder
        self._script = list(script) if script is not None else None
        self._script_i = 0
        self.calls: list[list[ChatMessage]] = []  # 全部调用历史,供断言

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: ResponseFormat = "text",
        seed: int | None = None,
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(
            text=self._next(messages),
            model=self.name,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
        )

    def _next(self, messages: list[ChatMessage]) -> str:
        if self._script is not None:
            if self._script_i >= len(self._script):
                raise IndexError(f"FakeChatModel script 用尽(已 {len(self._script)} 次调用)")
            out = self._script[self._script_i]
            self._script_i += 1
            return out
        if self._responder is not None:
            return self._responder(messages)
        return ""  # 默认空 = 沉默
