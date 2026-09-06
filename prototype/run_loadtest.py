"""Emit a k6 load-test plan whose thresholds are the engine's predictions.

    python3 run_loadtest.py [reference-name] [--out FILE] [--base-url URL] [--duration N]

The emitted script tries to prove the engine WRONG. Run it against a real deployment, then feed
summary.json back through `keystone.actuals` to reconcile measurement against prediction — that is
the L0 (Directional) → L1 (Calibrated) path in docs/03.
"""
from __future__ import annotations

import argparse
import sys

from _env import load_env
from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.loadtest import EMITTER_LIMITS, build_plan, render_k6
from keystone.simulation import simulate


def main(argv: list[str] | None = None) -> int:
    load_env()
    names = {n: b for n, b, _r in REFERENCE_MODELS}
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reference", nargs="?", default="url_shortener",
                    help=f"one of: {', '.join(sorted(names))}")
    ap.add_argument("--out", default=None, help="write here instead of stdout")
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--duration", type=int, default=60)
    args = ap.parse_args(argv)

    if args.reference not in names:
        print(f"unknown reference {args.reference!r}. Known: {', '.join(sorted(names))}",
              file=sys.stderr)
        return 2

    model = names[args.reference]()
    sim = simulate(model)                       # the engine is the sole source of every threshold
    script = render_k6(build_plan(model, sim, duration_s=args.duration), base_url=args.base_url)

    if args.out:
        with open(args.out, "w", encoding="utf8") as fh:
            fh.write(script)
        print(f"wrote {args.out}  ({model.name}: p95 {sim.p95_ms:.1f}ms, "
              f"safe breakpoint {sim.breakpoint_rps_safe:,.0f} rps)")
        print("\nWhat this test cannot prove:")
        for limit in EMITTER_LIMITS:
            print(f"  - {limit}")
    else:
        print(script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
