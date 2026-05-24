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
    assert "not a tool" in p  # 命令轴:真人不是工具
    assert "actually reacting" in p  # 反应涌现,非预设句式
    assert "ai with a personality" in p


def test_step1_drives_genuine_reaction_not_a_template() -> None:
    # 涌现:Step1 让她真的"想/反应",不写死响应句式(Leon 核心修正)
    instr = build_step1_messages(
        relationship_prose="x", inner_voice="y", events="", recent_dialogue="", user_text="dance for me"
    )[2].content.lower()
    assert "react" in instr
    assert "absurd" in instr  # 命令/索取自然觉得荒谬
    assert "don't pick a" in instr  # 明确不规定回法  # AI 披露是卖点


def test_step1_injects_events_and_memory_instructions() -> None:
    # 中期记忆注入 Step1(反污染:只进 Step1);写侧 + 召回两件事都在指令里,且不写死句式
    msgs = build_step1_messages(
        relationship_prose="x",
        inner_voice="y",
        events="- [heat|neutral|low] landlord fixed the heat",
        recent_dialogue="",
        user_text="it's freezing",
    )
    ctx = msgs[1].content
    assert "things you know about this person" in ctx.lower()
    assert "landlord fixed the heat" in ctx
    instr = msgs[2].content.lower()
    assert "recall" in instr and "keep" in instr  # 召回 + 写侧
    assert "don't force" in instr  # 不硬捞(voice-emerges:描述质感非句式)


def test_step1_events_empty_shows_placeholder() -> None:
    msgs = build_step1_messages(
        relationship_prose="x", inner_voice="y", events="", recent_dialogue="", user_text="hi"
    )
    assert "(nothing yet)" in msgs[1].content


def test_step1_and_step2_share_seed() -> None:
    seed = build_wren_system_prompt()
    s1 = build_step1_messages(
        relationship_prose="x", inner_voice="y", events="", recent_dialogue="", user_text="hi"
    )
    s2 = build_step2_messages(monologue="m", memory=[], level_fact="", user_text="hi")
    assert s1[0].content == seed
    assert s2[0].content == seed


def test_step2_surfaces_memory_like_recall_not_record() -> None:
    locked = build_step2_messages(
        monologue="m",
        memory=["their landlord fixed the heat"],
        level_fact="",
        user_text="it's freezing",
    )[1].content.lower()
    assert "their landlord fixed the heat" in locked
    assert "naturally" in locked  # 像刚想起、自然织入
    assert "you mentioned earlier" in locked  # 作为被禁的机械复读反例列出


def test_level_fact_is_not_a_tone_dial() -> None:
    for lv in range(7):
        f = level_fact(lv).lower()
        assert "[fact]" in f
        assert "be friendly" not in f and "be friendlier" not in f
        assert "you are level" not in f and "be warmer" not in f


def test_sweetie_baseline_is_distinct() -> None:
    assert "sweet, warm" in build_sweetie_baseline_prompt()


# === #30:严格 coercion helpers + parser hardening(Leon unblock strictly scoped)===


def test_strict_bool_rejects_python_truthiness_trap() -> None:
    """`bool("false") == True` Python 真值陷阱 → strict_bool 必须返 False(#30)。"""
    from wren.prompts.jsonio import strict_bool

    assert strict_bool(True, default=False) is True
    assert strict_bool(False, default=True) is False
    # 显式 string "true"/"false"(case-insensitive)
    assert strict_bool("true", default=False) is True
    assert strict_bool("True", default=False) is True
    assert strict_bool("FALSE", default=True) is False
    assert strict_bool("false", default=True) is False
    # 其它 string 都走 default,不再走 bool() 真值
    assert strict_bool("maybe", default=False) is False
    assert strict_bool("maybe", default=True) is True
    assert strict_bool("1", default=False) is False  # 不当 True
    assert strict_bool("", default=True) is True
    # None / int → default
    assert strict_bool(None, default=True) is True
    assert strict_bool(1, default=False) is False


