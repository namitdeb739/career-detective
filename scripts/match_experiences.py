"""Match TUM experiences to a set of jobs (step 7).

Given a set of N jobs, score every experience against the pooled job set
(collective centroid) on five weighted fields:

    skills       idf-weighted, breadth-normalised coverage of the job skills
    transversal  transferable-skills universal prior (job-independent)
    title        overlap of inferred job titles with the set's
    industry     cosine over the ~10 industries
    geo          fraction of the set's jobs whose country matches the
                 experience's cultural/linguistic regions (sparse)

Results are then MMR-diversified into two tracks — "direct skill matches"
(relevance-leaning) and "broaden your profile" (diversity-leaning, avoiding the
direct picks). See docs/diversity-and-transferable-skills.md.

Optional career preferences (--prefs) sharpen the experience search without
touching the job set: value-match answers (country, education=PhD, domain)
*multiply* the relevance of aligned experiences (so a preference only helps an
already-relevant club — skills stay at the forefront); heuristic answers (small
company, senior level) reshape the field weights. A `dealBreaker` flag applies
the stronger coefficient.

    uv run python scripts/match_experiences.py --sample 5 --top 5 --broaden 3
    uv run python scripts/match_experiences.py --jobs job-1,job-2 --prefs prefs.json
"""

from __future__ import annotations

import argparse
import json
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
    "skills": 0.55,
    "title": 0.17,
    "transversal": 0.13,
    "industry": 0.08,
    "geo": 0.07,
}
# The opt-in "broaden" track ranks transversal-forward, so transferable-skill
# clubs (debate, sports, cultural) rise instead of tech clubs that merely also
# have soft skills.
BROADEN_WEIGHTS = {
    "skills": 0.25,
    "transversal": 0.45,
    "title": 0.10,
    "industry": 0.12,
    "geo": 0.08,
}
SKILL_TYPES = frozenset({"skill", "language", "specialization"})
# Within the skills field, an AI specialization (Generative AI, Deep Learning)
# signals relevance far more than a commodity language (Python, Julia). Weight
# accordingly so a focused AI club beats a "we-use-every-language" umbrella org.
SKILL_TYPE_WEIGHT = {"specialization": 1.3, "skill": 1.0, "language": 0.4}
# The main list requires at least this much skill overlap — a club with no
# relevant skills isn't a "skill match", however well its industry/soft skills
# align. (The broaden track drops the floor to surface transferable-skill clubs.)
SKILLS_FLOOR = 0.10

# Layer 2 — MMR diversifies a relevance-ranked pool into two tracks: "direct"
# leans on relevance, "broaden" leans on diversity and avoids the direct picks.
CANDIDATE_POOL = 50
MMR_LAMBDA_DIRECT = 0.6
MMR_LAMBDA_BROADEN = 0.5

# A dealbreaker preference guarantees representation: reserve up to this many
# slots for experiences that match a value-match dealbreaker (country, domain,
# PhD/research) even if they'd fail the skills floor — a dealbreaker is
# non-negotiable, so at least one aligned experience must appear.
MAX_RESERVED = 2
RESERVABLE_FIELDS = frozenset({"country", "domain", "education_level"})

# Career-preference tuning (all small + interpretable). Value-match preferences
# *multiply* an experience's relevance when it aligns (so a preference only helps
# an already-relevant club — skills stay at the forefront); heuristic ones
# multiply a field weight. A dealbreaker applies the stronger coefficient.
PREF_FACTOR = {False: 0.08, True: 0.25}  # by dealBreaker: x1.08 / x1.25
PREF_WEIGHT_MULT = {False: 1.4, True: 1.9}
PREF_FACTOR_CAP = 0.5  # combined boost caps at +50%, so relevance stays dominant
RESEARCH_TAGS = frozenset(
    {"Research", "Scientific Writing", "Analysis", "Technical Documentation"}
)
SMALL_COMPANY = frozenset({"startup", "small", "micro"})
SENIOR_LEVELS = frozenset({"senior", "lead", "principal", "staff"})

Vector = dict[str, float]
Prefs = dict[str, tuple[str, bool]]  # field -> (value, dealBreaker)
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


def _load_prefs(arg: str) -> Prefs:
    if not arg:
        return {}
    raw = Path(arg).read_text() if Path(arg).exists() else arg
    prefs: Prefs = {}
    for field, val in json.loads(raw).items():
        if isinstance(val, dict) and str(val.get("data", "")).strip():
            prefs[field] = (str(val["data"]).strip(), bool(val.get("dealBreaker")))
    return prefs


