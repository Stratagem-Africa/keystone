# ADR-010 — Multi-LLM cross-vendor consensus

> **Renumbered 2026-06-25:** originally drafted as ADR-005, which collided with the older, already-ratified **ADR-005 — Canonical Model Store** (#45). Moved to the next free number (010); content unchanged.

**Status:** **Accepted** — architecture ratified by Bifola 2026-06-25 (independent adversarial review came back clean; code landed stub-default behind the unchanged `Council` interface, #79). Ratifying the architecture does **not** activate it: `consensus` stays opt-in via env (`COUNCIL_PROVIDER`), default `stub`, and runtime activation remains a manual Bifola trigger that inherits ADR-001's council gates.
**Date:** 2026-06-24 (drafted) · **Ratified:** 2026-06-25 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/02` §4 ("grounded consensus of AI architects"), ADR-001 (the council + the prime-directive guard reused here), `docs/03` §2 (prime directive) & §6 (never hide dissent), CLAUDE.md (cost rule, harm floor).

---

## Context
The council today is **one** model wearing 7 persona prompts (ADR-001, cost control). Bifola asked: can we run **multiple, independent LLMs** (Claude, OpenAI/ChatGPT, OpenRouter, local Ollama) for cross-comparison + an extra **consensus among the models**? This is the product's namesake ("grounded *consensus* of AI architects") and a genuine trust upgrade: independent vendors/trainings catching each other beats one model's blind spots.

## Decision
1. **Provider-agnostic transport (built).** The existing `LLM.complete(...)` seam already abstracts the model. Add `OpenAICompatibleLLM` — a **stdlib-HTTP** (`urllib`, no SDK dependency — CLAUDE.md stdlib-first) transport for OpenAI, OpenRouter, and a local Ollama server, which all speak the same `/chat/completions` API. `make_llm(provider, model)` selects: `claude`→`AnthropicLLM` (SDK), `openai`/`openrouter`/`ollama`→`OpenAICompatibleLLM`. The zero-dependency engine still imports **no** SDK (verified).
2. **Consensus layer (`ConsensusCouncil`, built).** Runs the council on a **primary** model (the full 3-stage / 7-persona design), then polls **N independent voter models** to vote AGREE / CAVEAT / DISAGREE on each synthesized ADR (one batched call per voter — cheap). Each ADR gains a `consensus` field: a summary (`N/M models agree`) + one line per voter. Agreement corroborates a decision across vendors; **disagreement is surfaced, never hidden** (Doc 03 §6).
3. **The prime directive holds across ALL models.** Every voter carries the same `_NO_NUMBERS_RULE` prompt, and **every vote's free text is run through ADR-001's `_redact_engine_metrics` guard** before it reaches an ADR — so no model (Claude, GPT, or Llama) can leak a throughput/latency/cost figure into a report. Reasons are additionally single-lined + length-bounded + backtick-stripped (defence-in-depth, like `Citation`). The deterministic engine remains the sole producer of every number.
4. **Default-OFF + $0.** `COUNCIL_PROVIDER` stays `stub`; `consensus` is opt-in via env (`CONSENSUS_PRIMARY`, `CONSENSUS_VOTERS`). A flaky/unavailable voter is **skipped, never fatal** (best-effort overlay; the primary ADRs always stand). Cost is controllable — voters can be **free** OpenRouter models or a **local** Ollama ($0).

## Activation gates (MUST, before `consensus` is wired to any user-facing path)
- **Inherits ALL of ADR-001's council gates** (guard, high-stakes gate, banner) — the consensus reuses them. The `claude` primary's activation conditions apply unchanged.
- **Provider keys** are read from env by the transport and **never logged** (`OPENAI_API_KEY` / `OPENROUTER_API_KEY`; Ollama is keyless/local). Same harm-floor posture as `ANTHROPIC_API_KEY`.
- **Prompt-injection envelope** on the model brief is still owed by the ingestion layer (ADR-002 M1) — the consensus interpolates the same model-derived text as the single-model council, so it inherits that GAP, not a new one.
- The cross-vendor agreement signal must be presented as **corroboration, not certification** — the report still carries the L0 banner + "where this is wrong"; "3/3 models agree" raises confidence, it does not make a number true.

## Recorded dissent
- **YAGNI skeptic:** N models = N× cost + latency for an L0 product. *Accepted, scoped:* it's opt-in and default-off; the cheap path (one full council + N one-shot votes, voters free/local) keeps it $0–pennies. Single-model stays the default.
- **Prime-directive guard:** more models = more surfaces to leak a number. *Accepted:* the SAME binding guard runs on every model's output (tested with a leak in a voter reason); a new model is not a new bypass.
- **Honesty purist:** cross-model agreement could read as "certified." *Accepted:* it's framed as corroboration; the L0 banner + dissent-surfacing stay.

## Consequences
Delivers the cross-vendor consensus the product is named for, behind the unchanged `Council` interface, stub-default and $0 until activated. `test_consensus.py` locks the guard-across-models, flaky-voter-survival, default-off, and transport behaviour. Adds two env knobs + a stdlib transport; no new dependency; the engine stays zero-dep.
