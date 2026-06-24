"""Eval harness (docs/03 §4) — the honest "how accurate are we?" report card.

Doc 03 makes an eval harness a MUST before external traffic. This consolidates what Keystone can
measure AGAINST GROUND TRUTH at L0 into one scorecard, in the shape HiSim uses (docs/13): a
per-dimension table, scoped to exactly what was tested, with an explicit "what this CANNOT say"
section. It deliberately prints **no single bragging accuracy number** (Doc 03: no bare numbers,
never overclaim) and is honest that latency/throughput error envelopes need ground truth we do
not have yet (L1/L2), and that council reasoning quality needs the real LLM (stub today).

Three evals run offline / $0:
  - **Simulation eval** — the deterministic engine vs the SysSimulator ground-truth corpus
    (cost band, bottleneck plausibility, breakpoint stability, determinism). Delegates to
    `benchmarks.scoring` (the engine is the sole producer of numbers — prime directive).
  - **Reconciliation eval** — planted-conflict model-corpora → recall (did it surface every
    planted conflict?) + false-halt rate (did it ever halt/invent a conflict spuriously?).
  - **Input-grounding coverage** — what fraction of the reference models' INPUT numbers now carry
    cited benchmark evidence (GROUNDED in-band / RECONCILE / still ASSUMPTION). The honest L0→L1
    progress metric; it measures input provenance, NOT engine-output accuracy.

GATED, not faked (see the report's limits section): the council reasoning-quality + confidence-
calibration eval (needs the real LLM) and per-component latency/throughput error envelopes
(need grounded/field-calibrated truth). We measure what we can, and say what we can't.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from keystone.benchmarks.benchmark_corpus import CuratedKnowledgeBase
from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.benchmarks.scoring import ScoreCard, score_all
from keystone.grounding import enrich
from keystone.ingestion import IngestResult
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
from keystone.provenance import GROUNDABLE_METRICS
from keystone.reconciliation import reconcile


# --------------------------------------------------------------------------- #
# Reconciliation eval — graded planted-conflict cases (docs/03 §4, docs/04 F2)
# --------------------------------------------------------------------------- #
@dataclass
class ReconCase:
    """One graded reconciliation case: a corpus with KNOWN planted conflicts + the expected outcome.
    Measures whether the (deterministic) reconciler surfaces what we planted, halts when it must,
    and invents nothing. This evaluates the model-level reconciler, NOT free-prose conflict
    extraction (that is the LLM ingestion step — out of scope here, stub today)."""
    name: str
    results: list[IngestResult]
    expect_halt: bool
    expect_kinds: frozenset[str]   # conflict kinds that MUST be surfaced (e.g. "component-kind")


@dataclass
class ReconScore:
    name: str
    halt_ok: bool                  # actual halt matched expectation (no missed/spurious halt)
    recall_ok: bool                # every planted conflict kind was surfaced
    no_spurious_hard: bool         # no UNEXPECTED hard conflict was invented
    detected_kinds: frozenset[str]

    @property
    def passed(self) -> bool:
        return self.halt_ok and self.recall_ok and self.no_spurious_hard


def _comp(cid: str, kind: K, rps: float = 1000.0, inst: int = 1) -> Component:
    return Component(cid, kind, cid, per_instance_rps=rps, instances=inst, base_latency_ms=1.0)


def _res(name: str, comps: list[Component], flows: list[Flow], rps: float = 1000.0) -> IngestResult:
    m = SystemModel(name=name, components={c.id: c for c in comps}, flows=flows,
                    workload=Workload(system_rps=rps), assumptions=[], domain_flags=[])
    return IngestResult(model=m, assumptions=[], notes=[])


def recon_cases() -> list[ReconCase]:
    """The graded corpus. Each plants a specific, known conflict (or none)."""
    return [
        ReconCase(
            # Two sources that AGREE: B restates A's app (same id/kind/params) and adds no flows of
            # its own, so there is genuinely nothing to flag — no contradiction, no v2-lever flag.
            name="clean two-source merge (no conflict)",
            results=[
                _res("A", [_comp("lb", K.LOAD_BALANCER, 40000), _comp("app", K.APP_SERVER, 2000)],
                     [Flow("f", 1.0, [FlowStep("lb"), FlowStep("app")])], rps=5000),
                _res("B", [_comp("app", K.APP_SERVER, 2000)], [], rps=5000),
            ],
            expect_halt=False, expect_kinds=frozenset(),
        ),
        ReconCase(
            name="hard conflict: same id, contradictory kind (must halt)",
            results=[
                _res("A", [_comp("store", K.SQL_DB)], [Flow("f", 1.0, [FlowStep("store")])]),
                _res("B", [_comp("store", K.OBJECT_STORE)], [Flow("f", 1.0, [FlowStep("store")])]),
            ],
            expect_halt=True, expect_kinds=frozenset({"component-kind"}),
        ),
        ReconCase(
            name="soft conflict: same db, divergent capacity (flag, never auto-resolve)",
            results=[
                _res("A", [_comp("db", K.SQL_DB, rps=3000, inst=1)], [Flow("f", 1.0, [FlowStep("db")])]),
                _res("B", [_comp("db", K.SQL_DB, rps=8000, inst=2)], [Flow("f", 1.0, [FlowStep("db")])]),
            ],
            expect_halt=False, expect_kinds=frozenset({"component-params"}),
        ),
        ReconCase(
            name="soft conflict: divergent stated workload (take max, flag)",
            results=[
                _res("A", [_comp("app", K.APP_SERVER, 50000)], [Flow("f", 1.0, [FlowStep("app")])], rps=5000),
                _res("B", [_comp("app", K.APP_SERVER, 50000)], [Flow("f", 1.0, [FlowStep("app")])], rps=20000),
            ],
            expect_halt=False, expect_kinds=frozenset({"workload"}),
        ),
    ]


def score_recon_case(case: ReconCase) -> ReconScore:
    out = reconcile(case.results)
    detected = frozenset(c.kind for c in out.report.conflicts)
    halt_ok = out.halted == case.expect_halt
    recall_ok = case.expect_kinds <= detected
    # a hard conflict we did NOT plant is a false positive (an invented contradiction)
    expected_hard = case.expect_kinds if case.expect_halt else frozenset()
    spurious_hard = {c.kind for c in out.report.conflicts if c.severity == "hard"} - expected_hard
    return ReconScore(case.name, halt_ok, recall_ok, not spurious_hard, detected)


def run_recon_eval() -> list[ReconScore]:
    return [score_recon_case(c) for c in recon_cases()]


# --------------------------------------------------------------------------- #
# Input-grounding coverage eval (ADR-006, the L0→L1 lever) — what fraction of the reference models'
# INPUT numbers are now backed by cited benchmark evidence. This measures input PROVENANCE + agreement,
# NOT engine-output accuracy: a "grounded in-band" input is cited evidence the modeler's value sits
# within; a "reconcile" input diverges from the evidence (flagged for a human, never auto-changed); it
# does not certify the derived result. Evidence-only (the engine never reads a grounding value).
# --------------------------------------------------------------------------- #
@dataclass
class GroundingCoverage:
    models: int = 0
    total: int = 0              # (component, input-metric) slots across the reference models
    grounded_in_band: int = 0   # cited evidence AND the modeler value sits inside the cited band
    reconcile: int = 0          # cited evidence but the modeler value is out-of-band (diverges)
    ungrounded: int = 0         # no cited datapoint matches → stays ASSUMPTION (the honest L0 default)

    @property
    def evidence_backed(self) -> int:
        return self.grounded_in_band + self.reconcile


def run_grounding_eval() -> GroundingCoverage:
    """Enrich every reference model against the curated corpus and tally input-metric provenance.
    Deterministic + offline; reads the shipped corpus regardless of KB_PROVIDER (measures the corpus,
    not the activation switch)."""
    kb = CuratedKnowledgeBase.from_default_corpus()
    cov = GroundingCoverage()
    for _key, build_fn, _rps in REFERENCE_MODELS:
        cov.models += 1
        model = build_fn()
        graded = {(g.component_id, g.metric): g for g in enrich(model, kb).groundings}
        for cid in model.components:
            for metric in GROUNDABLE_METRICS:
                cov.total += 1
                g = graded.get((cid, metric))
                if g is None:
                    cov.ungrounded += 1
                elif g.in_band:
                    cov.grounded_in_band += 1
                else:
                    cov.reconcile += 1
    return cov


# --------------------------------------------------------------------------- #
# Unified report
# --------------------------------------------------------------------------- #
@dataclass
class EvalReport:
    sim_cards: list[ScoreCard] = field(default_factory=list)
    recon_scores: list[ReconScore] = field(default_factory=list)
    grounding: GroundingCoverage = field(default_factory=GroundingCoverage)


def run_eval() -> EvalReport:
    return EvalReport(sim_cards=score_all(), recon_scores=run_recon_eval(),
                      grounding=run_grounding_eval())


def render_eval_report(rep: EvalReport) -> str:
    n = len(rep.sim_cards)
    in_band = sum(1 for c in rep.sim_cards if c.cost_verdict == "in-band")
    bn_ok = sum(1 for c in rep.sim_cards if c.bottleneck_ok)
    stable = sum(1 for c in rep.sim_cards if c.breakpoint_stable)
    det = sum(1 for c in rep.sim_cards if c.deterministic)
    rn = len(rep.recon_scores)
    recall = sum(1 for s in rep.recon_scores if s.recall_ok)
    no_fp = sum(1 for s in rep.recon_scores if s.no_spurious_hard)
    halt_ok = sum(1 for s in rep.recon_scores if s.halt_ok)

    L: list[str] = []
    L.append("# Keystone — Accuracy Report Card")
    L.append("")
    L.append("> **Accuracy level: L0 (Directional).** This card reports only what can be measured "
             "against ground truth today, with an explicit *what this cannot say* section. It "
             "publishes no single headline accuracy number (Doc 03: no bare numbers, never overclaim).")
    L.append("")
    L.append("## Simulation eval — engine vs the SysSimulator ground-truth corpus")
    L.append("")
    L.append("| Dimension | Result | What the ground truth is |")
    L.append("|---|--:|---|")
    L.append(f"| Cost within documented band | {in_band}/{n} | the corpus's published monthly cost band |")
    L.append(f"| Bottleneck is a real, saturatable component | {bn_ok}/{n} | plausibility (no ground-truth bottleneck in corpus) |")
    L.append(f"| Breakpoint stable (load-invariant) | {stable}/{n} | a correctness property of the open-network model |")
    L.append(f"| Deterministic (identical on re-run) | {det}/{n} | engine MUST be reproducible |")
    L.append("")
    L.append("## Reconciliation eval — planted-conflict corpora (model level)")
    L.append("")
    L.append("| Dimension | Result |")
    L.append("|---|--:|")
    L.append(f"| Planted conflicts surfaced (recall) | {recall}/{rn} |")
    L.append(f"| No invented hard conflict (false-positive-free) | {no_fp}/{rn} |")
    L.append(f"| Halts exactly when it must (no missed/spurious halt) | {halt_ok}/{rn} |")
    L.append("")
    g = rep.grounding
    pct = (lambda x: f"{100 * x / g.total:.0f}%" if g.total else "—")
    L.append("## Input grounding — input numbers backed by cited evidence (ADR-006, the L0→L1 lever)")
    L.append("")
    L.append(f"Across the {g.models} reference models, each component INPUT (capacity / service-time / "
             "per-instance cost) is matched to the curated benchmark corpus. This measures input "
             "**provenance + agreement**, NOT engine-output accuracy: a *grounded in-band* input is cited "
             "evidence the modeler's value sits within; a *reconcile* input diverges from the evidence and "
             "is flagged for a human (never auto-changed). It does not certify the derived result.")
    L.append("")
    L.append("| Dimension | Result |")
    L.append("|---|--:|")
    L.append(f"| Input numbers with cited evidence (grounded **or** reconcile) | {g.evidence_backed}/{g.total} ({pct(g.evidence_backed)}) |")
    L.append(f"| …modeler value AGREES with the cited band (GROUNDED, in-band) | {g.grounded_in_band}/{g.total} ({pct(g.grounded_in_band)}) |")
    L.append(f"| …modeler value DIVERGES from it (RECONCILE — flagged, kept) | {g.reconcile}/{g.total} ({pct(g.reconcile)}) |")
    L.append(f"| Still ASSUMPTION (no cited datapoint matches yet) | {g.ungrounded}/{g.total} ({pct(g.ungrounded)}) |")
    L.append("")
    L.append("> Honest read: most inputs are still ASSUMPTION — this is **early L1**, not calibrated truth. "
             "Coverage grows as the corpus does; a RECONCILE is a *signal to check an input*, not an engine error.")
    L.append("")
    L.append("## Where this scorecard CANNOT say more (read before trusting it)")
    L.append("")
    for line in (
        "Input grounding (above) measures **input provenance + agreement**, NOT an engine-OUTPUT error "
        "envelope — there is still **no per-component error envelope** on the engine's derived "
        "latency/cost. A grounded input is cited evidence the modeler's value sits within; it does not "
        "tell you how wrong the derived result is. Output error envelopes need field-calibrated ground "
        "truth (L2), and most inputs are still ASSUMPTION — this is early L1.",
        "Cost band is **scale-dependent**: a reference model built heavier than the band's assumed "
        "scale reads 'over' even with a correct engine — a model-calibration note, not an engine error.",
        "The **council's reasoning quality and confidence calibration are NOT evaluated here** — that "
        "needs the real LLM (stub-default today) and a graded set of expert-reviewed designs; it is a "
        "gated next step, never faked.",
        "Reconciliation recall is measured on **planted, model-level** conflicts — it does **not** "
        "measure conflict extraction from free prose (that is the LLM ingestion step, evaluated "
        "separately once activated).",
        "Every number here is produced by the deterministic engine / reconciler, never by a language "
        "model (prime directive).",
    ):
        L.append(f"- {line}")
    L.append("")
    return "\n".join(L)


def main() -> int:
    rep = run_eval()
    md = render_eval_report(rep)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "outputs", "accuracy_report_card.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\n(written to {out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
