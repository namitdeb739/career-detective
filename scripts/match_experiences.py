"""Match TUM club experiences to a set of jobs via sentence embeddings (v2).

Given a set of N job IDs, this script:
  1. Builds a single "job centroid" embedding by averaging the per-job
     embeddings (title + industry + skill tags + country).
  2. Embeds each TUM club using its `search_text` field (cached across calls).
  3. Scores each club by cosine similarity to the job centroid.
  4. MMR-diversifies the pool into two tracks:
       "direct" — relevance-leaning (lambda=0.6)
       "broaden" — diversity-leaning, skips direct picks (lambda=0.5)
  5. The "broaden" track gets a 1.2x score boost for clubs whose search_text
     contains transversal/soft-skill keywords (Leadership, Communication, etc.).

Career preferences (--prefs) multiply the relevance of aligned clubs (value-
match fields: country, domain, education_level) and reshape track weights
(heuristic fields: company_size, experience_level, title).  A dealBreaker flag
reserves up to MAX_RESERVED slots for matching clubs even if they'd otherwise
score low.

Data sources
  data/processed/entities.csv     — club name, description, search_text
  data/processed/jobs.csv         — job title, industry, country
  data/processed/job_tags.csv     — skill/language/specialization tags per job

Usage:
    uv run python scripts/match_experiences.py --sample 5 --top 5 --broaden 3
    uv run python scripts/match_experiences.py --jobs job-1,job-2 --prefs prefs.json
    uv run python scripts/match_experiences.py --jobs job-1 --json
"""

from __future__ import annotations

import argparse
import json
import math
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROCESSED = Path("data/processed")
ENTITIES = PROCESSED / "entities.csv"
JOB_TAGS = PROCESSED / "job_tags.csv"
JOBS = PROCESSED / "jobs.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Broaden-track bonus for clubs with transversal/soft-skill keywords.
BROADEN_BOOST = 1.2
TRANSVERSAL_KEYWORDS = frozenset({
    "leadership", "communication", "teamwork", "project management",
    "public speaking", "creativity", "critical thinking",
})

# MMR parameters
CANDIDATE_POOL = 50
MMR_LAMBDA_DIRECT = 0.6
MMR_LAMBDA_BROADEN = 0.5

# Skill tag types that contribute to the job text.
SKILL_TYPES = frozenset({"skill", "language", "specialization"})

# Career-preference multipliers (by dealBreaker flag).
PREF_FACTOR = {False: 0.08, True: 0.25}   # added as a multiplier to score
PREF_FACTOR_CAP = 0.5                       # combined boost cap (+50%)

# Dealbreaker reservation (guarantees ≥1 aligned club per dealBreaker pref).
MAX_RESERVED = 2
RESERVABLE_FIELDS = frozenset({"country", "domain", "education_level"})

# Heuristics for which pref fields affect the search (not the score itself).
SMALL_COMPANY = frozenset({"startup", "small", "micro"})
SENIOR_LEVELS = frozenset({"senior", "lead", "principal", "staff"})

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Prefs = dict[str, tuple[str, bool]]   # field -> (value, dealBreaker)
Scored = tuple[float, str]             # (score, entity_id)

# ---------------------------------------------------------------------------
# Embedding model — lazy-loaded and cached at module level.
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL = None
_CLUB_EMBEDDING_CACHE: dict[tuple, np.ndarray] = {}


def _get_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "sentence-transformers is required. Install with: "
            "pip install sentence-transformers"
        ) from e
    try:
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
    except Exception:
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDING_MODEL


def _embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalized embeddings for a list of strings."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True)


# ---------------------------------------------------------------------------
# Club embeddings — computed once per unique corpus, then cached.
# ---------------------------------------------------------------------------
def _get_club_embeddings(search_texts: list[str]) -> np.ndarray:
    """Embed club search_text strings, caching by content."""
    key = tuple(search_texts)
    if key not in _CLUB_EMBEDDING_CACHE:
        _CLUB_EMBEDDING_CACHE[key] = _embed(search_texts)
    return _CLUB_EMBEDDING_CACHE[key]


# ---------------------------------------------------------------------------
# Job centroid builder
# ---------------------------------------------------------------------------
def _build_job_text(job_row: pd.Series, tags: list[str]) -> str:
    """One natural-language string per job for embedding."""
    def _safe(val) -> str:
        s = str(val).strip()
        return "" if s.lower() == "nan" else s

    parts = [
        _safe(job_row.get("title", "")),
        _safe(job_row.get("industry", "")),
        _safe(job_row.get("country", "")),
        _safe(job_row.get("description", "")),
    ] + tags
    return " ".join(p for p in parts if p)


