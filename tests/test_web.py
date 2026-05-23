"""W8 viewer 测试:Flask 路由 + health 探针 fail-safe + remote_addr 中间件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wren.ops import health, web


@pytest.fixture
def fake_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """临时 data/users/<chat_id>/ 目录,塞两个 user + trace/settlement 各一条。"""
    users = tmp_path / "data" / "users"
    users.mkdir(parents=True)
    monkeypatch.setenv("WREN_DATA_ROOT", str(users))
    monkeypatch.setenv("WREN_METRICS_SALT", "test-salt")

    u1 = users / "11111"
    u1.mkdir()
    (u1 / "relationship_state.md").write_text("lv: 2\nfreeze: false\n\nprose…\n")
    (u1 / "source.md").write_text("launch")
    (u1 / "trace.jsonl").write_text(
        json.dumps(
            {
                "turn_id": "abc-1",
                "chat_id": "11111",
                "ts": "2026-05-23T10:00:00Z",
                "user_turn": "hey",
                "relationship": {"lv": 2, "freeze": False},
                "step1": {
                    "reply": True,
                    "delay_s": 8,
                    "inner_voice_after": "ok, casual hi.",
                    "impression": "",
                    "event_stored": "",
                    "tokens": 120,
                    "latency_ms": 130,
                    "model": "fake",
                },
                "step2": {"bubbles": ["hi"]},
                "sent": {"bubbles": ["hi"]},
                "kind": "reactive",
            }
        )
        + "\n"
    )
    (u1 / "settlement.jsonl").write_text(
        json.dumps(
            {
                "settlement_id": "abc-s1",
                "chat_id": "11111",
                "ts": "2026-05-23T06:30:00Z",
                "before": {"lv": 2, "freeze": False},
                "after": {"lv": 2, "freeze": False},
                "impressions": ["small win today"],
                "judge": {
                    "model": "fake",
                    "raw_out": "prose: still here.\ncore: patient.",
                    "tokens": 500,
                    "latency_ms": 800,
                    "parse_ok": True,
                },
            }
        )
        + "\n"
    )

    u2 = users / "22222"
    u2.mkdir()
    (u2 / "relationship_state.md").write_text("lv: 0\nfreeze: true\n")
    (u2 / "trace.jsonl").write_text("")  # 空

    return users


@pytest.fixture
def client(fake_data_dir: Path) -> Any:
    web.app.config["TESTING"] = True
    web._refresh_hash_index()
    return web.app.test_client()


# --- 中间件 ---


def test_remote_addr_middleware_blocks_non_localhost(client: Any) -> None:
    """非 127.0.0.1 的请求应被 403。"""
    resp = client.get("/", environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
    assert resp.status_code == 403


def test_remote_addr_middleware_allows_localhost(client: Any) -> None:
    resp = client.get("/", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200


# --- 路由 ---


def test_health_page_renders(client: Any) -> None:
    resp = client.get("/", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    body = resp.data.decode()
    # W8.1 浅色 admin 风:中文页面标题 + 8 nav 条 + echart 容器
    assert "总览" in body
    assert "容器" in body
    assert "出网" in body
    assert "chart-levels" in body  # echart 容器 id
    assert "echarts" in body  # echarts CDN
    # nav 8 条
    for label in ("总览", "用户", "等级", "来源", "成本", "夜结算", "错误", "系统"):
        assert label in body, f"nav 条目 {label!r} 缺失"


def test_users_page_lists_chat_ids(client: Any) -> None:
    resp = client.get("/users", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "11111" in body
    assert "22222" in body
    assert "launch" in body  # source.md 内容


def test_user_detail_shows_inner_voice_and_settlement(client: Any) -> None:
    resp = client.get("/u/11111", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    body = resp.data.decode()
    # V1 验证:trace 可看
    assert "hey" in body  # user_turn
    assert "ok, casual hi." in body  # inner_voice_after
    assert "hi" in body  # bubble
    # V2 验证:settlement 可看
    assert "夜结算" in body
    assert "small win today" in body
    assert "patient" in body  # raw_out


def test_user_detail_invalid_chat_id_400(client: Any) -> None:
    resp = client.get("/u/not-a-number", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 400


def test_user_detail_unknown_chat_id_404(client: Any) -> None:
    resp = client.get("/u/99999", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 404


def test_hash_redirect(client: Any) -> None:
    from wren.ops.db import chat_hash

    h = chat_hash("11111")
    resp = client.get(f"/h/{h}", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/u/11111")


def test_api_health_returns_json(client: Any) -> None:
    resp = client.get("/api/health", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    j = resp.get_json()
    assert "containers" in j
    assert "resources" in j
    assert "net" in j  # 30s 缓存的探针


def test_api_user_returns_full_trace(client: Any) -> None:
    resp = client.get("/api/u/11111", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["chat_id"] == "11111"
    assert len(j["traces"]) == 1
    assert j["traces"][0]["step1"]["inner_voice_after"] == "ok, casual hi."
    assert len(j["settlements"]) == 1


# --- health 探针 fail-safe ---


def test_container_status_failsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    """docker socket 不存在时,container_status 返回 unknown,不抛。"""
    monkeypatch.setattr(health, "DOCKER_SOCK", "/nonexistent-sock")
    out = health.container_status("wren-bot-1")
    assert out["status"] == "unknown"
    assert out["uptime_s"] is None


def test_disk_usage_real() -> None:
    out = health.disk_usage("/")
    assert out["used_pct"] is not None
    assert 0 <= out["used_pct"] <= 100


def test_mem_usage_failsafe_on_linux_only() -> None:
    """非 Linux 系统 /proc/meminfo 不存在 → fail-safe 返回 None。"""
    out = health.mem_usage()
    # 不假设 OS,只验证字段存在
    assert "used_pct" in out
    assert "total_mb" in out


def test_cpu_load_failsafe() -> None:
    out = health.cpu_load()
    assert "load_1m" in out


def test_today_metrics_failsafe_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """metrics.duckdb 不存在 → available=False,不抛。"""
    monkeypatch.setenv("WREN_METRICS_DB", str(tmp_path / "nonexistent.duckdb"))
    out = health.today_metrics()
    assert out["available"] is False


def test_last_backup_no_dir() -> None:
    out = health.last_backup("/nonexistent-dir")
    assert out["path"] is None
    assert out["ts"] is None


def test_last_settlement_finds_latest(fake_data_dir: Path) -> None:
    out = health.last_settlement(fake_data_dir)
    assert out["chat_id"] == "11111"
    assert out["ts"] == "2026-05-23T06:30:00Z"


def test_gather_doesnt_raise(fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """汇总函数必须永远不抛 —— viewer 首页是 last resort,翻车就看不到任何信号。"""
    monkeypatch.setattr(health, "DOCKER_SOCK", "/nonexistent-sock")
    out = health.gather()
    assert "containers" in out
    assert "resources" in out
    assert "net" in out
    assert "now" in out


# --- 安全:host 强制 ---


def test_main_strict_host(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """命令行传 --host 0.0.0.0 应被强制改回 127.0.0.1。"""
    called: dict[str, Any] = {}

    def fake_run(host: str, port: int, **kw: Any) -> None:
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(web.app, "run", fake_run)
    web.main(["--host", "0.0.0.0", "--port", "9999"])
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9999
    captured = capsys.readouterr()
    assert "强制 bind 127.0.0.1" in captured.out


# === W8.1 新增路由 ===


def test_w81_new_page_routes(client: Any) -> None:
    """6 个新页面应该 200 + 渲染。"""
    for path in ["/levels", "/sources", "/cost", "/nightly", "/errors", "/system"]:
        resp = client.get(path, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert resp.status_code == 200, f"{path} 返回 {resp.status_code}"


def test_w81_api_endpoints(client: Any) -> None:
    """新 API endpoint 返回 JSON。"""
    for path in ["/api/timeseries/engagement", "/api/timeseries/cost",
                 "/api/timeseries/latency", "/api/levels", "/api/sources",
                 "/api/cost", "/api/errors"]:
        resp = client.get(path, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert resp.status_code == 200, f"{path} 返回 {resp.status_code}"
        j = resp.get_json()
        assert j is not None, f"{path} 返回非 JSON"


def test_w81_chat_bubbles_render_inner_voice(client: Any) -> None:
    """单用户页应该用聊天泡泡渲染 + 展开看 inner_voice_after。"""
    resp = client.get("/u/11111", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    body = resp.data.decode()
    # 聊天泡泡风 class
    assert "bubble-row" in body
    assert "bubble-stack" in body
    # inner_voice_after 必须可见(Leon 强调"完整 trace 必须看到")
    assert "ok, casual hi." in body
    assert "inner_voice_after" in body
    # settlement 月亮卡
    assert "settle-card" in body
    assert "夜结算" in body
    # raw_out pretty-print 后还能找到原内容
    assert "patient" in body


def test_w81_user_list_filter_chips(client: Any) -> None:
    """用户列表有筛选 chip + 搜索框。"""
    resp = client.get("/users", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    body = resp.data.decode()
    for chip in ("全部", "冻结", "silence", "Lv≥2", "今日活跃"):
        assert chip in body, f"筛选 chip {chip!r} 缺失"
    assert "filter-text" in body  # 搜索框 id


def test_w81_net_probe_treats_4xx_as_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """net_probe 应该把 401/404 当作出网通(只要 TCP/HTTPS 可达)。"""
    health._NET_CACHE.clear()  # 清缓存
    from urllib.error import HTTPError

    def fake_urlopen(url: str, timeout: float = 5) -> Any:
        raise HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("wren.ops.health.urlopen", fake_urlopen)
    out = health.net_probe("test", "https://example.com/")
    assert out["ok"] is True
    assert out["code"] == 401


def test_w81_parse_relationship_real_format() -> None:
    """_parse_relationship 应该认 'level: 0' 真实 markdown 格式(不只是 'lv:')。"""
    from wren.ops.web import _parse_relationship

    text = "# Relationship State\n\nlevel: 3\nfreeze: false\n\n## prose\n\nyou ..."
    lv, freeze = _parse_relationship(text)
    assert lv == 3
    assert freeze is False

    text2 = "level: 0\nfreeze: true\n"
    lv2, freeze2 = _parse_relationship(text2)
    assert lv2 == 0
    assert freeze2 is True


def test_w81_strip_source_header() -> None:
    """source.md 第一行 # Source 头应被跳过,只取 value。"""
    from wren.ops.web import _strip_source_header

    text = "# Source (深链来源归因)\n\nsmoke\n"
    assert _strip_source_header(text) == "smoke"
    assert _strip_source_header("launch") == "launch"
    assert _strip_source_header("") == ""


def test_w81_tojson_pretty_filter() -> None:
    """tojson_pretty jinja filter 美化 JSON 字符串。"""
    raw = '{"level": 0, "prose": "you got pushy"}'
    pretty = web._tojson_pretty(raw)
    assert '"level": 0' in pretty
    assert "\n" in pretty  # 多行
    # 非 JSON 原样返回
    assert web._tojson_pretty("not json") == "not json"
