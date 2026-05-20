"""registry env 切换 + 候选清单(DeepSeek 必含)。"""

from __future__ import annotations

import json

import pytest

from wren import config
from wren.model import get_model, list_candidates
from wren.model.fake import FakeChatModel
from wren.model.openai_compat import OpenAICompatModel


def test_no_key_returns_fake() -> None:
    # autouse fixture 已设 WREN_FAKE_MODEL=1 且删 key
    assert isinstance(get_model("primary"), FakeChatModel)
    assert isinstance(get_model("judge"), FakeChatModel)


def test_with_key_returns_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WREN_FAKE_MODEL", raising=False)
    monkeypatch.setenv("WREN_API_KEY", "sk-test-not-real")
    model = get_model("primary")
    assert isinstance(model, OpenAICompatModel)  # 仅构造,不发网络
    assert model.name == "primary"


def test_default_candidates_include_deepseek() -> None:
    names = {c.model for c in list_candidates()}
    assert "deepseek-v4-flash" in names  # 头号风险:便宜候选必含


def test_candidates_overridable_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "WREN_CANDIDATES",
        json.dumps([{"name": "x", "model": "custom-model", "base_url": "https://example.com"}]),
    )
    assert [c.model for c in list_candidates()] == ["custom-model"]


def test_empty_judge_base_url_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """回归:.env 里空串 WREN_JUDGE_BASE_URL= 必须回退到 deepseek,不能停在 ''(否则连不上)。"""
    monkeypatch.setenv("WREN_JUDGE_BASE_URL", "")
    monkeypatch.setenv("WREN_BASE_URL", "https://api.deepseek.com")
    assert config.judge_model_spec().base_url == "https://api.deepseek.com"


def test_empty_model_envs_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("WREN_MODEL", "WREN_JUDGE_MODEL", "WREN_BASE_URL", "WREN_JUDGE_BASE_URL"):
        monkeypatch.setenv(k, "")
    assert config.primary_model_spec().model == "deepseek-v4-flash"
    assert config.primary_model_spec().base_url == "https://api.deepseek.com"
    assert config.judge_model_spec().model == "deepseek-v4-pro"
    assert config.judge_model_spec().base_url == "https://api.deepseek.com"
