"""Match TUM experiences to a set of jobs (step 7).

Given a set of N jobs, rank the experiences by fit and return the top M. Four
weighted fields, each comparing an experience field to the pooled job set
(collective centroid):

    skills    idf-weighted cosine over skill/language/specialization tags
    industry  cosine over the ~10 industries
    title     overlap of the experience's inferred job titles with the set's
    geo       fraction of the set's jobs whose country matches the experience's
              cultural/linguistic regions (sparse — most experiences score 0)

Only canonical tags (in the shared vocabulary) join. Weights are constants
below — the fields are kept separate precisely so they can be re-tuned. The
geo field needs experience_regions.csv (from tag-llm); without it geo = 0.

    uv run python scripts/match_experiences.py --sample 5 --top 5
    uv run python scripts/match_experiences.py --jobs job-1,job-2,job-3
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROCESSED = Path("data/processed")
EXPERIENCES = PROCESSED / "tum_student_experiences.csv"
EXP_TAGS = PROCESSED / "experience_tags.csv"
EXP_TITLES = PROCESSED / "experience_job_titles.csv"
EXP_REGIONS = PROCESSED / "experience_regions.csv"
JOB_TAGS = PROCESSED / "job_tags.csv"
JOBS = PROCESSED / "jobs.csv"
VOCAB = Path("data/reference/vocabulary.csv")

WEIGHTS = {"skills": 0.55, "title": 0.22, "industry": 0.15, "geo": 0.08}
SKILL_TYPES = frozenset({"skill", "language", "specialization"})

Vector = dict[str, float]


def _cosine(a: Vector, b: Vector) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b.get(tag, 0.0) for tag, weight in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _clean(value: object) -> str:
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _load_idf(total_jobs: int) -> dict[str, float]:
    idf: dict[str, float] = {}
    for _, row in pd.read_csv(VOCAB).iterrows():
        count = int(row["job_count"])
        idf[str(row["tag"])] = math.log(total_jobs / count) if count else 0.0
    return idf


def _load_experience_tags(
    idf: dict[str, float],
) -> tuple[dict[str, Vector], dict[str, Vector]]:
    skills: dict[str, Vector] = defaultdict(dict)
    industry: dict[str, Vector] = defaultdict(dict)
    tags = pd.read_csv(EXP_TAGS)
    for _, row in tags[tags["canonical"]].iterrows():
        eid, tag, tag_type = (
            str(row["experience_id"]),
            str(row["tag"]),
            str(row["tag_type"]),
        )
        conf = float(row["confidence"])
        if tag_type in SKILL_TYPES:
            skills[eid][tag] = conf * idf.get(tag, 0.0)
        elif tag_type == "industry":
            industry[eid][tag] = conf
    return skills, industry


def _load_sets(path: Path, value_col: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return out
    for _, row in pd.read_csv(path).iterrows():
        value = _clean(row[value_col])
        if value:
            out[str(row["experience_id"])].add(value)
    return out


def job_set_profiles(
    job_ids: list[str],
    idf: dict[str, float],
    jobs: pd.DataFrame,
    job_tags: pd.DataFrame,
) -> tuple[Vector, Vector, set[str], list[str]]:
    n = len(job_ids)
    sub_tags = job_tags[job_tags["job_id"].isin(job_ids)]
    tag_jobs: dict[str, set[str]] = defaultdict(set)
    for _, row in sub_tags.iterrows():
        if str(row["tag_type"]) in SKILL_TYPES:
            tag_jobs[str(row["tag"])].add(str(row["job_id"]))
    skill_profile = {
        tag: len(ids) / n * idf.get(tag, 0.0) for tag, ids in tag_jobs.items()
    }

    sub_jobs = jobs[jobs["job_id"].isin(job_ids)]
    industry_profile = {
        str(k): int(v) / n for k, v in sub_jobs["industry"].value_counts().items()
    }
    set_titles = {_clean(t) for t in sub_jobs["title"]} - {""}
    set_countries = [_clean(c) for c in sub_jobs["country"]]
    return skill_profile, industry_profile, set_titles, set_countries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", default="", help="comma-separated job_ids")
    parser.add_argument(
        "--sample", type=int, default=5, help="random N jobs if --jobs unset"
    )
    parser.add_argument(
        "--top", type=int, default=5, help="top M experiences to return"
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    jobs = pd.read_csv(JOBS)
    job_tags = pd.read_csv(JOB_TAGS)
    idf = _load_idf(len(jobs))
    exp_skills, exp_industry = _load_experience_tags(idf)
    exp_titles = _load_sets(EXP_TITLES, "matched_job_title")
    exp_regions = _load_sets(EXP_REGIONS, "country")
    experiences = pd.read_csv(EXPERIENCES)
    names = {str(r["experience_id"]): str(r["name"]) for _, r in experiences.iterrows()}

    if args.jobs:
        job_ids = [j.strip() for j in args.jobs.split(",") if j.strip()]
    else:
        job_ids = [
            str(j) for j in jobs.sample(args.sample, random_state=args.seed)["job_id"]
        ]

    skill_p, industry_p, set_titles, set_countries = job_set_profiles(
        job_ids, idf, jobs, job_tags
    )

    print(f"Job set ({len(job_ids)}):")
    for _, j in jobs[jobs["job_id"].isin(job_ids)].iterrows():
        print(f"  {j['title']} — {j['industry']} — {j['country']}")

    scored: list[tuple[float, str, dict[str, float]]] = []
    for eid in names:
        sims = {
            "skills": _cosine(exp_skills.get(eid, {}), skill_p),
            "industry": _cosine(exp_industry.get(eid, {}), industry_p),
            "title": (
                len(exp_titles.get(eid, set()) & set_titles) / len(set_titles)
                if set_titles
                else 0.0
            ),
            "geo": (
                sum(1 for c in set_countries if c in exp_regions.get(eid, set()))
                / len(set_countries)
                if set_countries
                else 0.0
            ),
        }
        total = sum(WEIGHTS[f] * sims[f] for f in WEIGHTS)
        scored.append((total, eid, sims))

    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"\nTop {args.top} experiences:")
    for total, eid, sims in scored[: args.top]:
        breakdown = " ".join(f"{f}={sims[f]:.2f}" for f in WEIGHTS if sims[f] > 0)
        top_skills = sorted(
            (exp_skills.get(eid, {}).items()),
            key=lambda kv: kv[1] * skill_p.get(kv[0], 0.0),
            reverse=True,
        )
        why = ", ".join(t for t, _ in top_skills[:4] if skill_p.get(t))
        print(f"  {total:.3f}  {names[eid][:40]:40} [{breakdown}]")
        if why:
            print(f"          via: {why}")


if __name__ == "__main__":
    main()
