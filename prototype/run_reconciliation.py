"""Reconciliation (F2) demo — merge partial models from a 2-document corpus.

Shows the differentiator: when two documents agree, Keystone merges them and flags soft
divergences; when they contradict (a hard conflict), it HALTS rather than designing on a
contradiction. In production the partial models come from ingesting real docs; here they
are hand-built to make the conflict obvious. Deterministic; $0/offline.

Run from prototype/:  python3 run_reconciliation.py
"""
from __future__ import annotations

from keystone.ingestion import IngestResult
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
from keystone.reconciliation import reconcile, render_reconciliation_report


def _result(model: SystemModel) -> IngestResult:
    return IngestResult(model=model, assumptions=model.assumptions, notes=[])


def _doc(name, comps, flows, rps):
    return SystemModel(name=name, components={c.id: c for c in comps}, flows=flows,
                       workload=Workload(system_rps=rps), assumptions=[])


def _summary(title, out):
    print(f"\n{title}")
    print(f"  halted: {out.halted}  ·  merged model: {out.model.name if out.model else 'NONE'}")
    print(f"  conflicts: {len(out.report.conflicts)} "
          f"(hard={len(out.report.hard_conflicts)})  ·  gaps: {len(out.report.gaps)}  ·  "
          f"duplications: {len(out.report.duplications)}")
    for c in out.report.conflicts:
        print(f"    [{c.severity}] {c.subject}: {c.a_ref}={c.a_value} vs {c.b_ref}={c.b_value}")


def main() -> None:
    # Doc 1 (a "requirements" doc) and Doc 2 (a "functional" doc) of the SAME system.
    doc1 = _doc("Booking system", [
        Component("lb", K.LOAD_BALANCER, "Load balancer", per_instance_rps=40000, base_latency_ms=1.0),
        Component("app", K.APP_SERVER, "App tier", per_instance_rps=2000, instances=3, base_latency_ms=8.0),
        Component("db", K.SQL_DB, "Inventory DB", per_instance_rps=3000, base_latency_ms=5.0),
    ], [Flow("book", 1.0, [FlowStep("lb"), FlowStep("app"), FlowStep("db")])], rps=5000)

    # Agreeing doc: adds a cache, raises the stated peak, names the DB slightly differently.
    doc2_agree = _doc("Booking system", [
        Component("cache", K.CACHE, "Seat cache", per_instance_rps=100000, base_latency_ms=0.5),
        Component("inventory", K.SQL_DB, "Inventory database", per_instance_rps=3000, base_latency_ms=5.0),
    ], [], rps=12000)

    # Contradicting doc: the same 'db' id, but a DIFFERENT kind — a hard conflict.
    doc2_conflict = _doc("Booking system", [
        Component("db", K.OBJECT_STORE, "Blob inventory", per_instance_rps=5000, base_latency_ms=10.0),
    ], [], rps=5000)

    print("=" * 74)
    print("KEYSTONE — Reconciliation (F2): merge a 2-document corpus")
    print("=" * 74)

    _summary("CASE A — agreeing docs (merge + flag soft divergences):",
             reconcile([_result(doc1), _result(doc2_agree)]))
    _summary("CASE B — contradicting docs (HALT — never design on a contradiction):",
             reconcile([_result(doc1), _result(doc2_conflict)]))

    print("\n" + "-" * 74)
    print("Full report (Case B):\n")
    print(render_reconciliation_report(reconcile([_result(doc1), _result(doc2_conflict)])))


if __name__ == "__main__":
    main()
