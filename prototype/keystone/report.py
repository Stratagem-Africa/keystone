"""Report generation (Doc 04 F7). Renders a Markdown stress-test report from the
canonical model, the council ADRs, and the deterministic simulation result -- with
the mandatory 'where this is wrong' section (Doc 03)."""
from __future__ import annotations

from keystone import __version__ as _ENGINE_VERSION
from keystone.model import SystemModel
from keystone.council import ADR, is_high_stakes
from keystone.simulation import SimulationResult


def _fmt_rps(x: float) -> str:
    if x == float("inf"):
        return "unbounded"
    return f"{x:,.0f}"


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
    if bd and (bd.get("egress") or bd.get("storage") or bd.get("requests") or discounted):
        # Honest compute line: under a discount, show list -> charged so the discount is never hidden.
        if discounted:
            compute_part = (f"compute ${bd['compute'] / 100:,.2f} "
                            f"(_{sim.compute_pricing}_, from ${sim.compute_list_cents / 100:,.2f} list)")
        else:
            compute_part = f"compute ${bd['compute'] / 100:,.2f}"
        parts = [compute_part]
        for k in ("egress", "storage", "requests"):
            if bd.get(k):
                parts.append(f"{k} ${bd[k] / 100:,.2f}")
        L.append(f"  - breakdown: {' · '.join(parts)} /month "
                 "(usage rates **+ discount ratios** are ASSUMPTION — ADR-009)")
    L.append("")

    # Headline metrics envelope (ADR-007): every headline number travels with the model that
    # produced it + the engine-stability confidence — no bare numbers (Doc 03 pillar 2). The
    # engine is the sole author of these values; this only renders them.
    if sim.metrics:
        L.append("## Headline metrics (model · confidence)")
        L.append("")
        L.append("| Metric | Value | Model | Confidence |")
        L.append("|---|--:|---|:--|")
        for name, m in sim.metrics.items():
            if m.unit == "rps":
                val = f"{_fmt_rps(m.value)} req/s"
            elif m.unit == "ratio":
                val = f"{m.value * 100:.0f}%"
            elif m.unit == "usd_minor_per_month":
                val = f"${m.value / 100:,.2f}/mo"  # integer cents → 2dp dollars (ADR-008)
            else:
                val = f"{m.value:,.0f} ms"
            short_conf = m.confidence.split("(")[0].strip()
            L.append(f"| {name} | {val} | {m.model} | {short_conf} |")
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
