"""
Job matching / ranking engine (v2).

============================================================
WHAT CHANGED FROM v1 (precision + simplification pass)
============================================================
PRECISION
  1. Text similarity is now always sentence embeddings (sentence-transformers,
     model "all-MiniLM-L6-v2") -- no TF-IDF/difflib fallback. This requires
     `sentence-transformers` to be installed; if it isn't, this module raises
     ImportError on first use rather than silently degrading to a weaker
     matcher. The model is lazily loaded on first use and cached.
  2. `domain` matching now weights the `AI Specialization` column (a
     controlled vocabulary that maps almost 1:1 onto values like
     "Generative AI") much more heavily than the free-text blend of
     Industry + Required Skills, instead of mashing all three into one
     document (which diluted the clean signal).
  3. `country` matching uses the raw `Country` column as the source of
     truth (case-insensitive exact match) -- no derivation/correction logic.
  4. `company_size` soft-filter scoring is now graded instead of a strict
     0/1 bucket match: same bucket = 1.0, adjacent bucket (small<->mid,
     mid<->large) = 0.5, two buckets apart = 0.0. Hard filters on
     company_size still require an exact bucket match (score == 1.0).
  5. Every soft filter's score array is min-max normalized across the
     surviving candidate pool *before* weighting. Binary fields (0/1) and
     continuous NLP fields (which rarely approach 1.0) previously used the
     same raw scale despite very different ranges, so "equal weight"
     didn't mean equal influence. Normalizing first makes the equal
     weighting assumption actually hold.
  6. Results are ranked by match_score, then tie-broken by Company Rating
     (desc) and risk_level_normalized (asc, i.e. prefer lower risk) --
     previously, an all-hard-filter query left every survivor tied at
     match_score=1.0 with an arbitrary order.
  7. Optional `max_per_company` caps how many postings from the same
     company can appear in the results, since this dataset contains
     templated/duplicate postings across near-identical listings.

SIMPLIFICATION
  8. The 7-branch if/elif field-scoring chain was replaced with a
     dispatch table (FIELD_SCORERS): field name -> scoring function.
     Adding a new filterable field means adding one dict entry, not a new
     branch.
  9. Removed `_ordinal()` -- it was defined but never called.
 10. The risk formula's alias-based ordinal lookup (experience level) now
     shares one helper (`_bucket_for_alias`) instead of a bespoke
     lambda/next() expression.

Everything else (dealBreaker semantics, hard vs. soft filter split, the
overall risk formula shape, output format) is unchanged from v1.
============================================================
FILTER DICT FORMAT (unchanged)
============================================================
   {
     "title":            {"data": "Software Engineer", "dealBreaker": True},
     "domain":           {"data": "Generative AI",      "dealBreaker": False},
     "country":          {"data": "United States",      "dealBreaker": True},
     "company_size":     {"data": "mid",                "dealBreaker": False},
     "work_format":      {"data": "hybrid",             "dealBreaker": False},
     "experience_level": {"data": "senior",             "dealBreaker": True},
     "education_level":  {"data": "msc",                "dealBreaker": False},
   }
   Not all keys need to be present. Unknown keys are ignored with a warning.
   A filter whose "dealBreaker" is not literally True or False is also
   ignored (with a warning) rather than silently dropped from scoring.
============================================================
"""

import warnings
from pathlib import Path
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
NLP_HARD_THRESHOLD = 0.35  # min cosine similarity (embedding space) to "pass" a hard NLP filter

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

DOMAIN_PRIMARY_WEIGHT = 0.7   # weight on AI Specialization
DOMAIN_SECONDARY_WEIGHT = 0.3  # weight on Industry + Required Skills blend

NLP_FIELDS = {"title", "domain"}


# ---------------------------------------------------------------------------
# Text similarity backend: sentence embeddings only (no fallback).
# Requires `pip install sentence-transformers`. Lazily loaded and cached.
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL = None
_CORPUS_EMBEDDING_CACHE: dict = {}


