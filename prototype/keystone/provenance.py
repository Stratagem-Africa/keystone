"""Provenance vocabulary (ADR-006, docs/03) — the evidence types shared by the canonical
model, the Knowledge Base, and the benchmark corpus.

Kept in its own module (pure stdlib, no Keystone imports) so `model.py` can carry grounding
evidence on a `Component` and the KB can produce it — without an import cycle. The honesty
contract lives here, enforced in the constructors:

  - a `Grounding` is impossible without ≥1 `Citation` + a finite, non-negative, value-bracketing
    confidence band (Doc 03 "evidence is a required field; no bare numbers");
  - evidence text is single-line + bounded (a citation can't smuggle markdown/control chars);
  - the KB may ground only INPUT capacities/costs, never a derived metric (prime directive).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Groundable INPUT metrics (the per-unit facts a benchmark can establish). A DERIVED metric
# — utilisation, bottleneck, breakpoint, latency percentiles, cost ESTIMATE — is the engine's
# to compute (prime directive; ADR-002 boundary). `instances` is a sizing choice, not a fact.
GROUNDABLE_METRICS = frozenset({"per_instance_rps", "base_latency_ms", "monthly_cost_per_instance"})

# Allowed units, matched to the groundable metrics (cost in integer minor units — harm floor).
GROUNDABLE_UNITS = frozenset({"rps", "ms", "usd_minor_per_month"})

_MAX_TEXT = 500     # source / reference: tightly bounded (a URL or name over this is suspicious)
_MAX_NOTE = 1500    # citation note: roomier — the rendered provenance reasoning shouldn't clip mid-sentence


def require_groundable_metric(metric: str) -> None:
    if metric not in GROUNDABLE_METRICS:
        raise ValueError(
            f"the KB may only ground INPUT metrics {sorted(GROUNDABLE_METRICS)}; {metric!r} is not "
            "groundable — a derived metric is the engine's to compute (prime directive)")


def _single_line(name: str, val: str, *, maxlen: int = _MAX_TEXT) -> None:
    """Evidence text is rendered in reports; keep it single-line + bounded so a citation
    can't smuggle markdown/control chars (same posture as ingestion's text cleaning)."""
    if not isinstance(val, str):
        raise TypeError(f"{name} must be a string")
    if "\n" in val or "\r" in val:
        raise ValueError(f"{name} must be a single line (no newlines)")
    if len(val) > maxlen:
        raise ValueError(f"{name} exceeds {maxlen} chars")


@dataclass(frozen=True)
class Citation:
    """A resolvable piece of evidence. `reference` must point at something real
    (a URL, a vendor spec, a load-test id, a paper) — an unresolvable citation is
    an invented one (Doc 03), so both fields are required and non-empty. The type
    cannot check that a reference *resolves*; that is the curation-review gate."""
    source: str          # who/what (e.g. "AWS r7g.large pgbench", "Redis benchmarks")
    reference: str        # where it resolves (URL / doc id / load-test run id)
    note: str = ""

    def __post_init__(self) -> None:
        _single_line("Citation.source", self.source)
        _single_line("Citation.reference", self.reference)
        _single_line("Citation.note", self.note, maxlen=_MAX_NOTE)
        if not self.source.strip():
            raise ValueError("Citation requires a non-empty source")
        if not self.reference.strip():
            raise ValueError("Citation requires a non-empty reference")


@dataclass(frozen=True)
class Grounding:
    """An input value backed by evidence. Constructing one REQUIRES ≥1 citation and a
    finite, non-negative, value-bracketing confidence band — so a GROUNDED value without
    resolvable evidence is structurally impossible (Doc 03 'evidence is a required field')."""
    value: float
    unit: str                       # e.g. "rps", "usd_minor_per_month", "ms"
    confidence_low: float
    confidence_high: float
    citations: tuple[Citation, ...] = ()
    provenance: str = "GROUNDED"
    # The evidence's MEASURED context (hardware / workload / region), surfaced so a reader can judge
    # whether it applies to THEIR setup. Display-only metadata — it never affects matching, the value,
    # the band, or any computed number (the engine never reads it). Empty when the source has no context.
    measured_context: str = ""

    def __post_init__(self) -> None:
        # Store citations immutably: a frozen dataclass still allows mutating a list
        # attribute (g.citations.clear()), which would void the evidence contract.
        object.__setattr__(self, "citations", tuple(self.citations))
        if self.provenance != "GROUNDED":
            raise ValueError("a Grounding is GROUNDED by definition; "
                             "use None (→ caller keeps ASSUMPTION) when there is no evidence")
        if not self.citations:
            raise ValueError("GROUNDED requires >=1 resolvable Citation (no evidence → return None)")
        _single_line("Grounding.measured_context", self.measured_context, maxlen=_MAX_NOTE)  # rendered in reports
        for v in (self.value, self.confidence_low, self.confidence_high):
            if not math.isfinite(v):
                raise ValueError("Grounding values must be finite (no NaN/inf)")
        if self.value < 0 or self.confidence_low < 0:
            raise ValueError("grounded capacities/costs are physical quantities; they cannot be negative")
        if not (self.confidence_low <= self.value <= self.confidence_high):
            raise ValueError("confidence band must bracket the value: low <= value <= high")
        # Harm floor (ADR-008): grounded MONEY is a WHOLE number of minor units (cents) — no fractional
        # cents. This closes the float-cost seam structurally: should a cost grounding ever be APPLIED to
        # an input (the opt-in override path), it cannot inject fractional money. Evidence values are
        # float-typed (rps/ms are legitimately continuous and the corpus loader parses to float), so the
        # achievable invariant for money is integral-VALUED, not int-typed. Only usd_minor_per_month.
        if self.unit == "usd_minor_per_month":
            for v in (self.value, self.confidence_low, self.confidence_high):
                if isinstance(v, bool) or not float(v).is_integer():
                    raise TypeError(
                        f"usd_minor_per_month grounding values must be whole minor units (cents), got "
                        f"{v!r} — fractional money is forbidden by the harm floor")
