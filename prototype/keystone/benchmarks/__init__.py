"""Benchmark corpus: SysSimulator's documented blueprints as Keystone's ground-truth
eval library (Accuracy Charter, Doc 03 §4). The end goal (per Adam): Keystone is
validated against every design challenge SysSimulator has already documented."""
from keystone.benchmarks.syssimulator_blueprints import (
    BLUEPRINTS, in_scope, out_of_scope, summary,
)

__all__ = ["BLUEPRINTS", "in_scope", "out_of_scope", "summary"]
