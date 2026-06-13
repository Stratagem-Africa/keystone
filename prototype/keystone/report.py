"""Report generation (Doc 04 F7). Renders a Markdown stress-test report from the
canonical model, the council ADRs, and the deterministic simulation result -- with
the mandatory 'where this is wrong' section (Doc 03)."""
from __future__ import annotations

from keystone.model import SystemModel
from keystone.council import ADR
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
             "Every number below is produced by the deterministic engine, not the LLM.")
    L.append("")
    L.append(f"**Offered load:** {_fmt_rps(sim.system_rps)} req/s — {model.workload.description}")
    L.append(f"**Overall confidence:** {sim.confidence}")
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
    L.append(f"- **Estimated compute cost:** ~${sim.monthly_cost:,.0f}/month")
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
