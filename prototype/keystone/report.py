"""Report generation (Doc 04 F7). Renders a Markdown stress-test report from the
canonical model, the council ADRs, and the deterministic simulation result -- with
the mandatory 'where this is wrong' section (Doc 03)."""
from __future__ import annotations

from keystone import __version__ as _ENGINE_VERSION
from keystone.model import SystemModel
from keystone.council import ADR, is_high_stakes
from keystone.provenance import GROUNDABLE_METRICS
from keystone.simulation import SimulationResult


def _fmt_rps(x: float) -> str:
    if x == float("inf"):
        return "unbounded"
    return f"{x:,.0f}"


def _fmt_grounded(metric: str, value: float, g) -> tuple[str, str, str]:
    """(your value, grounded central, cited band) formatted for the metric's unit."""
    if metric == "monthly_cost_per_instance":   # integer cents → dollars (ADR-008)
        return (f"${value / 100:,.2f}/mo", f"${g.value / 100:,.2f}/mo",
                f"${g.confidence_low / 100:,.2f}–${g.confidence_high / 100:,.2f}")
    if metric == "base_latency_ms":
        return (f"{value:,.2f} ms", f"{g.value:,.2f} ms",
                f"{g.confidence_low:,.2f}–{g.confidence_high:,.2f} ms")
    return (f"{value:,.0f} rps", f"{g.value:,.0f} rps",
            f"{g.confidence_low:,.0f}–{g.confidence_high:,.0f} rps")


def _grounding_section(model: SystemModel) -> list[str]:
    """Render the cited KB evidence attached to the model's INPUT numbers (ADR-006 L0→L1).

    Gated on at least one grounding, so a model with none (the stub default) emits ZERO bytes and the
    report is byte-for-byte unchanged. The engine still computed every result above; this annotates the
    *inputs* only — GROUNDED (value inside the cited band) vs RECONCILE (outside; the modeler value was
    kept, never overwritten). Reads evidence the model already carries; it produces no number.

    EVIDENCE-ONLY SEMANTICS: the "Your value" column is the model's *current* input value, which under
    `enrich(override=False)` (the only shipped mode) IS the modeler's value. Do NOT render an
    `enrich(override=True)` model through this section as-is — there the input has been replaced by the
    grounded central, so "Your value" would mislabel it. A future override-aware view must read the
    preserved original from `EnrichResult.groundings[*].modeler_value` and render it as OVERRIDDEN."""
    rows = [(c, m, c.groundings[m]) for c in model.components.values()
            for m in sorted(GROUNDABLE_METRICS) if m in c.groundings]
    if not rows:
        return []
    L = ["## Grounding & reconciliation (input evidence)", "",
         "Input numbers matched to **cited benchmark evidence**, by component **kind**. The engine still "
         "computed every result above; this annotates the *inputs* only. **GROUNDED** = your value sits "
         "inside the cited band; **RECONCILE** = it falls outside, and your value was **kept** (not "
         "overwritten). **Measured on** shows the hardware / workload the benchmark actually ran on — "
         "check it matches your setup before trusting the band.", "",
         "| Component | Input | Your value | Grounded central | Cited band | Status | Measured on | Source |",
         "|---|---|--:|--:|:--:|:--|:--|:--|"]
    reconcile: list[tuple] = []
    for comp, metric, g in rows:
        v = getattr(comp, metric)
        in_band = g.confidence_low <= v <= g.confidence_high
        yv, gv, band = _fmt_grounded(metric, v, g)
        status = "GROUNDED ✓" if in_band else "RECONCILE ⚠"
        mc = g.measured_context or "—"
        if len(mc) > 52:
            mc = mc[:51] + "…"
        L.append(f"| {comp.name} | {metric} | {yv} | {gv} | {band} | {status} | {mc} | {g.citations[0].source} |")
        if not in_band:
            reconcile.append((comp.name, metric, yv, gv, band))
    L.append("")
    if reconcile:
        L.append("**Reconcile — your value is outside the cited band (kept, not overwritten):**")
        for name, metric, yv, gv, band in reconcile:
            L.append(f"- **{name}** · `{metric}`: you have **{yv}**, the cited evidence says **{gv}** "
                     f"(band {band}). Check the context (hardware / region / workload) — the engine used "
                     "**your** value, not the benchmark.")
        L.append("")
    L.append("**Evidence (resolvable sources):**")
    seen: set[tuple[str, str]] = set()
    for _comp, _metric, g in rows:
        for c in g.citations:
            if (c.source, c.reference) not in seen:
                seen.add((c.source, c.reference))
                L.append(f"- {c.source} — {c.reference}")
    L.append("")
    return L


# Stable display order + natural-unit conversion for the grounded cost rates (ADR-009 slice 2).
_RATE_ORDER = ("egress", "storage", "requests", "llm_input", "llm_output",
               "reserved_1yr", "reserved_3yr", "spot")
