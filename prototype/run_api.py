"""Dev entrypoint for the FastAPI backend — loads the local .env, then starts uvicorn.

`api/main.py` deliberately never loads .env itself: it's imported directly by the test
suite (`from api.main import app`), and `_env.py`'s own contract is that `load_env()` is
opt-in, called only from a script's `main()`, so importing a module never mutates the
environment (tests inject their own fake SUPABASE_URL per-test instead). This script is
that opt-in call site for real (non-test) use — mirrors run_url_shortener.py /
run_from_note.py's pattern.

Without this, starting the API the "obvious" way (`uvicorn api.main:app`) leaves
SUPABASE_URL unset even when the root .env has real values, and every protected route
fails closed with 401 "auth not configured" (api/auth.py).

Also configures logging so the pipeline's INFO-level output (job completion, LLM
token/cost usage) actually reaches the console. `reload=True` makes uvicorn run the
real server in a SEPARATE subprocess, spawned via `multiprocessing.get_context("spawn")`
(uvicorn always uses "spawn" here, on every OS — see uvicorn/_subprocess.py) — a fresh
interpreter that inherits NOTHING from this process's memory. A plain
`logging.basicConfig()` call in this `main()` therefore only configures the RELOADER
process, which never serves a request or runs a line of pipeline code; it has no effect
on the actual server. `Config.configure_logging()`, by contrast, is called from inside
`subprocess_started()` — literally the target function of that spawned subprocess — so
passing `log_config` through `uvicorn.run()` is what actually reaches the process that
matters. Extending uvicorn's own LOGGING_CONFIG with a "root" logger entry (reusing its
"default" handler) lets every app logger — which propagates up to root by default —
inherit that handler too, without disturbing uvicorn's own formatting.

Run from prototype/:  python3 run_api.py
"""
from __future__ import annotations

import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from _env import load_env


def _log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    config["root"] = {"handlers": ["default"], "level": "INFO"}
    return config


def main() -> None:
    load_env()   # activates the root .env's SUPABASE_URL/etc.; existing env still wins
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True, log_config=_log_config())


if __name__ == "__main__":
    main()
