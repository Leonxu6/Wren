"""W8 运维平台健康探针 — viewer 首页的所有信号源都在这。

所有函数 fail-safe:遇错返回 sane defaults,不抛异常。viewer 即使在 docker socket 不可用 /
metrics db 不存在 / data 目录为空 的边缘情况下仍能渲染首页。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .. import config
from .db import connect, metrics_db_path
from .queries import run_named

DOCKER_SOCK = "/var/run/docker.sock"
_NET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_NET_CACHE_TTL = 30.0


def _docker_get(path: str, timeout_s: float = 3.0) -> tuple[int, bytes] | None:
    """裸 unix socket HTTP/1.0 GET。返回 (status_code, body) 或 None(失败)。"""
    if not os.path.exists(DOCKER_SOCK):
        return None
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    try:
        s.connect(DOCKER_SOCK)
        s.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        data = bytearray()
        while True:
            chunk = s.recv(8192)
            if not chunk:
                break
            data += chunk
    except (TimeoutError, OSError):
        return None
    finally:
        s.close()
    if b"\r\n\r\n" not in data:
        return None
    head, body = bytes(data).split(b"\r\n\r\n", 1)
    try:
        status = int(head.split(b"\r\n", 1)[0].split(b" ", 2)[1])
    except (IndexError, ValueError):
        return None
    return status, body


def container_status(name: str) -> dict[str, Any]:
    """通过 docker socket 查容器状态。失败 → status=unknown。"""
    out: dict[str, Any] = {
        "name": name,
        "status": "unknown",
        "uptime_s": None,
        "restart_count": None,
        "image": None,
    }
    res = _docker_get(f"/containers/{name}/json")
    if res is None or res[0] != 200:
        return out
    try:
        info = json.loads(res[1])
    except json.JSONDecodeError:
        return out
    state = info.get("State") or {}
    out["status"] = state.get("Status") or "unknown"
    out["restart_count"] = info.get("RestartCount", 0)
    out["image"] = (info.get("Config") or {}).get("Image")
    started_at = state.get("StartedAt") or ""
    if started_at and out["status"] == "running":
        try:
            t = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            out["uptime_s"] = int((datetime.now(tz=UTC) - t).total_seconds())
        except ValueError:
            pass
    return out


def disk_usage(path: str = "/") -> dict[str, Any]:
    try:
        st = os.statvfs(path)
    except OSError:
        return {"used_pct": None, "free_gb": None, "total_gb": None}
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {
        "used_pct": round((total - free) / total * 100, 1) if total > 0 else None,
        "free_gb": round(free / 1024**3, 1),
        "total_gb": round(total / 1024**3, 1),
    }


def mem_usage() -> dict[str, Any]:
    try:
        text = Path("/proc/meminfo").read_text()
    except OSError:
        return {"used_pct": None, "used_mb": None, "total_mb": None}
    info: dict[str, int] = {}
    for ln in text.splitlines():
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        try:
            info[k.strip()] = int(v.strip().split()[0])  # kB
        except (ValueError, IndexError):
            continue
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    if total <= 0:
        return {"used_pct": None, "used_mb": None, "total_mb": None}
    return {
        "used_pct": round((total - avail) / total * 100, 1),
        "used_mb": round((total - avail) / 1024),
        "total_mb": round(total / 1024),
    }


def cpu_load() -> dict[str, Any]:
    try:
        parts = Path("/proc/loadavg").read_text().split()
        return {
            "load_1m": float(parts[0]),
            "load_5m": float(parts[1]),
            "load_15m": float(parts[2]),
        }
    except (OSError, IndexError, ValueError):
        return {"load_1m": None, "load_5m": None, "load_15m": None}


def _dir_size_mb(p: Path) -> float | None:
    if not p.exists():
        return None
    total = 0
    for dirpath, _, fnames in os.walk(p):
        for fn in fnames:
            try:
                total += (Path(dirpath) / fn).stat().st_size
            except OSError:
                continue
    return round(total / 1024**2, 1)


def data_sizes() -> dict[str, Any]:
    """data / world / backups 目录大小(MB)。优先看 /srv/wren-backups,fallback 看 cwd 同级。"""
    data_root = config.data_root().parent  # config.data_root() 是 .../data/users → parent = .../data
    return {
        "data_mb": _dir_size_mb(data_root),
        "world_mb": _dir_size_mb(data_root.parent / "world"),
        "backups_mb": _dir_size_mb(Path("/srv/wren-backups")),
    }


def net_probe(name: str, url: str, timeout_s: float = 5.0) -> dict[str, Any]:
    """30s 缓存的出网探测。2xx/3xx/4xx 全当"通"(只 5xx/timeout/conn-refused 是 down) — 探测目的
    是验证 TCP/HTTPS 可达,不是验证 endpoint 有 auth。比如 DeepSeek root 路径 401 = 出网正常。"""
    now = time.time()
    cached = _NET_CACHE.get(name)
    if cached and now - cached[0] < _NET_CACHE_TTL:
        return cached[1]
    t0 = time.time()
    out: dict[str, Any]
    try:
        resp = urlopen(url, timeout=timeout_s)  # noqa: S310 - 探测固定白名单 URL
        code = resp.status
        out = {"ok": code < 500, "code": code, "latency_ms": int((time.time() - t0) * 1000)}
    except URLError as e:
        # HTTPError 是 URLError 子类:它有 code(说明 TCP 通了只是 4xx/5xx)
        from urllib.error import HTTPError

        if isinstance(e, HTTPError):
            code = e.code
            out = {"ok": code < 500, "code": code, "latency_ms": int((time.time() - t0) * 1000)}
        else:
            out = {"ok": False, "code": None, "latency_ms": None, "error": str(e.reason)[:80]}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "code": None, "latency_ms": None, "error": str(e)[:80]}
    _NET_CACHE[name] = (now, out)
    return out


def network_probes() -> dict[str, dict[str, Any]]:
    return {
        "telegram": net_probe("telegram", "https://api.telegram.org/"),
        "deepseek": net_probe("deepseek", "https://api.deepseek.com/"),
        "github": net_probe("github", "https://github.com/"),
    }


def last_backup(backup_dir: Path | str = "/srv/wren-backups") -> dict[str, Any]:
    d = Path(backup_dir)
    if not d.exists():
        return {"path": None, "ts": None, "size_mb": None, "age_h": None}
    cands = sorted(d.glob("wren-*.tgz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        return {"path": None, "ts": None, "size_mb": None, "age_h": None}
    p = cands[0]
    m = p.stat().st_mtime
    return {
        "path": str(p),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(m)),
        "size_mb": round(p.stat().st_size / 1024**2, 2),
        "age_h": round((time.time() - m) / 3600, 1),
    }


def last_settlement(data_root: Path | None = None) -> dict[str, Any]:
    """所有用户中最新的 settlement.jsonl 末尾条目(用于"上次夜结算"指示)。"""
    root = data_root or config.data_root()
    if not root.exists():
        return {"ts": None, "chat_id": None, "age_h": None}
    latest: tuple[float, str, str] | None = None
    for d in root.iterdir():
        if not d.is_dir():
            continue
        sp = d / "settlement.jsonl"
        if not sp.exists():
            continue
        try:
            last_line = ""
            with sp.open() as f:
                for ln in f:
                    if ln.strip():
                        last_line = ln.strip()
            if not last_line:
                continue
            ts = json.loads(last_line).get("ts", "")
            m = sp.stat().st_mtime
            if latest is None or m > latest[0]:
                latest = (m, d.name, ts)
        except (OSError, json.JSONDecodeError):
            continue
    if latest is None:
        return {"ts": None, "chat_id": None, "age_h": None}
    return {
        "ts": latest[2],
        "chat_id": latest[1],
        "age_h": round((time.time() - latest[0]) / 3600, 1),
    }


def today_metrics() -> dict[str, Any]:
    """从 metrics.duckdb 取今日指标。库不存在 → available=False。

    字段语义:
    - `user_msgs` / `silence_pct`:来自 `engagement_daily`,**仅 reactive** 用户消息。
    - `turn_count` / `completion_tokens` / `flash_s1_tokens`:来自 `cost_daily`,
      `turn_count` 是**全 turn** 计数(reactive + proactive + scheduler),是
      DAILY_CAP 应该参照的量,也是 cost dashboard 的"今日 turn 数"该展示的量。
    - 这里不返回 `cost_usd`——项目无 pricing model(§15 开放问题),
      过去那个字段实际上是 `cost_daily.turns` 错位填进 USD 槽,见 #10。
      要看成本压力就看 `turn_count` + `completion_tokens` 两个真实信号。
    """
    db = metrics_db_path()
    out: dict[str, Any] = {
        "available": False,
        "user_msgs": None,
        "silence_pct": None,
        "turn_count": None,
        "completion_tokens": None,
        "flash_s1_tokens": None,
    }
    if not db.exists():
        return out
    try:
        con = connect(read_only=True)
    except Exception:  # noqa: BLE001
        return out
    out["available"] = True
    today = date.today().isoformat()
    try:
        _, rows = run_named(con, "engagement_daily")
        r = next((r for r in rows if str(r[0]) == today), None)
        if r:
            out["user_msgs"] = r[1]
            out["silence_pct"] = r[2]
        else:
            out["user_msgs"] = 0
            out["silence_pct"] = 0.0
    except Exception:  # noqa: BLE001
        pass
    try:
        _, rows = run_named(con, "cost_daily")
        r = next((r for r in rows if str(r[0]) == today), None)
        if r:
            out["turn_count"] = r[1]
            out["completion_tokens"] = r[2]
            out["flash_s1_tokens"] = r[3]
        else:
            out["turn_count"] = 0
            out["completion_tokens"] = 0
            out["flash_s1_tokens"] = 0
    except Exception:  # noqa: BLE001
        pass
    with contextlib.suppress(Exception):
        con.close()
    return out


_ERR_PATTERN = re.compile(r"error|exception|traceback|conflict|critical", re.IGNORECASE)


def recent_errors(name: str = "wren-bot-1", hours: float = 1.0) -> dict[str, Any]:
    """docker logs 最近 N 小时里 error/exception/traceback/conflict/critical 计数。"""
    since = int(time.time() - hours * 3600)
    res = _docker_get(f"/containers/{name}/logs?stderr=1&stdout=1&since={since}&tail=2000")
    if res is None or res[0] != 200:
        return {"count": None, "available": False}
    text = res[1].decode("utf-8", errors="replace")
    return {"count": len(_ERR_PATTERN.findall(text)), "available": True}


def daily_cap_used_pct() -> dict[str, Any]:
    """今日 turn 数 vs WREN_DAILY_TURN_CAP 的进度。

    used = `turn_count`(全 turn,含 reactive + proactive + scheduler);
    不能用 `user_msgs`——proactive turn 不计 user_msgs 但消耗 CAP,
    用前者会让 dashboard 显示"还有余量",而真实 turn cap 已更逼近上限(#10)。
    """
    cap_raw = os.getenv("WREN_DAILY_TURN_CAP", "0").strip() or "0"
    try:
        cap = int(cap_raw)
    except ValueError:
        cap = 0
    tm = today_metrics()
    used = tm.get("turn_count") or 0
    if cap <= 0:
        return {"cap": 0, "used": used, "pct": None}
    return {"cap": cap, "used": used, "pct": round(used / cap * 100, 1)}


def _query_safe(name: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    """fail-safe run_named:metrics.duckdb 不存在/查询挂 → 返回空表。"""
    if not metrics_db_path().exists():
        return [], []
    try:
        con = connect(read_only=True)
    except Exception:  # noqa: BLE001
        return [], []
    try:
        return run_named(con, name)
    except Exception:  # noqa: BLE001
        return [], []
    finally:
        with contextlib.suppress(Exception):
            con.close()


def _rows_to_dicts(cols: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(cols, r, strict=False)) for r in rows]


def sources_distribution() -> list[dict[str, Any]]:
    """各 ?start=<campaign> 渠道带来用户数(W3 深链归因)。"""
    cols, rows = _query_safe("acquisition_by_source")
    return _rows_to_dicts(cols, rows)


def activation_by_source() -> list[dict[str, Any]]:
    cols, rows = _query_safe("activation_by_source")
    return _rows_to_dicts(cols, rows)


def retention_by_source() -> list[dict[str, Any]]:
    cols, rows = _query_safe("retention_by_source")
    return _rows_to_dicts(cols, rows)


def level_distribution() -> list[dict[str, Any]]:
    """每个 lv 多少人(头号指标)。返回 [{lv: 0, users: 1}, ...]。"""
    cols, rows = _query_safe("level_distribution")
    return _rows_to_dicts(cols, rows)


def level_transitions(days: int = 7) -> list[dict[str, Any]]:
    """每晚升/降/新冻结/解冻;只取最近 N 天。"""
    cols, rows = _query_safe("level_transitions")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def cost_history(days: int = 14) -> list[dict[str, Any]]:
    """每天 turn + completion tokens,最近 N 天。"""
    cols, rows = _query_safe("cost_daily")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def latency_history(days: int = 7) -> list[dict[str, Any]]:
    """每天 p50/p95(ms),最近 N 天。"""
    cols, rows = _query_safe("latency_daily")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def engagement_history(days: int = 14) -> list[dict[str, Any]]:
    """每天 user_msgs + silence_pct,最近 N 天。"""
    cols, rows = _query_safe("engagement_daily")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def proactive_history(days: int = 14) -> list[dict[str, Any]]:
    cols, rows = _query_safe("proactive_daily")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def settlement_health(days: int = 14) -> list[dict[str, Any]]:
    cols, rows = _query_safe("settlement_health")
    out = _rows_to_dicts(cols, rows)
    return out[-days:] if days > 0 else out


def per_user_overview() -> list[dict[str, Any]]:
    """metrics.duckdb 视角的用户概览(chat_hash 不含 chat_id)。"""
    cols, rows = _query_safe("per_user_overview")
    return _rows_to_dicts(cols, rows)


def time_to_level() -> dict[str, Any]:
    """中位达 Lv2/Lv3 天数(1 行 1 列结果转 dict)。"""
    cols, rows = _query_safe("time_to_level")
    if not rows:
        return {"median_days_to_lv2": None, "median_days_to_lv3": None}
    return dict(zip(cols, rows[0], strict=False))


def kpi_sparkline(metric: str, days: int = 7) -> list[float]:
    """给某 KPI 拿过去 N 天的趋势数组(用于 sparkline echart)。
    metric: 'user_msgs' | 'silence_pct' | 'turns' | 'completion_tokens'
    """
    if metric in {"user_msgs", "silence_pct"}:
        hist = engagement_history(days)
        key = metric
    elif metric in {"turns", "completion_tokens"}:
        hist = cost_history(days)
        key = metric
    else:
        return []
    return [float(r.get(key) or 0) for r in hist]


def total_users() -> int:
    """总用户数(扫 data/users/ 目录数,fallback 看 metrics)。"""
    root = config.data_root()
    if root.exists():
        return sum(1 for d in root.iterdir() if d.is_dir() and d.name.lstrip("-").isdigit())
    return 0


def active_today() -> int:
    """今日发过消息的用户数(从 metrics 库 engagement_daily 反推 — 没有则扫 trace.jsonl)。"""
    hist = engagement_history(days=1)
    if hist and hist[-1].get("user_msgs"):
        # engagement_daily 算的是 turn 数不是去重 user 数 — 退而求其次:扫 data 看今日有 trace 的用户数
        pass
    # 直接扫 data/users:今日有 trace.jsonl 写过的用户数
    root = config.data_root()
    if not root.exists():
        return 0
    today = date.today().isoformat()
    n = 0
    for d in root.iterdir():
        if not d.is_dir():
            continue
        tp = d / "trace.jsonl"
        if not tp.exists():
            continue
        try:
            for ln in tp.read_text().splitlines():
                if not ln.strip():
                    continue
                if today in ln:  # 粗暴 substring 匹配 ts 字段(够用)
                    n += 1
                    break
        except OSError:
            continue
    return n


def lv2_plus_pct() -> dict[str, Any]:
    """Lv≥2 用户占比。"""
    dist = level_distribution()
    if not dist:
        return {"count": 0, "pct": 0.0, "total": 0}
    total = sum(int(r["users"]) for r in dist)
    lv2_plus = sum(int(r["users"]) for r in dist if int(r["lv"]) >= 2)
    return {
        "count": lv2_plus,
        "total": total,
        "pct": round(lv2_plus / total * 100, 1) if total > 0 else 0.0,
    }


def error_log_lines(hours: float = 24, name: str = "wren-bot-1", limit: int = 50) -> dict[str, Any]:
    """近 N 小时 bot logs 里的错误行(含时间戳),最多返回 limit 条。"""
    since = int(time.time() - hours * 3600)
    res = _docker_get(f"/containers/{name}/logs?stderr=1&stdout=1&since={since}&tail=5000&timestamps=1")
    if res is None or res[0] != 200:
        return {"available": False, "count": 0, "lines": []}
    text = res[1].decode("utf-8", errors="replace")
    matched = []
    for ln in text.splitlines():
        if _ERR_PATTERN.search(ln):
            # docker logs raw 头部有 8-byte framing,先 strip non-printable
            clean = "".join(c for c in ln if c.isprintable() or c == " ")
            matched.append(clean[:300])
    return {
        "available": True,
        "count": len(matched),
        "lines": matched[-limit:] if matched else [],
    }


def gather() -> dict[str, Any]:
    """汇总所有探针 → 一个 dict,viewer 首页直接 render。"""
    return {
        "containers": {
            "bot": container_status("wren-bot-1"),
            "metrics": container_status("wren-metrics-1"),
            "viewer": container_status("wren-viewer-1"),
        },
        "resources": {
            "cpu": cpu_load(),
            "mem": mem_usage(),
            "disk": disk_usage("/"),
            "sizes": data_sizes(),
        },
        "net": network_probes(),
        "backup": last_backup(),
        "settlement": last_settlement(),
        "today": today_metrics(),
        "daily_cap": daily_cap_used_pct(),
        "errors_1h": recent_errors("wren-bot-1", hours=1.0),
        "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
