"""模型 JSON 输出的稳健解析(剥 ``` 围栏、截取首个 {...})+ 严格 coercion helpers(#30)。"""

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


# === #30:严格 coercion helpers(防 LLM 抽风给出 `"false"`/`"soon"`/`"foo"` 等坏类型)===
# 纯 parser/coercion,不改任何 voice / prompt 文案;严格 Leon unblock scope。


def strict_bool(v: Any, default: bool) -> bool:
    """严格 bool 解析:接受真 bool;或显式字符串 "true"/"false"(case-insensitive);
    其它值 → `default`,**不**走 Python `bool(v)`(那条 `bool("false") == True`,#30)。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s == "true":
            return True
        if s == "false":
            return False
    return default


def safe_int(
    v: Any, default: int = 0, *, lo: int | None = None, hi: int | None = None
) -> int:
    """safe int coerce:int / float / 纯数字 string → int;其它 → `default`(#30)。

    显式拒绝 bool(避免 `True`/`False` 被当 1/0 静默通过)+ 拒绝非数字 string
    (`int("soon")` 会 ValueError 让整个 turn 崩,见 #30)。
    可选 `lo`/`hi` clamp,防 LLM 给离谱大数。
    """
    if isinstance(v, bool):
        n = default
    else:
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def safe_list_of_str(v: Any, *, cap: int | None = None) -> list[str]:
    """v 是 `list[str-like]` → 元素 str+strip+过滤空;其它(**包括 str**)→ `[]`(#30)。

    Python 的 `for m in "foo"` 会按字符迭代字符串(`"f", "o", "o"`),
    无声地把 `"foo"` 变成 `["f", "o", "o"]`。这里显式拒绝 str / 其它类型。
    """
    if not isinstance(v, list):
        return []
    out = [str(x).strip() for x in v if str(x).strip()]
    return out[:cap] if cap is not None else out
