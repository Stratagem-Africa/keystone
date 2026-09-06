"""Emit a k6 load-test plan whose thresholds ARE the engine's predictions.

This is the artifact that closes Keystone's loop, and the one thing in this space nobody else can
emit: a load test can only assert a threshold if something made a falsifiable prediction first. The
engine predicts p95 latency and a breakpoint; this turns those predictions into k6 `thresholds`, so
running the test **tries to prove the engine wrong**. What comes back feeds `actuals.py` /
`reconciliation.py`, which is the L0 (Directional) → L1 (Calibrated) path in docs/03.

Design rules, each of them load-bearing:

* **Deterministic renderer, never an LLM.** Generated code is exactly where a model would be tempted
  to invent a threshold, and a number in a generated file looks every bit as authoritative as a
  number in the report. This module is a string template over engine output.
* **Every numeric literal is declared.** The emitted script opens with a PROVENANCE block mapping
  each literal to its origin — an engine `Metric` key, or a NAMED_CONSTANT with a stated reason. A
  test asserts the literals in the body are exactly the set the header declares, so an undeclared
  number cannot survive review.
* **Say what the test cannot prove.** k6's `http_req_duration` is client-observed wall time — it
  includes DNS, TCP, TLS and the network path. The engine's p95 is a modelled sum of per-component
  service times with **no network and no client** in it. They are not the same quantity, and feeding
  one to the other as if they were would manufacture DIVERGE verdicts that are not model error. The
  emitted header says so, and `EMITTER_LIMITS` carries it to any caller.

Prime directive: the engine already computed these numbers; this module only formats them. It
derives no metric of its own — the one arithmetic step (Little's Law for VU sizing) is applied to
the engine's own predicted latency and is declared as such in the provenance block.
"""
from __future__ import annotations

import json
import math
import re
import textwrap
from dataclasses import dataclass

from .model import SystemModel
from .simulation import SAFE_UTILIZATION, SimulationResult

__all__ = ["K6Plan", "EMITTER_LIMITS", "build_plan", "render_k6"]

# k6 v2 removed the legacy summary mode and `--no-summary`; `handleSummary()` is the documented,
# stable way to get machine-readable output, so the emitted script writes summary.json itself.
K6_SUPPORTED = ">=0.50 <3"

EMITTER_LIMITS: tuple[str, ...] = (
    "k6 measures http_req_duration as CLIENT-OBSERVED wall time — DNS, TCP, TLS, the network path "
    "and any proxy are all inside it. The engine's p95 is a modelled sum of per-component service "
    "times with no network and no client. Treat a gap as 'the model omits the network' before "
    "treating it as model error; the two are not the same quantity.",
    "Thresholds are the engine's steady-state prediction. k6 ramps, and a cold cache, a JIT warm-up "
    "or an autoscaler still scaling will all fail a threshold that the design would meet warm.",
    "One scenario per flow drives each flow independently at its share of system load. That "
    "reproduces the modelled MIX, not real arrival correlation — real traffic bursts together.",
    "The engine models capacity, not correctness. A passing run says the shape held under this "
    "load; it says nothing about whether the responses were right.",
    "Endpoints are placeholders. Nothing in the canonical model records a URL, so the emitted "
    "script cannot know what to call — you must fill in the paths before it runs.",
)


@dataclass(frozen=True)
class Literal:
    """One numeric literal in the emitted script, and where it came from."""
    name: str
    value: float
    source: str          # an engine Metric key, or NAMED_CONSTANT
    why: str


@dataclass(frozen=True)
class K6Plan:
    """The plan, separated from its rendering so both are testable."""
    model_name: str
    system_rps: float
    duration_s: int
    scenarios: tuple[dict, ...]
    thresholds: dict
    literals: tuple[Literal, ...]

    def declared(self) -> dict[str, float]:
        return {lit.name: lit.value for lit in self.literals}


def _round(x: float, places: int = 2) -> float:
    return float(f"{x:.{places}f}")


