"""Eval harness (docs/03 §4) — the honest "how accurate are we?" report card.

Doc 03 makes an eval harness a MUST before external traffic. This consolidates what Keystone can
measure AGAINST GROUND TRUTH at L0 into one scorecard, in the shape HiSim uses (docs/13): a
per-dimension table, scoped to exactly what was tested, with an explicit "what this CANNOT say"
section. It deliberately prints **no single bragging accuracy number** (Doc 03: no bare numbers,
never overclaim) and is honest that latency/throughput error envelopes need ground truth we do
not have yet (L1/L2), and that council reasoning quality needs the real LLM (stub today).

Two evals run offline / $0:
  - **Simulation eval** — the deterministic engine vs the SysSimulator ground-truth corpus
    (cost band, bottleneck plausibility, breakpoint stability, determinism). Delegates to
    `benchmarks.scoring` (the engine is the sole producer of numbers — prime directive).
  - **Reconciliation eval** — planted-conflict model-corpora → recall (did it surface every
    planted conflict?) + false-halt rate (did it ever halt/invent a conflict spuriously?).

GATED, not faked (see the report's limits section): the council reasoning-quality + confidence-
calibration eval (needs the real LLM) and per-component latency/throughput error envelopes
(need grounded/field-calibrated truth). We measure what we can, and say what we can't.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from keystone.benchmarks.scoring import ScoreCard, score_all
from keystone.ingestion import IngestResult
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
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
# Unified report
# --------------------------------------------------------------------------- #
@dataclass
class EvalReport:
    sim_cards: list[ScoreCard] = field(default_factory=list)
    recon_scores: list[ReconScore] = field(default_factory=list)


def run_eval() -> EvalReport:
    return EvalReport(sim_cards=score_all(), recon_scores=run_recon_eval())


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
    L.append("## Where this scorecard CANNOT say more (read before trusting it)")
    L.append("")
    for line in (
        "Latency & throughput have **no ground truth** in the corpus, so there is **no per-component "
        "error envelope** on them yet — only cost band + component count are checkable at L0. A real "
        "error envelope arrives with the grounded benchmark corpus (L1) and field calibration (L2).",
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
