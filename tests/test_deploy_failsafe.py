"""#23:deploy.sh 必须在远端 rebuild 失败时退出非零,不能因 `| tail` 把 ssh 的
非零 exit code 给吞掉 → 误报"部署完成"。

静态测 + 行为测(用 bash 直接跑脚本片段)。不真跑 ssh / rsync。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _deploy_text() -> str:
    return (_repo_root() / "scripts" / "deploy.sh").read_text()


def test_deploy_uses_pipefail_not_just_set_e() -> None:
    """`set -e` 单独不够:`false | tail -10` 在 pipefail 关时整体 exit 0 → 失败被吞(#23)。"""
    text = _deploy_text()
    assert "set -euo pipefail" in text, (
        "deploy.sh 必须 set -euo pipefail —— 否则 ssh ... | tail 吞失败(#23)"
    )


def test_deploy_validates_service_arg() -> None:
    """SERVICE 必须有 allowlist 校验,不能把意外字符串拼进 docker compose 命令(#23)。"""
    text = _deploy_text()
    assert "bot|metrics|viewer|all" in text


def test_deploy_does_not_pipe_ssh_rebuild_to_tail_naively() -> None:
    """旧 pattern `ssh ... up -d --build ... | tail -N` 让 tail 的 0 覆盖 ssh 的非零(#23)。
    新 pattern 应是显式捕获 → 失败 → tail + exit。"""
    text = _deploy_text()
    # 不再有 `up -d --build ...' | tail` 或 `up -d --build $SERVICE" | tail` 这种 naive 写法
    assert "up -d --build' | tail" not in text
    assert 'up -d --build $SERVICE" | tail' not in text
    # 应该有显式失败处理
    assert "✗ 远端 rebuild 失败" in text or "rebuild 失败" in text


def test_deploy_invalid_service_arg_exits_nonzero() -> None:
    """实际跑 bash 验证:SERVICE 非 allowlist 值时,deploy.sh 立即非零退出,
    **不进 step 1**(三件套是慢的,不能让 bad arg 跑过去才发现)。"""
    proc = subprocess.run(
        ["bash", str(_repo_root() / "scripts" / "deploy.sh"), "badservice"],
        capture_output=True,
        text=True,
        cwd=_repo_root(),
        timeout=10,
    )
    assert proc.returncode != 0, "invalid SERVICE 必须非零 exit"
    assert "SERVICE 必须是" in proc.stderr
    # 没进 step 1(没跑 pytest 等)
    assert "本机离线门" not in proc.stdout
    assert "本机离线门" not in proc.stderr


def test_pipefail_actually_catches_pipeline_middle_failure() -> None:
    """sanity:验证 bash `set -euo pipefail` 确实让 `false | tail` 整体失败。
    若哪天 bash 行为变了,这条会红 —— 我们的修复假设就坏了。"""
    proc = subprocess.run(
        ["bash", "-c", "set -euo pipefail; false | tail -10; echo MARK"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode != 0
    assert "MARK" not in proc.stdout
