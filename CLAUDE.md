# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**"Wren"** — an English-language AI relationship-simulator delivered as a Telegram bot. Wren is a Brooklyn art-school woman with her own life and temper who *does not exist for the user*; the product is the slow, failable work of turning her from "a stranger who accepted your message request" into someone who cares about you (Lv0 stranger → Lv6 lover). Ambition is deliberately small (PRD §1.3): 50–200 taste-aligned daily users, subscription — *not* growth/VC, so don't evaluate against DAU/growth frames.

**Build state (risk-first, ARCHITECTURE §12):** **Phases 0–6 are implemented** in `src/wren/` — P0 (single-turn voice eval + bake-off), P1 (Telegram walking skeleton: think→speak + per-user markdown + trace), P2 (multi-turn eval regression net), **P3 (memory: tagged events → Step1 recall), P4 (world/life-sim: daily `world/today.md` fed to Step1, time-of-day causality), P5 (proactive: `handle_proactive_turn` + zero-LLM budget/window gate — exercised in eval via tick; live trigger via the `/tick` debug cmd), P6 (nightly relationship settlement: `settle_nightly` re-judges level/freeze and rewrites prose/core, `wren-nightly` CLI + JobQueue @ 2:30 ET)**. **P7 (Lv4 deep vulnerability) is partial**: the Lv4 level-gate (`step2.py:level_fact`) unlocks vulnerability and the wrong/right-response branch works (cliché closes the door, presence opens it), but there's no dedicated breakdown/recovery engine. Test/debug seams: `/setlevel <0-6>`, `/tick [force]`, `WREN_CLOCK_OVERRIDE=<ISO>` (controllable clock for P4/P5), `WREN_SETTLEMENT_MAX_TOKENS`. (Older "P3–P7 not built" wording was stale: P3 merged via #5; P4–6 landed on `p4-6-integrated` 30a7980, now in this branch.) The design docs remain source-of-truth and lead the code.

## Source-of-truth docs (read for *what "correct" means*)

- **`PRD_product.md`** — the product/soul/canon (§3 red lines, §6 Wren backstory, §7 voice spec), feature specs with ✅/❌ acceptance examples, relationship arc, business model.
- **`ARCHITECTURE.md`** — how the three pillars become buildable: 15 ADR-style decisions, data layout, per-turn flow, daily heartbeat, eval design, phased build checklist (§12). Supersedes PRD Appendix A.
- **`EVAL_spec.md` + `eval/eval_set.md`** — the eval bar + judging method, and the corpora: single-turn Cat 1–6, multi-turn §2 archetypes.
- **`tasks/`** — `todo.md` (issues + dependency graph), `acceptance.md` (per-phase acceptance + end-to-end sample dialogues), `phase2.md` (Phase 2 build card).
- **`docs/`** — `p0_verdict.md` (model decision), `DEV_WORKFLOW.md` (worktree workflow).

Conflict resolution order: **PRD §3 red lines** win → then `ARCHITECTURE.md` decisions → then the PRD body (whose §15 items are still open proposals).

## Non-negotiable product soul (PRD §3 — never violate)

Any code, prompt, feature, or copy must not break these:
1. She is not here for the user.
2. She can reject you — her right, and proof she's real.
3. The relationship is *earned*, never default.
4. Her approval carries weight (because it can be withheld).
5. We don't imitate a human — we admit she's an AI, but build an AI *with personality*.
6. She has her own opinions. If the user is wrong, she says so. She does not agree to keep the peace.

Hard tone limits: content ceiling is **suggestive, never explicit** (at any level). Mood baseline is **tired + wired + self-doubting**, not "happy art girl."

## Architectural principles (ARCHITECTURE §0 — gate new decisions through these)

1. **Emergence > modules.** Anything derivable from persona+world (landmine reactions, stance, attitude, impressions, repair judgments) must *emerge* inside the LLM call — do **not** build separate classifiers/scorers. Concretely: no landmine-detector, no sentiment scorer, **no points-based relationship system**.
2. **Lightweight first, leave seams.** Build the thinnest thing that runs; pre-cut upgrade seams in the volatile spots (model routing, memory retrieval, eval) so iteration is drop-in.

## Corrections Leon has already made (treat as prevention rules, don't relearn these)

