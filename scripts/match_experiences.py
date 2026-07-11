"""Match TUM experiences to a set of jobs (step 7).

Given a set of N jobs, score every experience against the pooled job set
(collective centroid) on five weighted fields:

    skills       idf-weighted cosine over skill/language/specialization tags
    transversal  transferable-skills universal prior (job-independent)
    title        overlap of inferred job titles with the set's
    industry     cosine over the ~10 industries
    geo          fraction of the set's jobs whose country matches the
                 experience's cultural/linguistic regions (sparse)

Results are then MMR-diversified into two tracks — "direct skill matches"
(relevance-leaning) and "broaden your profile" (diversity-leaning, avoiding the
direct picks). See docs/diversity-and-transferable-skills.md.

    uv run python scripts/match_experiences.py --sample 5 --top 5 --broaden 3
    uv run python scripts/match_experiences.py --jobs job-1,job-2,job-3
"""

from __future__ import annotations

import argparse
import math
import textwrap
from collections import Counter, defaultdict
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

WEIGHTS = {
    "skills": 0.45,
    "transversal": 0.20,
    "title": 0.15,
    "industry": 0.12,
    "geo": 0.08,
}
# The "broaden" track ranks transversal-forward, so transferable-skill clubs
# (debate, sports, cultural) rise instead of tech clubs that merely also have
# soft skills.
BROADEN_WEIGHTS = {
    "skills": 0.25,
    "transversal": 0.45,
    "title": 0.10,
    "industry": 0.12,
    "geo": 0.08,
}
SKILL_TYPES = frozenset({"skill", "language", "specialization"})

# Layer 2 — MMR diversifies a relevance-ranked pool into two tracks: "direct"
# leans on relevance, "broaden" leans on diversity and avoids the direct picks.
CANDIDATE_POOL = 50
MMR_LAMBDA_DIRECT = 0.7
MMR_LAMBDA_BROADEN = 0.5

Vector = dict[str, float]
Scored = tuple[float, str, Vector]
# (exp_skills, exp_transversal, exp_titles, exp_regions, skill_profile)
Detail = tuple[
    dict[str, Vector],
    dict[str, Vector],
    dict[str, set[str]],
    dict[str, set[str]],
    Vector,
]


