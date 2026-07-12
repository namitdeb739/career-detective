"""
End-to-end pipeline: filters → jobs → clubs

Chains findJobs.py and match_experiences.py into a single run:
  1. Apply user filters to find the top N jobs via sentence embeddings.
  2. Feed those job IDs into match_clubs() to find matching TUM clubs.
  3. Print (or JSON-dump) the results.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --top-jobs 5 --top-clubs 5
    python scripts/run_pipeline.py --json
    python scripts/run_pipeline.py --top-jobs 10 --top-clubs 8 --broaden 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Resolve project root so the script works from any cwd.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
_JOBS_CSV = _PROJECT_ROOT / "data" / "cleaned" / "jobs_enriched_with_layoffs_complete (1).csv"
_PROCESSED = _PROJECT_ROOT / "data" / "processed"
_ENTITIES_CSV = _PROCESSED / "entities.csv"
_JOB_TAGS_CSV = _PROCESSED / "job_tags.csv"
_PROCESSED_JOBS_CSV = _PROCESSED / "jobs.csv"

# Add scripts/ to sys.path so we can import the sibling modules directly.
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from findJobs import find_top_k_jobs  # noqa: E402
from match_experiences import match_clubs  # noqa: E402

# ---------------------------------------------------------------------------
# Sample filter — edit this dict to try different queries.
# ---------------------------------------------------------------------------
DEFAULT_FILTERS: dict = {
    "title": {"data": "Machine Learning Engineer", "dealBreaker": False},
    "domain": {"data": "Deep Learning", "dealBreaker": False},
    "country": {"data": "Germany", "dealBreaker": True},
}


def run_pipeline(
    filters: dict,
    top_jobs: int = 5,
    top_clubs: int = 5,
    emit_json: bool = False,
) -> dict:
    """
    Run the full filters → jobs → clubs pipeline.

    Parameters
    ----------
    filters : dict
        Job-filter dict in the findJobs format.
    top_jobs : int
        Number of top jobs to surface.
    top_clubs : int
        Total number of clubs to return (mix of direct + broaden tracks).
    emit_json : bool
        If True, print JSON and return the raw dict.
        If False, print a human-readable report.

    Returns
    -------
    dict with keys "jobs", "clubs".
    """
    # ---- Load data ----
    if not _JOBS_CSV.exists():
        sys.exit(
            f"ERROR: jobs CSV not found at {_JOBS_CSV}\n"
            "Make sure the cleaned dataset is present."
        )

    cleaned_jobs = pd.read_csv(_JOBS_CSV)
    processed_jobs = pd.read_csv(_PROCESSED_JOBS_CSV)
    job_tags = pd.read_csv(_JOB_TAGS_CSV)
    entities = pd.read_csv(_ENTITIES_CSV)

    # ---- Step 1: find top jobs ----
    ranked_jobs = find_top_k_jobs(cleaned_jobs, filters, top_k=top_jobs, max_per_company=1, max_per_title=1)

    if not ranked_jobs:
        print("No jobs matched the given filters.", file=sys.stderr)
        return {"jobs": [], "direct_clubs": [], "broaden_clubs": []}

    # ---- Step 2: map job results to processed job IDs ----
    # cleaned dataset and processed/jobs.csv share the same job ordering;
    # we match on title + company to find the corresponding job_id.
    job_ids = _resolve_job_ids(ranked_jobs, processed_jobs)

    # ---- Step 3: match clubs (3 direct + 2 broaden, guaranteed split) ----
    n_direct = max(1, top_clubs - 2)
    n_broaden = top_clubs - n_direct
    direct_clubs, broaden_clubs = match_clubs(
        job_ids,
        processed_jobs,
        job_tags,
        entities,
        top=n_direct,
        broaden=n_broaden,
    )

    # Combine: direct first, then broaden picks (broaden is already seeded to
    # avoid direct picks, so no deduplication needed in practice).
    direct_ids = {c["entity_id"] for c in direct_clubs}
    clubs = direct_clubs + [c for c in broaden_clubs if c["entity_id"] not in direct_ids]

    # ---- Assemble output ----
    job_summary = [
        {
            "job_id": jid,
            "title": str(j.get("Job Title", "")),
            "company": str(j.get("Company Name", "")),
            "country": str(j.get("Country", "")),
            "skills": str(j.get("Required Skills", "")),
            "match_score": round(float(j.get("match_score", 0.0)), 4),
        }
        for jid, j in zip(job_ids, ranked_jobs)
    ]

    result = {
        "jobs": job_summary,
        "clubs": clubs,
    }

    if emit_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_report(filters, result)

    return result


def _resolve_job_ids(ranked_jobs: list[dict], processed_jobs: pd.DataFrame) -> list[str]:
    """Match ranked (cleaned) jobs back to processed/jobs.csv job_id values.

    Matching strategy: case-insensitive title equality. If a title appears
    multiple times, prefer the one whose company also matches. Falls back to
    sequential job_ids (job-0, job-1, …) if no match is found.
    """
    job_ids: list[str] = []
    title_idx: dict[str, list[str]] = {}
    for _, row in processed_jobs.iterrows():
        t = str(row["title"]).strip().lower()
        title_idx.setdefault(t, []).append(str(row["job_id"]))

    # Build a (title, company) → job_id lookup for tie-breaking.
    title_company_idx: dict[tuple[str, str], str] = {}
    for _, row in processed_jobs.iterrows():
        key = (str(row["title"]).strip().lower(), str(row["company"]).strip().lower())
        title_company_idx[key] = str(row["job_id"])

    for i, job in enumerate(ranked_jobs):
        title = str(job.get("Job Title", "")).strip().lower()
        company = str(job.get("Company Name", "")).strip().lower()
        key = (title, company)

        if key in title_company_idx:
            job_ids.append(title_company_idx[key])
        elif title in title_idx and title_idx[title]:
            job_ids.append(title_idx[title][0])
        else:
            # Fallback: use positional job_id (job-0, job-1, …).
            job_ids.append(f"job-{i}")

    return job_ids


def _print_report(filters: dict, result: dict) -> None:
    rule = "=" * 70
    thin = "-" * 70

    print(f"\n{rule}")
    print("CAREER DETECTIVE — END-TO-END PIPELINE RESULTS")
    print(rule)

    print("\nFILTERS APPLIED")
    print(thin)
    for field, spec in filters.items():
        db = " [dealBreaker]" if spec.get("dealBreaker") else ""
        print(f"  {field:<18}  {spec['data']}{db}")

    print(f"\n{rule}")
    print(f"STEP 1: TOP JOBS ({len(result['jobs'])} results)")
    print(rule)
    print(f"  {'#':<3}  {'TITLE':<38}  {'COMPANY':<22}  {'COUNTRY':<14}  {'SCORE':<7}  SKILLS")
    print(f"  {'-'*3}  {'-'*38}  {'-'*22}  {'-'*14}  {'-'*7}  {'-'*30}")
    for rank, job in enumerate(result["jobs"], 1):
        skills = job["skills"][:60] + "…" if len(job["skills"]) > 60 else job["skills"]
        print(
            f"  {rank:<3}  {job['title']:<38}  {job['company']:<22}  "
            f"{job['country']:<14}  {job['match_score']:.4f}   {skills}"
        )

    print(f"\n{rule}")
    print(f"STEP 2: TOP CLUBS ({len(result['clubs'])} results)")
    print(rule)
    print(f"  {'#':<3}  {'CLUB':<45}  {'SCORE':<7}  ABOUT")
    print(f"  {'-'*3}  {'-'*45}  {'-'*7}  {'-'*40}")
    for rank, club in enumerate(result["clubs"], 1):
        snippet = club.get("search_text", "")[:70].strip()
        if len(club.get("search_text", "")) > 70:
            snippet += "…"
        print(f"  {rank:<3}  {club['name']:<45}  {club['score']:.4f}   {snippet}")

    print(f"\n{rule}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full filters → jobs → clubs pipeline."
    )
    parser.add_argument(
        "--top-jobs",
        type=int,
        default=5,
        metavar="N",
        help="Number of top jobs to surface (default: 5)",
    )
    parser.add_argument(
        "--top-clubs",
        type=int,
        default=5,
        metavar="N",
        help="Total number of clubs to return (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full result as JSON instead of a human-readable report",
    )
    args = parser.parse_args()

    run_pipeline(
        filters=DEFAULT_FILTERS,
        top_jobs=args.top_jobs,
        top_clubs=args.top_clubs,
        emit_json=args.json,
    )


if __name__ == "__main__":
    main()