def _pref_weights(base: dict[str, float], prefs: Prefs) -> dict[str, float]:
    """Heuristic preferences reshape the field weights (renormalized)."""
    weights = dict(base)
    if "company_size" in prefs and prefs["company_size"][0].lower() in SMALL_COMPANY:
        weights["transversal"] *= PREF_WEIGHT_MULT[prefs["company_size"][1]]
    if (
        "experience_level" in prefs
        and prefs["experience_level"][0].lower() in SENIOR_LEVELS
    ):
        weights["transversal"] *= PREF_WEIGHT_MULT[prefs["experience_level"][1]]
    if "title" in prefs:
        weights["title"] *= PREF_WEIGHT_MULT[prefs["title"][1]]
    total = sum(weights.values())
    return {f: w / total for f, w in weights.items()} if total else weights


def _pref_boost(
    prefs: Prefs,
    regions: set[str],
    skills: Vector,
    transversal: Vector,
    source: str,
) -> tuple[float, list[str]]:
    """Value-match preferences give a relevance *multiplier* (+ a reason)."""
    factor, reasons = 0.0, []
    if "country" in prefs:
        value, deal = prefs["country"]
        if value.lower() in {r.lower() for r in regions}:
            factor += PREF_FACTOR[deal]
            reasons.append(f"{value} affinity")
    if "education_level" in prefs and "phd" in prefs["education_level"][0].lower():
        _, deal = prefs["education_level"]
        if "prep" in source or set(transversal) & RESEARCH_TAGS:
            factor += PREF_FACTOR[deal]
            reasons.append("research focus")
    if "domain" in prefs:
        value, deal = prefs["domain"]
        low = value.lower()
        if any(low in t.lower() or t.lower() in low for t in skills):
            factor += PREF_FACTOR[deal]
            reasons.append(f"{value} focus")
    return min(factor, PREF_FACTOR_CAP), reasons


