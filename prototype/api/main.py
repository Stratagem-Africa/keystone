from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import dataclasses
import math
from typing import Optional

from keystone.simulation import simulate
from keystone.council import make_council
from keystone.blueprints.url_shortener import build as build_url_shortener

app = FastAPI(title="Keystone API", version="0.1.0")

# Permissive for local dev — restrict allow_origins before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize(obj):
    # float("inf") is not valid JSON; the simulation produces it when load is zero.
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    return obj


@app.get("/health")
def health():
    return {"status": "ok"}


class DesignRequest(BaseModel):
    system_rps: Optional[float] = 10_000


@app.post("/design")
def design(req: DesignRequest):
    model = build_url_shortener(system_rps=req.system_rps)
    council = make_council()
    adrs = council.design(model)

    # simulate() is the ONLY source of numbers — prime directive.
    sim_result = simulate(model)

    payload = _sanitize({
        "model": model.name,
        "simulation": dataclasses.asdict(sim_result),
        "adrs": [dataclasses.asdict(adr) for adr in adrs],
    })
    return JSONResponse(content=payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
