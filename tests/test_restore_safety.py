"""#27:restore.sh 默认 staging(不碰 live),live 需显式 flag,归档结构强校验。
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _restore_sh() -> Path:
    return _repo_root() / "scripts" / "restore.sh"


def _good_archive(tmp_path: Path) -> Path:
    """造一个合法 archive(只含 data/ + world/ 相对路径)。"""
    src = tmp_path / "src"
    (src / "data" / "users" / "123").mkdir(parents=True)
    (src / "data" / "users" / "123" / "x.md").write_text("hi")
    (src / "world").mkdir()
    (src / "world" / "life_arcs.md").write_text("seed")
    archive = tmp_path / "backup.tgz"
    subprocess.run(
        ["tar", "czf", str(archive), "data", "world"], cwd=src, check=True
    )
    return archive


def _bad_archive_traversal(tmp_path: Path) -> Path:
    """造一个含 ../ 穿越的恶意 archive。"""
    src = tmp_path / "src"
    src.mkdir()
    # 直接用 python tar 构造,因为 shell tar 会拒绝 ../
    archive = tmp_path / "bad.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(name="data/../etc/passwd")
        info.size = 0
        tar.addfile(info)
    return archive


def _bad_archive_absolute(tmp_path: Path) -> Path:
    """造一个含绝对路径的恶意 archive。"""
    archive = tmp_path / "abs.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(name="/etc/wren-evil")
        info.size = 0
        tar.addfile(info)
    return archive


def _bad_archive_wrong_toplevel(tmp_path: Path) -> Path:
    """造一个顶层不是 data/ 也不是 world/ 的 archive。"""
    src = tmp_path / "src"
    (src / "system" / "bin").mkdir(parents=True)
    (src / "system" / "bin" / "evil.sh").write_text("oops")
    archive = tmp_path / "wrong.tgz"
    subprocess.run(["tar", "czf", str(archive), "system"], cwd=src, check=True)
    return archive


def _run(archive: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_restore_sh()), str(archive), *args],
        capture_output=True,
        text=True,
        cwd=cwd or _repo_root(),
        timeout=15,
    )


def test_restore_default_is_staging_not_live(tmp_path: Path) -> None:
    """**核心**:不传 --live → 默认 staging 解到 tmp 目录,绝不碰 /srv/wren(#27)。"""
    archive = _good_archive(tmp_path)
    proc = _run(archive)
    assert proc.returncode == 0, f"staging 应成功:\n{proc.stderr}"
    assert "staging 模式" in proc.stdout
    assert "/srv/wren" not in proc.stdout  # 默认输出不该提到 live 目标


def test_restore_explicit_staging_target(tmp_path: Path) -> None:
    """`--staging <dir>` 显式 staging 路径。"""
    archive = _good_archive(tmp_path)
    target = tmp_path / "stage"
    proc = _run(archive, "--staging", str(target))
    assert proc.returncode == 0, proc.stderr
    assert (target / "data" / "users" / "123" / "x.md").exists()
    assert (target / "world" / "life_arcs.md").exists()


def test_restore_rejects_traversal_archive(tmp_path: Path) -> None:
    """归档含 `../` → 拒绝,exit 非零,**不解压**(#27 路径穿越防御)。"""
    archive = _bad_archive_traversal(tmp_path)
    proc = _run(archive)
    assert proc.returncode != 0
    assert "穿越" in proc.stderr or "穿越" in proc.stdout


def test_restore_rejects_absolute_path_archive(tmp_path: Path) -> None:
    """归档含绝对路径(/etc/...) → 拒绝。"""
    archive = _bad_archive_absolute(tmp_path)
    proc = _run(archive)
    assert proc.returncode != 0


def test_restore_rejects_unexpected_toplevel(tmp_path: Path) -> None:
    """归档顶层不是 data/ 或 world/ → 拒绝(防意外内容覆盖)。"""
    archive = _bad_archive_wrong_toplevel(tmp_path)
    proc = _run(archive)
    assert proc.returncode != 0
    assert "unexpected-toplevel" in proc.stderr or "结构不合法" in proc.stderr


def test_restore_unknown_flag_exits_nonzero(tmp_path: Path) -> None:
    """未知参数 → exit 2,不执行恢复。"""
    archive = _good_archive(tmp_path)
    proc = _run(archive, "--unknown")
    assert proc.returncode == 2
    assert "未知参数" in proc.stderr


def test_restore_smoke_reports_user_count(tmp_path: Path) -> None:
    """smoke check 报告 users 计数(部署演练要看到这一行)。"""
    archive = _good_archive(tmp_path)
    target = tmp_path / "stage"
    proc = _run(archive, "--staging", str(target))
    assert proc.returncode == 0
    assert "users:" in proc.stdout
    assert "1" in proc.stdout  # 我们造的 archive 有 1 个用户

    # --- 双用户 archive,确认 count 是 2 ---
    src2 = tmp_path / "src2"
    (src2 / "data" / "users" / "111").mkdir(parents=True)
    (src2 / "data" / "users" / "222").mkdir(parents=True)
    (src2 / "world").mkdir()
    (src2 / "world" / "life_arcs.md").write_text("seed")
    archive2 = tmp_path / "b2.tgz"
    subprocess.run(["tar", "czf", str(archive2), "data", "world"], cwd=src2, check=True)
    target2 = tmp_path / "stage2"
    proc2 = _run(archive2, "--staging", str(target2))
    assert proc2.returncode == 0
    assert "users:    2" in proc2.stdout


def test_docs_do_not_show_stale_positional_restore_examples() -> None:
    """#27 PR review followup: MAINTENANCE.md / docs/RUNBOOK.md 不该再有旧 positional
    restore 命令(本 PR 后旧 `restore.sh ... /srv/wren` 会被 unknown-arg fail)。

    Stale 信号 = 旧 incident-runbook 教错命令,运维真灾时跑了直接 exit 2。
    """
    for doc in ("MAINTENANCE.md", "docs/RUNBOOK.md"):
        text = (_repo_root() / doc).read_text()
        # 旧 positional 模式:`restore.sh <archive> /srv/wren`(live 位置参数)
        # 旧 positional 模式:`restore.sh <archive> /tmp/...`(staging 位置参数)
        # 新模式必须显式 `--live` 或 `--staging <dir>`
        import re
        bad = re.findall(
            r"restore\.sh\s+[^\s]+\s+/(?:srv/wren\b|tmp/restore-check)",
            text,
        )
        assert not bad, (
            f"{doc} 仍含旧 positional restore 命令(PR #41 reviewer 要求清理):{bad}"
        )


def test_live_restore_docs_mention_stop_services() -> None:
    """#27 PR review followup: live restore 必须配 docker compose stop 提示
    (本 PR 不主动 stop services,但 runbook 必须教 ops 先停服,否则 race)。"""
    for doc in ("MAINTENANCE.md", "docs/RUNBOOK.md"):
        text = (_repo_root() / doc).read_text()
        # 找含 `--live` 的段落,附近(同段落内)应该有 docker compose stop 提示
        if "--live" not in text:
            continue
        # 简单 heuristic:`--live` 出现的同时,文档某处也提了 `docker compose stop`
        assert "docker compose stop" in text, (
            f"{doc} 提到 --live 但缺 `docker compose stop` 停服提示(PR #41 reviewer)"
        )


@pytest.fixture(autouse=True)
def _cleanup_staging_tmp() -> None:
    """staging 默认调用 mktemp 在 OS tmp 区(macOS /var/folders;Linux /tmp),
    不在 pytest tmp_path 下;test 退出时手动清掉,避免长期累积。"""
    yield
    import tempfile
    for p in Path(tempfile.gettempdir()).glob("wren-restore-*"):
        shutil.rmtree(p, ignore_errors=True)
