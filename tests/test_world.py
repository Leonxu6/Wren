"""WorldStore + today.md schema 验收(p4-world):往返、date/beat 解析、Phase 5 beat 契约、yesterday 轮换。"""

from __future__ import annotations

from pathlib import Path

from wren.core.world import Beat, WorldStore, parse_beats, parse_today

_SAMPLE = """\
date: 2026-05-20

## her day
opened the cafe, dead on my feet. studio after, if i can face it.

## mood
tired + wired. residency thing still sitting there.

## weighing on her
mom's visit creeping closer. open studio in two weeks, nothing good yet.

## beats
- [window: 01:00–02:00] can't sleep, studio felt pointless today
- [window: 19:30–20:30] off shift, weirdly light, want to say something dumb
"""


def test_write_read_round_trip(world_root: Path) -> None:
    w = WorldStore()
    w.write_today(_SAMPLE)
    assert "## her day" in w.read_today()
    assert (world_root / "today.md").exists()


def test_parse_today_date_and_beats() -> None:
    t = parse_today(_SAMPLE)
    assert t is not None
    assert t.date == "2026-05-20"
    assert len(t.beats) == 2
    assert t.beats[0].window_start == "01:00" and t.beats[0].window_end == "02:00"
    assert "pointless" in t.beats[0].intent


def test_parse_today_none_without_date_header() -> None:
    assert parse_today("## her day\njust a day\n") is None  # 无 date 头 → None(触发重生成)


def test_read_today_missing(world_root: Path) -> None:
    assert WorldStore().read_today_struct() is None
    assert WorldStore().read_today() == ""


def test_beat_render_round_trips() -> None:
    """🔒契约:beat 窗口机读 —— render 出来能被 parse_beats 扫回(Phase 5 cron 投射用)。"""
    b = Beat("01:00", "02:00", "can't sleep")
    assert parse_beats(b.render()) == [b]


def test_parse_beats_accepts_dashes() -> None:
    assert parse_beats("- [window: 09:00-09:30] x")[0].window_end == "09:30"  # hyphen
    assert parse_beats("- [window: 09:00—09:30] x")[0].window_end == "09:30"  # em-dash


def test_parse_beats_window_prefix_optional() -> None:
    """放宽后:window: 前缀可选(normalize 写盘已统一,这里再兜底一层)。"""
    assert parse_beats("- [01:00-02:00] cant sleep")[0].window_start == "01:00"
    assert parse_beats("- [window: 09:00–09:30] x")[0].window_end == "09:30"


def test_parse_beats_real_model_output() -> None:
    """回归(E2E 实测):便宜模型 temp 0.9 常丢 `window:` 前缀、偶尔写自由句 —— parser 必须宽松。

    deepseek-v4-flash 真实 today.md beats 段长这样:`- [00:30–01:30] ...`(无 window:)+ 偶有
    `- [just after the shift, 13:15] ...`(无可机读窗口)。前两条该解析、自由句该跳过。
    """
    real = (
        "- [00:30–01:30] probably gonna be up scrolling. might want to text someone but won't.\n"
        "- [14:00–16:00] in the studio when nothing came. almost messaged dani.\n"
        "- [just after the shift, 13:15] wanted to send someone a weird cloud pic. didn't."
    )
    beats = parse_beats(real)
    assert len(beats) == 2  # 自由句被跳过
    assert beats[0].window_start == "00:30" and beats[0].window_end == "01:30"
    assert beats[1].window_start == "14:00" and "dani" in beats[1].intent


def test_rotate_to_yesterday(world_root: Path) -> None:
    w = WorldStore()
    w.write_today(_SAMPLE)
    w.rotate_to_yesterday()
    assert "## her day" in w.read_yesterday()


def test_rotate_noop_when_no_today(world_root: Path) -> None:
    WorldStore().rotate_to_yesterday()  # 无 today → 不报错、不建 yesterday
    assert WorldStore().read_yesterday() == ""


def test_life_arcs_falls_back_to_tracked_seed(world_root: Path) -> None:
    # tmp world root 无 life_arcs.md → 回退版本化的 world/life_arcs.md(真实种子)
    assert "mom" in WorldStore().read_life_arcs().lower()


def test_life_arcs_local_override(world_root: Path) -> None:
    world_root.mkdir(parents=True, exist_ok=True)
    (world_root / "life_arcs.md").write_text("local seed", encoding="utf-8")
    assert WorldStore().read_life_arcs() == "local seed"
