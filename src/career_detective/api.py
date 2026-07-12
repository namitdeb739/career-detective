"""HTTP API for career-detective.

Wraps job_matching.search_jobs() (the ML-based ranking engine) behind a
POST endpoint the Vite frontend calls once the quiz finishes.

Run with:  just api   (or: uv run uvicorn career_detective.api:app --reload)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from career_detective.job_matching import search_jobs

# The experience matcher is the single-source module in scripts/ (not a
# package); make it importable without duplicating it into the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from match_experiences import match_from_job_records

app = FastAPI(title="career-detective API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class JobMatchRequest(BaseModel):
    filters: dict[str, dict[str, Any]]
    top_k: int = 5


# The quiz's answer vocabulary doesn't always match the literal strings
# job_matching's alias tables expect (5 company-size tiers vs. its 3,
# "onsite" vs. "On-site", etc.). Map to values it actually recognizes;
# values with no honest equivalent (e.g. "flexible", "European Union") are
# dropped so that field is left unfiltered rather than silently scored
# against the wrong thing.
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
    # search_jobs only supports an exact single-country match; "European
    # Union" and "Global" have no literal equivalent in the Country column.
    "country": {"Germany": "Germany", "United States": "United States"},
}


def adapt_filters(filters: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Translate quiz-vocabulary filter values into dataset-vocabulary
    values job_matching understands, dropping fields with no honest match."""
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
    """Coerce a pandas/numpy scalar to a JSON-safe native Python value."""
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


@app.post("/api/jobs")
def match_jobs(request: JobMatchRequest) -> dict[str, Any]:
    filters = adapt_filters(request.filters)
    results = search_jobs(filters, top_k=request.top_k, max_per_company=1)

    jobs = []
    for row in results:
        match_score = _clean(row.get("match_score"))
        jobs.append(
            {
                "title": _clean(row.get("Job Title")),
                "company": _clean(row.get("Company Name")),
                "country": _clean(row.get("Country")),
                "industry": _clean(row.get("Industry")),
                "salary": _clean(row.get("salary_mid_eur")),
                "currency": "EUR",
                "match": round(match_score * 100) if match_score is not None else None,
            }
        )

    # Match real TUM experiences against exactly these jobs. Use the *raw*
    # answer set (not adapt_filters' job-dataset-narrowed values) so intent
    # like country=Japan survives to reach cultural clubs.
    matched = match_from_job_records(results, request.filters, top=request.top_k)
    experiences = [
        {"name": e["name"], "skills": e["skills"], "description": e["description"]}
        for e in matched["experiences"]
    ]
    return {"jobs": jobs, "experiences": experiences}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