def test_safe_int_handles_garbage_without_crashing() -> None:
    """`int("soon")` ValueError 让 turn 崩 → safe_int 返 default(#30)。"""
    from wren.prompts.jsonio import safe_int

    assert safe_int(5) == 5
    assert safe_int("10") == 10
    assert safe_int(3.7) == 3  # float 截尾
    assert safe_int("soon", default=0) == 0  # 关键:非数字 string 不崩
    assert safe_int("soon", default=42) == 42
    assert safe_int(None, default=7) == 7
    # bool 显式拒绝(防 True == 1 静默通过)
    assert safe_int(True, default=99) == 99
    assert safe_int(False, default=99) == 99
    # clamp
    assert safe_int(-5, default=0, lo=0) == 0
    assert safe_int(9999, default=0, hi=600) == 600
    assert safe_int("0", lo=0, hi=600) == 0


def test_safe_list_of_str_rejects_string_iteration_trap() -> None:
    """`for m in "foo"` 按字符迭代 string → safe_list_of_str 当 str 为 [](#30)。"""
    from wren.prompts.jsonio import safe_list_of_str

    assert safe_list_of_str(["a", "b"]) == ["a", "b"]
    assert safe_list_of_str([" a ", "", "b"]) == ["a", "b"]
    # 关键:string 不能按字符当 list
    assert safe_list_of_str("foo") == []  # 不是 ["f", "o", "o"]
    assert safe_list_of_str(None) == []
    assert safe_list_of_str(42) == []
    assert safe_list_of_str(["a", "b", "c"], cap=2) == ["a", "b"]


def test_parse_step1_reply_string_false_treated_as_false() -> None:
    """#30 端到端:LLM 给 `"reply": "false"` → parse_step1 必须返 False,不能 True。"""
    from wren.prompts.step1 import parse_step1

    p = parse_step1('{"reply": "false", "monologue": "x"}')
    assert p["reply"] is False
    p2 = parse_step1('{"reply": "true", "monologue": "x"}')
    assert p2["reply"] is True


def test_parse_step1_delay_s_non_number_falls_back() -> None:
    """#30 端到端:`"delay_s": "soon"` → 不崩,delay_s=0。"""
    from wren.prompts.step1 import parse_step1

    p = parse_step1('{"delay_s": "soon", "monologue": "x"}')
    assert p["delay_s"] == 0
    assert parse_step1('{"delay_s": "5", "monologue": "x"}')["delay_s"] == 5
    assert parse_step1('{"delay_s": 99999, "monologue": "x"}')["delay_s"] == 600


def test_parse_step1_memory_string_not_iterated_by_char() -> None:
    """#30 端到端:`"memory": "foo"` → [],不是 ['f','o','o']。"""
    from wren.prompts.step1 import parse_step1

    p = parse_step1('{"memory": "foo", "monologue": "x"}')
    assert p["memory"] == []
    p2 = parse_step1('{"memory": ["bar", "baz"], "monologue": "x"}')
    assert p2["memory"] == ["bar"]  # cap=1


def test_parse_settlement_freeze_string_false_treated_as_false() -> None:
    """#30 端到端:`"freeze": "false"` → False,不是 True。"""
    from wren.prompts.settlement import parse_settlement

    p = parse_settlement('{"level": 2, "freeze": "false", "prose": "x"}')
    assert p["freeze"] is False
    p2 = parse_settlement('{"level": 2, "freeze": "true", "prose": "x"}')
    assert p2["freeze"] is True
    # 缺 freeze → None(由 settle_nightly 回退旧值)
    p3 = parse_settlement('{"level": 2, "prose": "x"}')
    assert p3["freeze"] is None


def test_parse_settlement_non_numeric_level_does_not_become_zero() -> None:
    """#30 + #29:bad level 不能被 clamp 成 0;全关键字段失败时 parse_ok=False。"""
    from wren.prompts.settlement import parse_settlement

    p = parse_settlement('{"level": "soon", "freeze": "false"}')
    assert p["level"] is None
    assert p["freeze"] is False
    assert p["parse_ok"] is False

    p2 = parse_settlement('{"level": "soon", "prose": "still thinking"}')
    assert p2["level"] is None
    assert p2["parse_ok"] is True