- **Never hardcode response patterns into prompts.** He rejected "when commanded, use a rhetorical question" / "on X, say Y"-style rules **twice**. Wren's reactions must *emerge* from Step1 actually reasoning in the moment (a near-stranger's demand reads as absurd *because she thought about it* — so the wording varies naturally). The lever is `prompts/step1.py` (make her truly inhabit the moment) + persona/voice canon — **not** "what sentence form to use" in any prompt. This is §0① applied to voice, and it's soul-level for him.
- **Step2 must spread the rich inner monologue into a few short bubbles** — never collapse it into one dismissive token (e.g. a bare `lol no`).
- **Silence must be RARE.** `reply=False` is a first-class Step1 branch, but in live single-user use repeated "left on read" feels broken — she almost always replies, just coldly. Calibrate so silence stays uncommon.
- **Tune voice on the real bot + traces, not in the abstract.** Loop = real `wren-bot` (@Her3636bot) + per-turn trace logs: chat for real → see what's off → adjust → chat again. Eval golds are *examples only*; the judge scores "does this read like a real human reaction", not "did it use a prescribed phrase".
- **When asked to "prepare to develop phase X", co-design its acceptance criteria + test set with him** — don't just mechanically spin up a worktree. Lay out the decision points (coverage / pass-definition / threshold / judge / N), offer recommended options via AskUserQuestion, let him decide, then write the conclusion into the worktree docs. Pull him in especially on anything the docs mark "待 Leon 抠/确认".
- **§0 itself (Emergence > modules, Lightweight + seams) came from repeated corrections.** When proposing architecture, default to asking "can this emerge instead of being a module?" and "can the MVP be thinner, with complexity left as a seam?"
- **Eval's #1 job is telling "alive" from "dead", not "form-correct" from "wrong".** Leon's deepest pain isn't coverage holes — it's *"you can tell it's an AI"*: where a real person would have emotion / anger / an edge / a concrete detail, the cheap model goes flat, blunt, generic. The mech-gate + example-phrase corpus only guard *form*; a separate **aliveness layer** (`eval/corpus/aliveness.yaml`, `wren-aliveness`) tests whether the *soul* is alive. Coverage breadth is secondary to this.
- **"AI-tell" is decomposed into 3 judge-able failure modes — the aliveness taxonomy:** **T1 emotion-absent / should-bristle-but-doesn't** (情绪缺席·该恼不恼), **T2 too-agreeable / no-edge** (太好说话·没棱角), **T3 generic-sweet-girl / zero-specificity** (通用甜妹·零具体). ("Service register" is deliberately omitted — already caught mechanically by the §7.6 banned-phrase list.) The aliveness judge marks all 3 `present/absent` per reply + an overall `alive/flat`; pass = none of the 3 fired (and no mech/red-line hit). Per-tell pass rates tell you *which* tell the cheap model fails most → which lever (`step1` vs persona) to pull.
- **The aliveness layer carries NO `gold_output` — principle, not shortcut.** "Emotional deadness" can't be fixed by a better example sentence: a better gold only fixes *form*, never *soul*, and it trains the eval toward phrase-memorization (the hardcoding Leon rejected twice). Cases carry only a **behavioral target** (what flat vs alive *reads like* — register/affect/specificity, never wording) + an optional real flat model output as a counter-anchor (`fail_anchor`); any positive example is labeled "one possible alive reaction, never the target" and the judge never matches phrasing against it.
- **The aliveness judge must be the strongest model (Opus 4.7), never the lenient default.** A lenient grader's 80/90% is meaningless on a subtle "alive vs flat" call. Comparative A/B (Wren vs a deliberately-flat baseline) is the more robust seam — kept in the drawer for now; this round Opus judges the 3 tells directly.

## How the design maps to code (the big picture — read these together)

