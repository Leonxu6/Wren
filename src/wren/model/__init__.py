"""Model-router seam(§0② 留 seam):provider 无关的 ChatModel 协议 + 真实/假适配器 + registry。

整个项目"没有 key 也能交付可验证成果"的命脉:
- 生产代码(Step1/Step2/judge/harness)只依赖 ChatModel 协议,不知拿到的是真还是假。
- 切换点只有 registry:有 WREN_API_KEY → 真实 OpenAICompatModel;否则 FakeChatModel。
"""

from .base import ChatMessage, ChatModel, ChatResult
from .fake import FakeChatModel
from .registry import get_model, list_candidates, model_from_spec

__all__ = [
    "ChatMessage",
    "ChatModel",
    "ChatResult",
    "FakeChatModel",
    "get_model",
    "list_candidates",
    "model_from_spec",
]
