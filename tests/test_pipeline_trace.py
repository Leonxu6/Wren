"""pipeline + trace(p1-trace):回复轮落完整 trace、沉默轮 step2=null、inner_voice 更新。"""

from __future__ import annotations

import json
from pathlib import Path

from wren.core.pipeline import compute_pacing, handle_turn
from wren.core.storage import UserStore
from wren.core.trace import read_traces
from wren.model.fake import FakeChatModel

_S1_REPLY = json.dumps(
    {
        "monologue": "let's see what they've got",
        "reply": True,
        "delay_s": 6,
        "impression": "noticed the small painting",
        "memory": [],
    }
)
_S1_SILENT = json.dumps(
    {"monologue": "ugh", "reply": False, "delay_s": 0, "impression": "", "memory": []}
)
_S2 = json.dumps({"messages": ["ha", "the wine was bad though", "which one were you"]})
_S1_REPLY_EVENT = json.dumps(
    {
        "monologue": "ok the heat thing",
        "reply": True,
        "delay_s": 4,
        "impression": "",
        "memory": [],
        "event": {"text": "landlord fixed the heat", "topic": "heat", "valence": "neutral", "salience": "low"},
    }
)
_S1_SILENT_EVENT = json.dumps(
    {
        "monologue": "spam, ignore",
        "reply": False,
        "delay_s": 0,
        "impression": "",
        "memory": [],
        "event": {"text": "their sister is visiting", "topic": "sister", "valence": "neutral", "salience": "med"},
    }
)


def test_reply_turn_writes_full_trace(data_root: Path) -> None:
    s = UserStore("100", data_root)
    s.init_user()
    out = handle_turn(
        "100",
        "you were at theo's show right",
        s,
        FakeChatModel(script=[_S1_REPLY]),
        FakeChatModel(script=[_S2]),
    )
    assert out.replied and out.bubbles[0] == "ha"
    traces = read_traces(s.dir)
    assert len(traces) == 1
    t = traces[0]
    assert t["step2"] is not None
    assert t["sent"]["bubbles"] == out.bubbles
    assert t["step1"]["reply"] is True
    assert t["relationship"]["lv"] == 0
    assert t["turn_id"] == "100-1"


def test_silence_turn_writes_trace_with_null_step2(data_root: Path) -> None:
    s = UserStore("101", data_root)
    s.init_user()
    out = handle_turn(
        "101", "hey gorgeous", s, FakeChatModel(script=[_S1_SILENT]), FakeChatModel(script=[_S2])
    )
    assert not out.replied and out.bubbles == []
    t = read_traces(s.dir)[0]
    assert t["step2"] is None and t["sent"] is None
    assert t["step1"]["reply"] is False


def test_inner_voice_updated_after_turn(data_root: Path) -> None:
    s = UserStore("102", data_root)
    s.init_user()
    handle_turn("102", "hi", s, FakeChatModel(script=[_S1_REPLY]), FakeChatModel(script=[_S2]))
    assert "let's see what they've got" in s.read_inner_voice()


def test_event_persisted_and_traced(data_root: Path) -> None:
    s = UserStore("103", data_root)
    s.init_user()
    handle_turn(
        "103", "landlord finally fixed the heat", s,
        FakeChatModel(script=[_S1_REPLY_EVENT]), FakeChatModel(script=[_S2]),
    )
    evs = s.read_event_list()
    assert len(evs) == 1 and evs[0].topic == "heat"
    t = read_traces(s.dir)[0]
    assert t["step1"]["event_stored"]["text"] == "landlord fixed the heat"
    assert "events" in t["step1"]["prompt"]  # 注入的中期记忆进了 trace


def test_no_event_means_no_write(data_root: Path) -> None:
    s = UserStore("104", data_root)
    s.init_user()
    handle_turn("104", "hi", s, FakeChatModel(script=[_S1_REPLY]), FakeChatModel(script=[_S2]))
    assert s.read_event_list() == []  # event 缺省 → 不写
    assert read_traces(s.dir)[0]["step1"]["event_stored"] is None


def test_silence_turn_still_records_event(data_root: Path) -> None:
    s = UserStore("105", data_root)
    s.init_user()
    out = handle_turn(
        "105", "...", s, FakeChatModel(script=[_S1_SILENT_EVENT]), FakeChatModel(script=[_S2])
    )
    assert not out.replied  # 沉默(leave on read)
    evs = s.read_event_list()
    assert len(evs) == 1 and evs[0].topic == "sister"  # 沉默轮也记住了 → 写在 reply 分支前