_RATE_LABEL = {"egress": "egress", "storage": "storage", "requests": "requests",
               "llm_input": "LLM input", "llm_output": "LLM output",
               "reserved_1yr": "reserved 1yr", "reserved_3yr": "reserved 3yr", "spot": "spot"}


def _fmt_rate(rid: str, g) -> tuple[str, str]:
    """(value, band) in human-friendly units, converted from the engine unit the Grounding carries."""
    v, lo, hi = g.value, g.confidence_low, g.confidence_high
    if rid in ("egress", "storage"):                 # micro-USD/GB(-mo) → $/GB
        unit = "/GB-mo" if rid == "storage" else "/GB"
        dp = 4 if rid == "storage" else 3            # storage band-high $0.0253 needs 4dp (don't under-state)
        return (f"${v / 1e6:,.{dp}f}{unit}", f"${lo / 1e6:,.{dp}f}–${hi / 1e6:,.{dp}f}")
    if rid == "requests":                            # micro-USD per 1k → $/1M requests
        return (f"${v / 1000:,.2f}/1M req", f"${lo / 1000:,.2f}–${hi / 1000:,.2f}")
    if rid in ("llm_input", "llm_output"):           # micro-USD per 1k tokens → $/1M tokens
        return (f"${v / 1000:,.2f}/1M tok", f"${lo / 1000:,.2f}–${hi / 1000:,.2f}")
    if rid in ("reserved_1yr", "reserved_3yr", "spot"):   # basis points RETAINED → % off (band inverts)
        return (f"{(10_000 - v) / 100:,.0f}% off", f"{(10_000 - hi) / 100:,.0f}–{(10_000 - lo) / 100:,.0f}% off")
    # Fail loud: a new rate id added to the evidence file without a formatter must not silently
    # mis-render as a discount (test_rate_tables_match_evidence_ids locks the id sets together).
    raise ValueError(f"_fmt_rate: no formatter for rate id {rid!r} — add it here + to _RATE_ORDER/_RATE_LABEL")


def _rate_evidence_section(model: SystemModel) -> list[str]:
    """Cited evidence behind the per-unit cost RATES (ADR-009 grounding, ratified #71). Gated on
    `pricing.groundings`, so it emits ZERO bytes when rate grounding isn't active (report unchanged).
    The rate VALUES already equal these grounded centrals; this shows the citation + band behind each.
    Reads evidence the model carries; produces no number."""
    gd = model.pricing.groundings
    if not gd:
        return []
    L = ["## Cost rate evidence (grounded)", "",
         "The per-unit cost rates are matched to **cited** vendor/benchmark pricing (researched + "
         "adversarially verified, ratified). Values are the grounded centrals; the band shows the real "
         "provider/model spread. Rates apply only to the cost lines a model actually uses.", "",
         "| Rate | Grounded value | Band | Source |", "|---|--:|:--:|:--|"]
    seen: set[tuple[str, str]] = set()
    for rid in _RATE_ORDER:
        g = gd.get(rid)
        if g is None:
            continue
        val, band = _fmt_rate(rid, g)
        L.append(f"| {_RATE_LABEL[rid]} | {val} | {band} | {g.citations[0].source} |")
        for c in g.citations:
            seen.add((c.source, c.reference))
    L.append("")
    L.append("**Evidence (resolvable sources):**")
    for source, reference in sorted(seen):
        L.append(f"- {source} — {reference}")
    L.append("")
    return L


