"""W8 viewer — 运维平台 Flask app(127.0.0.1:8002 + SSH 隧道访问)。

隐私铁律:只读 data/users/* 的 trace/settlement(含原文)用于人工深挖,**不持久化、不出机器**。
强制 bind 127.0.0.1(命令行传 0.0.0.0 也会被忽略) + before_request 拒非 localhost remote_addr。
"""

from __future__ import annotations

import argparse
import contextlib
import time
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, redirect, render_template, request

from .. import config
from ..core.trace import read_settlements, read_traces
from . import health
from .db import chat_hash as _hash_fn
from .db import connect
from .health import gather as gather_health
from .queries import NAMED_QUERIES, run_named

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.template_filter("tojson_pretty")
def _tojson_pretty(value: Any) -> str:
    """jinja filter:把 JSON 字符串美化(2 空格缩进)。如果不是 JSON 原样返回。"""
    import json as _json

    if isinstance(value, str):
        try:
            return _json.dumps(_json.loads(value), indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            return value
    try:
        return _json.dumps(value, indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return str(value)

# chat_hash → chat_id 反查表(60s 缓存)。仅 viewer 内存,不进库不出机。
_HASH_INDEX: dict[str, str] = {}
_HASH_INDEX_TS: float = 0.0
_HASH_INDEX_TTL = 60.0


def _refresh_hash_index() -> None:
    global _HASH_INDEX, _HASH_INDEX_TS
    root = config.data_root()
    if not root.exists():
        _HASH_INDEX = {}
        _HASH_INDEX_TS = time.time()
        return
    idx: dict[str, str] = {}
    for d in root.iterdir():
        if d.is_dir() and d.name.lstrip("-").isdigit():
            idx[_hash_fn(d.name)] = d.name
    _HASH_INDEX = idx
    _HASH_INDEX_TS = time.time()


def _hash_to_chat_id(h: str) -> str | None:
    if time.time() - _HASH_INDEX_TS > _HASH_INDEX_TTL:
        _refresh_hash_index()
    return _HASH_INDEX.get(h)


def _parse_relationship(text: str) -> tuple[int | None, bool]:
    """relationship_state.md 顶部 ~30 行里找 'level: N' / 'lv: N' / 'freeze: bool'。容错。"""
    lv: int | None = None
    freeze = False
    for ln in text.splitlines()[:30]:
        s = ln.strip().lower()
        # match: "level: 0" OR "lv: 0" OR "level=0" (markdown 列表 / yaml-ish 都接)
        if (s.startswith("level") or s.startswith("lv")) and (":" in s or "=" in s):
            sep = ":" if ":" in s else "="
            with contextlib.suppress(ValueError, IndexError):
                lv = int(s.split(sep, 1)[1].strip().split()[0])
        if s.startswith("freeze") and (":" in s or "=" in s):
            sep = ":" if ":" in s else "="
            v = s.split(sep, 1)[1].strip().lower()
            freeze = v.startswith("true") or v.startswith("yes")
    return lv, freeze


def _strip_source_header(text: str) -> str:
    """source.md 第一行可能是 markdown header(# Source ...),取真正的 value。"""
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        return s
    return ""


def _read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _user_list() -> list[dict[str, Any]]:
    root = config.data_root()
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in root.iterdir():
        if not d.is_dir() or not d.name.lstrip("-").isdigit():
            continue
        traces = read_traces(d)
        rel = _read_text_safe(d / "relationship_state.md")
        source = _strip_source_header(_read_text_safe(d / "source.md"))
        lv, freeze = _parse_relationship(rel)
        # silence_pct 简单计算: step2 is None / total
        silent = sum(1 for t in traces if t.get("step2") is None)
        out.append(
            {
                "chat_id": d.name,
                "chat_hash": _hash_fn(d.name),
                "msg_count": len(traces),
                "settle_count": len(read_settlements(d)),
                "last_ts": traces[-1].get("ts") if traces else None,
                "lv": lv,
                "freeze": freeze,
                "source": source[:60] if source else "",
                "silence_pct": round(silent / len(traces) * 100, 1) if traces else 0.0,
            }
        )
    out.sort(key=lambda x: (x.get("last_ts") or ""), reverse=True)
    return out


@app.before_request
def _localhost_only() -> Any:
    """硬限 remote_addr ∈ {127.0.0.1, ::1};即使 bind 误改 0.0.0.0 也兜底。"""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403, "localhost only (SSH 隧道访问)")
    return None


# --- HTML 页面 ---


@app.route("/")
def overview_page() -> Any:
    h = gather_health()
    users = _user_list()
    lv2 = health.lv2_plus_pct()
    return render_template(
        "health.html",
        h=h,
        total_users=health.total_users(),
        active_today=health.active_today(),
        lv2_plus=lv2,
        users_count=len(users),
        engagement_history=health.engagement_history(days=14),
        cost_history=health.cost_history(days=14),
        latency_history=health.latency_history(days=7),
        level_distribution=health.level_distribution(),
        level_transitions=health.level_transitions(days=7),
        sources_distribution=health.sources_distribution(),
        spark_user_msgs=health.kpi_sparkline("user_msgs", days=7),
        spark_silence=health.kpi_sparkline("silence_pct", days=7),
        spark_turns=health.kpi_sparkline("turns", days=7),
        spark_tokens=health.kpi_sparkline("completion_tokens", days=7),
    )


@app.route("/users")
def users_page() -> Any:
    return render_template("users.html", users=_user_list())


@app.route("/levels")
def levels_page() -> Any:
    return render_template(
        "levels.html",
        level_distribution=health.level_distribution(),
        level_transitions=health.level_transitions(days=14),
        time_to_level=health.time_to_level(),
        users=_user_list(),
    )


@app.route("/sources")
def sources_page() -> Any:
    return render_template(
        "sources.html",
        sources=health.sources_distribution(),
        activation=health.activation_by_source(),
        retention=health.retention_by_source(),
    )


@app.route("/cost")
def cost_page() -> Any:
    return render_template(
        "cost.html",
        cost_history=health.cost_history(days=30),
        daily_cap=health.daily_cap_used_pct(),
        today=health.today_metrics(),
    )


@app.route("/nightly")
def nightly_page() -> Any:
    root = config.data_root()
    items: list[dict[str, Any]] = []
    if root.exists():
        for d in root.iterdir():
            if not d.is_dir() or not d.name.lstrip("-").isdigit():
                continue
            for s in read_settlements(d):
                items.append({"chat_id": d.name, **s})
    items.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return render_template(
        "nightly.html",
        settlements=items[:50],
        health_history=health.settlement_health(days=14),
    )


@app.route("/errors")
def errors_page() -> Any:
    return render_template(
        "errors.html",
        errors_1h=health.recent_errors("wren-bot-1", hours=1.0),
        errors_24h=health.error_log_lines(hours=24.0),
    )


@app.route("/system")
def system_page() -> Any:
    import os as _os

    env_keys = [
        "TELEGRAM_BOT_TOKEN",
        "WREN_API_KEY",
        "WREN_BASE_URL",
        "WREN_MODEL",
        "WREN_OWNER_CHAT_IDS",
        "WREN_METRICS_SALT",
        "WREN_DAILY_TURN_CAP",
        "WREN_RATE_LIMIT_PER_MIN",
        "WREN_SETTLEMENT_MODEL",
        "WREN_DEBOUNCE_S",
    ]
    env_status = [{"key": k, "filled": bool(_os.getenv(k, "").strip())} for k in env_keys]
    return render_template(
        "system.html",
        h=gather_health(),
        env_status=env_status,
    )


@app.route("/u/<chat_id>")
def user_detail(chat_id: str) -> Any:
    if not chat_id.lstrip("-").isdigit():
        abort(400, "invalid chat_id")
    root = config.data_root() / chat_id
    if not root.exists():
        abort(404, f"no data for chat_id={chat_id}")
    traces = read_traces(root)
    settles = read_settlements(root)
    items: list[dict[str, Any]] = [
        {"kind": "turn", "ts": t.get("ts", ""), "data": t} for t in traces
    ]
    items += [{"kind": "settle", "ts": s.get("ts", ""), "data": s} for s in settles]
    items.sort(key=lambda x: x["ts"], reverse=True)
    return render_template(
        "user_trace.html",
        chat_id=chat_id,
        chat_hash=_hash_fn(chat_id),
        rel=_read_text_safe(root / "relationship_state.md"),
        source=_read_text_safe(root / "source.md").strip(),
        core=_read_text_safe(root / "core_impression.md"),
        events=_read_text_safe(root / "events.md"),
        items=items,
        turn_count=len(traces),
        settle_count=len(settles),
    )


@app.route("/h/<h>")
def user_by_hash(h: str) -> Any:
    cid = _hash_to_chat_id(h)
    if not cid:
        abort(404, f"chat_hash 反查失败: {h}(尝试 60s 后刷新或直接用 /u/<chat_id>)")
    return redirect(f"/u/{cid}", code=302)


# --- JSON API(给监控/cron 探针用)---


@app.route("/api/health")
def api_health() -> Any:
    return jsonify(gather_health())


@app.route("/api/users")
def api_users() -> Any:
    return jsonify(_user_list())


@app.route("/api/u/<chat_id>")
def api_user(chat_id: str) -> Any:
    if not chat_id.lstrip("-").isdigit():
        abort(400, "invalid chat_id")
    root = config.data_root() / chat_id
    if not root.exists():
        abort(404, f"no data for chat_id={chat_id}")
    return jsonify(
        {
            "chat_id": chat_id,
            "chat_hash": _hash_fn(chat_id),
            "traces": read_traces(root),
            "settlements": read_settlements(root),
        }
    )


@app.route("/api/timeseries/<name>")
def api_timeseries(name: str) -> Any:
    """喂 echarts 数据 — 14 天历史的指定指标。"""
    days_str = request.args.get("days", "14")
    try:
        days = max(1, min(60, int(days_str)))
    except ValueError:
        days = 14
    if name == "engagement":
        return jsonify({"rows": health.engagement_history(days=days)})
    if name == "cost":
        return jsonify({"rows": health.cost_history(days=days)})
    if name == "latency":
        return jsonify({"rows": health.latency_history(days=days)})
    if name == "proactive":
        return jsonify({"rows": health.proactive_history(days=days)})
    if name == "level_transitions":
        return jsonify({"rows": health.level_transitions(days=days)})
    if name == "settlement_health":
        return jsonify({"rows": health.settlement_health(days=days)})
    abort(404, f"unknown timeseries: {name}")


@app.route("/api/levels")
def api_levels() -> Any:
    return jsonify(
        {
            "distribution": health.level_distribution(),
            "transitions": health.level_transitions(days=14),
            "lv2_plus": health.lv2_plus_pct(),
            "time_to_level": health.time_to_level(),
        }
    )


@app.route("/api/sources")
def api_sources() -> Any:
    return jsonify(
        {
            "acquisition": health.sources_distribution(),
            "activation": health.activation_by_source(),
            "retention": health.retention_by_source(),
        }
    )


@app.route("/api/cost")
def api_cost() -> Any:
    days_str = request.args.get("days", "14")
    try:
        days = max(1, min(60, int(days_str)))
    except ValueError:
        days = 14
    return jsonify(
        {
            "history": health.cost_history(days=days),
            "daily_cap": health.daily_cap_used_pct(),
            "today": health.today_metrics(),
        }
    )


@app.route("/api/errors")
def api_errors() -> Any:
    hours_str = request.args.get("hours", "24")
    try:
        hours = max(0.1, min(168.0, float(hours_str)))
    except ValueError:
        hours = 24.0
    return jsonify(health.error_log_lines(hours=hours))


@app.route("/api/queries/<name>")
def api_query(name: str) -> Any:
    if name not in NAMED_QUERIES:
        abort(404, f"unknown query: {name}")
    try:
        con = connect(read_only=True)
    except Exception:  # noqa: BLE001 - duckdb 库不存在等 fail-safe
        return jsonify({"available": False, "rows": []})
    try:
        cols, rows = run_named(con, name)
        return jsonify(
            {"available": True, "cols": cols, "rows": [list(r) for r in rows]}
        )
    finally:
        with contextlib.suppress(Exception):
            con.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="wren-view", description="W8 viewer(运维平台,绑 127.0.0.1,SSH 隧道访问)"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    # SAFETY:命令行强制传 0.0.0.0 也忽略(隐私铁律 — 不可暴露公网)
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        print(f"⚠️  强制 bind 127.0.0.1(传入 host={args.host} 被忽略,隐私铁律)")
        args.host = "127.0.0.1"
    _refresh_hash_index()
    print(
        f"Wren viewer: http://{args.host}:{args.port}/  (本机 / SSH 隧道访问;"
        f"已索引 {len(_HASH_INDEX)} 个 chat_hash → chat_id)"
    )
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