def _build_job_centroid(
    job_ids: list[str],
    jobs: pd.DataFrame,
    job_tags: pd.DataFrame,
) -> np.ndarray:
    """Average L2-normalized embeddings of all jobs in the set into a centroid.

    Returns a unit vector (re-normalized after averaging) so cosine similarity
    against it stays in the expected 0..1 range.
    """
    tag_by_job: dict[str, list[str]] = {}
    for _, row in job_tags[job_tags["job_id"].isin(job_ids)].iterrows():
        if str(row["tag_type"]) in SKILL_TYPES:
            tag_by_job.setdefault(str(row["job_id"]), []).append(str(row["tag"]))

    job_texts: list[str] = []
    sub_jobs = jobs[jobs["job_id"].isin(job_ids)]
    for _, jrow in sub_jobs.iterrows():
        jid = str(jrow["job_id"])
        text = _build_job_text(jrow, tag_by_job.get(jid, []))
        if text.strip():
            job_texts.append(text)

    if not job_texts:
        # All jobs produced empty text — return a zero vector.
        dim = _get_model().get_sentence_embedding_dimension()
        return np.zeros(dim, dtype=float)

    vecs = _embed(job_texts)           # shape: (n_jobs, dim)
    centroid = vecs.mean(axis=0)       # mean of unit vectors
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 1e-12 else centroid