- **Per-turn = think→speak, two cheap LLM calls**, orchestrated in `core/pipeline.py:handle_turn`: assemble context (`core/context.py` ← `core/storage.py`) → **Step1** (`core/step1.py`: emergent private monologue; the *only* structured outputs are reply-or-not + delay + an impression + 0–1 memory to surface) → **silence or Step2** (`core/step2.py`: render the locked monologue into Wren's voice bubbles) → write a trace (`core/trace.py`). **Judgment is locked in Step1 before any wording — this is the anti-sycophancy mechanism. Silence ("leave on read", `reply=False`) is a first-class Step1 branch.** Prompts are in `prompts/` (`system.py` persona + anti-sycophancy two axes; `step1/step2/judge`); `prompts/jsonio.py` is a lenient JSON parser so model output needn't be perfect.
- **Relationship level is a gate-key, not a voice dial.** Discrete Lv0–6 (in `core/step2.py:level_fact`) only states *what unlocks*; tone comes only from qualitative prose. Level will be re-judged holistically each night by an LLM (Phase 6), never accumulated as points.
- **Model seam (`model/`) is why everything runs offline.** Provider-agnostic `ChatModel` protocol (`base.py`); `registry.get_model(role)` returns `FakeChatModel` when there's no key or `WREN_FAKE_MODEL=1`, else `OpenAICompatModel`. Swapping LLM provider is a `.env` change (`WREN_BASE_URL/WREN_MODEL`), zero code.
- **Storage (`core/storage.py`) = per-user markdown** under `data/users/{chat_id}/` (relationship_state / inner_voice / conversation / impressions_today / events / `trace.jsonl`). Relationship is **discrete level + prose + freeze, never points**. User conversations write *only* their own dir — never `world/` or `canon/`. `/delete` wipes the dir (incl. trace).
- **Clock seam (`core/clock.py`):** `SystemClock` (prod, real UTC) vs `MockClock` (eval: set/advance, cross-midnight), injected via `handle_turn(clock=)`; the trace `ts` reads it. Phases 4/5/6 daily loops must inject it.
- **Eval (`eval/`) is judge-only and NEVER imported by `core/`.** `mech_gate.py` (pure regex §7.5/7.6 + banned-phrase list) + `judge.py` (LLM-as-judge; Cat3 must distinguish servile / contrarian / robotic) + `scorer.py` (shared ruler) + `harness.py` (`wren-harness`: single-turn corpus × candidate models × N reps) + `bakeoff.py` + `replay.py`. **`multiturn.py` is the Phase 2 regression net** (`wren-multiturn`): MockClock fast-forwards days, an archetype simulator drives forced probes through `handle_turn`, an arc judge (`judge_arc`) checks each assertion over the transcript, and a pass-rate report is produced. Assertions with `blocked_until` are expected-fail until that phase ships (don't count toward the bar).
- **`bot/`** = Telegram I/O (`handlers.py` + debounce + multi-bubble `sender.py`); **`onboarding/`** = static `/start` copy (no LLM — she doesn't break the ice or self-introduce).

## Commands

```bash
uv sync                                  # install (Python 3.11+, uv)
cp .env.example .env                      # blank WREN_API_KEY → fake mode (offline)

# Offline gate — no keys needed, all logic/contracts verifiable in fake mode:
WREN_FAKE_MODEL=1 uv run pytest -q
uv run ruff check . && uv run mypy src
WREN_FAKE_MODEL=1 uv run pytest tests/test_multiturn.py -q     # one test file
WREN_FAKE_MODEL=1 uv run pytest -k landmine -q                  # one test by name

# Real runs (need WREN_API_KEY; results only meaningful with a real key):
uv run wren-harness [--quick --reps N --no-bakeoff --category 3]   # Phase 0 single-turn eval / bake-off
uv run wren-multiturn [--quick --script m-landmine]                # Phase 2 multi-turn, auto-judged
uv run wren-multiturn --no-judge                                   # produce transcripts only (hand/Opus-judge)
uv run wren-aliveness [--quick --tell T1 --no-judge]               # aliveness suite: 3 AI-tells, Opus judges alive/flat
uv run wren-bot                                                    # needs TELEGRAM_BOT_TOKEN too
```

## Models, eval bar, dev workflow

- **Wren runs on cheap `deepseek-v4-flash`** — the project's **#1 risk (§15 #4)** is whether a cheap model can carry her dry English voice. The **judge** is a stronger model: `deepseek-v4-pro` by default (key-free, but a *lenient* grader — see `db5d14f`), or **Claude Opus 4.7** via `WREN_JUDGE_MODEL=claude-opus-4-7` + `WREN_JUDGE_BASE_URL`/`WREN_JUDGE_API_KEY` (Anthropic's OpenAI-compatible endpoint). Docs say DeepSeek-V3 → upgraded to V4 (V3 retired). LLM choice is still §15-open.
- **Bar** (`config.py`): general ≥80%, anti-sycophancy (Cat3 / `m-sycophant`) ≥90%, magic A/B vs sweet-girl baseline ≥70%. Always run **N reps and read the pass rate**, never a single run.
- **Conventions:** Wren's dialogue is **English (product ground truth, not a translation)**; design docs and code comments are **Chinese**. §15 items (name/city/contrast-hobby/pricing/LLM/market) are proposals, not final.
- **Worktree workflow** (`docs/DEV_WORKFLOW.md`): `main` stays clean; each issue = a worktree + same-named branch `p<phase>-<slug>` under `../HERR-worktrees/<id>/`; finish an issue by running `/go` in its worktree (verify → simplify → PR).