def test_compute_pacing() -> None:
    typing, gaps = compute_pacing(["ha", "the wine was bad though", "which one were you"])
    assert typing > 0 and len(gaps) == 2
    assert compute_pacing([]) == (0, [])


# === #53:model 失败 → 必须留 failure trace,不留半状态、不假装回复成功 ===


class _RaisingChatModel:
    """fake model that raises on .complete() — 模拟 provider 异常 / 超时。"""

    def __init__(self, name: str = "raise-fake",
                 error_type: type[Exception] = RuntimeError,
                 msg: str = "provider down") -> None:
        self.name = name
        self._error_type = error_type
        self._msg = msg
        self.calls: list = []

    def complete(self, messages, **_):  # type: ignore[no-untyped-def]
        self.calls.append(messages)
        raise self._error_type(self._msg)


def test_step1_exception_writes_failure_trace_no_reply(data_root: Path) -> None:
    """#53:Step1 抛 → 写 1 条 failure trace(step1.error / stage='step1'),
    outcome.replied=False,**不**调 Step2,**不**留半状态(no inner_voice / impression / event)。"""
    s = UserStore("err1", data_root)
    s.init_user()
    s1_bad = _RaisingChatModel(msg="step1 timed out")
    s2_unused = FakeChatModel(script=["should-not-be-called"])

    out = handle_turn("err1", "hey", s, s1_bad, s2_unused)

    assert not out.replied
    assert out.bubbles == []
    traces = read_traces(s.dir)
    assert len(traces) == 1
    assert traces[0]["step1"].get("error") == "step1 timed out"
    assert traces[0]["step1"].get("stage") == "step1"
    assert traces[0]["step2"] is None
    assert traces[0]["sent"] is None
    assert s2_unused.calls == []  # Step2 一次都没被调
    assert "hey" in (s.dir / "conversation.md").read_text(encoding="utf-8")  # user_text 仍写(用户事实发了)
    assert s.read_impressions() == []  # 半状态防御:没 step1 结果可衍生


def test_step2_exception_writes_failure_trace_with_step1(data_root: Path) -> None:
    """#53:Step1 成功 + Step2 抛 → failure trace 含完整 step1_dict + step2.error,
    outcome.replied=False,**不**写 wren dialogue(防"伪发送"假阳)。"""
    s = UserStore("err2", data_root)
    s.init_user()
    s1_ok = FakeChatModel(script=[_S1_REPLY])
    s2_bad = _RaisingChatModel(msg="step2 5xx", error_type=ConnectionError)

    out = handle_turn("err2", "you up", s, s1_ok, s2_bad)

    assert not out.replied
    traces = read_traces(s.dir)
    assert len(traces) == 1
    t = traces[0]
    assert t["step1"]["reply"] is True
    assert t["step1"].get("error") is None
    assert t["step2"].get("error") == "step2 5xx"
    assert t["step2"].get("error_type") == "ConnectionError"
    assert t["step2"].get("stage") == "step2"
    assert t["sent"] is None
    conv = (s.dir / "conversation.md").read_text(encoding="utf-8")
    assert "user: you up" in conv
    assert "wren:" not in conv  # 关键:无伪发送
    # step1 衍生印象保留(step1 真思考结果,与 step2 能否发气泡无关)
    assert s.read_impressions() == ["noticed the small painting"]


def test_consecutive_failure_traces_have_distinct_turn_ids(data_root: Path) -> None:
    """连续 2 个失败 turn 必须 turn_id 不同(count_traces 在 failure trace 写后递增)。"""
    s = UserStore("err3", data_root)
    s.init_user()
    s2_unused = FakeChatModel(script=["x", "y"])

    handle_turn("err3", "msg1", s, _RaisingChatModel(msg="first"), s2_unused)
    handle_turn("err3", "msg2", s, _RaisingChatModel(msg="second"), s2_unused)

    traces = read_traces(s.dir)
    assert len(traces) == 2
    assert traces[0]["turn_id"] != traces[1]["turn_id"]
    assert traces[0]["step1"]["error"] == "first"
    assert traces[1]["step1"]["error"] == "second"


# === #31:silence-on-malformed(parse_bubbles 失败 → silence,不发 raw text)===


