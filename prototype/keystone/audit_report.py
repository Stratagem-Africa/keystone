"""Architecture audit report — the client deliverable of the stress-test / audit service.

Assembles the engine's design analysis + the observed-vs-predicted reconciliation into a
single signed findings document, in the spirit of a security firm's audit: severity-ranked
findings, a mandatory "where this is wrong", an explicit NON-GUARANTEE disclaimer, and the
L0 (Directional) maturity label — it never certifies. High-stakes domains carry the
mandatory expert-review banner (reused from the design report, so the framing is identical).

Prime directive: this only READS an already-computed `SimulationResult` + an
`ActualsReconciliation`; it produces NO number of its own (every figure it prints is an
engine value or a gap the reconciliation already computed) and never builds a `Metric`.
Deterministic and offline — the reconciliation is evidence, never auto-resolved (ADR-004).
"""
from __future__ import annotations

from keystone import __version__ as _ENGINE_VERSION
from keystone.actuals import ActualsReconciliation, _sanitize_field, render_actuals_section
from keystone.council import is_high_stakes
from keystone.model import SystemModel
from keystone.simulation import SimulationResult


def _overall(outcome: ActualsReconciliation) -> str:
    """A qualitative headline for the reconciliation — never a certification. Critically, a
    'consistent' verdict is reserved for when observations were ACTUALLY compared: no rows, or
    rows that were all incomparable (unit-mismatch / not-predicted), must NOT read as a pass."""
    if not outcome.rows:
        return "MODEL-ONLY — no observed data supplied, so nothing was reconciled against reality"
    if outcome.hard_divergences:
        return "NEEDS ATTENTION — the running system diverges hard from the model in places"
    if outcome.diverged:
        return "SOFT DIVERGENCES — worth review, none severe"
    if not outcome.matched:
        # rows exist but every one was unit-mismatch / not-predicted — nothing was truly compared
        return ("NOT RECONCILED — observations were supplied but none could be compared to an "
                "engine prediction (unit mismatch / not predicted); nothing was validated")
    return "BROADLY CONSISTENT — the compared metrics track the model within tolerance"


def _gap_str(gap_ratio: float | None) -> str:
    return f"{gap_ratio * 100:+.0f}%" if gap_ratio is not None else "gap n/a (predicted ≈ 0)"


