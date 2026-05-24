"""#24:metrics 容器不能用 `|| true` 永久吞失败 → 让 ingest 静默陈旧而容器仍 running。

修后应该:连续 N 次失败 → exit 1(让 restart 形成信号);+ healthcheck 基于 DB mtime
作为另一层。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


def _compose() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "compose.yaml").read_text()
    )


def _metrics_command_text() -> str:
    cmd = _compose()["services"]["metrics"]["command"]
    # docker compose `command` 可以是 list ["sh", "-c", "..."] 或 str
    if isinstance(cmd, list):
        return "\n".join(str(x) for x in cmd)
    return str(cmd)


def test_metrics_command_does_not_silently_swallow_failures() -> None:
    """#24 核心:`|| true` 模式被禁(让 ingest 永久 running 而 DB 不更新)。"""
    text = _metrics_command_text()
    assert "|| true" not in text, (
        "metrics 不能 `|| true` 吞 ingest 失败(#24);改为连续失败 N 次后 exit 1"
    )


def test_metrics_command_exits_after_consecutive_failures() -> None:
    """命令文本应含连续失败计数 + exit 1 的处理逻辑。"""
    text = _metrics_command_text()
    # 失败计数器
    assert "fail=" in text or "FAIL=" in text, "应有失败计数变量"
    # 累加
    assert "fail+1" in text or "FAIL+1" in text, "应累加失败计数"
    # 阈值后 exit
    assert "exit 1" in text, "失败阈值后应 exit 1(触发 restart: always 暴露问题)"


def test_metrics_has_healthcheck_based_on_db_freshness() -> None:
    """#24 推荐:healthcheck 基于 metrics.duckdb mtime 判断 stale。"""
    metrics = _compose()["services"]["metrics"]
    hc = metrics.get("healthcheck")
    assert hc is not None, "metrics 服务必须有 healthcheck(#24)"
    test_cmd = hc.get("test")
    assert test_cmd, "healthcheck.test 不能空"
    # 实际跑的命令应该引用 metrics.duckdb
    test_str = " ".join(test_cmd) if isinstance(test_cmd, list) else str(test_cmd)
    assert "metrics.duckdb" in test_str, "healthcheck 应基于 metrics.duckdb mtime"
    # start_period 给首次 ingest 留宽限,避免容器一启动就 unhealthy
    assert "start_period" in hc, "healthcheck 需要 start_period 给首次 ingest 宽限(否则启动即 unhealthy)"


def test_metrics_shell_snippet_is_valid_bash() -> None:
    """实际跑 `bash -n` 验证 sh -c 后面的脚本片段语法正确。"""
    cmd = _compose()["services"]["metrics"]["command"]
    assert isinstance(cmd, list) and cmd[:2] == ["sh", "-c"], (
        "metrics command 必须是 list 形式 ['sh', '-c', <script>]"
    )
    snippet = cmd[2]
    proc = subprocess.run(
        ["bash", "-n"],
        input=snippet,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0, f"shell snippet 语法错:{proc.stderr}"
