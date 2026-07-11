"""Build the controlled tag vocabulary from the AI-jobs dataset.

The job dataset's own labels are our matching vocabulary: TUM experiences are
tagged against this set so their tags join exactly to job postings. Sources
(column -> tag_type):

    Required Skills                -> skill
    Programming Languages Required -> language
    AI Specialization              -> specialization
    Company Industry               -> industry

Singletons (a tag on a single posting) are dropped as synthetic-dataset
artifacts and because a tag that matches one job is useless for matching.

Run:
    uv run python scripts/build_vocabulary.py
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

JOBS = Path("data/cleaned/ai_jobs_2026_cleaned.csv")
OUTPUT = Path("data/reference/vocabulary.csv")
MIN_JOB_COUNT = 2

SOURCES = {
    "Required Skills": "skill",
    "Programming Languages Required": "language",
    "AI Specialization": "specialization",
    "Company Industry": "industry",
}

# A tag may appear under several source columns (e.g. Python as both skill and
# language); keep it once under the highest-priority type.
PRIORITY = {"language": 0, "specialization": 1, "skill": 2, "industry": 3}

_SPLIT = re.compile(r"[;,/|]")


def _tokens(value: str) -> list[str]:
    return [tok.strip() for tok in _SPLIT.split(value) if tok.strip()]


def build_vocabulary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dropped = 0
    for column, tag_type in SOURCES.items():
        counts: Counter[str] = Counter()
        for value in df[column].dropna().astype(str):
            counts.update(_tokens(value))
        for tag, job_count in counts.items():
            if job_count < MIN_JOB_COUNT:
                dropped += 1
                continue
            rows.append({"tag": tag, "tag_type": tag_type, "job_count": job_count})
    print(f"Dropped {dropped} singleton tags (job_count < {MIN_JOB_COUNT}).")
    out = pd.DataFrame(rows, columns=["tag", "tag_type", "job_count"])
    out["_priority"] = out["tag_type"].map(PRIORITY)
    out = out.sort_values(["tag", "_priority"]).drop_duplicates("tag", keep="first")
    return (
        out.drop(columns="_priority")
        .sort_values(["tag_type", "job_count"], ascending=[True, False])
        .reset_index(drop=True)
    )


def main() -> None:
    df = pd.read_csv(JOBS)
    vocab = build_vocabulary(df)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    vocab.to_csv(OUTPUT, index=False)
    by_type = {str(k): int(v) for k, v in vocab["tag_type"].value_counts().items()}
    print(f"Wrote {len(vocab)} tags to {OUTPUT}: {by_type}")


if __name__ == "__main__":
    main()
