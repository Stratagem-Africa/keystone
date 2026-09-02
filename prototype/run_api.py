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

Run from prototype/:  python3 run_api.py
"""
from __future__ import annotations

import uvicorn

from _env import load_env


def main() -> None:
    load_env()   # activates the root .env's SUPABASE_URL/etc.; existing env still wins
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