def test_parse_bubbles_returns_empty_on_malformed_json() -> None:
    """#31:parse_bubbles 在 JSON 解析失败时返 `[]`,**不再** fallback `splitlines`。"""
    from wren.prompts.system import parse_bubbles

    # 截断 JSON(老 fallback 会按行切把 `{"messages":["hi"` 当 1 bubble 发)
    assert parse_bubbles('{"messages":["hi"') == []
    # 普通错误文本
    assert parse_bubbles("Sorry, I cannot help with that.") == []
    # debug text
    assert parse_bubbles("DEBUG: model selected gpt-4") == []
    # 合法 JSON 但 schema 错(顶层 dict 无 messages key)
    assert parse_bubbles('{"foo": "bar"}') == []
    # 顶层 string
    assert parse_bubbles('"just a string"') == []
    # 合法 JSON 仍正常解析
    assert parse_bubbles('{"messages":["hi","there"]}') == ["hi", "there"]
    # 顶层 list 也接受
    assert parse_bubbles('["hi","there"]') == ["hi", "there"]
    # fenced JSON
    assert parse_bubbles('```json\n{"messages":["hi"]}\n```') == ["hi"]


def test_parse_bubbles_rejects_unsafe_delivery_bounds() -> None:
    """#48:too many / too long bubbles fail closed to silence, not partial delivery."""
    from wren.prompts.system import parse_bubbles

    assert parse_bubbles(json.dumps({"messages": [str(i) for i in range(8)]})) == [
        str(i) for i in range(8)
    ]
    assert parse_bubbles(json.dumps({"messages": [str(i) for i in range(9)]})) == []
    assert parse_bubbles(json.dumps({"messages": ["x" * 4096]})) == ["x" * 4096]
    assert parse_bubbles(json.dumps({"messages": ["x" * 4097]})) == []


_S2_MALFORMED = '{"messages":["hi"'  # 截断 JSON,parse_bubbles 返 []


def test_step2_malformed_output_goes_silence_no_send(data_root: Path) -> None:
    """#31 端到端:Step2 返截断 JSON → parse_bubbles=[] → pipeline silence,
    **不写 wren dialogue**,**不发 raw text**,落 failure trace 含 step2.error。"""
    s = UserStore("mal1", data_root)
    s.init_user()
    s1 = FakeChatModel(script=[_S1_REPLY])
    s2_bad = FakeChatModel(script=[_S2_MALFORMED])

    out = handle_turn("mal1", "you up", s, s1, s2_bad)

    assert not out.replied
    assert out.bubbles == []
    # 关键:wren dialogue **不写**(防截断 JSON 残片被当 wren 回话进 conversation)
    conv = (s.dir / "conversation.md").read_text(encoding="utf-8")
    assert "user: you up" in conv
    assert "wren:" not in conv
    assert "messages" not in conv  # 防 raw `{"messages":["hi"` 漏到 conversation
    # failure trace 落,标 step2 stage
    traces = read_traces(s.dir)
    assert len(traces) == 1
    assert traces[0]["step2"].get("stage") == "step2"
    err = traces[0]["step2"].get("error", "").lower()
    assert "empty" in err or "malformed" in err


def test_step2_plain_error_text_does_not_become_bubbles(data_root: Path) -> None:
    """#31:模型返"Sorry, I cannot..."等供应商错误文本 → silence,不当 bubble 发。"""
    s = UserStore("mal2", data_root)
    s.init_user()
    s1 = FakeChatModel(script=[_S1_REPLY])
    s2_err = FakeChatModel(script=["I'm sorry, I can't help with that request."])

    out = handle_turn("mal2", "hi", s, s1, s2_err)

    assert not out.replied
    conv = (s.dir / "conversation.md").read_text(encoding="utf-8")
    assert "Sorry" not in conv and "sorry" not in conv
    assert "wren:" not in conv


def test_step2_too_many_bubbles_goes_silence_no_partial_send(data_root: Path) -> None:
    """#48:unsafe bubble count routes through the same fail-closed step2 path."""
    s = UserStore("mal3", data_root)
    s.init_user()
    s1 = FakeChatModel(script=[_S1_REPLY])
    s2_many = FakeChatModel(script=[json.dumps({"messages": [str(i) for i in range(9)]})])

    out = handle_turn("mal3", "hi", s, s1, s2_many)

    assert not out.replied
    assert out.bubbles == []
    conv = (s.dir / "conversation.md").read_text(encoding="utf-8")
    assert "wren:" not in conv
    trace = read_traces(s.dir)[0]
    assert trace["sent"] is None
    assert trace["step2"]["stage"] == "step2"
