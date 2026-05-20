# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**Pre-implementation design repo** for **"Wren"** — an English-language AI relationship-simulator delivered as a Telegram bot. Wren is a Brooklyn art-school woman with her own life and temper who *does not exist for the user*; the product is the slow, failable work of turning her from "a stranger who accepted your message request" into someone who cares about you (Lv0 stranger → Lv6 lover).

There is **no code yet** — only two source-of-truth documents. The ambition is deliberately small (PRD §1.3): a product Leon finds cool that 50–200 taste-aligned users use daily, monetized by subscription. *Not* growth/VC — don't evaluate it against DAU/growth frames.

## The two source-of-truth docs

- **`PRD_product.md`** — the product itself: problem, user, soul, character canon (§6 Wren backstory + §7 voice spec), feature specs with ✅/❌ acceptance examples, relationship arc, business model. Read for *what the product is and what "correct" looks like*. Technical/payment/ops detail is in its appendices A–F.
- **`ARCHITECTURE.md`** — how the three pillars (proactivity / own-mind / relationship-stages) become a buildable system: 15 ADR-style decisions, data layout, per-turn flow, daily heartbeat, eval design, phased build checklist. Read for *how to build it*. Supersedes PRD Appendix A.

Conflict resolution order: **§3 red lines** win → then `ARCHITECTURE.md` decisions → then the PRD body (whose §15 items are still open proposals).

## Non-negotiable product soul (PRD §3 — never violate)

Any code, prompt, feature, or copy must not break these:
1. She is not here for the user.
2. She can reject you — her right, and proof she's real.
3. The relationship is *earned*, never default.
4. Her approval carries weight (because it can be withheld).
5. We don't imitate a human — we admit she's an AI, but build an AI *with personality*.
6. She has her own opinions. If the user is wrong, she says so. She does not agree to keep the peace.

Hard tone limits: content ceiling is **suggestive, never explicit** (at any level). Mood baseline is **tired + wired + self-doubting**, not "happy art girl."

## Architectural principles (ARCHITECTURE.md §0 — gate new decisions through these)

1. **Emergence > modules.** Anything derivable from persona+world (landmine reactions, stance, attitude, impressions, repair judgments) must *emerge* inside the LLM call — do **not** build separate classifiers/scorers. Concretely: no landmine-detector, no sentiment scorer, **no points-based relationship system**.
2. **Lightweight first, leave seams.** Build the thinnest thing that runs; pre-cut upgrade seams in the volatile spots (model routing, memory retrieval, eval) so iteration is drop-in.

Consequences worth internalizing before touching the design:
- **Think → speak = two cheap LLM calls.** Step1 = her emergent private inner monologue, whose *only* structured outputs are reply-or-not(+delay) and an impression note; Step2 = render that monologue into Wren's voice. Judgment is locked before wording (this is the anti-sycophancy mechanism). Silence ("leave on read") is a first-class Step1 outcome.
- **Relationship level is a gate-key, not a voice dial.** Discrete Lv0–6 only gates *what unlocks*; tone comes from a qualitative prose state, never "you are Lv3, be friendly." Level is re-judged holistically each night by an LLM, never accumulated as points.
- **Memory feeds Step1 only.** Per-user markdown, **not RAG**. The full (capped, tagged) event memory enters Step1, which surfaces 0–1 relevant items to Step2 — this is the anti-context-pollution mechanism.
- **One Wren, one life (global) + per-user relationships.** Daily life-events are global ground truth; whether/how she reaches out is per-user. User conversations write only their own thread, never the global world.

## Conventions

- **All of Wren's dialogue is English — it is product ground truth, not a translation** (PRD §7 voice rule). Design docs and code comments are Chinese.
- **PRD §15 is unresolved.** Name (Wren), city (Brooklyn), the "contrast hobby" (astronomy), pricing, **LLM choice**, and launch market are *proposals*, not locked. Don't treat them as final.
- **Biggest open risk = voice quality** (§15 #4 / Appendix B): whether a cheap model (DeepSeek-V3) can carry Wren's dry English texting voice. Unverified — de-risk it before building on top of it.

## Where to start (no build/lint/test exists yet)

Planned stack (PRD Appendix D): Python 3.11+, `python-telegram-bot`, `openai`-compatible SDK, `apscheduler` (proactive cron + delayed sends), per-user markdown storage, Telegram Stars for payments, Railway/Fly.io (US/EU region).

Build order is **risk-first** (ARCHITECTURE.md §12). **Phase 0 precedes any product code:** build a single-turn eval (mechanical voice checks from §7.5/§7.6 + a golden-dialogue LLM-judge from §7.4) and run a **voice bake-off** to pick the main model — this kills the project's #1 uncertainty before anything is built on it.
