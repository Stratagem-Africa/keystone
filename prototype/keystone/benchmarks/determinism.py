"""Cross-process determinism digest for the engine (prior art: madsim/RisingWave DST, docs/13).

A stable fingerprint of `simulate()`'s output over the whole reference corpus. `scripts/check.sh`
runs this in TWO processes with different `PYTHONHASHSEED`; if the digests differ, some hash-order
or iteration nondeterminism has leaked into the engine path. The lesson borrowed from deterministic
simulation testing: **determinism rots silently — gate it, don't assert it.** An in-process
"run twice" check (see `tests/test_simulation.py`) cannot catch cross-process hash-seed effects;
this can.

The engine MUST be a pure function of its inputs ("same corpus + seed -> same result",
docs/04; CLAUDE.md). This module only READS engine output to fingerprint it — it produces no
metric of its own (prime directive).
"""
from __future__ import annotations

import hashlib

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.simulation import simulate


def corpus_digest() -> str:
    """A sha256 over every reference model's full simulation result, in a stable order."""
    lines: list[str] = []
    for key, build_fn, _ref_rps in REFERENCE_MODELS:  # build_fn is a 0-arg thunk; rps is baked in
        sim = simulate(build_fn())
        comps = ";".join(
            f"{cid}={r.utilization:.9g}/{r.mean_latency_ms:.9g}/{r.arrival_rps:.9g}"
            for cid, r in sorted(sim.components.items())
        )
        lines.append(
            f"{key}|bn={sim.bottleneck_id}|rho={sim.bottleneck_utilization:.9g}"
            f"|bp_safe={sim.breakpoint_rps_safe:.9g}|bp_theo={sim.breakpoint_rps_theoretical:.9g}"
            f"|p50={sim.p50_ms:.9g}|p95={sim.p95_ms:.9g}|p99={sim.p99_ms:.9g}"
            f"|cost={sim.monthly_cost:.9g}|spofs={sorted(sim.spofs)}|{comps}"
        )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


if __name__ == "__main__":
    print(corpus_digest())
