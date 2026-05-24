"""#36:backup.sh 默认 umask 077 防同机偷读;--encrypt 走 openssl/age 让异地副本
不再是明文 data/users + inner voice + chat_id 离机。
"""

from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _backup_sh() -> Path:
    return _repo_root() / "scripts" / "backup.sh"


def _seed_app(tmp_path: Path) -> tuple[Path, Path]:
    """造一个 fake app_dir(data/users/ + world/)+ 一个 fake backup_dest。"""
    app = tmp_path / "app"
    (app / "data" / "users" / "999").mkdir(parents=True)
    (app / "data" / "users" / "999" / "x.md").write_text("SECRET-USER-DATA")
    (app / "world").mkdir()
    (app / "world" / "today.md").write_text("today")
    dest = tmp_path / "dest"
    return app, dest


def _run(app: Path, dest: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["WREN_APP_DIR"] = str(app)
    env["WREN_BACKUP_DIR"] = str(dest)
    env["WREN_BACKUP_KEEP"] = "14"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(_backup_sh()), *args],
        capture_output=True, text=True, env=env, timeout=15,
    )


def test_plain_backup_file_mode_is_root_only(tmp_path: Path) -> None:
    """#36 防御性:即使默认明文 .tgz,文件权限也必须 0600(umask 077)。
    防同机其他用户读到原始聊天 / inner voice / chat_id。"""
    app, dest = _seed_app(tmp_path)
    proc = _run(app, dest)
    assert proc.returncode == 0, proc.stderr
    backups = list(dest.glob("wren-*.tgz"))
    assert len(backups) == 1
    mode = backups[0].stat().st_mode & 0o777
    assert mode == 0o600, f"明文 backup 必须 0600(umask 077),实际 {oct(mode)}"


def test_encrypted_backup_with_passphrase(tmp_path: Path) -> None:
    """#36 核心:--encrypt + WREN_BACKUP_PASSPHRASE → openssl AES-256-CBC + PBKDF2,
    产物 .tgz.age,**异地能 cp 出去也不是明文**。"""
    app, dest = _seed_app(tmp_path)
    proc = _run(app, dest, "--encrypt", env_extra={"WREN_BACKUP_PASSPHRASE": "test-pass-123"})
    assert proc.returncode == 0, proc.stderr
    encrypted = list(dest.glob("wren-*.tgz.age"))
    assert len(encrypted) == 1, "应产生 .tgz.age 加密产物"
    # 文件不是明文 tar(magic bytes 应该是 openssl Salted__,不是 gzip 1f 8b)
    head = encrypted[0].read_bytes()[:8]
    assert head.startswith(b"Salted__"), f"openssl 产物应以 Salted__ 开头,实际 {head!r}"
    assert head[:2] != b"\x1f\x8b", "**不应**是 gzip magic(那就是明文 tar.gz)"


def test_encrypted_backup_roundtrips(tmp_path: Path) -> None:
    """end-to-end:openssl 解密 + tar 解包应能完整还原原 SECRET-USER-DATA。
    防回归:加密链路没把内容搞坏。"""
    app, dest = _seed_app(tmp_path)
    proc = _run(app, dest, "--encrypt", env_extra={"WREN_BACKUP_PASSPHRASE": "test-pass-123"})
    assert proc.returncode == 0

    encrypted = next(dest.glob("wren-*.tgz.age"))
    decrypted_tgz = tmp_path / "decrypted.tgz"
    subprocess.run(
        [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
            "-pass", "pass:test-pass-123",
            "-in", str(encrypted), "-out", str(decrypted_tgz),
        ],
        check=True, capture_output=True,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with tarfile.open(decrypted_tgz, "r:gz") as tar:
        tar.extractall(out_dir, filter="data")  # py 3.12+ tar 安全 filter
    secret = (out_dir / "data" / "users" / "999" / "x.md").read_text()
    assert secret == "SECRET-USER-DATA", "round-trip 应原样还原"


def test_encrypt_without_passphrase_or_recipient_fails(tmp_path: Path) -> None:
    """`--encrypt` 但既没 WREN_BACKUP_PASSPHRASE 也没 --encrypt-to → fail fast,
    防"以为加密了实际啥都没做"。"""
    app, dest = _seed_app(tmp_path)
    # 清掉环境里可能存在的 passphrase
    env_extra = {"WREN_BACKUP_PASSPHRASE": ""}
    proc = _run(app, dest, "--encrypt", env_extra=env_extra)
    assert proc.returncode != 0
    assert "需要" in proc.stderr or "encrypt-to" in proc.stderr
    assert not list(dest.glob("wren-*.tgz.age")), "fail 时不该留下任何加密产物"


def test_unknown_flag_exits_nonzero(tmp_path: Path) -> None:
    """未知 flag → exit 2,不留产物。"""
    app, dest = _seed_app(tmp_path)
    proc = _run(app, dest, "--unknown")
    assert proc.returncode == 2
    assert "未知参数" in proc.stderr
    assert not list(dest.glob("wren-*")), "fail 时不该留下任何产物"


def test_runbook_offsite_rsync_only_matches_encrypted_artifact() -> None:
    """#36 PR review followup:RUNBOOK 的 offsite rsync 必须**只匹配 .tgz.age**,
    不能含让明文 .tgz 离机的 pattern。"""
    runbook = (_repo_root() / "docs" / "RUNBOOK.md").read_text()
    # 必须 include 加密产物
    assert "wren-*.tgz.age" in runbook, (
        "RUNBOOK offsite rsync 应 include 加密 wren-*.tgz.age(#36)"
    )
    # 整段(找含 rsync /srv/wren-backups 的行)不应不带 --include 限制
    # 简单 heuristic:含 rsync /srv/wren-backups 但同行没 .tgz.age 限制 = 危险
    for line in runbook.splitlines():
        if "rsync" in line and "wren-backups" in line:
            assert ".tgz.age" in line or "--include=" in line, (
                f"RUNBOOK 含无限制的 offsite rsync:`{line.strip()}`(#36)"
            )


def test_runbook_cron_backup_uses_encrypt_flag() -> None:
    """#36 PR review followup:RUNBOOK 的 cron 命令必须用 --encrypt,
    不能裸跑 backup.sh 输出明文 .tgz 再 offsite。"""
    runbook = (_repo_root() / "docs" / "RUNBOOK.md").read_text()
    # 找含 backup.sh 的 cron line
    for line in runbook.splitlines():
        if "backup.sh" in line and "* * *" in line:
            assert "--encrypt" in line, (
                f"RUNBOOK cron 命令必须带 --encrypt(#36):`{line.strip()}`"
            )


def test_maintenance_acknowledges_encrypted_backup_artifacts() -> None:
    """#36 PR review followup:MAINTENANCE 描述备份目录时必须提 .tgz.age 加密产物。"""
    maint = (_repo_root() / "MAINTENANCE.md").read_text()
    assert "wren-backups/" in maint
    # 描述备份目录的段落附近必须出现 .tgz.age
    assert "tgz.age" in maint, (
        "MAINTENANCE 描述 wren-backups/ 时未提加密 .tgz.age 产物(#36)"
    )