def _get_model():
    """Lazily load and cache the MiniLM sentence-transformer model. Raises
    ImportError with a clear message if the package isn't installed --
    intentionally no fallback to a weaker text-matching method."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "This module requires `sentence-transformers` for text similarity "
            "(title/domain matching). Install it with: "
            "pip install sentence-transformers"
        ) from e

    try:
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
    except Exception:
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDING_MODEL



def _get_corpus_embeddings(corpus: list) -> np.ndarray:
    """Return embeddings for `corpus`, using a module-level cache keyed by
    corpus content so repeated calls with the same DataFrame column don't
    re-run the model."""
    key = tuple(corpus)
    if key not in _CORPUS_EMBEDDING_CACHE:
        _CORPUS_EMBEDDING_CACHE[key] = _get_model().encode(corpus, normalize_embeddings=True)
    return _CORPUS_EMBEDDING_CACHE[key]


def _text_similarity(query: str, corpus: list) -> np.ndarray:
    """Return array of cosine-similarity scores (0..1, higher = more
    similar) between `query` and each item in `corpus`, using MiniLM
    sentence embeddings."""
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
    """Check if `value` (a df cell) matches the alias list for filter_key."""
    if pd.isna(value):
        return False
    value_l = str(value).lower()
    aliases = alias_map.get(filter_key.lower(), [filter_key.lower()])
    return any(alias in value_l for alias in aliases)


def _bucket_for_alias(value, alias_map: dict, ordinal_map: dict, default: int = 2) -> int:
    """Find which canonical bucket `value` matches via alias substrings and
    return its ordinal, or `default` if nothing matches."""
    if pd.isna(value):
        return default
    for bucket, ordinal in ordinal_map.items():
        if _alias_match(value, bucket, alias_map):
            return ordinal
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
    """Scale an array to 0..1 across its own range. Constant arrays (no
    discriminative signal) become all zeros rather than dividing by zero."""
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return np.zeros_like(arr, dtype=float)
    return (arr - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# Per-field scorers (dispatch table)
# ---------------------------------------------------------------------------
def _score_title(query, df: pd.DataFrame) -> np.ndarray:
    return _text_similarity(query, df["Job Title"].tolist())


def _score_domain(query, df: pd.DataFrame) -> np.ndarray:
    primary = _text_similarity(query, df["AI Specialization"].tolist())
    industry = df["Industry"].fillna("") if "Industry" in df.columns else pd.Series([""] * len(df))
    skills = df["Required Skills"].fillna("") if "Required Skills" in df.columns else pd.Series([""] * len(df))
    secondary_text = industry + " " + skills
    secondary = _text_similarity(query, secondary_text.tolist())
    return DOMAIN_PRIMARY_WEIGHT * primary + DOMAIN_SECONDARY_WEIGHT * secondary


def _score_country(query, df: pd.DataFrame) -> np.ndarray:
    """Country matching trusts the raw `Country` column as the source of
    truth (case-insensitive exact match)."""
    target = str(query).strip().lower()
    return df["Country"].fillna("").str.lower().eq(target).astype(float).to_numpy()


def _score_company_size(query, df: pd.DataFrame) -> np.ndarray:
    target_ord = COMPANY_SIZE_ORDINAL.get(str(query).strip().lower(), 2)
    bucket_ord = df["company_size_midpoint"].apply(_company_size_bucket).map(COMPANY_SIZE_ORDINAL).fillna(2)
    diff = (bucket_ord - target_ord).abs()
    # exact bucket = 1.0, adjacent bucket = 0.5, two buckets apart = 0.0
    return (1.0 - 0.5 * diff).clip(lower=0.0).to_numpy()


def _make_alias_scorer(column: str, alias_map: dict):
    def _scorer(query, df: pd.DataFrame) -> np.ndarray:
        target = str(query).strip().lower()
        return df[column].apply(lambda v: float(_alias_match(v, target, alias_map))).to_numpy()
    return _scorer


FIELD_SCORERS = {
    "title": _score_title,
    "domain": _score_domain,
    "country": _score_country,
    "company_size": _score_company_size,
    "work_format": _make_alias_scorer("Remote / Hybrid / On-site", WORK_FORMAT_ALIASES),
    "experience_level": _make_alias_scorer("Experience Level", EXPERIENCE_ALIASES),
    "education_level": _make_alias_scorer("Education Requirements", EDUCATION_ALIASES),
}

SUPPORTED_FIELDS = set(FIELD_SCORERS.keys())


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
def find_top_k_jobs(
    jobs_df: pd.DataFrame,
    filters: dict,
    top_k: int = 10,
    max_per_company: int = None,
) -> list:
    """
    Rank jobs against a set of filters and return the top_k matches.

    Parameters
    ----------
    jobs_df : pd.DataFrame
        Job data matching the expected column schema (Job Title, Company
        Name, Industry, Country, company_size_midpoint, Experience Level,
        Education Requirements, Remote / Hybrid / On-site, AI
        Specialization, Required Skills, layoff_* columns, ...).
    filters : dict
        {"<field>": {"data": <value>, "dealBreaker": <bool>}, ...}
        Supported fields: title, domain, country, company_size,
        work_format, experience_level, education_level.
    top_k : int
        Number of top-ranked jobs to return.
    max_per_company : int, optional
        Cap on how many results may come from the same "Company Name",
        applied after ranking. Use this to avoid a top_k list dominated by
        near-duplicate postings from one company. None = no cap.

    Returns
    -------
    list[dict]
        Each dict = all original job columns +:
          - "field_scores": {field: raw score 0..1} for every filter applied
            (not normalized -- this is the true, interpretable match quality
            per field; normalization only affects the internal match_score
            weighting, not this breakdown)
          - "match_score": weighted soft-filter score (0..1), used for ranking
          - "industry_risk_level": raw industry risk value
          - "risk_level": raw inverse-risk formula output (very small
            number; bigger inputs -> smaller risk_level)
          - "risk_level_normalized": 0..1 across the result pool, higher =
            riskier (this is the practically useful one)
          - "filters_applied": the filters dict that was used
    """
    df = jobs_df.copy()

    # ---- Validate filters ----
    unknown = set(filters.keys()) - SUPPORTED_FIELDS
    if unknown:
        warnings.warn(f"Ignoring unsupported filter fields: {unknown}")
    filters = {k: v for k, v in filters.items() if k in SUPPORTED_FIELDS}

    malformed = {k: v for k, v in filters.items() if v.get("dealBreaker") not in (True, False)}
    if malformed:
        warnings.warn(
            f"Ignoring filters with a non-boolean 'dealBreaker' (neither scored nor "
            f"filtered): {list(malformed)}"
        )
    filters = {k: v for k, v in filters.items() if k not in malformed}

    hard_filters = {k: v for k, v in filters.items() if v["dealBreaker"] is True}
    soft_filters = {k: v for k, v in filters.items() if v["dealBreaker"] is False}
    n_soft = len(soft_filters)
    soft_weight = 1.0 / n_soft if n_soft > 0 else 0.0

    # ---- Score every filtered field (dispatch table instead of if/elif) ----
    field_scores = {
        field: FIELD_SCORERS[field](spec.get("data"), df)
        for field, spec in filters.items()
    }

    # ---- Apply HARD filters (exclusion) ----
    keep_mask = np.ones(len(df), dtype=bool)
    for field in hard_filters:
        scores = field_scores[field]
        if field in NLP_FIELDS:
            keep_mask &= scores >= NLP_HARD_THRESHOLD
        else:
            keep_mask &= scores >= 1.0  # exact/alias match required

    df = df[keep_mask].reset_index(drop=True)
    for field in field_scores:
        field_scores[field] = field_scores[field][keep_mask]

    if df.empty:
        return []

    # ---- Weighted soft-filter score (normalized before weighting) ----
    if n_soft > 0:
        match_score = np.zeros(len(df))
        for field in soft_filters:
            match_score += soft_weight * _minmax_normalize(field_scores[field])
    else:
        match_score = np.ones(len(df))

    # ---- Risk formula (informational only, not used for ranking) ----
    company_size_ord = (
        df["company_size_midpoint"].apply(_company_size_bucket).map(COMPANY_SIZE_ORDINAL).fillna(2).to_numpy()
    )
    exp_ord = df["Experience Level"].apply(
        lambda v: _bucket_for_alias(v, EXPERIENCE_ALIASES, EXPERIENCE_ORDINAL)
    ).to_numpy()

    industry_risk_level = (
        df["layoff_total_events"].fillna(0) * df["layoff_total_employees_laid_off"].fillna(0)
    ).to_numpy()
    industry_risk_level_safe = np.where(industry_risk_level == 0, 1, industry_risk_level)

    denom = FACTOR1 * company_size_ord * FACTOR2 * exp_ord * FACTOR3 * industry_risk_level_safe
    denom = np.where(denom == 0, 1e-9, denom)
    risk_level = 1.0 / denom

    if len(risk_level) > 1 and risk_level.max() != risk_level.min():
        # risk_level is inversely related to riskiness, so negate before
        # min-max scaling: higher risk_level_normalized = riskier.
        risk_level_normalized = _minmax_normalize(-risk_level)
    else:
        risk_level_normalized = np.zeros(len(risk_level))

    # ---- Assemble results ----
    df["match_score"] = match_score
    df["industry_risk_level"] = industry_risk_level
    df["risk_level"] = risk_level
    df["risk_level_normalized"] = risk_level_normalized

    # Attach per-field scores as a column BEFORE sorting/capping/slicing, so
    # row identity (and therefore field_scores) is never ambiguous afterward.
    df["_field_scores"] = [
        {f: float(field_scores[f][pos]) for f in field_scores}
        for pos in range(len(df))
    ]

    # ---- Rank: match_score desc, then Company Rating desc, then risk asc ----
    sort_cols, ascending = ["match_score"], [False]
    if "Company Rating" in df.columns:
        sort_cols.append("Company Rating")
        ascending.append(False)
    sort_cols.append("risk_level_normalized")
    ascending.append(True)

    df = df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

    # ---- Optional diversity cap (avoid duplicate postings from one company) ----
    if max_per_company and "Company Name" in df.columns:
        seen_counts = {}
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


import json

# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------
DEFAULT_DATA_PATH = Path(__file__).parent.parent / "data" / "cleaned" / "jobs_enriched_with_layoffs_complete (1).csv"


def search_jobs(
    filters: dict,
    top_k: int = 10,
    max_per_company: int = 1,
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
    data_path : Path
        Path to the jobs CSV. Defaults to the project's cleaned dataset.

    Returns
    -------
    list[dict]
        Ranked job results, each dict containing all job columns plus
        match_score, risk_level_normalized, field_scores, filters_applied.
    """
    df = pd.read_csv(data_path)
    return find_top_k_jobs(df, filters, top_k=top_k, max_per_company=max_per_company)


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
