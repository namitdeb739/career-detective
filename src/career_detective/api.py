"""HTTP API for career-detective.

Wraps job_matching.search_jobs() and match_experiences.match_from_job_records()
behind a single POST /api/search endpoint.

Run with:  just api   (or: uv run uvicorn career_detective.api:app --reload --port 8000)
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from career_detective.job_matching import search_jobs, warm_model

# The experience matcher lives in scripts/ — make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from match_experiences import match_from_job_records  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm the embedding model at startup so the first request is fast."""
    warm_model()
    yield


app = FastAPI(title="career-detective API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    filters: dict[str, dict[str, Any]]
    top_k: int = 5


# Translate quiz-vocabulary values to dataset-vocabulary values.
# Fields with no honest mapping are dropped so they don't silently
# score against the wrong thing.
FIELD_VALUE_MAPS: dict[str, dict[str, str]] = {
    "company_size": {
        "micro": "small",
        "startup": "small",
        "small_mid": "mid",
        "mid_sized": "mid",
        "mega": "large",
    },
    "work_format": {"onsite": "in-person", "hybrid": "hybrid", "remote": "remote"},
    "experience_level": {"entry": "start", "mid": "mid", "senior": "senior"},
    "education_level": {"bachelor": "bsc", "master": "msc", "phd": "phd"},
    "country": {"Germany": "Germany", "United States": "United States"},
}


def _adapt_filters(filters: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    adapted = {}
    for field, spec in filters.items():
        value_map = FIELD_VALUE_MAPS.get(field)
        data = spec.get("data")
        if value_map is not None:
            data = value_map.get(data)
            if data is None:
                continue
        adapted[field] = {"data": data, "dealBreaker": bool(spec.get("dealBreaker"))}
    return adapted


def _clean(value: Any) -> Any:
    """Coerce pandas/numpy scalars to JSON-safe Python values."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def _clean_row(row: dict) -> dict:
    """Recursively clean all values in a job result dict."""
    return {k: _clean(v) for k, v in row.items() if k not in ("_field_scores",)}


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    adapted = _adapt_filters(request.filters)
    job_records = search_jobs(adapted, top_k=request.top_k, max_per_company=1, max_per_title=1)

    jobs = [_clean_row(row) for row in job_records]

    # Use original filters (not adapted) for club matching so intent like
    # country=Japan still reaches cultural clubs even if the jobs filter dropped it.
    matched = match_from_job_records(
        job_records,
        prefs=None,
        top=max(1, request.top_k - 2),
        broaden=min(2, request.top_k),
    )
    clubs = matched["clubs"]

    return {"jobs": jobs, "clubs": clubs}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
