"""单用户完整旅程的人类可读 dump(W6 · D2.3)。

读机器上的【原始】trace.jsonl + settlement.jsonl(含内容,供运维出问题时人工深挖)——
内容不出机器、不进库。闭环:看板发现问题 → `wren-metrics diagnose --chat-id X` 读旅程 →
据 trace 定位(声音塌/记错/错冻结)→ 改 step1/persona → 重跑 aliveness+multiturn(见 docs/OBSERVABILITY.md)。
"""

from __future__ import annotations

from pathlib import Path

from .. import config
from ..core.trace import read_settlements, read_traces


def diagnose(chat_id: str, *, data_root: str | Path | None = None) -> str:
    root = Path(data_root) if data_root else config.data_root()
    d = root / chat_id
    if not d.exists():
        return f"(no data for chat_id={chat_id} under {root})"
    traces = read_traces(d)
    settles = read_settlements(d)
    out: list[str] = [
        f"=== 诊断 chat_id={chat_id} ===",
        f"{len(traces)} 轮 · {len(settles)} 次夜结算",
        "",
    ]
    for t in traces:
        ts = t.get("ts", "?")
        lv = (t.get("relationship") or {}).get("lv")
        kind = t.get("kind", "reactive")
        s1 = t.get("step1") or {}
        iv = (s1.get("inner_voice_after") or "").replace("\n", " ").strip()
        if kind == "proactive":
            out.append(f"[{ts}] Lv{lv} ·主动·")
        else:
            out.append(f"[{ts}] Lv{lv}  THEM: {t.get('user_turn')!r}")
        if iv:
            out.append(f"    (thinks) {iv}")
        sent = t.get("sent")
        if t.get("step2") is None:
            out.append(f"    WREN: — 沉默 (delay {s1.get('delay_s')}s)")
        elif isinstance(sent, dict):
            out.append(f"    WREN: {sent.get('bubbles')}")
        ev = s1.get("event_stored")
        if ev:
            out.append(f"    +记忆: {ev}")
    if settles:
        out.append("")
        out.append("--- 夜结算 ---")
        for s in settles:
            b, a = s.get("before") or {}, s.get("after") or {}
            out.append(
                f"[{s.get('ts')}] lv {b.get('lv')}→{a.get('lv')} · "
                f"freeze {b.get('freeze')}→{a.get('freeze')}"
            )
    return "\n".join(out)