def _matches(
    field: str,
    value: str,
    regions: set[str],
    skills: Vector,
    transversal: Vector,
    source: str,
) -> bool:
    low = value.lower()
    if field == "country":
        return low in {r.lower() for r in regions}
    if field == "domain":
        return any(low in t.lower() or t.lower() in low for t in skills)
    if field == "education_level":
        return "phd" in low and (
            "prep" in source or bool(set(transversal) & RESEARCH_TAGS)
        )
    return False


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
            skills[eid][tag] = conf * idf.get(tag, 0.0) * SKILL_TYPE_WEIGHT[tag_type]
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
        "--broaden",
        type=int,
        default=0,
        help="add N opt-in transferable-skill 'broaden your profile' picks",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="fix the sample for reproducibility"
    )
    parser.add_argument(
        "--prefs", default="", help="career preferences as JSON (string or file path)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the job set and matched experiences as JSON instead of text",
    )
    args = parser.parse_args()

    jobs = pd.read_csv(JOBS)
    job_tags = pd.read_csv(JOB_TAGS)
    idf = _load_idf(len(jobs))
    exp_skills, exp_industry, exp_transversal = _load_experience_tags(idf)
    exp_titles = _load_sets(EXP_TITLES, "matched_job_title")
    exp_regions = _load_sets(EXP_REGIONS, "country")
    prefs = _load_prefs(args.prefs)
    experiences = pd.read_csv(EXPERIENCES)
    info = {
        str(r["experience_id"]): (str(r["name"]), _clean(r["description"]))
        for _, r in experiences.iterrows()
    }
    sources = {
        str(r["experience_id"]): str(r["sources"]) for _, r in experiences.iterrows()
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

    # Skills use coverage (idf-weighted dot with the job profile), not cosine, so
    # covering the jobs' specific, high-value skills beats a couple of generic
    # aligned tags (Git/Python). Divided by sqrt(tag count) — pivoted-length
    # normalisation (BM25-style) so an umbrella org tagged with the whole
    # vocabulary can't max out coverage on breadth alone, without cosine's
    # over-reward of tiny 2-tag clubs. Normalised by the best-covering experience.
    skills_dot = {
        eid: sum(w * skill_p.get(t, 0.0) for t, w in exp_skills.get(eid, {}).items())
        / math.sqrt(len(exp_skills[eid]) if exp_skills.get(eid) else 1)
        for eid in info
    }
    max_skills = max(skills_dot.values(), default=0.0) or 1.0

    sims_by_eid: dict[str, Vector] = {}
    for eid in info:
        sims_by_eid[eid] = {
            "skills": skills_dot[eid] / max_skills,
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

    pref_effect = {
        eid: _pref_boost(
            prefs,
            exp_regions.get(eid, set()),
            exp_skills.get(eid, {}),
            exp_transversal.get(eid, {}),
            sources.get(eid, ""),
        )
        for eid in info
    }
    reasons = {eid: r for eid, (_, r) in pref_effect.items()}

    def _rank(weights: dict[str, float], skills_floor: float) -> list[Scored]:
        ranked = [
            (
                sum(weights[f] * sims[f] for f in weights)
                * (1.0 + pref_effect[eid][0]),
                eid,
                sims,
            )
            for eid, sims in sims_by_eid.items()
            if sims["skills"] >= skills_floor
        ]
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[:CANDIDATE_POOL]

    tagsets = {
        eid: frozenset(exp_skills.get(eid, {}))
        | frozenset(exp_industry.get(eid, {}))
        | frozenset(exp_transversal.get(eid, {}))
        for eid in info
    }
    # MMR selects a diverse-but-relevant set; display it in plain score order.
    direct_weights = _pref_weights(WEIGHTS, prefs)
    direct = _mmr(
        _rank(direct_weights, SKILLS_FLOOR),
        tagsets,
        MMR_LAMBDA_DIRECT,
        args.top,
        set(),
    )

    # A dealbreaker guarantees a slot: surface the best-matching experience even
    # if it failed the skills floor (e.g. a Japanese culture club for country=Japan).
    direct_score = {
        eid: sum(direct_weights[f] * s[f] for f in direct_weights)
        * (1.0 + pref_effect[eid][0])
        for eid, s in sims_by_eid.items()
    }
    used = {e for _, e, _ in direct}
    reserved: list[Scored] = []
    for field, (value, deal) in prefs.items():
        if not deal or field not in RESERVABLE_FIELDS or len(reserved) >= MAX_RESERVED:
            continue
        matchers = [
            eid
            for eid in info
            if eid not in used
            and _matches(
                field,
                value,
                exp_regions.get(eid, set()),
                exp_skills.get(eid, {}),
                exp_transversal.get(eid, {}),
                sources.get(eid, ""),
            )
        ]
        if not matchers:
            continue
        # for country, surface a cultural representative (least skill-heavy);
        # otherwise the strongest matcher.
        if field == "country":
            pick = min(matchers, key=lambda e: sims_by_eid[e]["skills"])
        else:
            pick = max(matchers, key=lambda e: direct_score[e])
        reserved.append((direct_score[pick], pick, sims_by_eid[pick]))
        used.add(pick)

    if reserved:
        direct = direct[: max(0, args.top - len(reserved))] + reserved
    direct = sorted(direct, key=lambda x: x[0], reverse=True)

    if args.json:
        _emit_json(job_ids, jobs, direct, info, exp_skills)
        return

    broaden = sorted(
        _mmr(
            _rank(_pref_weights(BROADEN_WEIGHTS, prefs), 0.0),
            tagsets,
            MMR_LAMBDA_BROADEN,
            args.broaden,
            {e for _, e, _ in direct},
        ),
        key=lambda x: x[0],
        reverse=True,
    )

    detail = (exp_skills, exp_transversal, exp_titles, exp_regions, skill_p)
    _render_jobset(job_ids, jobs, prefs)
    _render_list(
        "TOP EXPERIENCES", direct, info, detail, set_titles, country_set, reasons
    )
    if broaden:
        _render_list(
            "BROADEN YOUR PROFILE",
            broaden,
            info,
            detail,
            set_titles,
            country_set,
            reasons,
        )


def _jsonable(value: object) -> object:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _emit_json(
    job_ids: list[str],
    jobs: pd.DataFrame,
    direct: list[Scored],
    info: dict[str, tuple[str, str]],
    exp_skills: dict[str, Vector],
) -> None:
    set_jobs = (
        jobs[jobs["job_id"].isin(job_ids)]
        .set_index("job_id")
        .reindex(job_ids)
        .reset_index()
    )
    job_records = [
        {k: _jsonable(v) for k, v in r.items()}
        for r in set_jobs.to_dict(orient="records")
    ]
    experiences = [
        {
            "name": info[eid][0],
            "description": info[eid][1],
            "skills": sorted(exp_skills.get(eid, {})),
            "score": round(total, 3),
        }
        for total, eid, _ in direct
    ]
    print(
        json.dumps(
            {"jobs": job_records, "experiences": experiences},
            indent=2,
            ensure_ascii=False,
        )
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


def _render_jobset(job_ids: list[str], jobs: pd.DataFrame, prefs: Prefs) -> None:
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
    if prefs:
        chips = " · ".join(f"{v}{'!' if deal else ''}" for v, deal in prefs.values())
        print(f"\nPREFERENCES  {chips}   (! = dealbreaker)")


def _render_list(
    title: str,
    items: list[Scored],
    info: dict[str, tuple[str, str]],
    detail: Detail,
    set_titles: set[str],
    country_set: set[str],
    reasons: dict[str, list[str]],
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
        if reasons.get(eid):
            _detail("boosted", ", ".join(reasons[eid]))
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
