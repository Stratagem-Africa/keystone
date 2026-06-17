"""Score the deterministic engine against the SysSimulator ground-truth corpus.

Run from prototype/:  python3 run_scoring.py   ->  outputs/engine_scorecard.md
"""
from __future__ import annotations

import os

from keystone.benchmarks.scoring import render_scorecard, score_all

OUT = os.path.join(os.path.dirname(__file__), "outputs", "engine_scorecard.md")


def main() -> None:
    cards = score_all()
    md = render_scorecard(cards)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(md)

    print("=" * 78)
    print("KEYSTONE ENGINE SCORECARD (vs SysSimulator ground truth)")
    print("=" * 78)
    for c in cards:
        v = c.cost_verdict if c.cost_verdict == "in-band" else f"{c.cost_verdict} {c.cost_factor:.1f}x"
        print(f"  {c.name:26s} ${c.cost_engine:>6,.0f}  band ${c.cost_low:,}-{c.cost_high:,}  "
              f"-> {v:10s}  bottleneck={c.bottleneck} ({c.bottleneck_util*100:.0f}%)")
    print("-" * 78)
    in_band = sum(c.cost_verdict == "in-band" for c in cards)
    print(f"cost in-band: {in_band}/{len(cards)}  ·  "
          f"bottleneck ok: {sum(c.bottleneck_ok for c in cards)}/{len(cards)}  ·  "
          f"stable bp: {sum(c.breakpoint_stable for c in cards)}/{len(cards)}  ·  "
          f"deterministic: {sum(c.deterministic for c in cards)}/{len(cards)}")
    print(f"Full scorecard -> outputs/engine_scorecard.md")


if __name__ == "__main__":
    main()
