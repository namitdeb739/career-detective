"""
Job matching / ranking engine (v3 — embedding-only).

============================================================
WHAT CHANGED FROM v2 (embedding-only pass)
============================================================
SCORING
  All soft-filter scoring now uses a single sentence-embedding cosine
  similarity between a concatenated "job text" (title + specialization +
  industry + skills + country + remote + experience level + education +
  company size bucket) and a concatenated "query text" built from every
  filter value supplied by the caller.

  This replaces the previous approach of per-field alias/exact scorers for
  country, company_size, work_format, experience_level, and education_level.
  Title and domain already used embeddings; now every dimension goes through
  the same model, making the combined score directly comparable across fields.

HARD FILTERS
  dealBreaker filters still apply per-field logic to exclude candidates:
  - NLP fields (title, domain): embedding cosine >= NLP_HARD_THRESHOLD
  - country: case-insensitive exact match (unchanged -- it's a structured field)
  - All other fields: substring alias match (unchanged)
  Hard-filter logic is intentionally NOT altered (per spec).

EVERYTHING ELSE UNCHANGED
  - min-max normalization of the combined soft score
  - Risk formula and tie-breaking (match_score desc, Company Rating desc,
    risk_level_normalized asc)
  - max_per_company diversity cap
  - Output format (same columns, field_scores dict, filters_applied)
  - search_jobs() / find_top_k_jobs() public API

============================================================
FILTER DICT FORMAT
============================================================
   {
     "title":            {"data": "Software Engineer", "dealBreaker": True,  "ranking": 1},
     "domain":           {"data": "Generative AI",     "dealBreaker": False, "ranking": 2},
     "country":          {"data": "United States",     "dealBreaker": True,  "ranking": 3},
     "company_size":     {"data": "mid",               "dealBreaker": False, "ranking": 4},
     "work_format":      {"data": "hybrid",            "dealBreaker": False, "ranking": 5},
     "experience_level": {"data": "senior",            "dealBreaker": True,  "ranking": 6},
     "education_level":  {"data": "msc",               "dealBreaker": False, "ranking": 7},
   }
   Not all keys need to be present. Unknown keys are ignored with a warning.
   A filter whose "dealBreaker" is not literally True or False is also
   ignored (with a warning) rather than silently dropped from scoring.

   "ranking" (optional, int 1-N): user priority ordering for soft-filter
   scoring. ranking=1 is the highest priority and receives the largest weight;
   the highest ranking number receives weight 1.  Converted to a weight via:
     weight = (max_ranking + 1 - ranking)
   so rank 1 of 7 → weight 7, rank 7 of 7 → weight 1.
   Hard-filter (dealBreaker=True) pass/fail logic is not affected by ranking.

   Legacy "weight" (int 1-5) is still accepted when "ranking" is absent.
============================================================
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
# Minimum cosine similarity (embedding space) for an NLP hard filter to pass.
NLP_HARD_THRESHOLD = 0.35

COMPANY_SIZE_ORDINAL = {"small": 1, "mid": 2, "large": 3}
EXPERIENCE_ORDINAL = {"start": 1, "mid": 2, "senior": 3}

EXPERIENCE_ALIASES = {
    "start": ["entry", "junior", "start", "grad", "intern"],
    "mid": ["mid", "intermediate", "associate"],
    "senior": ["senior", "lead", "principal", "staff", "director", "head"],
}

EDUCATION_ALIASES = {
    "no deg": ["no degree", "none", "not required", "n/a", "high school"],
    "bsc": ["bachelor", "bsc", "b.sc", "undergraduate"],
    "msc": ["master", "msc", "m.sc", "graduate"],
    "phd": ["phd", "doctorate", "ph.d"],
}

WORK_FORMAT_ALIASES = {
    "remote": ["remote"],
    "hybrid": ["hybrid"],
    "in-person": ["on-site", "onsite", "in-person", "in person", "office"],
}

FACTOR1 = 1.0
FACTOR2 = 1.0
FACTOR3 = 1.0

# MMR: candidate pool size and default lambda (1.0 = relevance, 0.0 = diversity).
MMR_CANDIDATE_POOL = 200
MMR_LAMBDA_DEFAULT = 0.7

# Fields that use the embedding model for hard-filter threshold checks.
NLP_FIELDS = {"title", "domain"}

SUPPORTED_FIELDS = {
    "title",
    "domain",
    "country",
    "company_size",
    "work_format",
    "experience_level",
    "education_level",
}


# ---------------------------------------------------------------------------
# Text similarity backend: sentence embeddings (lazy-loaded, cached).
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL = None
_CORPUS_EMBEDDING_CACHE: dict = {}


def _get_model():
    """Lazily load and cache the MiniLM sentence-transformer model.

    Raises ImportError with a clear message if the package is missing —
    intentionally no fallback to a weaker text-matching method.
    """
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "This module requires `sentence-transformers` for text similarity. "
            "Install it with: pip install sentence-transformers"
        ) from e

    try:
        _EMBEDDING_MODEL = SentenceTransformer(
            EMBEDDING_MODEL_NAME, local_files_only=True
        )
    except Exception:
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDING_MODEL


def warm_model() -> None:
    """Eagerly load the embedding model. Call at server startup to avoid
    a slow first request."""
    _get_model()


def _get_corpus_embeddings(corpus: list) -> np.ndarray:
    """Return normalized embeddings for `corpus`, cached by content."""
    key = tuple(corpus)
    if key not in _CORPUS_EMBEDDING_CACHE:
        _CORPUS_EMBEDDING_CACHE[key] = _get_model().encode(
            corpus, normalize_embeddings=True
        )
    return _CORPUS_EMBEDDING_CACHE[key]


def _text_similarity(query: str, corpus: list) -> np.ndarray:
    """Cosine similarity between `query` and each item in `corpus` (0..1)."""
    query = str(query) if pd.notna(query) else ""
    corpus = [str(c) if pd.notna(c) else "" for c in corpus]

    if not query.strip():
        return np.zeros(len(corpus))

    corpus_vecs = _get_corpus_embeddings(corpus)
    query_vec = _get_model().encode([query], normalize_embeddings=True)[0]
    return corpus_vecs @ query_vec


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def _alias_match(value: str, filter_key: str, alias_map: dict) -> bool:
    """True if `value` contains any alias for `filter_key`."""
    if pd.isna(value):
        return False
    value_l = str(value).lower()
    aliases = alias_map.get(filter_key.lower(), [filter_key.lower()])
    return any(alias in value_l for alias in aliases)


def _bucket_for_alias(
    value, alias_map: dict, ordinal_map: dict, default: int = 2
) -> int:
    """Return the ordinal for whichever bucket `value` matches, or `default`."""
    if pd.isna(value):
        return default
    for bucket in ordinal_map:
        if _alias_match(value, bucket, alias_map):
            return ordinal_map[bucket]
    return default


def _company_size_bucket(midpoint: float) -> str:
    if pd.isna(midpoint):
        return "unknown"
    if midpoint < 500:
        return "small"
    if midpoint <= 5000:
        return "mid"
    return "large"


def _minmax_normalize(arr: np.ndarray) -> np.ndarray:
    """Scale arr to 0..1. Constant arrays become all-zeros."""
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return np.zeros_like(arr, dtype=float)
    return (arr - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# Hard-filter scorers (used only to decide pass/fail for dealBreaker fields)
# ---------------------------------------------------------------------------
def _hard_score_title(query: str, df: pd.DataFrame) -> np.ndarray:
    return _text_similarity(query, df["Job Title"].tolist())


def _hard_score_domain(query: str, df: pd.DataFrame) -> np.ndarray:
    primary = _text_similarity(query, df["AI Specialization"].tolist())
    industry = (
        df["Industry"].fillna("")
        if "Industry" in df.columns
        else pd.Series([""] * len(df))
    )
    skills = (
        df["Required Skills"].fillna("")
        if "Required Skills" in df.columns
        else pd.Series([""] * len(df))
    )
    secondary = _text_similarity(query, (industry + " " + skills).tolist())
    return 0.7 * primary + 0.3 * secondary


def _hard_score_country(query: str, df: pd.DataFrame) -> np.ndarray:
    target = str(query).strip().lower()
    return df["Country"].fillna("").str.lower().eq(target).astype(float).to_numpy()


def _hard_score_work_format(query: str, df: pd.DataFrame) -> np.ndarray:
    return (
        df["Remote / Hybrid / On-site"]
        .apply(
            lambda v: float(
                _alias_match(v, str(query).strip().lower(), WORK_FORMAT_ALIASES)
            )
        )
        .to_numpy()
    )


def _hard_score_experience_level(query: str, df: pd.DataFrame) -> np.ndarray:
    return (
        df["Experience Level"]
        .apply(
            lambda v: float(
                _alias_match(v, str(query).strip().lower(), EXPERIENCE_ALIASES)
            )
        )
        .to_numpy()
    )


def _hard_score_education_level(query: str, df: pd.DataFrame) -> np.ndarray:
    return (
        df["Education Requirements"]
        .apply(
            lambda v: float(
                _alias_match(v, str(query).strip().lower(), EDUCATION_ALIASES)
            )
        )
        .to_numpy()
    )


def _hard_score_company_size(query: str, df: pd.DataFrame) -> np.ndarray:
    target_ord = COMPANY_SIZE_ORDINAL.get(str(query).strip().lower(), 2)
    bucket_ord = (
        df["company_size_midpoint"]
        .apply(_company_size_bucket)
        .map(COMPANY_SIZE_ORDINAL)
        .fillna(2)
    )
    diff = (bucket_ord - target_ord).abs()
    return (1.0 - 0.5 * diff).clip(lower=0.0).to_numpy()


# Dispatch table for hard-filter pass/fail scoring only.
_HARD_SCORERS = {
    "title": _hard_score_title,
    "domain": _hard_score_domain,
    "country": _hard_score_country,
    "company_size": _hard_score_company_size,
    "work_format": _hard_score_work_format,
    "experience_level": _hard_score_experience_level,
    "education_level": _hard_score_education_level,
}


# ---------------------------------------------------------------------------
# Job text builder — converts one job row into a natural-language summary
# ---------------------------------------------------------------------------
def _job_text(row: pd.Series) -> str:
    """Concatenate the most informative job fields into a single text string
    for embedding. Missing fields are skipped rather than included as 'nan'."""

    def _safe(col: str) -> str:
        val = row.get(col, "")
        return (
            str(val).strip()
            if pd.notna(val) and str(val).strip().lower() != "nan"
            else ""
        )

    parts = [
        _safe("Job Title"),
        _safe("AI Specialization"),
        _safe("Industry"),
        _safe("Required Skills"),
        _safe("Country"),
        _safe("Remote / Hybrid / On-site"),
        _safe("Experience Level"),
        _safe("Education Requirements"),
    ]
    # Include the company-size bucket as a readable token.
    midpoint = row.get("company_size_midpoint", None)
    if pd.notna(midpoint):
        parts.append(_company_size_bucket(float(midpoint)))

    return " ".join(p for p in parts if p)


def _mmr_jobs(
    scores: np.ndarray,
    embeddings: np.ndarray,
    k: int,
    lam: float,
) -> list[int]:
    """Greedily select k indices from a candidate pool balancing relevance
    (lam) vs semantic novelty (1 - lam).

    Parameters
    ----------
    scores : shape (n,) match scores for the candidate pool.
    embeddings : shape (n, dim) L2-normalized job embeddings.
    k : number of items to select.
    lam : 1.0 = pure relevance (no diversity), 0.0 = pure diversity.
    """
    max_score = float(scores.max()) or 1.0
    remaining = list(range(len(scores)))
    selected: list[int] = []
    selected_vecs: list[np.ndarray] = []

    while remaining and len(selected) < k:
        best_i, best_val = None, float("-inf")
        for idx in remaining:
            relevance = scores[idx] / max_score
            if selected_vecs:
                max_sim = max(float(embeddings[idx] @ v) for v in selected_vecs)
                novelty = 1.0 - max_sim
            else:
                novelty = 1.0
            val = lam * relevance + (1.0 - lam) * novelty
            if val > best_val:
                best_val, best_i = val, idx
        selected.append(best_i)
        selected_vecs.append(embeddings[best_i])
        remaining.remove(best_i)

    return selected


def _query_text(filters: dict) -> str:
    """Concatenate all filter values into a single query string."""
    parts = [str(spec.get("data", "")).strip() for spec in filters.values()]
    return " ".join(p for p in parts if p)


def _weighted_query_vector(filters: dict) -> np.ndarray:
    """Build a weighted query embedding from per-field embeddings.

    Each field's ``data`` value is embedded separately; the resulting vector
    is scaled by a weight derived from the field's ``ranking`` (1 = highest
    priority).  The weight formula is:

        weight = max_ranking + 1 - ranking

    so rank 1 of 7 fields → weight 7, rank 7 → weight 1.  The scaled vectors
    are summed and L2-normalised into a single query vector.

    Falls back to the legacy ``weight`` field (int 1-5) when ``ranking`` is
    absent, and to weight=1 when neither key is present.
    """
    model = _get_model()
    weighted_sum: np.ndarray | None = None

    # Determine max ranking so we can convert rank → weight.
    rankings = [
        int(spec["ranking"])
        for spec in filters.values()
        if "ranking" in spec
    ]
    max_rank = max(rankings) if rankings else 1

    for spec in filters.values():
        text = str(spec.get("data", "")).strip()
        if not text:
            continue

        if "ranking" in spec:
            try:
                rank = int(spec["ranking"])
            except (TypeError, ValueError):
                rank = max_rank
            # Lower rank number → higher weight.
            raw_weight = max_rank + 1 - rank
        else:
            raw_weight = spec.get("weight", 1)

        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(1.0, weight)

        vec = model.encode([text], normalize_embeddings=True)[0]
        if weighted_sum is None:
            weighted_sum = weight * vec
        else:
            weighted_sum += weight * vec

    if weighted_sum is None or np.linalg.norm(weighted_sum) < 1e-12:
        # Fallback: zero-length query → no preference
        dim = model.get_sentence_embedding_dimension()
        return np.zeros(dim, dtype=np.float32)

    return weighted_sum / np.linalg.norm(weighted_sum)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
def find_top_k_jobs(
    jobs_df: pd.DataFrame,
    filters: dict,
    top_k: int = 10,
    max_per_company: int | None = None,
    max_per_title: int | None = None,
    mmr_lambda: float = MMR_LAMBDA_DEFAULT,
) -> list:
    """
    Rank jobs against a set of filters and return the top_k matches.

    Parameters
    ----------
    jobs_df : pd.DataFrame
        Job data matching the expected column schema.
    filters : dict
        {"<field>": {"data": <value>, "dealBreaker": <bool>}, ...}
        Supported fields: title, domain, country, company_size,
        work_format, experience_level, education_level.
    top_k : int
        Number of top-ranked jobs to return.
    max_per_company : int, optional
        Cap on results per company to avoid duplicate postings.

    Returns
    -------
    list[dict]
        Each dict = all original job columns plus:
          - "field_scores": {"embedding_score": <float>} — the single
            embedding cosine similarity used for soft scoring, plus per-field
            hard scores for any dealBreaker fields.
          - "match_score": combined soft score (0..1), used for ranking.
          - "industry_risk_level", "risk_level", "risk_level_normalized"
          - "filters_applied": the filters dict used.
    """
    df = jobs_df.copy()

    # ---- Validate filters ----
    unknown = set(filters.keys()) - SUPPORTED_FIELDS
    if unknown:
        warnings.warn(f"Ignoring unsupported filter fields: {unknown}", stacklevel=2)
    filters = {k: v for k, v in filters.items() if k in SUPPORTED_FIELDS}

    malformed = {
        k: v for k, v in filters.items() if v.get("dealBreaker") not in (True, False)
    }
    if malformed:
        warnings.warn(
            f"Ignoring filters with non-boolean 'dealBreaker': {list(malformed)}",
            stacklevel=2,
        )
    filters = {k: v for k, v in filters.items() if k not in malformed}

    hard_filters = {k: v for k, v in filters.items() if v["dealBreaker"] is True}
    soft_filters = {k: v for k, v in filters.items() if v["dealBreaker"] is False}

    # ---- Per-field scores (hard filters only — needed for exclusion) ----
    hard_field_scores = {
        field: _HARD_SCORERS[field](spec.get("data"), df)
        for field, spec in hard_filters.items()
    }

    # ---- Apply HARD filters (exclusion) ----
    keep_mask = np.ones(len(df), dtype=bool)
    for field, scores in hard_field_scores.items():
        if field in NLP_FIELDS:
            keep_mask &= scores >= NLP_HARD_THRESHOLD
        else:
            keep_mask &= scores >= 1.0  # exact/alias match required

    df = df[keep_mask].reset_index(drop=True)
    for field in hard_field_scores:
        hard_field_scores[field] = hard_field_scores[field][keep_mask]

    if df.empty:
        return []

    # ---- Soft scoring: weighted per-field embedding similarity ----
    # Each field is embedded separately and scaled by its weight (1-5) before
    # being summed into a single normalised query vector.  This replaces the
    # previous single-concatenated-string approach so that higher-weighted
    # fields exert proportionally more pull on the ranked results.
    job_texts = df.apply(_job_text, axis=1).tolist()
    job_embeddings = _get_corpus_embeddings(job_texts)

    if soft_filters:
        query_vec = _weighted_query_vector(filters)
        embedding_scores = job_embeddings @ query_vec
        match_score = _minmax_normalize(embedding_scores)
    else:
        embedding_scores = np.zeros(len(df))
        match_score = np.ones(len(df))

    # ---- Risk formula (informational only, not used for ranking) ----
    company_size_ord = (
        df["company_size_midpoint"]
        .apply(_company_size_bucket)
        .map(COMPANY_SIZE_ORDINAL)
        .fillna(2)
        .to_numpy()
    )
    exp_ord = (
        df["Experience Level"]
        .apply(lambda v: _bucket_for_alias(v, EXPERIENCE_ALIASES, EXPERIENCE_ORDINAL))
        .to_numpy()
    )

    industry_risk_level = (
        df["layoff_total_events"].fillna(0)
        * df["layoff_total_employees_laid_off"].fillna(0)
    ).to_numpy()
    industry_risk_level_safe = np.where(
        industry_risk_level == 0, 1, industry_risk_level
    )

    denom = (
        FACTOR1
        * company_size_ord
        * FACTOR2
        * exp_ord
        * FACTOR3
        * industry_risk_level_safe
    )
    denom = np.where(denom == 0, 1e-9, denom)
    risk_level = 1.0 / denom

    if len(risk_level) > 1 and risk_level.max() != risk_level.min():
        risk_level_normalized = _minmax_normalize(-risk_level)
    else:
        risk_level_normalized = np.zeros(len(risk_level))

    # ---- Assemble results ----
    df["match_score"] = match_score
    df["industry_risk_level"] = industry_risk_level
    df["risk_level"] = risk_level
    df["risk_level_normalized"] = risk_level_normalized

    # Build field_scores: includes the shared embedding score plus per-field
    # hard scores for interpretability.
    def _row_field_scores(pos: int) -> dict:
        scores = {"embedding_score": float(embedding_scores[pos])}
        for f, arr in hard_field_scores.items():
            scores[f] = float(arr[pos])
        return scores

    df["_field_scores"] = [_row_field_scores(pos) for pos in range(len(df))]

    # ---- Rank: sort to get candidate pool, then MMR for diversity ----
    sort_cols, ascending = ["match_score"], [False]
    if "Company Rating" in df.columns:
        sort_cols.append("Company Rating")
        ascending.append(False)
    sort_cols.append("risk_level_normalized")
    ascending.append(True)

    df_sorted = df.sort_values(sort_cols, ascending=ascending)
    pool_size = min(len(df_sorted), MMR_CANDIDATE_POOL)
    # pool_idx: original (post-hard-filter, post-reset_index) row positions
    pool_idx = df_sorted.index[:pool_size].tolist()
    pool_scores = match_score[pool_idx]
    pool_embeddings = job_embeddings[pool_idx]
    mmr_positions = _mmr_jobs(pool_scores, pool_embeddings, pool_size, mmr_lambda)
    df = df.iloc[[pool_idx[p] for p in mmr_positions]].reset_index(drop=True)

    # ---- Optional diversity caps ----
    if max_per_title and "Job Title" in df.columns:
        seen_counts: dict = {}
        keep_idx = []
        for idx, title in enumerate(df["Job Title"]):
            seen_counts[title] = seen_counts.get(title, 0) + 1
            if seen_counts[title] <= max_per_title:
                keep_idx.append(idx)
        df = df.loc[keep_idx].reset_index(drop=True)

    if max_per_company and "Company Name" in df.columns:
        seen_counts: dict = {}
        keep_idx = []
        for idx, company in enumerate(df["Company Name"]):
            seen_counts[company] = seen_counts.get(company, 0) + 1
            if seen_counts[company] <= max_per_company:
                keep_idx.append(idx)
        df = df.loc[keep_idx].reset_index(drop=True)

    df = df.head(top_k).reset_index(drop=True)

    results = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        row_dict["field_scores"] = row_dict.pop("_field_scores")
        row_dict["filters_applied"] = filters
        results.append(row_dict)

    return results


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------
DEFAULT_DATA_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "cleaned"
    / "jobs_enriched_with_layoffs_complete.csv"
)


def search_jobs(
    filters: dict,
    top_k: int = 10,
    max_per_company: int = 1,
    max_per_title: int = 1,
    mmr_lambda: float = MMR_LAMBDA_DEFAULT,
    data_path: Path = DEFAULT_DATA_PATH,
) -> list[dict]:
    """
    Load job data, apply filters, and return ranked results as a list of dicts.

    Parameters
    ----------
    filters : dict
        Filter spec — see find_top_k_jobs for the expected format.
    top_k : int
        Number of results to return.
    max_per_company : int
        Max results per company (1 = no duplicates).
    mmr_lambda : float
        MMR diversity control. 1.0 = pure relevance, 0.0 = pure diversity.
        Default 0.7 — relevance-leaning with meaningful diversity.
    data_path : Path
        Path to the jobs CSV. Defaults to the project's cleaned dataset.

    Returns
    -------
    list[dict]
        Ranked job results, each dict containing all job columns plus
        match_score, risk_level_normalized, field_scores, filters_applied.
    """
    df = pd.read_csv(data_path)
    return find_top_k_jobs(
        df,
        filters,
        top_k=top_k,
        max_per_company=max_per_company,
        max_per_title=max_per_title,
        mmr_lambda=mmr_lambda,
    )


if __name__ == "__main__":
    filters = {
        "title": {"data": "AI Engineer", "dealBreaker": True},
        "domain": {"data": "Generative AI", "dealBreaker": False},
        "country": {"data": "United States", "dealBreaker": True},
        "company_size": {"data": "mid", "dealBreaker": False},
        "work_format": {"data": "hybrid", "dealBreaker": False},
        "experience_level": {"data": "senior", "dealBreaker": True},
        "education_level": {"data": "phd", "dealBreaker": False},
    }

    results = search_jobs(filters, top_k=5)
    print(json.dumps(results, indent=2, default=str))
