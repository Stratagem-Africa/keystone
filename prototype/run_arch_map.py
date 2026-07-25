"""Demo: render a validated design as an interactive, engine-driven architecture map.

    build model -> ground with cited evidence -> simulate (the engine owns every number) ->
    serialise (model + result) -> write a self-contained interactive HTML you can open in any browser.

Every RESULT number is engine-computed; inputs are declared and, where the curated KB has cited
evidence, carry GROUNDED / RECONCILE provenance. Each node also shows the engine's bottleneck / SPOF /
saturation states, the L0 label, the high-stakes flag, and a mandatory "where this is wrong" panel.
Offline, $0, deterministic (no LLM — grounding is the curated, cited corpus).

Run from prototype/:  python3 run_arch_map.py   ->   outputs/<name>_map.html
"""
from __future__ import annotations

import os

from keystone.arch_map import build_arch_map, render_html
from keystone.blueprints import payments, url_shortener
from keystone.confidence_bands import simulate_with_confidence
from keystone.grounding import ground_model
from keystone.knowledge_base import make_knowledge_base

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "outputs")

# (name, model-builder) pairs the demo renders. url_shortener is the primary showcase; payments adds
# the high-stakes banner. A module constant so the golden test renders EXACTLY what main() writes
# (same grounding + confidence path) — no drift between the demo and the committed golden.
DEMOS = (
    ("url_shortener", lambda: url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)),
    ("payments", lambda: payments.build()),
)


def render_map(builder):
    """Ground with the CURATED KB (cited evidence, deterministic, no LLM — the same pathway the report
    uses), propagate confidence bands, then serialise to HTML. Grounding is evidence-only: it changes no
    computed number, it only lights up the GROUNDED / RECONCILE provenance the map displays.
    Returns (model, sim, html)."""
    model = ground_model(builder(), make_knowledge_base("curated"))
    sim = simulate_with_confidence(model)
    return model, sim, render_html(build_arch_map(model, sim))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    print("=" * 74)
    print("KEYSTONE — interactive architecture maps (engine-driven, self-contained)")
    print("=" * 74)
    for name, builder in DEMOS:
        model, sim, html = render_map(builder)
        with open(os.path.join(OUT, f"{name}_map.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  {model.name}: bottleneck {sim.bottleneck_name} "
              f"({sim.bottleneck_utilization * 100:.0f}% util) -> outputs/{name}_map.html")
    print("-" * 74)
    print("Open the .html in a browser. Every RESULT is engine-computed; inputs are declared and cited. "
          "Hover a node to trace its flows, click for provenance, read 'Where this is wrong'.")


if __name__ == "__main__":
    main()