def build_plan(model: SystemModel, sim: SimulationResult, *, duration_s: int = 60) -> K6Plan:
    """Turn an engine result into a k6 plan. Every figure here is read off `sim`."""
    literals: list[Literal] = [
        Literal("DURATION_S", float(duration_s), "NAMED_CONSTANT",
                "test length; long enough to pass a ramp, short enough to iterate"),
        Literal("ERROR_RATE_CEILING", 0.01, "NAMED_CONSTANT",
                "1% — a conventional smoke ceiling, NOT an engine prediction"),
        Literal("VU_SAFETY", 1.5, "NAMED_CONSTANT",
                "headroom on maxVUs so k6 itself is not the bottleneck"),
        # Declared rather than inlined so the rule stays absolute: EVERY number in the emitted body
        # has a provenance entry. An exception list is where an invented threshold would hide.
        Literal("HTTP_OK_MIN", 200.0, "NAMED_CONSTANT", "HTTP 2xx lower bound — protocol, not a prediction"),
        Literal("HTTP_OK_MAX", 300.0, "NAMED_CONSTANT", "HTTP 2xx upper bound — protocol, not a prediction"),
        Literal("JSON_INDENT", 2.0, "NAMED_CONSTANT", "summary.json formatting only"),
    ]

    scenarios: list[dict] = []
    # Threshold EXPRESSIONS, not literals: each references the const declared above, so every
    # number in the emitted file has exactly one definition and one provenance entry.
    thresholds: dict = {
        "http_req_failed": ["rate<${ERROR_RATE_CEILING}"],
        # The headline prediction the whole plan exists to test.
        "http_req_duration": ["p(95)<${SYSTEM_P95_MS}"],
    }
    literals.append(Literal("SYSTEM_P95_MS", _round(sim.p95_ms), "p95_ms",
                            "engine prediction for the dominant flow — the headline assertion"))

    by_name = {f.name: f for f in sim.flow_latencies}
    for flow in model.flows:
        rate = model.workload.system_rps * flow.share
        fl = by_name.get(flow.name)
        p95 = _round(fl.p95_ms) if fl else _round(sim.p95_ms)
        # Little's Law on the engine's OWN predicted latency: concurrency = arrival rate x time in
        # system. k6 requires preAllocatedVUs, and this is the only honest source for it.
        mean_s = (fl.mean_ms if fl else sim.mean_latency_ms) / 1000.0
        pre = max(1, math.ceil(rate * mean_s))
        mx = max(pre, math.ceil(rate * (p95 / 1000.0) * 1.5))
        key = "".join(ch if ch.isalnum() else "_" for ch in flow.name).strip("_").lower() or "flow"
        scenarios.append({
            "key": key,
            "flow": flow.name,
            "rate": _round(rate),
            "preAllocatedVUs": pre,
            "maxVUs": mx,
            "p95_ms": p95,
        })
        literals += [
            Literal(f"RATE_{key.upper()}", _round(rate), "workload.system_rps x flow.share",
                    f"offered load for the '{flow.name}' flow"),
            Literal(f"P95_{key.upper()}_MS", p95, f"flow_latencies[{flow.name}].p95_ms",
                    "engine prediction for this flow"),
            Literal(f"PREVUS_{key.upper()}", float(pre), "Little's Law on mean_ms",
                    "concurrency = rate x engine-predicted time in system"),
            Literal(f"MAXVUS_{key.upper()}", float(mx), "Little's Law on p95_ms x VU_SAFETY",
                    "upper bound so k6 is not the constraint"),
        ]
        thresholds[f"http_req_duration{{scenario:{key}}}"] = ["p(95)<${P95_" + key.upper() + "_MS}"]

    literals.append(Literal("BREAKPOINT_SAFE_RPS", _round(sim.breakpoint_rps_safe),
                            "breakpoint_rps_safe",
                            f"engine's safe ceiling at {SAFE_UTILIZATION:.0%} utilisation — "
                            f"recorded for the operator, not asserted"))

    return K6Plan(
        model_name=model.name,
        system_rps=model.workload.system_rps,
        duration_s=duration_s,
        scenarios=tuple(scenarios),
        thresholds=thresholds,
        literals=tuple(literals),
    )


