"""Regression locks for the four defects found by the 2026-09-07 adversarial audit.

Each one had shipped for months behind a green suite, so each gets a test that fails if it comes
back — and, where the old behaviour was itself pinned by a test, a note saying which assertion was
doing the pinning.
"""
from __future__ import annotations

import math
import unittest

from keystone.blueprints import payments, ticket_booking, twitter, url_shortener
from keystone.council import DeterministicStubCouncil, is_high_stakes
from keystone.domains import HIGH_STAKES_TERMS, detect_high_stakes
from keystone.generate import generate_architecture
from keystone.loadtest import OverloadedDesignError, build_plan
from keystone.model import Flow, FlowStep
from keystone.simulation import _erlang_c, _mmc_sojourn_ms, simulate


class QueueingModelTest(unittest.TestCase):
    """`docs/02-System-Architecture.md:58` has always advertised "M/M/c utilization". The engine
    implemented `S / (1 - rho)` — the SINGLE-server formula — and fed it the whole tier's AGGREGATE
    utilisation, so a 12-instance app tier at rho=0.694 was charged the queueing delay of one
    server at 69.4% busy. Measured overstatement on the flagship: 3.12x on that tier, 2.10x on the
    summed path; `blueprints/library/ci_cd.json:282` self-documents ~12x."""

    def test_single_server_reduces_to_the_old_formula_exactly(self):
        """c=1 must be bit-identical to M/M/1 — the fix must not move a number it had right."""
        for rho in (0.0, 0.05, 0.25, 0.5, 0.694, 0.85, 0.95, 0.99, 0.999):
            with self.subTest(rho=rho):
                self.assertAlmostEqual(_mmc_sojourn_ms(10.0, 1, rho), 10.0 / (1.0 - rho), places=12)

    def test_erlang_c_matches_the_closed_form(self):
        """C(2, 0.5) = 1/3 and C(3, 2/3) = 4/9 are textbook; the recursion must reproduce them."""
        self.assertAlmostEqual(_erlang_c(2, 0.5), 1.0 / 3.0, places=12)
        self.assertAlmostEqual(_erlang_c(3, 2.0 / 3.0), 4.0 / 9.0, places=12)

    def test_the_recursion_survives_the_largest_fleet_in_the_library(self):
        """The closed form needs a^c / c!, which overflows long before youtube's 320 transcoders."""
        c = _erlang_c(320, 0.75)
        self.assertTrue(math.isfinite(c) and 0.0 <= c <= 1.0)

    def test_more_servers_queue_better_at_the_same_utilisation(self):
        """The whole point: aggregate rho alone does not determine the wait."""
        one = _mmc_sojourn_ms(10.0, 1, 0.694)
        twelve = _mmc_sojourn_ms(10.0, 12, 0.694)
        self.assertLess(twelve, one)
        self.assertGreater(one / twelve, 3.0, "the flagship's measured overstatement was 3.12x")

    def test_service_time_is_the_floor(self):
        """W = S + Wq, so the wait can never take a request below its own service time."""
        for servers in (1, 2, 12, 320):
            for rho in (0.01, 0.5, 0.9):
                with self.subTest(servers=servers, rho=rho):
                    self.assertGreaterEqual(_mmc_sojourn_ms(10.0, servers, rho), 10.0)


class OverloadIsUnboundedTest(unittest.TestCase):
    """`_RHO_CEIL = 0.999` clamped rho before dividing, so an overloaded design returned a finite
    latency — 46,051.7 ms on the flagship, IDENTICALLY at 100x, 1,000x, 10,000x and 1,000,000x
    load. That is the same flat-past-saturation artifact Keystone's own teardown convicts
    SysSimulator of ("p50/p99 unchanged from 10 to 100,000 RPS")."""

    def test_latency_is_infinite_at_and_above_saturation(self):
        for rho in (1.0, 1.0001, 5.0, 1e6):
            with self.subTest(rho=rho):
                self.assertEqual(_mmc_sojourn_ms(10.0, 12, rho), math.inf)

    def test_latency_does_not_flatten_into_a_constant_below_saturation(self):
        """The signature of the old bug: the same number at wildly different loads."""
        seen = [_mmc_sojourn_ms(10.0, 4, r) for r in (0.90, 0.95, 0.98, 0.99)]
        self.assertEqual(len(set(seen)), len(seen), "latency must keep responding to load")
        self.assertEqual(seen, sorted(seen), "and must rise monotonically toward saturation")

    def test_a_load_test_plan_is_refused_for_an_overloaded_design(self):
        """Every k6 threshold is the engine's predicted latency. Unbounded is not a threshold."""
        model = url_shortener.build()
        model.workload.system_rps *= 50
        sim = simulate(model)
        self.assertEqual(sim.mean_latency_ms, math.inf)
        with self.assertRaises(OverloadedDesignError):
            build_plan(model, sim)


