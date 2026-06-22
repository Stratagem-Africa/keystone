# ADR-007 — Output `Metric` envelope (close the input/output honesty asymmetry)

**Status:** **Proposed** — awaiting Bifola ratification; **not applied**. Touches the trust-critical engine output + report rendering, so per CLAUDE.md (schema / trust core) **AI proposes, a human ratifies**; it must land via branch → PR → review gate with an invariant test, never self-applied.
**Date:** 2026-06-22 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/03` §2 pillar 2 ("Transparency — no bare numbers") + the §3 "On confidence bands" note, `docs/12` §2 ("two confidence axes — keep them separate"), `prototype/keystone/simulation.py` (the sole number producer), `prototype/keystone/provenance.py` (the input-side `Grounding` envelope this mirrors), CLAUDE.md (prime directive; accuracy honesty).
**Prior art:** the multi-repo study (`docs/13` lineage) — gem5's typed self-describing statistics (every metric is an object carrying value + unit + description, never a bare float) and HiSim's "a number never travels without its model + scope."

---

## Context

Keystone enforces "no bare numbers" rigorously on **inputs**: a grounded capacity is a `Grounding(value, unit, confidence_low/high, citations, provenance)` — it cannot exist without its evidence (`provenance.py`). But **outputs are bare**: `SimulationResult` carries `breakpoint_rps_safe: float`, `p99_ms: float`, `monthly_cost: float`, … plus **one** result-wide `confidence: str`. The report then renders each as a lone figure (`report.py` — `~{p99_ms:.0f} ms`, `~${monthly_cost:,.0f}/month`).

That is an **honesty asymmetry**: pillar 2 ("every quantitative output ships with the model/formula used … and a confidence band") is satisfied for inputs but only loosely for outputs (a single shared string). gem5 and HiSim both show the mature posture — a metric is a **typed, self-describing object**, never a raw scalar. We should close the asymmetry on the side that actually reaches the user.

**The L0 honesty constraint (load-bearing — do not get this wrong).** At L0 the engine does **not** compute a per-metric numeric confidence band; `_confidence(rho_max)` yields a *qualifier* from utilisation. Manufacturing a numeric `±%` per output now would be **false precision** — exactly what `docs/03` forbids. So this envelope must carry a **band only when one is earned** (later: L1 grounding bands, L2 calibration, or v2 DES replications); at L0 it carries the model + the qualifier, and the numeric band stays `None`. It must also **not** blend the two confidence axes (`docs/12` §2): engine-stability confidence ≠ input-provenance confidence.

## Decision (proposed)

### 1. A passive, engine-only `Metric` value object

```python
@dataclass(frozen=True)
class Metric:
    value: float
    unit: str                 # "rps" | "ms" | "usd_minor_per_month" | "ratio"
    model: str                # the formula that produced it, e.g. "M/M/1 sojourn W=S/(1-rho)"
    confidence: str           # the engine-stability qualifier (NOT an input-provenance tag)
    low: float | None = None  # numeric band — ONLY when earned (L1/L2/DES); None at L0
    high: float | None = None
    caveats: tuple[str, ...] = ()
```
- **Frozen + validated** (mirror `provenance.py`): `value` finite; `unit` in an allow-list; `model` non-empty single-line bounded; if `low`/`high` are set they must bracket `value` (no fabricated band). Construction with a band but no earned source is a bug, not a feature.
- **Constructed only inside `simulation.py`.** `SimulationResult`'s numeric fields are retyped `float → Metric` (or a parallel `metrics: dict[str, Metric]` if retyping ripples too far — see dissent). `council.py` and `report.py` consume it **read-only**.

### 2. The prime-directive invariant (enforced by a test, not goodwill)

`Metric` has **no setter path reachable from `council.py` / `report.py`** (frozen dataclass; built only in `simulate()`). Add an **invariant test** asserting the only module that constructs a `Metric` is `simulation.py` (an import-graph / source-scan assertion, mirroring the spirit of the KB's "only inputs are groundable" guard). This makes the asymmetry-closing change *strengthen* the prime directive rather than risk it.

### 3. The report renders the envelope, not a bare float

`report.py` renders each headline number as `value unit · model · confidence` (and `± band` only when `low/high` are present). This is additive to the existing "Where this is wrong" caveats and the (separately-proposed) "How these numbers were computed" derivation — value-per-number provenance, shown not asserted.

## Recorded dissent (kept, not smoothed)

- **YAGNI skeptic:** at L0 with no numeric bands, is a `Metric` object worth retyping the result for? *Partly accepted:* the value is the **typed envelope + the engine-only invariant** (which hardens the prime directive) and a clean seam for when bands ARE earned — not the (absent) L0 band. If retyping every field ripples too far, the cheaper variant is a parallel `metrics: dict[str,Metric]` left beside the existing floats, deprecating the floats later. Bifola to choose retype-vs-parallel at ratification.
- **Accuracy purist:** a per-number "confidence" string risks implying more rigour than L0 has. *Accepted:* `confidence` is the *engine-stability* qualifier verbatim (utilisation-driven), explicitly not a band and not an input-provenance tag; the report labels it as such.
- **Prime-directive guard:** any new numeric field is a new place a number could be born. *Accepted, mitigated:* frozen + engine-only construction + the invariant test; `report.py`/`council.py` can only read.

## Confidence

**High** on the design (mirrors the proven input-side `Grounding` envelope; the invariant is testable). **Medium** on scope (retype-vs-parallel ripple through `report.py`, `run_*.py`, scoring). **This is why it is Proposed, not applied** — Bifola ratifies the shape + the retype/parallel call first.

## Kill criteria (revisit if…)

- A `Metric` is ever constructed outside `simulation.py` → prime-directive breach (the invariant test must fail the build).
- A numeric band (`low`/`high`) is set at L0 without an earned source → false-precision breach.
- The envelope blends engine-stability and input-provenance confidence into one scalar → `docs/12` §2 breach.

## Consequences

Closes the "no bare numbers" asymmetry on the user-facing side and hardens the prime directive with an explicit engine-only-construction invariant — at the cost of a typed retype the reviewer must ratify. No behaviour change until applied; nothing here lets a non-engine layer produce a number.
