"""prompt 验收:反谄媚两轴显式立、Step1/Step2 复用同一种子、level 不当语气旋钮。"""

from __future__ import annotations

from wren.core.step2 import level_fact
from wren.prompts.step1 import build_step1_messages
from wren.prompts.step2 import build_step2_messages
from wren.prompts.system import build_sweetie_baseline_prompt, build_wren_system_prompt


def test_system_prompt_has_anti_sycophancy_anchors() -> None:
    p = build_wren_system_prompt().lower()
    assert "not an assistant" in p
    assert "earned" in p
    assert "you say so" in p  # 她有自己观点
    assert "lol no" in p  # in-voice 拒绝示例(非机器拒)
    assert "ai with a personality" in p  # AI 披露是卖点


def test_step1_and_step2_share_seed() -> None:
    seed = build_wren_system_prompt()
    s1 = build_step1_messages(
        relationship_prose="x", inner_voice="y", recent_dialogue="", user_text="hi"
    )
    s2 = build_step2_messages(monologue="m", memory=[], level_fact="", user_text="hi")
    assert s1[0].content == seed
    assert s2[0].content == seed


def test_level_fact_is_not_a_tone_dial() -> None:
    for lv in range(7):
        f = level_fact(lv).lower()
        assert "[fact]" in f
        assert "be friendly" not in f and "be friendlier" not in f
        assert "you are level" not in f and "be warmer" not in f


def test_sweetie_baseline_is_distinct() -> None:
    assert "sweet, warm" in build_sweetie_baseline_prompt()
