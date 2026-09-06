"""Author and gate library blueprints.

    python3 run_blueprint_tool.py price    <file.json>   # fill costs from the GROUNDED catalogue
    python3 run_blueprint_tool.py validate <file.json>   # the gate one blueprint must pass
    python3 run_blueprint_tool.py check-all              # gate the whole library
    python3 run_blueprint_tool.py list                   # what is in the library today

`price` exists so nobody — human or model — hand-types a cost. It reads each component's instance
class (or the documented default for its kind), takes the cited price from
`benchmarks/compute_prices.json`, and attaches the citation as a `Grounding`. Kinds with no
per-instance price (API gateway, object store, CDN, load balancer) are left at zero ON PURPOSE and
reported, because inventing a per-instance number for them would be wrong in a way that compounds:
`model.py` multiplies cost by instance count.
"""
from __future__ import annotations

import json
import pathlib
import sys

from keystone.blueprint_library import LIBRARY_DIR, library, validate_library_entry
from keystone.export import from_dict, to_dict
from keystone.model import ComponentKind
from keystone.pricing_catalogue import (
    KINDS_WITHOUT_PER_INSTANCE_PRICE, default_price_for_kind, grounding_for, price_for,
)


def _price(path: pathlib.Path) -> int:
    payload = json.loads(path.read_text(encoding="utf8"))
    meta = payload.get("_library")
    model = from_dict(payload)

    priced = skipped = 0
    for comp in model.components.values():
        if comp.kind.value in KINDS_WITHOUT_PER_INSTANCE_PRICE:
            skipped += 1
            continue
        cls = comp.match_context.get("instance_class")
        row = price_for(comp.kind, cls) if cls else None
        row = row or default_price_for_kind(comp.kind)
        if row is None:
            skipped += 1
            continue
        comp.monthly_cost_per_instance = row.monthly_cents
        comp.match_context = {**comp.match_context, "instance_class": row.instance_class}
        comp.groundings = {**comp.groundings, "monthly_cost_per_instance": grounding_for(row)}
        comp.provenance = "GROUNDED"
        priced += 1

    out = to_dict(model)
    if meta is not None:
        out["_library"] = meta
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf8")
    print(f"priced {priced} component(s) from the grounded catalogue; "
          f"{skipped} left at 0 (no per-instance price for that kind)")
    return 0


def _validate(path: pathlib.Path) -> int:
    report = validate_library_entry(path)
    print(report.summary_line())
    if not report.ok:
        for f in report.failures:
            print(f"    - {f}")
    return 0 if report.ok else 1


def _check_all() -> int:
    paths = sorted(LIBRARY_DIR.glob("*.json")) if LIBRARY_DIR.is_dir() else []
    if not paths:
        print(f"no blueprints in {LIBRARY_DIR}")
        return 0
    bad = 0
    for p in paths:
        report = validate_library_entry(p)
        print(report.summary_line())
        if not report.ok:
            bad += 1
            for f in report.failures:
                print(f"    - {f}")
    print(f"\n{len(paths) - bad}/{len(paths)} valid")
    return 1 if bad else 0


def _list() -> int:
    entries = library()
    print(f"{len(entries)} blueprint(s)")
    for e in entries:
        print(f"  {e.key:<28} {e.category:<16} {e.difficulty:<13} {e.name}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "check-all":
        return _check_all()
    if cmd == "list":
        return _list()
    if cmd in ("price", "validate"):
        if not rest:
            print(f"{cmd} needs a file path", file=sys.stderr)
            return 2
        path = pathlib.Path(rest[0])
        if not path.is_file():
            print(f"no such file: {path}", file=sys.stderr)
            return 2
        return _price(path) if cmd == "price" else _validate(path)
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
