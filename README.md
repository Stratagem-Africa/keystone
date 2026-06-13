# Keystone

*Describe what you're building in plain English — a grounded consensus of AI architects designs it, justifies every decision, and validates it with simulation.*

Takes a builder from **intent → validated design**. The simulation engine is deterministic math (free, no AI); the council reasons about design and never emits a number. See `CLAUDE.md` for the working contract and `docs/` for the full spec.

## Quick start

```bash
cd prototype
python3 run_url_shortener.py                 # the loop -> outputs/url_shortener_report.md
python3 -m unittest discover -s tests -v     # 7 engine tests
```

No dependencies, no API key needed to run the engine. Status: **Phase 0 complete** (engine + loop running; council stubbed). Next: real Claude council + the LLM ingestion layer.

## Docs

`docs/product-definition.md` · `00`–`06` (README, PRD, architecture, accuracy charter, functional spec, data model, roadmap).
