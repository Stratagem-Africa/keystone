"""Tests for cross-document reconciliation (ADR-004, F2, issue #8).

Offline/deterministic. The trust-critical invariants: HALT on a hard conflict (never
design on a contradiction), NEVER auto-resolve a soft conflict, surface gaps/duplications,
and fail closed on an invalid merge.
"""
from __future__ import annotations

import unittest

from keystone.ingestion import IngestError, IngestResult, Source, ingest_corpus, validate_model
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
from keystone.reconciliation import reconcile, render_reconciliation_report


def _comp(cid, kind, name=None, rps=1000.0, inst=1):
    return Component(cid, kind, name or cid, per_instance_rps=rps, instances=inst, base_latency_ms=1.0)


def _model(name, comps, flows, rps=1000.0, flags=None):
    return SystemModel(name=name, components={c.id: c for c in comps}, flows=flows,
                       workload=Workload(system_rps=rps), assumptions=[], domain_flags=flags or [])


def _res(model):
    return IngestResult(model=model, assumptions=model.assumptions, notes=[])


class TestReconcile(unittest.TestCase):
    def test_empty_corpus_halts(self):
        out = reconcile([])
        self.assertTrue(out.halted)
        self.assertIsNone(out.model)

    def test_single_source_passthrough(self):
        m = _model("S", [_comp("app", K.APP_SERVER)], [Flow("f", 1.0, [FlowStep("app")])])
        out = reconcile([_res(m)])
        self.assertFalse(out.halted)
        self.assertIs(out.model, m)

    def test_clean_two_source_merge(self):
        m1 = _model("A", [_comp("lb", K.LOAD_BALANCER, rps=40000), _comp("app", K.APP_SERVER, rps=2000)],
                    [Flow("f", 1.0, [FlowStep("lb"), FlowStep("app")])], rps=5000)
        m2 = _model("B", [_comp("db", K.SQL_DB, rps=3000)], [], rps=5000)
        out = reconcile([_res(m1), _res(m2)])
        self.assertFalse(out.halted)
        self.assertEqual(set(out.model.components), {"lb", "app", "db"})
        self.assertEqual(out.report.hard_conflicts, [])
        # m2 contributed `db` but no flow, so it is unwired in the merged model: kept (never
        # auto-dropped) but surfaced as a SOFT conflict so it is never silently simulated at 0%.
        unwired = [c for c in out.report.conflicts if c.kind == "unwired-component"]
        self.assertTrue(unwired and unwired[0].subject == "db", "orphan db should be flagged")
        self.assertEqual(unwired[0].severity, "soft")  # MUST be soft: never hard-halt, never auto-drop
        self.assertEqual(out.report.hard_conflicts, [])
        # The merged model is structurally sound apart from the flagged orphan; strict
        # connectivity (the single-model engine contract) correctly rejects that orphan.
        validate_model(out.model, require_connected=False)  # does not raise
        with self.assertRaises(IngestError):
            validate_model(out.model)  # strict: an unwired component must not reach the engine

    def test_hard_conflict_kind_mismatch_halts(self):
        m1 = _model("A", [_comp("store", K.SQL_DB)], [Flow("f", 1.0, [FlowStep("store")])])
        m2 = _model("B", [_comp("store", K.OBJECT_STORE)], [Flow("f", 1.0, [FlowStep("store")])])
        out = reconcile([_res(m1), _res(m2)])
        self.assertTrue(out.halted)
        self.assertIsNone(out.model)
        self.assertTrue(any(c.kind == "component-kind" and c.severity == "hard" for c in out.report.conflicts))

    def test_soft_conflict_merges_and_never_autoresolves(self):
        m1 = _model("A", [_comp("db", K.SQL_DB, rps=3000, inst=1)], [Flow("f", 1.0, [FlowStep("db")])])
        m2 = _model("B", [_comp("db", K.SQL_DB, rps=8000, inst=2)], [Flow("f", 1.0, [FlowStep("db")])])
        out = reconcile([_res(m1), _res(m2)])
        self.assertFalse(out.halted)
        soft = [c for c in out.report.conflicts if c.kind == "component-params"]
        self.assertTrue(soft, "param divergence should be flagged")
        # merged keeps the FIRST value (not averaged / auto-resolved); BOTH sides are recorded.
        self.assertEqual(out.model.components["db"].per_instance_rps, 3000)
        self.assertIn("3000", soft[0].a_value)
        self.assertIn("8000", soft[0].b_value)

    def test_workload_divergence_takes_max_and_flags(self):
        m1 = _model("A", [_comp("app", K.APP_SERVER, rps=50000)], [Flow("f", 1.0, [FlowStep("app")])], rps=5000)
        m2 = _model("B", [_comp("app", K.APP_SERVER, rps=50000)], [Flow("f", 1.0, [FlowStep("app")])], rps=20000)
        out = reconcile([_res(m1), _res(m2)])
        self.assertEqual(out.model.workload.system_rps, 20000)
        self.assertTrue(any(c.kind == "workload" for c in out.report.conflicts))

    def test_duplication_detected(self):
        m1 = _model("A", [_comp("db", K.SQL_DB, name="Primary database")], [Flow("f", 1.0, [FlowStep("db")])])
        m2 = _model("B", [_comp("database", K.SQL_DB, name="Primary DB store")], [])
        out = reconcile([_res(m1), _res(m2)])
        self.assertTrue(out.report.duplications)
        self.assertEqual({out.report.duplications[0].a_id, out.report.duplications[0].b_id}, {"db", "database"})

    def test_gap_detected_no_workload(self):
        m = _model("A", [_comp("app", K.APP_SERVER)], [Flow("f", 1.0, [FlowStep("app")])], rps=0)
        out = reconcile([_res(m)])
        self.assertTrue(any(g.subject == "workload" for g in out.report.gaps))

    def test_invalid_merge_fails_closed(self):
        m = _model("A", [_comp("app", K.APP_SERVER)], [Flow("f", 1.0, [FlowStep("ghost")])])
        out = reconcile([_res(m)])
        self.assertTrue(out.halted)
        self.assertIsNone(out.model)

    def test_report_renders_halt(self):
        m1 = _model("A", [_comp("store", K.SQL_DB)], [Flow("f", 1.0, [FlowStep("store")])])
        m2 = _model("B", [_comp("store", K.OBJECT_STORE)], [Flow("f", 1.0, [FlowStep("store")])])
        md = render_reconciliation_report(reconcile([_res(m1), _res(m2)]))
        self.assertIn("HALTED", md)
        self.assertIn("Conflicts", md)


class TestIngestCorpus(unittest.TestCase):
    def test_one_result_per_source(self):
        results = ingest_corpus([Source(text="a web app"), Source(text="a payments system")])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r.model, SystemModel) for r in results))

    def test_corpus_feeds_reconcile(self):
        results = ingest_corpus([Source(text="a web app"), Source(text="a payments checkout system")])
        out = reconcile(results)
        # stub ingestor yields identical models; high-stakes flag from the 2nd should survive the union
        self.assertFalse(out.halted)
        self.assertIn("high_stakes:payments", out.model.domain_flags)


if __name__ == "__main__":
    unittest.main()