def render_audit_report(model: SystemModel, sim: SimulationResult,
                        outcome: ActualsReconciliation) -> str:
    """The full audit deliverable: maturity + non-guarantee, high-stakes gate, executive
    summary, severity-ranked findings, the model-vs-observed table, limitations, and
    reproducibility. Reads engine + reconciliation evidence only; never asserts certification."""
    L: list[str] = [f"# Keystone Architecture Audit — {model.name}", ""]

    # Maturity + non-guarantee (identical framing to the design report's L0 line, Doc 03).
    L.append("> **Accuracy level: L0 (Directional).** A model-based stress-test for decision "
             "support — **not** a certification and **not** a guarantee. This audit does **not** "
             "guarantee the absence of bottlenecks, outages, or failures; it reports where the "
             "engine's model and your observed reality diverge, with stated assumptions. Read "
             "*Limitations & where this is wrong* before trusting a number.")
    L.append("")
    if is_high_stakes(model.domain_flags):
        L.append("> ⚠️ **HIGH-STAKES DOMAIN — mandatory expert review.** This system touches a "
                 "high-stakes domain and **REQUIRES expert / legal / security review before any "
                 "production use.** Keystone does **not** certify safety or production-readiness.")
        L.append("")

    # Executive summary — engine figures (read, not produced) + the reconciliation tally.
    L.append("## Executive summary")
    L.append("")
    L.append(f"- **Design bottleneck:** {sim.bottleneck_name} at "
             f"{sim.bottleneck_utilization * 100:.0f}% utilisation (engine-computed).")
    L.append(f"- **Max safe load:** {sim.breakpoint_rps_safe:,.0f} rps (engine-computed).")
    if sim.spofs:
        L.append(f"- **Single points of failure:** {', '.join(sim.spofs)}.")
    L.append(f"- **Observed reconciliation:** {len(outcome.matched)} matched · "
             f"{len(outcome.diverged)} diverged ({len(outcome.hard_divergences)} hard) · "
             f"{len(outcome.unit_mismatched)} unit-mismatch · "
             f"{len(outcome.no_prediction)} not predicted.")
    L.append(f"- **Overall:** {_overall(outcome)}.")
    L.append("")

    # Findings — severity-ranked divergences (hard first, then by gap magnitude). This is the
    # audit's core value: where your running reality differs from your design model.
    L.append("## Findings")
    L.append("")
    diverged = sorted(
        outcome.diverged,
        key=lambda r: (r.severity != "hard", -abs(r.gap_ratio) if r.gap_ratio is not None else 0),
    )
    if diverged:
        for r in diverged:
            o = r.observed
            sev = "⛔ HARD" if r.severity == "hard" else "⚠ soft"
            # Sanitise every observation-derived string (untrusted export) even here, so the
            # report is self-defending if built from unparsed Observations — cf. render_actuals_section.
            tgt = _sanitize_field(o.component_id or "(system)")
            L.append(f"- **[{sev}] {tgt} / {_sanitize_field(o.metric)}** — predicted {r.predicted:g}, "
                     f"observed {o.value:g} {_sanitize_field(o.unit)} ({_gap_str(r.gap_ratio)}). "
                     f"{_sanitize_field(r.note)}")
    elif outcome.matched:
        L.append("_No divergence between the compared metrics and the engine's predictions "
                 "(within tolerance). This is **not** a guarantee of correctness — see Limitations._")
    elif outcome.rows:
        # rows were supplied but none were comparable — do NOT imply a within-tolerance pass
        L.append("_None of the supplied observations could be compared to an engine prediction "
                 "(unit mismatch / not predicted) — see \"Could not be compared\" below. "
                 "**Nothing was reconciled.**_")
    else:
        L.append("_No observed metrics were supplied, so nothing was reconciled against your "
                 "running system (model-only)._")

    # Rows that could not be compared — surfaced, never dropped (honesty).
    unresolved = outcome.unit_mismatched + outcome.no_prediction
    if unresolved:
        L.append("")
        L.append("**Could not be compared (surfaced, not dropped):**")
        for r in unresolved:
            o = r.observed
            L.append(f"- {_sanitize_field(o.component_id or '(system)')} / "
                     f"{_sanitize_field(o.metric)}: {_sanitize_field(r.note)}")
    L.append("")

    # The full predicted-vs-observed table (reuses the sanitised actuals renderer).
    L.append(render_actuals_section(outcome))
    L.append("")

    # Limitations & where this is wrong.
    L.append("## Limitations & where this is wrong")
    L.append("")
    L.append("- **Modeled vs measured:** the engine's predictions are MODELED from the design, "
             "not measured; the observed values are MEASURED from your running system. This audit "
             "reconciles the two — it does not validate the model's numbers except where an "
             "observation confirms one.")
    L.append("- **L0 (Directional):** the engine is not yet field-calibrated — treat every number "
             "as directional. Divergences are surfaced for your review and **never auto-resolved**.")
    for c in sim.caveats:
        L.append(f"- {c}")
    L.append("- **No guarantee:** this audit does not certify production-readiness or the absence "
             "of failures. It is a point-in-time, model-based analysis against the observations "
             "you supplied, with the assumptions stated above.")
    L.append("")

    # Reproducibility + observation provenance.
    L.append("## Reproducibility")
    L.append("")
    L.append(f"**Engine** v{_ENGINE_VERSION} · model {model.name!r} · deterministic "
             "(identical inputs → identical output).")
    sources = sorted({_sanitize_field(r.observed.source) for r in outcome.rows})
    if sources:
        L.append(f"**Observation sources:** {', '.join(sources)}.")
    return "\n".join(L)
