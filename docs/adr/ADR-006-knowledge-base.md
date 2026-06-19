# ADR-006 — Knowledge Base / Grounding Layer (capacities → evidence)

**Status:** **Accepted (scaffold)** — the seam + stub-default + honesty contract land now; the `curated`/`rag` providers (real grounding data) are **gated**, awaiting curated benchmark data + a Bifola activation trigger (like the council/ingestion activation). Hardened by an adversarial review (see below).
**Date:** 2026-06-19 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/03` (Accuracy & Trust Charter — provenance `GROUNDED`/`GAP`/`ASSUMPTION`, the L0→L1 path), `docs/02` §4 (KB/RAG), `docs/05` + ADR-005 (model store — a *possible* v2 home for persisted KB entries; **not scoped there yet**), ADR-001/002 (the seam + stub-default pattern), CLAUDE.md (prime directive; accuracy honesty; cost rule; "grow the reference-model corpus toward L1 calibration — needs the KB")
**Implements:** the "Next" item *"Knowledge base / RAG (pgvector grounding)"* — **scaffold only** here (the design + an inert seam); curating real benchmark data is the L1 work, gated.

---

## Context

Today **nothing in Keystone is `GROUNDED`.** Every capacity and cost — in `benchmarks/reference_models.py`, in ingestion's output, in the blueprints — is a SEED `ASSUMPTION`, and the reports say so honestly. That is correct for **L0 (Directional)**, but the Accuracy Charter's promised climb to **L1 (calibrated)** needs a source of *evidence*: a place that can say "an app server sustains ~X rps — here is the benchmark that shows it," so a value can move `ASSUMPTION → GROUNDED` **with a citation**.

That source is the **Knowledge Base (KB)**. This ADR scaffolds it the same way ADR-001/002 scaffolded the council/ingestor: a small interface, a stub default, and a clear trust contract — so it can be built and wired without activating anything, and the offline loop keeps running $0.

The single hardest rule it must encode (Charter, CLAUDE.md): **"Evidence is a required field. A citation that doesn't resolve is *invented* — drop the dependent claim."** The KB's whole job is to attach resolvable evidence to a value; without evidence, it must produce nothing.

## Decision

### 1. The KB grounds **inputs**, never produces a metric (prime directive)

The KB supplies **input capacities/costs with provenance** (e.g. a component kind's service rate, a cost-per-instance) backed by a citation. It **never** emits a derived metric (utilisation, bottleneck, breakpoint, latency, cost *estimate*) — those remain the deterministic engine's sole output. So the KB sits on the **input side** of ADR-002's input-vs-derived boundary; it raises a value's *provenance*, it does not compute anything.

Concretely, the KB may only ground the input fields **`{per_instance_rps, base_latency_ms, monthly_cost_per_instance}`** (a module-level `GROUNDABLE_METRICS` allow-list; `instances` is a sizing choice, not a grounded fact). Asking the KB to ground anything else — *especially* a derived metric — **raises**, so the prime-directive boundary is enforced at the seam, not left to each implementation's goodwill.

### 2. The trust contract: **no `GROUNDED` without a resolvable citation** (enforced by the type)

A grounding result carries **≥1 `Citation`** (source + a reference: a URL, a vendor spec, a load-test id, a paper) and a **confidence band** (no bare numbers). The dataclass constructor enforces what *can* be checked locally and cheaply: **a `Grounding` cannot be built without at least one citation**, each citation's `source`/`reference` is non-empty + single-line + length-bounded (so evidence text can't smuggle markdown/control chars), the value is finite + non-negative, and the band brackets the value. So "GROUNDED-with-no-citation" is structurally impossible.

What the type **cannot** check is whether a reference actually *resolves to real evidence* — that is verified at **curation time** (the `curated` provider's dataset is human-reviewed before it ships), **not** by a runtime network fetch (which would break the engine's offline/$0/deterministic guarantees). The honesty rule "a citation that doesn't resolve is invented" is therefore a **curation discipline backed by the structural floor above**, not a live URL check.

If the KB has no evidence for a query, it returns **`None`** and the caller keeps the value as `ASSUMPTION`. Absence of evidence → stays `ASSUMPTION` (the honest, safe direction); the dangerous direction (a false `GROUNDED`) is blocked.

### 3. The seam (mirror the council/ingestor)

```python
class KnowledgeBase(Protocol):
    def ground(self, kind: ComponentKind, metric: str, *, context: dict | None = None) -> Grounding | None: ...