# ---------------------------------------------------------------------------
# MMR diversification
# ---------------------------------------------------------------------------
def _cosine_np(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two already-normalized vectors."""
    return float(np.dot(a, b))


def _mmr(
    pool: list[tuple[float, str, np.ndarray]],  # (score, eid, embedding)
    lam: float,
    k: int,
    seeds: set[str],
    seed_vecs: list[np.ndarray],
) -> list[Scored]:
    """Greedily pick k items balancing relevance (lam) vs novelty (1-lam).

    Novelty is 1 - max cosine similarity to already-picked items, computed in
    embedding space (rather than Jaccard over tag sets as in v1).
    """
    max_rel = max((s for s, _, _ in pool), default=0.0) or 1.0
    picked_vecs = list(seed_vecs)
    remaining = [(s, eid, vec) for s, eid, vec in pool if eid not in seeds]
    selected: list[Scored] = []

    while remaining and len(selected) < k:
        best_i, best_val = 0, float("-inf")
        for i, (score, _eid, vec) in enumerate(remaining):
            if picked_vecs:
                max_sim = max(_cosine_np(vec, p) for p in picked_vecs)
                novelty = 1.0 - max_sim
            else:
                novelty = 1.0
            val = lam * (score / max_rel) + (1.0 - lam) * novelty
            if val > best_val:
                best_val, best_i = val, i
        chosen_score, chosen_eid, chosen_vec = remaining.pop(best_i)
        selected.append((chosen_score, chosen_eid))
        picked_vecs.append(chosen_vec)

    return selected


# ---------------------------------------------------------------------------
# Career preferences
# ---------------------------------------------------------------------------
def _load_prefs(arg: str) -> Prefs:
    if not arg:
        return {}
    raw = Path(arg).read_text() if Path(arg).exists() else arg
    prefs: Prefs = {}
    for field, val in json.loads(raw).items():
        if isinstance(val, dict) and str(val.get("data", "")).strip():
            prefs[field] = (str(val["data"]).strip(), bool(val.get("dealBreaker")))
    return prefs


def _pref_boost(
    prefs: Prefs,
    search_text: str,
    entity_id: str,
) -> tuple[float, list[str]]:
    """Compute a score multiplier based on value-match preferences."""
    factor, reasons = 0.0, []
    low = search_text.lower()

    if "country" in prefs:
        value, deal = prefs["country"]
        if value.lower() in low:
            factor += PREF_FACTOR[deal]
            reasons.append(f"{value} affinity")

    if "domain" in prefs:
        value, deal = prefs["domain"]
        if value.lower() in low:
            factor += PREF_FACTOR[deal]
            reasons.append(f"{value} focus")

    if "education_level" in prefs:
        value, deal = prefs["education_level"]
        if "phd" in value.lower() and ("research" in low or "phd" in low):
            factor += PREF_FACTOR[deal]
            reasons.append("research focus")

    return min(factor, PREF_FACTOR_CAP), reasons


def _matches_pref(field: str, value: str, search_text: str) -> bool:
    low = search_text.lower()
    if field == "country":
        return value.lower() in low
    if field == "domain":
        return value.lower() in low
    if field == "education_level":
        return "phd" in value.lower() and ("research" in low or "phd" in low)
    return False


# ---------------------------------------------------------------------------
# Main scoring function (callable from run_pipeline.py)
# ---------------------------------------------------------------------------
def match_clubs(
    job_ids: list[str],
    jobs: pd.DataFrame,
    job_tags: pd.DataFrame,
    entities: pd.DataFrame,
    top: int = 5,
    broaden: int = 3,
    prefs: Prefs | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Score and rank TUM clubs against a pool of jobs.

    Parameters
    ----------
    job_ids : list[str]
        IDs of the jobs to match against.
    jobs : pd.DataFrame
        jobs.csv data.
    job_tags : pd.DataFrame
        job_tags.csv data.
    entities : pd.DataFrame
        entities.csv data (must have entity_id, name, search_text columns).
    top : int
        Number of direct matches to return.
    broaden : int
        Number of broaden-your-profile picks to return.
    prefs : Prefs, optional
        Career preferences dict.

    Returns
    -------
    (direct_results, broaden_results) where each item is a dict with:
        entity_id, name, score, search_text, reasons (list[str])
    """
    if prefs is None:
        prefs = {}

    # Build job centroid embedding.
    centroid = _build_job_centroid(job_ids, jobs, job_tags)

    # Embed all clubs (cached).
    club_ids = entities["entity_id"].tolist()
    search_texts = entities["search_text"].fillna("").tolist()
    club_vecs = _get_club_embeddings(search_texts)  # shape: (n_clubs, dim)

    # Raw cosine similarity to centroid.
    base_scores = club_vecs @ centroid  # shape: (n_clubs,)

    # Per-club preference boost.
    boosts = []
    reasons_map: dict[str, list[str]] = {}
    for i, (eid, st) in enumerate(zip(club_ids, search_texts)):
        boost, rsns = _pref_boost(prefs, st, eid)
        boosts.append(boost)
        reasons_map[eid] = rsns

    # Direct track scores: base * (1 + boost)
    direct_scores = base_scores * (1.0 + np.array(boosts))

    # Broaden track scores: base * 1.2 if club has transversal keywords.
    broaden_scores = base_scores.copy()
    for i, st in enumerate(search_texts):
        st_low = st.lower()
        if any(kw in st_low for kw in TRANSVERSAL_KEYWORDS):
            broaden_scores[i] *= BROADEN_BOOST
    broaden_scores = broaden_scores * (1.0 + np.array(boosts))

    # Build scored pool for MMR (direct track).
    direct_pool: list[tuple[float, str, np.ndarray]] = []
    for i, eid in enumerate(club_ids):
        direct_pool.append((float(direct_scores[i]), eid, club_vecs[i]))
    direct_pool.sort(key=lambda x: x[0], reverse=True)
    direct_pool = direct_pool[:CANDIDATE_POOL]

    # MMR — direct track.
    direct_picks = _mmr(direct_pool, MMR_LAMBDA_DIRECT, top, set(), [])
    used_eids = {eid for _, eid in direct_picks}

    # Dealbreaker reservation: guarantee ≥1 club per dealBreaker pref field.
    reserved: list[Scored] = []
    for field, (value, deal) in prefs.items():
        if not deal or field not in RESERVABLE_FIELDS or len(reserved) >= MAX_RESERVED:
            continue
        candidates = [
            (float(direct_scores[i]), club_ids[i])
            for i, st in enumerate(search_texts)
            if club_ids[i] not in used_eids
            and _matches_pref(field, value, st)
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda x: x[0])
        reserved.append(best)
        used_eids.add(best[1])

    if reserved:
        direct_picks = direct_picks[: max(0, top - len(reserved))] + reserved
    direct_picks = sorted(direct_picks, key=lambda x: x[0], reverse=True)

    # MMR — broaden track (avoids direct picks, uses broaden scores).
    broaden_pool: list[tuple[float, str, np.ndarray]] = []
    for i, eid in enumerate(club_ids):
        if eid not in used_eids:
            broaden_pool.append((float(broaden_scores[i]), eid, club_vecs[i]))
    broaden_pool.sort(key=lambda x: x[0], reverse=True)
    broaden_pool = broaden_pool[:CANDIDATE_POOL]

    # Seed MMR with direct picks so broaden results are dissimilar to them.
    seed_vecs = [club_vecs[club_ids.index(eid)] for _, eid in direct_picks if eid in club_ids]
    broaden_picks = _mmr(
        broaden_pool, MMR_LAMBDA_BROADEN, broaden, used_eids, seed_vecs
    )
    broaden_picks = sorted(broaden_picks, key=lambda x: x[0], reverse=True)

    # Build entity lookup for output.
    entity_lookup = {
        str(row["entity_id"]): row for _, row in entities.iterrows()
    }

    def _to_dict(score: float, eid: str) -> dict:
        row = entity_lookup.get(eid)
        if row is None:
            name = eid
            st = ""
        else:
            name = str(row["name"]) if "name" in row.index else eid
            st = str(row["search_text"]) if "search_text" in row.index else ""
        return {
            "entity_id": eid,
            "name": name,
            "score": round(float(score), 4),
            "search_text": st,
            "reasons": reasons_map.get(eid, []),
        }

    direct_results = [_to_dict(s, e) for s, e in direct_picks]
    broaden_results = [_to_dict(s, e) for s, e in broaden_picks]
    return direct_results, broaden_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match TUM clubs to a set of jobs via sentence embeddings."
    )
    parser.add_argument("--jobs", default="", help="comma-separated job_ids")
    parser.add_argument(
        "--sample", type=int, default=5, help="random N jobs if --jobs unset"
    )
    parser.add_argument("--top", type=int, default=5, help="direct matches to return")
    parser.add_argument(
        "--broaden",
        type=int,
        default=0,
        help="N 'broaden your profile' picks to return",
    )
    parser.add_argument("--seed", type=int, default=None, help="random seed for --sample")
    parser.add_argument(
        "--prefs", default="", help="career preferences as JSON string or file path"
    )
    parser.add_argument("--json", action="store_true", help="emit output as JSON")
    args = parser.parse_args()

    jobs = pd.read_csv(JOBS)
    job_tags = pd.read_csv(JOB_TAGS)
    entities = pd.read_csv(ENTITIES)
    prefs = _load_prefs(args.prefs)

    if args.jobs:
        job_ids = [j.strip() for j in args.jobs.split(",") if j.strip()]
    else:
        job_ids = jobs.sample(args.sample, random_state=args.seed)["job_id"].astype(str).tolist()

    direct, broaden_list = match_clubs(
        job_ids,
        jobs,
        job_tags,
        entities,
        top=args.top,
        broaden=args.broaden,
        prefs=prefs,
    )

    if args.json:
        set_jobs = (
            jobs[jobs["job_id"].isin(job_ids)]
            .set_index("job_id")
            .reindex(job_ids)
            .reset_index()
        )
        job_records = set_jobs.where(pd.notna(set_jobs), None).to_dict(orient="records")
        print(json.dumps(
            {"jobs": job_records, "direct": direct, "broaden": broaden_list},
            indent=2,
            ensure_ascii=False,
        ))
        return

    rule = "─" * 78
    set_jobs = jobs[jobs["job_id"].isin(job_ids)]
    print(f"{rule}\nJOB SET · {len(job_ids)} jobs\n{rule}")
    for _, j in set_jobs.iterrows():
        salary = j.get("salary_mid_usd")
        money = f"${int(salary) // 1000}k" if pd.notna(salary) else "—"
        print(f"  {j['title']!s:<40}  {j['industry']!s:<22} {j['country']!s:<15} {money}")

    if prefs:
        chips = " · ".join(f"{v}{'!' if deal else ''}" for v, deal in prefs.values())
        print(f"\nPREFERENCES  {chips}   (! = dealbreaker)")

    def _render(title: str, items: list[dict]) -> None:
        print(f"\n{rule}\n{title} · {len(items)}\n{rule}")
        for rank, club in enumerate(items, 1):
            print(f"\n{rank:>2}. {club['score']:.4f}  {club['name']}")
            if club["reasons"]:
                print(f"     boosted  {', '.join(club['reasons'])}")
            snippet = club["search_text"][:120].strip()
            if snippet:
                wrapped = textwrap.fill(
                    snippet,
                    width=90,
                    initial_indent="     about    ",
                    subsequent_indent=" " * 14,
                    max_lines=2,
                    placeholder=" …",
                )
                print(wrapped)

    _render("TOP EXPERIENCES", direct)
    if broaden_list:
        _render("BROADEN YOUR PROFILE", broaden_list)


if __name__ == "__main__":
    main()
