"""ADR-009 Tier 2 part 2 — AI/LLM per-token cost.

For AI/agent systems the per-token model bill can dominate everything else and was invisible. The
engine adds an "ai" cost line = each component's monthly input/output token volumes × the model's
per-1K-token rates, in integer cents (harm floor, ADR-008). Token volumes default 0, so non-AI models
are byte-for-byte unchanged — that regression guard is here too.
"""
from __future__ import annotations

import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.model import (Component, ComponentKind as K, Flow, FlowStep,
                            PricingRates, SystemModel, Workload)
from keystone.simulation import simulate


def _model(**llm) -> SystemModel:
    # $50/mo compute, plus whatever LLM token volumes the test supplies.
    c = Component("llm", K.APP_SERVER, "LLM", per_instance_rps=1000.0, instances=1,
                  monthly_cost_per_instance=5000, **llm)
    return SystemModel(name="ai", components={"llm": c},
                       flows=[Flow("f", 1.0, [FlowStep("llm")])], workload=Workload(1000.0))


class TestAICost(unittest.TestCase):
    def test_worked_example(self):
        # GROUNDED rates: input $0.50/1M, output $4.00/1M → 10M in = $5.00, 2M out = $8.00, ai $13.00
        sim = simulate(_model(llm_input_tokens_per_month=10_000_000,
                              llm_output_tokens_per_month=2_000_000))
        self.assertEqual(sim.cost_breakdown["ai"], 1300)          # $13.00 (500 + 800)
        self.assertEqual(sim.cost_breakdown["compute"], 5000)     # compute untouched
        self.assertEqual(sim.monthly_cost, 5000 + 1300)
        self.assertIsInstance(sim.cost_breakdown["ai"], int)      # harm floor: integer cents

    def test_output_priced_higher_than_input(self):
        same = 1_000_000
        in_only = simulate(_model(llm_input_tokens_per_month=same)).cost_breakdown["ai"]
        out_only = simulate(_model(llm_output_tokens_per_month=same)).cost_breakdown["ai"]
        self.assertGreater(out_only, in_only)                     # output tokens cost more

    def test_no_tokens_is_no_ai_cost(self):
        sim = simulate(_model())   # no token volumes
        self.assertEqual(sim.cost_breakdown["ai"], 0)
        self.assertEqual(sim.monthly_cost, sim.cost_breakdown["compute"])

    def test_breakdown_sums_to_total(self):
        sim = simulate(_model(llm_input_tokens_per_month=3_210_987,
                              llm_output_tokens_per_month=1_234_567))
        self.assertEqual(sum(sim.cost_breakdown.values()), sim.monthly_cost)

    def test_exact_to_the_cent_no_truncation(self):
        # two components each with tokens → numerator accumulated and divided once (no per-comp bias)
        a = Component("a", K.APP_SERVER, "A", per_instance_rps=1.0, llm_input_tokens_per_month=1)
        b = Component("b", K.APP_SERVER, "B", per_instance_rps=1.0, llm_input_tokens_per_month=1)
        m = SystemModel("ai", {"a": a, "b": b}, [Flow("f", 1.0, [FlowStep("a")])], Workload(1.0))
        # 2 tokens × 500 micro/1k = 1000 micro → rounds to 0 cents, but the SUM path
        # must be exact: assert it equals round((1+1)*500 / (1000*10_000)) == 0 and reconciles.
        sim = simulate(m)
        self.assertEqual(sim.cost_breakdown["ai"], 0)
        self.assertEqual(sum(sim.cost_breakdown.values()), sim.monthly_cost)

    def test_token_volumes_reject_float_and_negative(self):
        for bad in (dict(llm_input_tokens_per_month=1.5),
                    dict(llm_output_tokens_per_month=-1),
                    dict(llm_input_tokens_per_month=True)):
            with self.assertRaises((TypeError, ValueError)):
                Component("c", K.APP_SERVER, "C", per_instance_rps=1.0, **bad)

    def test_rates_reject_float_money(self):
        with self.assertRaises(ValueError):
            PricingRates(llm_input_micro_usd_per_1k_tokens=0.5)
        with self.assertRaises(ValueError):
            PricingRates(llm_output_micro_usd_per_1k_tokens=-1)

    def test_all_reference_models_have_zero_ai_cost(self):
        # no shipped blueprint declares tokens → ai line is 0, totals unchanged (regression guard)
        for key, build_fn, _rps in REFERENCE_MODELS:
            sim = simulate(build_fn())
            self.assertEqual(sim.cost_breakdown["ai"], 0, key)


if __name__ == "__main__":
    unittest.main()
