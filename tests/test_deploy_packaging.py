"""#13:deploy.sh 部署面 = allowlist by construction(`git archive HEAD`),
不再是 `--exclude` opt-out。

这里**不**真跑 rsync(没 VPS 访问),只验证:
1. `scripts/deploy.sh` 用 `git archive HEAD` 而不是直接 rsync `./`
2. `git archive HEAD` 输出不含 .env / .git / 未跟踪 WIP(.env / recap package / plan.md)
3. `git archive HEAD` 输出含必要产品代码(src/ / canon/ / compose.yaml / scripts/deploy.sh)
4. dirty working tree 时 deploy.sh fail fast(只静态扫脚本里有 `git diff --quiet HEAD`)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    """worktree 里的 repo 根。"""
    return Path(__file__).resolve().parent.parent


def _archive_listing() -> list[str]:
    """`git archive HEAD | tar -tf -` 输出的文件 / 目录列表。"""
    archive = subprocess.check_output(
        ["git", "archive", "HEAD"], cwd=_repo_root()
    )
    listing = subprocess.check_output(["tar", "-tf", "-"], input=archive)
    return listing.decode().splitlines()


def test_deploy_script_uses_git_archive_not_raw_rsync() -> None:
    """deploy.sh 必须走 git archive(allowlist),不是 `rsync -az ./` 直传(opt-out)。"""
    deploy = (_repo_root() / "scripts" / "deploy.sh").read_text()
    assert "git archive HEAD" in deploy, "deploy.sh 应该用 git archive HEAD 打包(#13)"
    # 不再有直接 rsync 当前目录:`./ root@` 这种 pattern
    assert "./ root@" not in deploy, (
        "deploy.sh 仍在直接 rsync `./` 到 VPS —— "
        "应该 rsync 临时 stage 目录($STAGE)而非工作树(#13)"
    )


def test_deploy_script_fails_fast_on_dirty_tree() -> None:
    """deploy.sh 必须在 working tree 有未 commit tracked 改动时 fail —— 否则
    git archive 漏掉本地改动会让"以为部署了 vs 实际部署了"对不上。"""
    deploy = (_repo_root() / "scripts" / "deploy.sh").read_text()
    assert "git diff --quiet HEAD" in deploy
    # 检测后必须 exit/return non-zero,不是只 warn
    assert "exit 1" in deploy


def test_git_archive_excludes_secrets_and_wip() -> None:
    """git archive HEAD 输出**绝对**不能含:
    - .env(secrets,gitignored 但仍可能 untracked 在本地)
    - .git/(metadata,不该 deploy)
    - tasks/wren_distribution_recap_package/(recap 素材包,~29M untracked)
    - tasks/distribution_assets/(同)
    - plan.md / tasks/distribution_log.md(WIP)
    """
    files = _archive_listing()
    forbidden_exact = {".env", "plan.md", "tasks/distribution_log.md"}
    forbidden_prefixes = (
        ".git/",
        "tasks/wren_distribution_recap_package/",
        "tasks/distribution_assets/",
    )
    for f in files:
        assert f not in forbidden_exact, f"git archive 含禁文件 {f!r}(#13)"
        for pre in forbidden_prefixes:
            assert not f.startswith(pre), f"git archive 含禁前缀 {f!r}(#13)"


def test_git_archive_includes_product_code() -> None:
    """git archive HEAD 必须含部署必要的产品代码 / 配置:
    - src/wren/ 整个包
    - canon/(关系 ground truth seed)
    - compose.yaml + Dockerfile(容器编排)
    - scripts/deploy.sh 自己(VPS 上也要能 self-deploy)
    """
    files = _archive_listing()
    required_exact = {
        "compose.yaml",
        "Dockerfile",
        "scripts/deploy.sh",
        "canon/backstory.md",
        "canon/voice_spec.md",
        "world/life_arcs.md",  # life-sim 种子(ARCHITECTURE §5)
    }
    for r in required_exact:
        assert r in files, f"git archive 缺产品文件 {r!r}(#13)"
    # src/wren/ 至少 1 个文件
    assert any(f.startswith("src/wren/") and f.endswith(".py") for f in files), (
        "git archive 缺 src/wren/ 产品包(#13)"
    )