class HighStakesGateDetectsTest(unittest.TestCase):
    """`ensure_high_stakes_gate` defends against a FORGED expert-review ADR, and nothing ever
    DETECTED a high-stakes domain from what the user asked for. Measured on the shipped path:
    payments fired (because `payments.build()` hardcodes the flag) while 'a hospital patient
    records system', 'an election result tallying platform' and 'a medication dosing calculator'
    all returned domain_flags == [] — three of docs/03's four mandatory domains, failing OPEN."""

    CASES = [
        ("a hospital patient records system", "health"),
        ("a medication dosing calculator for nurses", "health"),
        ("an EHR with lab results", "health"),
        ("an election result tallying platform", "elections"),
        ("a system for counting ballots", "elections"),
        ("a flight control telemetry dashboard", "safety"),
        ("an emergency dispatch system", "safety"),
        ("a payments checkout system", "payments"),
        ("a payroll and tax filing tool", "payments"),
    ]

    def test_each_mandatory_domain_is_detected_from_the_intent(self):
        for intent, domain in self.CASES:
            with self.subTest(intent):
                self.assertIn(f"high_stakes:{domain}", detect_high_stakes(intent))

    def test_the_shipped_generation_path_sets_the_flag(self):
        """Detection is worthless if it is not wired into the call `/generate` actually makes."""
        for intent, domain in self.CASES:
            with self.subTest(intent):
                flags = list(generate_architecture(intent, provider="stub").domain_flags)
                self.assertTrue(is_high_stakes(flags), f"{intent!r} -> {flags}")

    def test_the_expert_review_adr_reaches_the_council_output(self):
        """End to end: a flagged intent must carry the mandatory review block into the ADRs."""
        model = generate_architecture("a hospital patient records system", provider="stub")
        areas = [a.area for a in DeterministicStubCouncil().design(model)]
        self.assertIn("Review gate", areas)

    def test_ordinary_intents_stay_quiet(self):
        """An always-on flag means nothing. The common case must not fire."""
        for intent in ("a url shortener", "a photo sharing app", "a blog", "a ci pipeline",
                       "an app like Uber with video call capabilities"):
            with self.subTest(intent):
                self.assertEqual(detect_high_stakes(intent), ())

    def test_all_four_charter_domains_are_covered(self):
        """docs/03 names exactly these four; a fifth key or a missing one is a drift."""
        self.assertEqual(set(HIGH_STAKES_TERMS), {"elections", "payments", "health", "safety"})


class FlowValidationTest(unittest.TestCase):
    """`Flow` had no `__post_init__` at all, so `share=-5.0` was accepted — which makes a
    component's arrival rate negative, and a negative rho reports a hammered system as idle."""

    def test_a_share_outside_zero_to_one_is_refused(self):
        for share in (-5.0, 0.0, 1.5, float("nan"), float("inf")):
            with self.subTest(share=share):
                with self.assertRaises(ValueError):
                    Flow("f", share, [FlowStep("c")])

    def test_an_empty_path_is_refused(self):
        with self.assertRaises(ValueError):
            Flow("f", 1.0, [])

    def test_a_negative_visit_probability_is_refused(self):
        with self.assertRaises(ValueError):
            FlowStep("c", -1.0)

    def test_fan_out_above_one_is_still_allowed(self):
        """youtube models a 6-rendition transcode fan-out as visit_prob 6.0. Not a bug."""
        self.assertEqual(FlowStep("c", 6.0).visit_prob, 6.0)


class StubCouncilDescribesThisDesignTest(unittest.TestCase):
    """`DeterministicStubCouncil.design()` took `model` and IGNORED it, returning three hardcoded
    URL-shortener decisions for everything. `outputs/ticket_booking_report.md` therefore shipped
    "the mapping table" and "the redirect (read) path" under "Design decisions (council)"."""

    def test_no_design_is_described_using_another_products_vocabulary(self):
        leaks = ("mapping table", "redirect (read) path", "shorten", "short link")
        for build in (ticket_booking.build, payments.build, twitter.build):
            model = build()
            blob = " ".join(f"{a.decision} {a.rationale} {' '.join(a.kill_criteria)}"
                            for a in DeterministicStubCouncil().design(model)).lower()
            for leak in leaks:
                with self.subTest(model.name, leak=leak):
                    self.assertNotIn(leak, blob)

    def test_each_design_is_described_by_its_own_components(self):
        for build in (url_shortener.build, ticket_booking.build, twitter.build):
            model = build()
            with self.subTest(model.name):
                blob = " ".join(a.decision for a in DeterministicStubCouncil().design(model))
                self.assertIn(model.name, blob, "the ADRs must name the system they are about")
                named = [c.name for c in model.components.values() if c.name in blob]
                self.assertTrue(named, f"no component of {model.name} is named in its own ADRs")


if __name__ == "__main__":
    unittest.main()
