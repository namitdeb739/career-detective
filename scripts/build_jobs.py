"""Standardize the AI-jobs dataset: slim jobs table + tag table + title index.

Explodes the native skill/industry columns into `job_tags`, filtered to the
controlled vocabulary so job tags join exactly to entity tags. No NLP — the
job columns already are the vocabulary. Also emits a distinct-title index,
the grounding target for LLM-proposed job titles in step 5.

Run:
    uv run python scripts/build_jobs.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

JOBS = Path("data/cleaned/ai_jobs_2026_cleaned.csv")
VOCAB = Path("data/reference/vocabulary.csv")
OUT_DIR = Path("data/processed")

TAG_COLUMNS = {
    "Required Skills": "skill",
    "Programming Languages Required": "language",
    "AI Specialization": "specialization",
    "Company Industry": "industry",
}
_SPLIT = re.compile(r"[;,/|]")


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    text = str(value).strip()
    return "" if text in {"-", "nan"} else text


def _tokens(value: str) -> list[str]:
    return [tok.strip() for tok in _SPLIT.split(value) if tok.strip()]


def _load_vocab(path: Path) -> dict[str, set[str]]:
    vocab: dict[str, set[str]] = {}
    for _, row in pd.read_csv(path).iterrows():
        vocab.setdefault(str(row["tag_type"]), set()).add(str(row["tag"]))
    return vocab


def main() -> None:
    df = pd.read_csv(JOBS).reset_index(drop=True)
    vocab = _load_vocab(VOCAB)

    jobs_rows: list[dict[str, object]] = []
    tag_rows: list[dict[str, str]] = []
    for i, row in df.iterrows():
        job_id = f"job-{i}"
        jobs_rows.append(
            {
                "job_id": job_id,
                "title": _clean(row["Job Title"]),
                "company": _clean(row["Company Name"]),
                "industry": _clean(row["Company Industry"]),
                "country": _clean(row["Country"]),
                "remote": _clean(row["Remote / Hybrid / On-site"]),
                "experience_level": _clean(row["Experience Level"]),
                "salary_mid_usd": row["salary_mid_usd_approx"],
                "job_url": _clean(row["Job URL"]),
            }
        )
        seen: set[tuple[str, str]] = set()
        for column, tag_type in TAG_COLUMNS.items():
            allowed = vocab.get(tag_type, set())
            for tok in _tokens(_clean(row[column])):
                if tok in allowed and (tok, tag_type) not in seen:
                    seen.add((tok, tag_type))
                    tag_rows.append(
                        {"job_id": job_id, "tag": tok, "tag_type": tag_type}
                    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jobs_rows).to_csv(OUT_DIR / "jobs.csv", index=False)
    pd.DataFrame(tag_rows, columns=["job_id", "tag", "tag_type"]).to_csv(
        OUT_DIR / "job_tags.csv", index=False
    )

    titles = df["Job Title"].map(_clean)
    title_index = (
        titles[titles != ""]
        .value_counts()
        .rename_axis("title")
        .reset_index(name="job_count")
    )
    title_index.to_csv(OUT_DIR / "job_titles.csv", index=False)

    print(
        f"Wrote {len(jobs_rows)} jobs, {len(tag_rows)} job_tags, "
        f"{len(title_index)} distinct titles to {OUT_DIR}/"
    )


if __name__ == "__main__":
    main()
