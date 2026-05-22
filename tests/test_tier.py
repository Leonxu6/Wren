"""W7 付费档 seam(gate-key,非积分):read_tier 默认 premium;write_tier 只认 premium/free。

订阅日后接:支付 webhook → write_tier;free 在 core/proactive 短路成 0(见 test_proactive_scheduler)。
"""

from __future__ import annotations

from pathlib import Path

from wren.core.storage import UserStore


def test_tier_default_premium(data_root: Path) -> None:
    s = UserStore("u")
    s.init_user()
    assert s.read_tier() == "premium"  # v1 全员免费开放 = 默认 premium


def test_tier_write_read(data_root: Path) -> None:
    s = UserStore("u")
    s.init_user()
    s.write_tier("free")
    assert s.read_tier() == "free"
    s.write_tier("premium")
    assert s.read_tier() == "premium"


def test_tier_rejects_garbage(data_root: Path) -> None:
    s = UserStore("u")
    s.init_user()
    s.write_tier("enterprise")
    assert s.read_tier() == "premium"  # 只认 premium/free,其他回退 premium
