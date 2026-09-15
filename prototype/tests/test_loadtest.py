"""The k6 emitter: a load test whose thresholds are the engine's own predictions.

The guard that matters is PROVENANCE. Generated code is exactly where a number can be invented —
a literal in a .js file looks as authoritative as one in the report, and nobody re-derives it. So
every numeric literal in the emitted script must be a declared constant, and every declared constant
must name its source. A stray number fails the suite.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import ticket_booking, twitter, url_shortener
from keystone.loadtest import EMITTER_LIMITS, build_plan, render_k6
from keystone.simulation import simulate

# A JS numeric literal, ignoring those inside an identifier (p95_ms) or a version range.
_NUMBER = re.compile(r"(?<![\w.$])\d+(?:\.\d+)?(?![\w.])")


def _plan_for(build):
    model = build()
    return model, simulate(model)


def _body(script: str) -> str:
    """The script with its header comment block removed — the executable part."""
    return script.split("*/", 1)[1]


class ProvenanceTest(unittest.TestCase):
    def test_every_number_in_the_body_is_a_declared_constant(self):
        for build in (url_shortener.build, twitter.build, ticket_booking.build):
            model, sim = _plan_for(build)
            plan = build_plan(model, sim)
            script = render_k6(plan)
            declared = {f"{v:g}" for v in plan.declared().values()}
            with self.subTest(model.name):
                for line in _body(script).splitlines():
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("const "):
                        continue          # comments, and the declaration block itself
                    # `p(95)` / `p(99)` is k6's PERCENTILE SELECTOR — part of the metric name, not
                    # a value, so it has no provenance to declare. Strip the selector, then scan.
                    scanned = re.sub(r"p\(\d+\)", "p", line)
                    for num in _NUMBER.findall(scanned):
                        self.assertIn(
                            num, declared,
                            f"undeclared numeric literal {num!r} in: {stripped}")

    def test_every_declared_constant_names_its_source(self):
        model, sim = _plan_for(url_shortener.build)
        for lit in build_plan(model, sim).literals:
            with self.subTest(lit.name):
                self.assertTrue(lit.source.strip(), f"{lit.name} has no source")
                self.assertTrue(lit.why.strip(), f"{lit.name} has no rationale")

    def test_the_header_lists_every_constant(self):
        model, sim = _plan_for(url_shortener.build)
        plan = build_plan(model, sim)
        header = render_k6(plan).split("*/", 1)[0]
        for lit in plan.literals:
            self.assertIn(lit.name, header, f"{lit.name} missing from the PROVENANCE block")

    def test_named_constants_are_marked_as_not_predictions(self):
        """A convention is not a prediction, and the file must not blur the two."""
        model, sim = _plan_for(url_shortener.build)
        named = [x for x in build_plan(model, sim).literals if x.source == "NAMED_CONSTANT"]
        self.assertTrue(named)
        self.assertTrue(any("NOT an engine prediction" in x.why for x in named))


class ThresholdsAreThePredictionTest(unittest.TestCase):
    def test_thresholds_track_the_engine_exactly(self):
        model, sim = _plan_for(url_shortener.build)
        plan = build_plan(model, sim)
        self.assertEqual(plan.declared()["SYSTEM_P95_MS"], float(f"{sim.p95_ms:.2f}"))
        by_name = {f.name: f for f in sim.flow_latencies}
        for s in plan.scenarios:
            with self.subTest(s["flow"]):
                self.assertEqual(s["p95_ms"], float(f"{by_name[s['flow']].p95_ms:.2f}"))
                self.assertEqual(s["rate"], float(
                    f"{model.workload.system_rps * next(f.share for f in model.flows if f.name == s['flow']):.2f}"))

    def test_a_slower_design_produces_a_looser_threshold(self):
        """The thresholds must MOVE with the engine, or they are decoration."""
        import dataclasses
        model = url_shortener.build()
        slow = dataclasses.replace(model, components={
            **model.components,
            "app": dataclasses.replace(model.components["app"], base_latency_ms=80.0)})
        fast_p95 = build_plan(model, simulate(model)).declared()["SYSTEM_P95_MS"]
        slow_p95 = build_plan(slow, simulate(slow)).declared()["SYSTEM_P95_MS"]
        self.assertGreater(slow_p95, fast_p95)

    def test_one_scenario_per_flow(self):
        model, sim = _plan_for(twitter.build)
        plan = build_plan(model, sim)
        self.assertEqual(len(plan.scenarios), len(model.flows))
        self.assertEqual(len({s["key"] for s in plan.scenarios}), len(model.flows))


class HonestyTest(unittest.TestCase):
    def test_the_limits_are_published_and_name_the_measurement_mismatch(self):
        self.assertGreaterEqual(len(EMITTER_LIMITS), 5)
        joined = " ".join(EMITTER_LIMITS).lower()
        self.assertIn("client-observed", joined,
                      "the k6-vs-engine measurement mismatch must be stated")
        self.assertIn("network", joined)

    def test_the_limits_appear_in_the_emitted_file(self):
        model, sim = _plan_for(url_shortener.build)
        script = render_k6(build_plan(model, sim))
        for limit in EMITTER_LIMITS:
            self.assertIn(limit.split(".")[0][:40], script)

    def test_the_script_says_a_breach_is_evidence_not_a_verdict(self):
        model, sim = _plan_for(url_shortener.build)
        self.assertIn("EVIDENCE, not a verdict", render_k6(build_plan(model, sim)))


class SyntaxTest(unittest.TestCase):
    """The emitted file must actually parse. `node --check` only reports ESM errors for .mjs —
    on a .js file containing `import` it silently exits 0, which would be a false green."""

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_every_reference_model_emits_valid_javascript(self):
        builders = [b for _n, b, _r in REFERENCE_MODELS]
        with tempfile.TemporaryDirectory() as tmp:
            for i, build in enumerate(builders):
                model = build()
                script = render_k6(build_plan(model, simulate(model)))
                path = Path(tmp) / f"plan_{i}.mjs"          # .mjs, not .js — see the docstring
                path.write_text(script, encoding="utf8")
                proc = subprocess.run(["node", "--check", str(path)],
                                      capture_output=True, text=True)
                with self.subTest(model.name):
                    self.assertEqual(proc.returncode, 0, proc.stderr[:400])

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_the_syntax_check_itself_catches_a_break(self):
        """Poison the checker: a validator that cannot fail proves nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.mjs"
            path.write_text("import x from 'y';\nconst a = 'unterminated;\n", encoding="utf8")
            proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0, "node --check must reject broken ESM")


class DeterminismTest(unittest.TestCase):
    def test_same_model_same_script(self):
        for build in (url_shortener.build, twitter.build):
            model = build()
            with self.subTest(model.name):
                a = render_k6(build_plan(model, simulate(model)))
                b = render_k6(build_plan(model, simulate(model)))
                self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