def render(model: SystemModel, adrs: list[ADR], sim: SimulationResult,
           whatifs: list[tuple[str, SimulationResult]] | None = None) -> str:
    L: list[str] = []
    L.append(f"# Keystone Stress-Test Report — {model.name}")
    L.append("")
    L.append("> Accuracy level **L0 (Directional)**. Decision support, **not** certification. "
             "Numbers come from the deterministic engine; the council reasons about design and is "
             "constrained and scrubbed to keep figures out of its output (best-effort, not a "
             "guarantee). Read *Where this is wrong* before trusting a number.")
    L.append("")
    L.append(f"**Offered load:** {_fmt_rps(sim.system_rps)} req/s — {model.workload.description}")
    L.append(f"**Overall confidence:** {sim.confidence}")
    # Reproduction handle (prior art: MadRaft's seed-as-handle, docs/13). The engine is a pure,
    # deterministic function of the model, so (engine version + model) reproduces this run exactly;
    # a seed is reserved for future stochastic what-ifs (it does not affect today's analytical run).
    L.append(f"**Reproduce:** engine v{_ENGINE_VERSION} · model {model.name!r} · "
             "deterministic (identical inputs → identical output)")
    L.append("")

    # Mandatory high-stakes block (Doc 03 §6 MUST; ADR-001 C1 defence-in-depth).
    # Rendered straight from domain_flags so it can NEVER be dropped by an ADR-list
    # mutation, independent of the council's own Review-gate ADR.
    if is_high_stakes(model.domain_flags):
        L.append("> ⚠️ **HIGH-STAKES DOMAIN — mandatory expert review.** This design touches a "
                 "high-stakes domain. It **REQUIRES expert / legal / security review before any "
                 "production use.** Keystone does **not** certify safety or production-readiness.")
        L.append("")

    # Headline
    L.append("## Verdict")
    L.append("")
    L.append(f"- **Bottleneck:** {sim.bottleneck_name} "
             f"(utilisation {sim.bottleneck_utilization*100:.0f}%)")
    L.append(f"- **Max sustainable load:** ~{_fmt_rps(sim.breakpoint_rps_safe)} req/s at the "
             f"85% safe ceiling · ~{_fmt_rps(sim.breakpoint_rps_theoretical)} req/s theoretical")
    L.append(f"- **Latency (dominant path):** p50 ~{sim.p50_ms:.0f} ms · "
             f"p95 ~{sim.p95_ms:.0f} ms · p99 ~{sim.p99_ms:.0f} ms (mean {sim.mean_latency_ms:.0f} ms)")
    L.append(f"- **Single points of failure:** {', '.join(sim.spofs) if sim.spofs else 'none detected'}")
    # Money is rendered at 2 decimals so sub-dollar / fractional-cost lines survive and the breakdown
    # reconciles to the total (the integer-cent math is exact; only the display formats it).
    discounted = sim.compute_pricing != "on_demand" and sim.compute_list_cents != sim.cost_breakdown.get("compute")
    pricing_tag = f" · _{sim.compute_pricing} pricing_" if discounted else ""
    L.append(f"- **Estimated monthly cost:** ~${sim.monthly_cost / 100:,.2f}/month{pricing_tag}")  # cents (ADR-008)
    # Cost breakdown (ADR-009 Tiers 1–2) — shown when usage is declared OR a non-list pricing model is
    # chosen, so plain compute-only/on-demand models are unchanged.
    bd = sim.cost_breakdown
    if bd and (bd.get("egress") or bd.get("storage") or bd.get("requests") or bd.get("ai") or discounted):
        # Honest compute line: under a discount, show list -> charged so the discount is never hidden.
        if discounted:
            compute_part = (f"compute ${bd['compute'] / 100:,.2f} "
                            f"(_{sim.compute_pricing}_, from ${sim.compute_list_cents / 100:,.2f} list)")
        else:
            compute_part = f"compute ${bd['compute'] / 100:,.2f}"
        parts = [compute_part]
        for k in ("egress", "storage", "requests", "ai"):
            if bd.get(k):
                parts.append(f"{k} ${bd[k] / 100:,.2f}")
        # The rate provenance flips when the rates carry cited evidence (ADR-009 slice 2).
        rate_tag = ("rates **GROUNDED** to cited benchmarks — see *Cost rate evidence*"
                    if model.pricing.groundings else
                    "usage / AI / discount ratios are **ASSUMPTION**")
        L.append(f"  - breakdown: {' · '.join(parts)} /month ({rate_tag} — ADR-009)")
    L.append("")

    # Headline metrics envelope (ADR-007): every headline number travels with the model that
    # produced it + the engine-stability confidence — no bare numbers (Doc 03 pillar 2). The
    # engine is the sole author of these values; this only renders them.
    if sim.metrics:
        def _fmt_val(unit: str, x: float) -> str:
            if unit == "rps":
                return f"{_fmt_rps(x)} req/s"
            if unit == "ratio":
                return f"{x * 100:.0f}%"
            if unit == "usd_minor_per_month":
                return f"${x / 100:,.2f}/mo"  # integer cents → 2dp dollars (ADR-008)
            return f"{x:,.0f} ms"
        has_bands = any(m.low is not None for m in sim.metrics.values())
        L.append("## Headline metrics (model · confidence)")
        L.append("")
        L.append("| Metric | Value | Range (cited inputs) | Model | Confidence |" if has_bands
                 else "| Metric | Value | Model | Confidence |")
        L.append("|---|--:|--:|---|:--|" if has_bands else "|---|--:|---|:--|")
        for name, m in sim.metrics.items():
            val = _fmt_val(m.unit, m.value)
            short_conf = m.confidence.split("(")[0].strip()
            if has_bands:
                rng = f"{_fmt_val(m.unit, m.low)} – {_fmt_val(m.unit, m.high)}" if m.low is not None else "—"
                L.append(f"| {name} | {val} | {rng} | {m.model} | {short_conf} |")
            else:
                L.append(f"| {name} | {val} | {m.model} | {short_conf} |")
        L.append("")
        if has_bands:
            L.append("_Range = the output span when each GROUNDED input is swept across its **cited** "
                     "confidence band (assumed / reconciled inputs held fixed). It expresses "
                     "input-evidence uncertainty only — **not** a validated-accuracy guarantee, and the "
                     "true value can fall outside it. A **—** means no grounded input moves that number "
                     "(no cited spread to show) — it is not zero uncertainty. Accuracy stays "
                     "**L0 (Directional)** until field-calibrated._")
            L.append("")

    # Per-component table
    L.append("## Component load")
    L.append("")
    L.append("| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |")
    L.append("|---|--:|--:|--:|--:|:--|")
    for c in sorted(sim.components.values(), key=lambda r: r.utilization, reverse=True):
        status = "SATURATED" if c.saturated else ("hot" if c.utilization >= 0.85 else "ok")
        L.append(f"| {c.name} | {c.arrival_rps:,.0f} | {c.capacity_rps:,.0f} | "
                 f"{c.utilization*100:.0f}% | {c.mean_latency_ms:.1f} | {status} |")
    L.append("")

    # Input grounding (ADR-006) — cited evidence behind the input numbers + the cost rates, when the KB
    # is active. Both empty (zero bytes) under the stub default, so a non-grounded report is unchanged.
    L.extend(_grounding_section(model))
    L.extend(_rate_evidence_section(model))

    # ADRs
    L.append("## Design decisions (council)")
    src = adrs[0].source if adrs else "stub"
    if src == "stub":
        L.append("")
        L.append("> _Council running in DETERMINISTIC STUB mode — illustrative ADRs, not live "
                 "reasoning. Provide a Claude API key to activate the real consensus engine._")
    for a in adrs:
        L.append("")
        L.append(f"### {a.area} — confidence: {a.confidence}")
        L.append(f"**Decision:** {a.decision}")
        L.append("")
        L.append(f"**Rationale:** {a.rationale}")
        if a.dissent:
            L.append("")
            L.append("**Recorded dissent:**")
            for d in a.dissent:
                L.append(f"- {d}")
        if a.kill_criteria:
            L.append("")
            L.append("**Kill criteria (revisit this decision if):**")
            for k in a.kill_criteria:
                L.append(f"- {k}")
        # Cross-model consensus (ADR-010): independent vendor models' votes on this decision. The first
        # line is the summary ("N/M agree"); the rest are per-model verdicts. Empty for single-model runs.
        if a.consensus:
            L.append("")
            L.append(f"**Cross-model consensus:** {a.consensus[0].split(': ', 1)[-1]} "
                     "— _independent models corroborating this design choice, not certifying a number._")
            for vote in a.consensus[1:]:
                L.append(f"- {vote}")
    L.append("")

    # What-ifs
    if whatifs:
        L.append("## What-if interrogation")
        L.append("")
        L.append("| Scenario | Bottleneck | Util | Max safe load (rps) |")
        L.append("|---|---|--:|--:|")
        for label, w in whatifs:
            L.append(f"| {label} | {w.bottleneck_name} | {w.bottleneck_utilization*100:.0f}% "
                     f"| {_fmt_rps(w.breakpoint_rps_safe)} |")
        L.append("")

    # How these numbers were computed (generated by the engine, not the council).
    # Provenance for every headline figure: the deterministic steps, in order. Renders
    # the engine's own trace so the report shows its working rather than asserting numbers.
    if sim.derivation:
        L.append("## How these numbers were computed")
        L.append("")
        for step in sim.derivation:
            L.append(f"- {step}")
        L.append("")

    # Honesty section (mandatory)
    L.append("## Where this is wrong (read before trusting a number)")
    L.append("")
    for cav in sim.caveats:
        L.append(f"- {cav}")
    # When the KB grounded some inputs, say so honestly: grounded != calibrated, and the matches are
    # by component-kind (not your exact stack), so any RECONCILE row needs a human's eye.
    if any(c.groundings for c in model.components.values()):
        L.append("- Some inputs above are GROUNDED to cited benchmarks matched by component **kind** "
                 "(not your exact instance type / region / workload), so treat them as directional "
                 "evidence, not stack-calibrated truth. RECONCILE rows fall outside the cited band and "
                 "kept **your** value — a human should check them. These component-input citations are "
                 "AI-matched and pass the curation gate; independent citation review remains the standing "
                 "bar before treating them as calibrated (the per-unit cost **rates** were separately "
                 "ratified — see *Cost rate evidence*).")
    L.append("")

    # Assumptions ledger
    if model.assumptions:
        L.append("## Assumptions (each editable)")
        L.append("")
        L.append("| Subject | Statement | Confidence | Provenance |")
        L.append("|---|---|:--:|:--:|")
        for a in model.assumptions:
            L.append(f"| {a.subject} | {a.statement} | {a.confidence} | {a.provenance} |")
        L.append("")

    return "\n".join(L)
