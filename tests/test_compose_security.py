"""#22:`compose.yaml` 的 viewer 服务**不能**直接挂 `/var/run/docker.sock`。

`:ro` 只防文件系统写,不约束 Docker API 动词;一旦 viewer compromise,blast radius
会从"读 ops 数据"扩到"宿主 Docker 控制面"。
`container_status()` 已在 socket 不存在时 fail-safe 返回 "unknown"(见
`test_container_status_failsafe`),dashboard 仍可渲染。
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _compose() -> dict:  # type: ignore[type-arg]
    path = Path(__file__).resolve().parent.parent / "compose.yaml"
    return yaml.safe_load(path.read_text())


def test_viewer_does_not_mount_docker_socket() -> None:
    """关键安全断言:viewer 服务 volumes 不能含 `/var/run/docker.sock`(#22)。"""
    services = _compose().get("services", {})
    viewer = services.get("viewer", {})
    volumes = viewer.get("volumes", [])
    assert volumes, "viewer 服务必须有 volumes 块"
    for v in volumes:
        # docker-compose volume 字符串形式 "src:dst[:flag]"
        src = v.split(":", 1)[0] if isinstance(v, str) else v.get("source", "")
        assert "docker.sock" not in src, (
            f"viewer 不应挂 docker socket(#22):{v!r}。"
            f"若需容器状态,走 docker-socket-proxy sidecar。"
        )


def test_no_service_mounts_docker_socket() -> None:
    """整个 compose 都不该有任何服务挂 docker.sock —— 不是只 viewer 的问题,
    bot / metrics 服务一旦被利用 + 拿到 docker.sock = 同样的宿主控制面升级。"""
    services = _compose().get("services", {})
    assert services, "compose.yaml 必须有 services 块"
    for name, svc in services.items():
        for v in svc.get("volumes") or []:
            src = v.split(":", 1)[0] if isinstance(v, str) else v.get("source", "")
            assert "docker.sock" not in src, (
                f"服务 {name} 不应挂 docker socket(#22):{v!r}"
            )
