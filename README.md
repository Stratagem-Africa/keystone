# Keystone

*Describe what you're building in plain English — a grounded consensus of AI architects designs it, justifies every decision, and validates it with simulation.*

Takes a builder from **intent → validated design**. The simulation engine is deterministic math (free, no AI); the council reasons about design and never emits a number. See `CLAUDE.md` for the working contract and `docs/` for the full spec.

## Run it (Stratagem staff)

**macOS — a Dock icon:**

```bash
./scripts/make-mac-app.sh     # builds Keystone.app; double-click it from then on
```

**Any platform — a command:**

```bash
./scripts/keystone-local.sh            # your own Claude subscription drives the council
./scripts/keystone-local.sh --offline  # no AI at all — engine + 56 reference designs, $0
```

Either way it opens **http://127.0.0.1:3000/studio** in your browser, and it is the **same app** —
the same Next.js frontend the web build serves, pixel for pixel. `Keystone.app` is a thin launcher
pointing at this checkout, not a copy and not a second UI: `git pull` updates it, and there is no
second interface to keep in sync because there isn't a second interface.
No account, no API key, no Supabase project needed — the app runs without any of them.

**Why a local run and not a website.** The council can run on Claude Code's CLI (`claude -p`),
which means it runs on *your* subscription: nothing to bill, no key to manage. That only works
because the CLI is a program on your laptop. A hosted site cannot reach it — a server calling
`claude -p` would be running one account and answering everyone's requests, which is account
sharing whoever the users are. `llm_cli._refuse_if_served()` fails closed on exactly that, and
`scripts/keystone-local.sh` is the only place the documented local override is set, after proving
the bind address is loopback.

Missing the CLI? `--offline` still gives you the whole engine and all 56 reference architectures
with every number computed and cited. The AI is what explains a design; it never produces a figure.

## Engine only

```bash
cd prototype
python3 run_url_shortener.py                 # the loop -> outputs/url_shortener_report.md
python3 -m unittest discover -s tests -v     # the engine suite
../scripts/check.sh                          # the merge gate (Python + frontend)
```

No dependencies and no API key needed to run the engine.

## Docs

`docs/product-definition.md` · `00`–`06` (README, PRD, architecture, accuracy charter, functional spec, data model, roadmap).