```
- `Grounding(value, unit, confidence_low, confidence_high, citations: list[Citation], provenance="GROUNDED")` — construction requires `citations` non-empty.
- `Citation(source, reference, note="")` — `source` + a resolvable `reference` are mandatory.
- `EmptyKnowledgeBase` — the **default stub**: `ground(...) → None` for everything (no data yet → nothing is grounded; this is the honest L0 state). Deterministic, $0, offline.
- `make_knowledge_base(provider="stub", ...)` — env-driven (`KB_PROVIDER`), default **stub**; future providers (`curated` file-dataset, then `rag` pgvector) raise `NotImplementedError` until built. Lazy imports so the zero-dep engine never pulls a data/RAG dependency.

### 4. Data shape & evolution (free-tier first)

- **v1 (this scaffold):** the interface + `EmptyKnowledgeBase` + the `Grounding`/`Citation` types. Grounds nothing — it just makes the *shape* and the *contract* real.
- **v1.5 (`curated`):** a small, hand-curated, file-based dataset of benchmark datapoints, each with a citation — stdlib/JSON, $0. This is what first lets a handful of reference-model capacities become `GROUNDED`.
- **v2 (`rag`):** pgvector retrieval over a benchmark corpus (ADR-003's pgvector; entries persist in the model store, ADR-005). Gated — its own ADR.

### 5. How it wires in (additive, behind the seam)

A consumer (the reference-model scorer, or ingestion) may *optionally* call `kb.ground(kind, metric)`; on a hit, it tags that input `GROUNDED` and records the citation in the assumption ledger; on `None`, it leaves the existing `ASSUMPTION` untouched. **Nothing changes for v1** because the stub grounds nothing — wiring is inert until a real provider + curated data land, on Bifola's trigger (like the council/ingestion activation).

## Recorded dissent (kept, not smoothed)

- **YAGNI skeptic:** building a KB seam before any benchmark data exists is speculative. *Accepted:* it's a tiny inert seam (a Protocol + a stub + types), and the *contract* (no GROUNDED without a citation) is the valuable part — it guarantees that when data does arrive, it cannot be tagged GROUNDED dishonestly. Cheap now, expensive to retrofit onto live grounding.
- **AI-infusion specialist:** real grounding wants RAG/pgvector now. *Accepted, deferred:* a curated file dataset proves the contract end-to-end at $0; RAG is a later ADR once there's a corpus worth retrieving over.
- **Accuracy purist:** even "curated benchmark" numbers are someone else's measurements, not ours. *Accepted, surfaced:* a `Grounding` carries its citation + confidence band, so the report shows *whose* evidence it is; that is exactly the honesty the Charter asks for.

## Confidence

**High** on the contract (no GROUNDED without a resolvable citation; KB grounds inputs only) and the seam (proven pattern). **Lower** on the eventual *quality/coverage* of curated benchmark data — which is precisely why v1 grounds nothing and accuracy stays L0 until real, cited data is curated.

## Kill criteria (revisit this ADR if…)

- Any value reaches a user tagged `GROUNDED` without a resolvable citation, or with a citation that doesn't resolve → honesty breach; block (this is the one rule the type enforces).
- The KB ever emits a **derived** metric (utilisation/bottleneck/breakpoint/latency/cost estimate) → prime-directive breach.
- A grounded value ships without a confidence band → "no bare numbers" breach.
- `rag`/pgvector or a persisted KB enters scope → that is a new ADR (and ties to ADR-005 storage).

## Consequences

Scaffolds the L0→L1 path: with the seam + contract in place, curating real cited benchmark data (the `curated` provider) becomes a contained, gated step that can move specific reference-model capacities to `GROUNDED` — honestly, with evidence. The engine stays pure-stdlib; the KB stays **stub-default** ($0, grounds nothing) until Bifola activates a real provider. No existing behaviour changes.
