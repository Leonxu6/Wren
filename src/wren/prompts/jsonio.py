"""模型 JSON 输出的稳健解析(剥 ``` 围栏、截取首个 {...})。"""

from __future__ import annotations

import json
from typing import Any


def loads_lenient(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        if 0 <= i < j:
            try:
                data = json.loads(text[i : j + 1])
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