def render_k6(plan: K6Plan, *, base_url: str = "http://localhost:8080") -> str:
    """Render the k6 script. Pure string formatting over `plan`."""
    prov = "\n".join(
        f" *   {lit.name:<28} = {lit.value:<14g} <- {lit.source}  ({lit.why})"
        for lit in plan.literals)
    # Wrapped so the header stays readable AND valid: an unwrapped limit line can be 300 chars.
    limits = "\n".join(
        " *   - " + textwrap.indent(textwrap.fill(line, 92), " *     ").lstrip(" *")
        for line in EMITTER_LIMITS)

    consts = "\n".join(f"const {lit.name} = {lit.value:g};" for lit in plan.literals)

    scen = ",\n".join(
        f"""    {s['key']}: {{
      executor: "constant-arrival-rate",
      rate: RATE_{s['key'].upper()},
      timeUnit: "1s",
      duration: `${{DURATION_S}}s`,
      preAllocatedVUs: PREVUS_{s['key'].upper()},
      maxVUs: MAXVUS_{s['key'].upper()},
      exec: "journey_{s['key']}",
      tags: {{ scenario: "{s['key']}" }},
    }}""" for s in plan.scenarios)

    # json.dumps already emits a valid JS object literal — double quotes are legal JavaScript.
    # An earlier version post-processed this to prettify the quotes and produced 'rate<0.01"
    # (opening single, closing double), i.e. broken JS. Never regex-edit generated syntax.
    # Rendered as backtick template literals so the ${CONST} references resolve at runtime.
    body = json.dumps(plan.thresholds, indent=2)
    body = re.sub(r'"((?:rate|p\(95\))<\$\{[A-Z0-9_]+\})"', r"`\1`", body)
    thresholds = textwrap.indent(body, "  ").lstrip()

    # Every exec function is prefixed. A flow slugged `check` would otherwise redeclare k6's own
    # imported `check`, and a slug starting with a digit is not a valid identifier at all — both
    # emit a file that will not parse. Caught by the syntax test, not by review.
    funcs = "\n\n".join(
        f"""export function journey_{s['key']}() {{
  // TODO: point this at the real endpoint for the '{s['flow']}' journey.
  const res = http.get(`${{BASE_URL}}/{s['key']}`);
  check(res, {{ "status is 2xx": (r) => r.status >= HTTP_OK_MIN && r.status < HTTP_OK_MAX }});
}}""" for s in plan.scenarios)

    return f"""/*
 * k6 load-test plan for: {plan.model_name}
 *
 * GENERATED by keystone/loadtest.py — a deterministic renderer, no LLM. Do not hand-edit the
 * thresholds: they are the engine's predictions, and the point of this file is to try to prove
 * them wrong. Re-generate it when the design changes.
 *
 * k6 {K6_SUPPORTED}.   Run:  k6 run this-file.js
 *
 * PROVENANCE — every numeric literal below, and where it came from:
{prov}
 *
 * WHAT THIS TEST CANNOT PROVE:
{limits}
 *
 * A threshold breach is EVIDENCE, not a verdict. Feed summary.json back through
 * keystone.actuals to reconcile it against the prediction.
 */

import http from "k6/http";
import {{ check }} from "k6";

const BASE_URL = __ENV.BASE_URL || "{base_url}";

{consts}

export const options = {{
  scenarios: {{
{scen}
  }},
  thresholds: {thresholds},
}};

{funcs}

// k6 v2 removed the legacy summary mode; handleSummary is the documented machine-readable path.
export function handleSummary(data) {{
  return {{ "summary.json": JSON.stringify(data, null, JSON_INDENT) }};
}}
"""