def _cosine(a: Vector, b: Vector) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b.get(tag, 0.0) for tag, weight in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _mmr(
    pool: list[Scored],
    tagsets: dict[str, frozenset[str]],
    lam: float,
    k: int,
    seeds: set[str],
) -> list[Scored]:
    """Greedily pick k items balancing relevance against novelty (MMR)."""
    max_rel = max((item[0] for item in pool), default=0.0) or 1.0
    picked = [tagsets.get(s, frozenset()) for s in seeds]
    remaining = [item for item in pool if item[1] not in seeds]
    selected: list[Scored] = []
    while remaining and len(selected) < k:
        best_i, best_val = 0, float("-inf")
        for i, (total, eid, _sims) in enumerate(remaining):
            novelty = 1.0 - max(
                (_jaccard(tagsets.get(eid, frozenset()), p) for p in picked),
                default=0.0,
            )
            val = lam * (total / max_rel) + (1.0 - lam) * novelty
            if val > best_val:
                best_val, best_i = val, i
        chosen = remaining.pop(best_i)
        selected.append(chosen)
        picked.append(tagsets.get(chosen[1], frozenset()))
    return selected


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
) -> tuple[dict[str, Vector], dict[str, Vector], dict[str, Vector]]:
    skills: dict[str, Vector] = defaultdict(dict)
    industry: dict[str, Vector] = defaultdict(dict)
    transversal: dict[str, Vector] = defaultdict(dict)
    for _, row in pd.read_csv(EXP_TAGS).iterrows():
        eid, tag, tag_type = (
            str(row["experience_id"]),
            str(row["tag"]),
            str(row["tag_type"]),
        )
        conf = float(row["confidence"])
        if tag_type == "transversal":  # its own axis; never in the jobs vocabulary
            transversal[eid][tag] = conf
        elif not bool(row["canonical"]):
            continue
        elif tag_type in SKILL_TYPES:
            skills[eid][tag] = conf * idf.get(tag, 0.0)
        elif tag_type == "industry":
            industry[eid][tag] = conf

    # idf-weight transversal tags by rarity across experiences, so distinctive
    # transferable skills (public speaking) outweigh ubiquitous ones (teamwork).
    doc_freq: Counter[str] = Counter()
    for tag_map in transversal.values():
        doc_freq.update(tag_map)
    n_docs = len(transversal) or 1
    for tag_map in transversal.values():
        for tag in tag_map:
            tag_map[tag] *= math.log(n_docs / doc_freq[tag]) if doc_freq[tag] else 0.0

    return skills, industry, transversal


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
    parser.add_argument("--top", type=int, default=5, help="direct matches to return")
    parser.add_argument(
        "--broaden", type=int, default=3, help="broaden-your-profile picks"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="fix the sample for reproducibility"
    )
    args = parser.parse_args()

    jobs = pd.read_csv(JOBS)
    job_tags = pd.read_csv(JOB_TAGS)
    idf = _load_idf(len(jobs))
    exp_skills, exp_industry, exp_transversal = _load_experience_tags(idf)
    exp_titles = _load_sets(EXP_TITLES, "matched_job_title")
    exp_regions = _load_sets(EXP_REGIONS, "country")
    experiences = pd.read_csv(EXPERIENCES)
    info = {
        str(r["experience_id"]): (str(r["name"]), _clean(r["description"]))
        for _, r in experiences.iterrows()
    }

    if args.jobs:
        job_ids = [j.strip() for j in args.jobs.split(",") if j.strip()]
    else:
        job_ids = [
            str(j) for j in jobs.sample(args.sample, random_state=args.seed)["job_id"]
        ]

    skill_p, industry_p, set_titles, set_countries = job_set_profiles(
        job_ids, idf, jobs, job_tags
    )
    country_set = set(set_countries)

    transversal_raw = {eid: sum(v.values()) for eid, v in exp_transversal.items()}
    max_transversal = max(transversal_raw.values(), default=0.0) or 1.0

    sims_by_eid: dict[str, Vector] = {}
    for eid in info:
        sims_by_eid[eid] = {
            "skills": _cosine(exp_skills.get(eid, {}), skill_p),
            "transversal": transversal_raw.get(eid, 0.0) / max_transversal,
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

    def _rank(weights: dict[str, float]) -> list[Scored]:
        ranked = [
            (sum(weights[f] * sims[f] for f in weights), eid, sims)
            for eid, sims in sims_by_eid.items()
        ]
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[:CANDIDATE_POOL]

    tagsets = {
        eid: frozenset(exp_skills.get(eid, {}))
        | frozenset(exp_industry.get(eid, {}))
        | frozenset(exp_transversal.get(eid, {}))
        for eid in info
    }
    direct = _mmr(_rank(WEIGHTS), tagsets, MMR_LAMBDA_DIRECT, args.top, set())
    broaden = _mmr(
        _rank(BROADEN_WEIGHTS),
        tagsets,
        MMR_LAMBDA_BROADEN,
        args.broaden,
        {e for _, e, _ in direct},
    )

    detail = (exp_skills, exp_transversal, exp_titles, exp_regions, skill_p)
    _render_jobset(job_ids, jobs)
    _render_list("DIRECT SKILL MATCHES", direct, info, detail, set_titles, country_set)
    if broaden:
        _render_list(
            "BROADEN YOUR PROFILE", broaden, info, detail, set_titles, country_set
        )


def _detail(label: str, content: str) -> None:
    wrapped = textwrap.fill(
        content,
        width=90,
        initial_indent="",
        subsequent_indent=" " * 14,
        max_lines=3,
        placeholder=" …",
    )
    print(f"     {label:<8} {wrapped}")


def _render_jobset(job_ids: list[str], jobs: pd.DataFrame) -> None:
    rule = "─" * 78
    set_jobs = jobs[jobs["job_id"].isin(job_ids)]
    width = max((len(str(t)) for t in set_jobs["title"]), default=10)
    print(f"{rule}\nJOB SET · {len(job_ids)} jobs\n{rule}")
    for _, j in set_jobs.iterrows():
        salary = j["salary_mid_usd"]
        money = f"${int(salary) // 1000}k" if pd.notna(salary) else "—"
        print(
            f"  {j['title']!s:<{width}}  {j['industry']!s:<22} "
            f"{j['country']!s:<15} {money}"
        )


def _render_list(
    title: str,
    items: list[Scored],
    info: dict[str, tuple[str, str]],
    detail: Detail,
    set_titles: set[str],
    country_set: set[str],
) -> None:
    exp_skills, exp_transversal, exp_titles, exp_regions, skill_p = detail
    rule = "─" * 78
    print(f"\n{rule}\n{title} · {len(items)}\n{rule}")
    for rank, (total, eid, sims) in enumerate(items, 1):
        name, desc = info[eid]
        fields = " · ".join(
            f"{f} {sims[f]:.2f}" if sims[f] > 0 else f"{f} —" for f in WEIGHTS
        )
        top_skills = sorted(
            exp_skills.get(eid, {}).items(),
            key=lambda kv: kv[1] * skill_p.get(kv[0], 0.0),
            reverse=True,
        )
        matched_titles = sorted(exp_titles.get(eid, set()) & set_titles)
        matched_regions = sorted(exp_regions.get(eid, set()) & country_set)

        print(f"\n{rank:>2}. {total:.3f}  {name}")
        _detail("match", fields)
        skills = ", ".join(t for t, _ in top_skills[:5] if skill_p.get(t))
        if skills:
            _detail("skills", skills)
        soft = ", ".join(sorted(exp_transversal.get(eid, {})))
        if soft:
            _detail("soft", soft)
        if matched_titles:
            _detail("titles", ", ".join(matched_titles))
        if matched_regions:
            _detail("regions", ", ".join(matched_regions))
        if desc:
            _detail("about", desc)


if __name__ == "__main__":
    main()
