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


class CoverageDisclosureTest(unittest.TestCase):
    """Traced 2026-09-07: "an app like Uber with video call capabilities" matched ride_sharing on
    the word "uber" and returned an 8-component design with no media server, no signalling and no
    TURN — presenting its bottleneck, breakpoint, latency and cost as the answer to the whole
    question, with no mention that half of it was dropped."""

    def test_the_uber_with_video_case_is_disclosed(self):
        from keystone.coverage import missing_capabilities
        intent = "I wanna build an app like Uber with video call capabilities"
        model = generate_architecture(intent, provider="stub")
        self.assertEqual([c for c, _ in missing_capabilities(intent, model)],
                         ["real-time video or voice calling"])

    def test_the_gap_lands_on_the_model_as_a_GAP_assumption(self):
        """It has to travel with the numbers, not sit in a docstring."""
        model = generate_architecture(
            "an app like Uber with video call capabilities", provider="stub")
        gaps = [a for a in model.assumptions
                if a.provenance == "GAP" and a.subject == "coverage"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("NOT IN THIS DESIGN", gaps[0].statement)
        self.assertIn("floor", gaps[0].statement)

    def test_it_reaches_the_rendered_report(self):
        from keystone.report import render
        model = generate_architecture(
            "an app like Uber with video call capabilities", provider="stub")
        text = render(model, [], simulate(model))
        self.assertIn("NOT IN THIS DESIGN", text)
        self.assertIn("| GAP |", text)

    def test_a_covered_capability_is_not_reported_missing(self):
        """Noise is the failure mode that makes the whole section ignorable."""
        from keystone.coverage import missing_capabilities
        for intent in ("a payment system", "a url shortener", "a video streaming service",
                       "a search engine"):
            with self.subTest(intent):
                model = generate_architecture(intent, provider="stub")
                self.assertEqual(missing_capabilities(intent, model), [])

    def test_evidence_terms_are_specific_enough_to_be_evidence(self):
        """Bare "gateway" used to count as proof of a payment path, so Twitter's "API Gateway
        (auth + routing)" marked a real payments gap as covered. A generic evidence term is worse
        than none: it silently clears the flag."""
        from keystone.coverage import missing_capabilities
        from keystone.blueprints import twitter
        self.assertEqual(
            [c for c, _ in missing_capabilities("a twitter clone with payments", twitter.build())],
            ["taking payments"])


# `TailModelIsHonestlyLabelledTest` LIVED HERE and has been retired on purpose. It pinned the OLD
# limitation — that p99/p50 was the constant 6.6439 for every design at every load — and its own
# docstring said: "If this ever stops being constant, a real tail model landed — update the caveat."
# One landed (see TailModelIsDerivedNotAssumedTest at the end of this file), so the class asserting
# the limitation is obsolete rather than failing. Deleting a test that pins a shortcoming is correct
# ONLY when the shortcoming is gone; the replacement asserts the stronger property in its place.


class GroundedMeansTheEngineInputsAreCitedTest(unittest.TestCase):
    """`_node_provenance` returned "GROUNDED if ANYTHING is grounded", and `run_blueprint_tool price`
    set `comp.provenance = "GROUNDED"` after attaching an AWS price. Between them, 298 of the
    library's 406 components rendered GROUNDED-green on the strength of one cited field — the
    monthly price — while `per_instance_rps` and `base_latency_ms` were uncited `llm_inferred`
    guesses on every one. Those two are what the engine reads to produce the bottleneck, the
    breakpoint and every latency figure. CLAUDE.md: "Never present an ASSUMPTION as GROUNDED."
    """

    def test_a_priced_but_unmeasured_component_is_not_badged_grounded(self):
        from keystone.arch_map import build_arch_map
        from keystone.blueprint_library import library
        entry = next(e for e in library() if e.key == "ride_sharing")
        model = entry.build()
        nodes = build_arch_map(model, simulate(model))["nodes"]
        for n in nodes:
            with self.subTest(n["name"]):
                cited = {e["metric"] for e in n["evidence"] if e["status"] == "GROUNDED"}
                if n["provenance"] == "GROUNDED":
                    self.assertIn("per_instance_rps", cited)
                    self.assertIn("base_latency_ms", cited)

    def test_the_cost_citation_is_still_shown_not_deleted(self):
        """Downgrading the badge must not hide the evidence we DO have."""
        from keystone.arch_map import build_arch_map
        from keystone.blueprint_library import library
        entry = next(e for e in library() if e.key == "ride_sharing")
        model = entry.build()
        nodes = build_arch_map(model, simulate(model))["nodes"]
        priced = [n for n in nodes
                  if any(e["metric"] == "monthly_cost_per_instance" for e in n["evidence"])]
        self.assertTrue(priced, "the AWS price citations must still reach the map")

    def test_no_library_component_claims_grounded_without_cited_capacity(self):
        """Across all 56 — the label is a claim, and it has to be earned per component."""
        import json
        from keystone.blueprint_library import LIBRARY_DIR
        for path in sorted(LIBRARY_DIR.glob("*.json")):
            for c in json.loads(path.read_text())["components"]:
                if (c.get("provenance") or "").upper() != "GROUNDED":
                    continue
                g = set((c.get("groundings") or {}).keys())
                with self.subTest(f"{path.stem}/{c['id']}"):
                    self.assertIn("per_instance_rps", g)
                    self.assertIn("base_latency_ms", g)


class BottleneckIsACandidateNotAVerdictTest(unittest.TestCase):
    """Web research against primary sources (2026-09-08) found the same defect in blueprint after
    blueprint: the named bottleneck leads by a margin far smaller than the uncertainty in the inputs
    that produce it. Measured across the library: 30 of 56 (54%) name one by 5 percentage points or
    less, and FOUR are exact ties. Keystone's single most-read output was a coin-flip presented as a
    determination."""

    def test_a_tie_reports_every_contender_not_a_winner(self):
        from keystone.blueprint_library import library
        entry = next(e for e in library() if e.key == "mcp_starter")
        # distributed_consensus was the exact-tie fixture until the round-2 reality-check fix gave
        # it a real leader (margin 18.28). mcp_starter is the remaining exact tie. Repoint rather
        # than loosen: if a future fix cures this one too, that is the whole point of the exercise.
        r = simulate(entry.build())
        self.assertLess(r.bottleneck_margin_pts, 0.001, "this design is an exact tie")
        self.assertGreater(len(r.bottleneck_contenders), 1,
                           "a tie must name its co-leaders, not pick one")

    def test_a_clear_winner_is_still_reported_as_one(self):
        """The disclosure must not fire everywhere, or it becomes noise nobody reads."""
        from keystone.blueprint_library import library
        entry = next(e for e in library() if e.key == "ride_sharing")
        r = simulate(entry.build())
        self.assertGreater(r.bottleneck_margin_pts, 5.0)
        self.assertEqual(len(r.bottleneck_contenders), 1)

    def test_the_caveat_says_which_case_it_is(self):
        # This fixture has now been cured TWICE by reality-check fixes: google_maps (2.7 pts, 4
        # contenders) -> kv_store -> iot_platform, the current tightest non-tie. Each repoint is a
        # blueprint that stopped presenting a coin-flip as a determination, so repoint again rather
        # than ever loosening the assertion.
        from keystone.blueprint_library import library
        close = simulate(next(e for e in library() if e.key == "iot_platform").build())
        clear = simulate(next(e for e in library() if e.key == "ride_sharing").build())
        self.assertIn("CANDIDATE, NOT A DETERMINATION", " ".join(close.caveats))
        self.assertNotIn("CANDIDATE, NOT A DETERMINATION", " ".join(clear.caveats))
        self.assertIn("wide enough that the ordering survives", " ".join(clear.caveats))

    def test_the_margin_is_arithmetic_over_the_two_top_utilisations(self):
        """No new source of truth — it reduces to the component results the engine already produced."""
        from keystone.blueprint_library import library
        for key in ("google_maps", "ride_sharing", "youtube"):
            with self.subTest(key):
                r = simulate(next(e for e in library() if e.key == key).build())
                us = sorted((c.utilization for c in r.components.values()), reverse=True)
                self.assertAlmostEqual(r.bottleneck_margin_pts, (us[0] - us[1]) * 100.0, places=9)


class TailModelIsDerivedNotAssumedTest(unittest.TestCase):
    """Percentiles used to be `mean x ln(2)/ln(20)/ln(100)`, so p99/p50 was the constant 6.6439 for
    every design at every load — the percentiles carried no information the mean did not. They are
    now read off the M/M/c sojourn distribution, with optional hops enumerated as a mixture because
    a visit_prob < 1 makes the path bimodal.
    """

    def test_the_incomplete_gamma_matches_its_closed_forms(self):
        """P(1,x) = 1-e^-x and P(2,x) = 1-(1+x)e^-x. If this is wrong, every percentile is wrong."""
        from keystone.simulation import _gammp
        for x in (0.5, 1.0, 2.0, 4.6051701859880914):
            self.assertAlmostEqual(_gammp(1.0, x), 1.0 - math.exp(-x), places=10)
        for x in (1.0, 3.0, 7.0):
            self.assertAlmostEqual(_gammp(2.0, x), 1.0 - (1.0 + x) * math.exp(-x), places=10)

    def test_single_server_variance_is_the_exponential(self):
        """Var = mean^2 at c=1 — the case the old model had right must stay right."""
        from keystone.simulation import _mmc_sojourn_ms, _mmc_sojourn_var_ms2
        for rho in (0.1, 0.5, 0.85, 0.95):
            with self.subTest(rho=rho):
                mean = _mmc_sojourn_ms(10.0, 1, rho)
                self.assertAlmostEqual(_mmc_sojourn_var_ms2(10.0, 1, rho), mean * mean, places=6)

    def test_a_single_exponential_hop_still_gives_the_old_multipliers(self):
        """The old constants were the EXACT answer for one M/M/1 hop. Reproduce them, or the new
        model has broken the one case the old one got right."""
        from keystone.simulation import _path_percentiles_ms
        mean = 20.0                                     # S=10, rho=0.5 -> exponential, var = mean^2
        p50, p95, p99 = _path_percentiles_ms([(mean, mean * mean, 1.0)])
        self.assertAlmostEqual(p50, mean * math.log(2), delta=mean * 1e-3)
        self.assertAlmostEqual(p95, mean * math.log(20), delta=mean * 1e-3)
        self.assertAlmostEqual(p99, mean * math.log(100), delta=mean * 1e-3)

    def test_more_equal_hops_tighten_the_tail(self):
        """Averaging independent delays is self-cancelling — the physics the old constant denied."""
        from keystone.simulation import _path_percentiles_ms
        ratios = []
        for n in (1, 2, 5):
            p50, _, p99 = _path_percentiles_ms([(10.0, 100.0, 1.0)] * n)
            ratios.append(p99 / p50)
        self.assertGreater(ratios[0], ratios[1])
        self.assertGreater(ratios[1], ratios[2])
        self.assertAlmostEqual(ratios[0], math.log(100) / math.log(2), delta=0.02)

    def test_a_rare_slow_hop_is_modelled_as_a_mixture_not_a_blur(self):
        """The defect that forced the mixture: pooling mean+variance across a 2%-chance 151ms hop
        gave a p50 of 0.07ms when the truth is ~3.4ms. Verified against a 200k Monte Carlo of the
        exact sojourn (p50 3.375, p95 11.668, p99 104.985) — the values below are the engine's."""
        from keystone.blueprint_library import library
        r = simulate(next(e for e in library() if e.key == "code_editor").build())
        self.assertAlmostEqual(r.p50_ms, 3.375, delta=0.35)     # MC 3.375
        self.assertAlmostEqual(r.p95_ms, 11.668, delta=1.2)     # MC 11.668
        self.assertAlmostEqual(r.p99_ms, 104.985, delta=12.0)   # MC 104.985
        # and it must NOT be the old answer, which was 69% low here
        self.assertGreater(r.p99_ms, 60.0, "the old fixed multiplier gave 32.9 on this path")

    def test_the_shape_is_no_longer_a_constant_across_the_library(self):
        from keystone.blueprint_library import library
        ratios = {round(simulate(e.build()).p99_ms / simulate(e.build()).p50_ms, 2)
                  for e in library() if simulate(e.build()).p50_ms > 0}
        self.assertGreater(len(ratios), 20, "p99/p50 was the single constant 6.64 for all 56")

    def test_percentiles_stay_ordered_and_finite_everywhere(self):
        from keystone.blueprint_library import library
        for e in library():
            with self.subTest(e.key):
                r = simulate(e.build())
                self.assertLessEqual(r.p50_ms, r.p95_ms)
                self.assertLessEqual(r.p95_ms, r.p99_ms)
                self.assertTrue(math.isfinite(r.p99_ms))
                self.assertGreaterEqual(r.p50_ms, 0.0)
