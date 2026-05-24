"""#21:生产 bot 入口 fail fast —— 无 WREN_API_KEY 且未显式 WREN_FAKE_MODEL=1 → raise。

避免 .env 漏填 / 部署变量丢失时 bot 静默退化到 fake 模式,显示"启动成功" 假阳信号。
"""

from __future__ import annotations

import pytest

from wren.bot.app import require_real_api_key_unless_fake


def test_require_raises_when_no_key_and_no_fake_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """关键路径:无 WREN_API_KEY + 未启用 WREN_FAKE_MODEL → 必须 raise。

    否则 bot 启动成功 + 调度已挂,但真实对话全沉默 —— 是公开宣传链接阶段
    的"错误上线信号"(#21)。
    """
    monkeypatch.delenv("WREN_API_KEY", raising=False)
    monkeypatch.delenv("WREN_FAKE_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="WREN_API_KEY"):
        require_real_api_key_unless_fake()


def test_require_allows_explicit_fake_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """显式 WREN_FAKE_MODEL=1 → 允许通过(本地演示 / 离线),但打 warning。"""
    monkeypatch.delenv("WREN_API_KEY", raising=False)
    monkeypatch.setenv("WREN_FAKE_MODEL", "1")
    require_real_api_key_unless_fake()  # 不抛
    out = capsys.readouterr().out
    assert "WREN_FAKE_MODEL=1" in out  # 有警告留痕
    assert "生产绝不该看到" in out  # 醒目提示


def test_require_allows_real_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有真实 WREN_API_KEY → 不抛(正常生产路径)。"""
    monkeypatch.delenv("WREN_FAKE_MODEL", raising=False)
    monkeypatch.setenv("WREN_API_KEY", "sk-real-key-xyz")
    require_real_api_key_unless_fake()  # 不抛


def test_require_real_key_wins_over_fake_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """有真实 key 时不需 fake flag(走第一分支,不打 warning)。"""
    monkeypatch.setenv("WREN_API_KEY", "sk-real-key-xyz")
    monkeypatch.setenv("WREN_FAKE_MODEL", "1")  # 同时存在
    require_real_api_key_unless_fake()
    out = capsys.readouterr().out
    assert out == ""  # has_api_key 早 return,fake warning 不打
