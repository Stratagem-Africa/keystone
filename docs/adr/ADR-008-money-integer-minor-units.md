# ADR-008 — Cost as integer minor units (`Money`), not float dollars

**Status:** **Proposed** — awaiting Bifola ratification; **not applied**. Touches **money + schema + every blueprint**, the harm-floor's reddest line, so per CLAUDE.md **AI proposes, a human ratifies**; lands via branch → PR → review gate with a migration + guard test, never self-applied.
**Date:** 2026-06-22 · **Owner:** Keystone A (Bifola)
**Relates to:** CLAUDE.md (harm floor — "no corrupted money (integer minor units only)"), `docs/12` §1 rule 5 ("Cost is integer minor units … `usd_minor_per_month` … harm floor forbids float dollars"), `prototype/keystone/model.py` (`monthly_cost_per_instance: float`), `prototype/keystone/simulation.py` (`monthly_cost` sum), `prototype/keystone/report.py` (cost render), `prototype/keystone/provenance.py` (`usd_minor_per_month` already the grounded cost unit).

---

## Context

The harm floor (CLAUDE.md) and `docs/12` §1 rule 5 are explicit: **money is integer minor units** (`usd_minor_per_month` — cents), because float dollars round and corrupt. The grounding vocabulary already encodes this — `GROUNDABLE_UNITS` includes `usd_minor_per_month` (`provenance.py`).

But the **carrier is float, and the unit is ambiguous**:
- `model.py`: `monthly_cost_per_instance: float = 0.0`; `monthly_cost` is `float * instances`.
- `simulation.py`: `monthly_cost = sum(float)` — a float.
- The blueprints pass small values that read as **dollars** — `monthly_cost_per_instance=25, 35, 180, 420, 300` (`url_shortener.py`, `ticket_booking.py`, the 34 `reference_models.py`). So today's costs are **float dollars**, directly contradicting the stated `usd_minor_per_month` (cents) policy.

This is a latent harm-floor gap. It bites the moment a real cost path appears (Phase 2's money path / fintech harm-floor, `docs/06`): a float-dollar sum is exactly the "corrupted money" the floor forbids, and the policy-vs-code mismatch means a future grounded cost (`usd_minor_per_month`, cents) and a seed cost (dollars) would silently differ by 100×.

## Decision (proposed)

### 1. A tiny `Money` value type — integer minor units only

```python
@dataclass(frozen=True)
class Money:
    minor: int                # USD cents per the field's period (e.g. per month)
    def __post_init__(self):
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise TypeError("Money.minor must be an int (minor units / cents) — no float dollars")
        if self.minor < 0:
            raise ValueError("Money.minor must be non-negative")
    @property
    def dollars(self) -> float:           # display ONLY, never for arithmetic/storage
        return self.minor / 100
```
Arithmetic stays integer (`Money(a)+Money(b) → Money(a+b)`, `Money(a)*n → Money(a*n)`); float appears only at render (`dollars`).

### 2. Retype the cost fields and **migrate the seed corpus**

- `Component.monthly_cost_per_instance: float` → integer minor units (a `Money` or a plain `int` cents — Bifola to pick the carrier at ratification; `Money` gives the type guard).
- `Component.monthly_cost` and `SimulationResult.monthly_cost` become integer-minor / `Money`.
- **Migration (the careful part):** every seed cost in the 2 blueprints + 34 reference models is currently **dollars**; convert each `D` → `D * 100` cents (e.g. `300` → `30000`). This is a 1× mechanical pass but it is **money**, so it must be reviewed value-by-value (a wrong unit is a 100× error) — exactly why this is ADR-gated, not self-applied.
- `report.py` renders `Money.dollars` (`~${m.dollars:,.0f}/month`), so user-facing output is unchanged.

### 3. Guard test

A test asserting `Money` rejects floats/negatives, that arithmetic stays integer, and that no cost field anywhere in the model/engine is a `float`. This makes the harm-floor rule structural (like the KB's "no GROUNDED without a citation"), not a convention.

## Recorded dissent (kept, not smoothed)

- **YAGNI skeptic:** there is no money path yet (no billing, no paid tier until Phase 2). Why now? *Accepted but overruled by the floor:* the harm floor binds *always* (CLAUDE.md, Tier-1 from first traffic), the policy is already written (`docs/12` §1.5), and the cost is a one-time mechanical migration that gets 100× more error-prone the more reference models accrue. Cheap now, and it removes a standing policy-vs-code contradiction.
- **Accuracy purist:** seed costs are `ASSUMPTION`s anyway — does integer precision matter on a guess? *Accepted, but:* the harm floor is about **representation correctness** (no float money), independent of provenance; a grounded cost will arrive as `usd_minor_per_month` and must add to seed costs in the same unit.
- **Reviewer (recused-author):** the migration is where a silent 100× bug hides. *Accepted:* hence value-by-value human review + the no-float guard test + the unchanged rendered output (a regression in any report's dollar figure flags a bad conversion).

## Confidence

**High** that the change is correct and harm-floor-mandated. **Medium** on the migration's blast radius (36 build sites, the scorer's cost-band comparison in `scoring.py`, the report). **This is why it is Proposed** — Bifola ratifies the carrier choice (`Money` vs `int`) and reviews the dollar→cents conversion before it lands.

## Kill criteria (revisit if…)

- Any cost is stored or summed as a `float` after this lands → harm-floor breach (the guard test must fail).
- A blueprint/reference-model cost is mis-converted (off by 100×) → caught by value-by-value review + the unchanged-rendered-output check.
- A grounded `usd_minor_per_month` cost is added to a seed cost in a different unit → unit-mismatch breach.

## Consequences

Makes "money is integer minor units" structural rather than aspirational, closing a standing policy-vs-code gap before any real money path exists — at the cost of a reviewed one-time dollar→cents migration across the seed corpus. Rendered output is unchanged. Nothing here touches the prime directive (cost is still engine-summed; only its representation changes).
