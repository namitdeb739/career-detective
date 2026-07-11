"""Dictionary tagging: match controlled-vocabulary terms verbatim in experiences.

High-precision, zero-cost first pass. Each canonical tag (>= 3 chars, to skip
short-token noise like 'R'/'Go' which the later LLM pass handles) is matched
against experience `search_text` with word boundaries. Emits experience_tags with
method=dict, confidence=1.0. The LLM pass later adds inferential/paraphrase
tags on top.

Run:
    uv run python scripts/tag_experiences_dict.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

EXPERIENCES = Path("data/processed/tum_student_experiences.csv")
VOCAB = Path("data/reference/vocabulary.csv")
OUTPUT = Path("data/processed/experience_tags_dict.csv")
MIN_TAG_LEN = 3


def _pattern(tag: str) -> re.Pattern[str]:
    escaped = re.escape(tag)
    return re.compile(rf"(?<![A-Za-z0-9+#]){escaped}(?![A-Za-z0-9+#])", re.IGNORECASE)


def main() -> None:
    vocab = pd.read_csv(VOCAB)
    # Industries are broad sectors better inferred by the LLM than string-matched
    # (literal "Technology" is a common word); the dict pass covers concrete terms.
    patterns = [
        (str(row["tag"]), str(row["tag_type"]), _pattern(str(row["tag"])))
        for _, row in vocab.iterrows()
        if len(str(row["tag"])) >= MIN_TAG_LEN and str(row["tag_type"]) != "industry"
    ]

    rows: list[dict[str, object]] = []
    for _, experience in pd.read_csv(EXPERIENCES).iterrows():
        text = _clean(experience["search_text"])
        experience_id = str(experience["experience_id"])
        for tag, tag_type, pattern in patterns:
            if pattern.search(text):
                rows.append(
                    {
                        "experience_id": experience_id,
                        "tag": tag,
                        "tag_type": tag_type,
                        "confidence": 1.0,
                        "method": "dict",
                        "canonical": True,
                    }
                )

    out = pd.DataFrame(
        rows,
        columns=[
            "experience_id",
            "tag",
            "tag_type",
            "confidence",
            "method",
            "canonical",
        ],
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)
    tagged = int(out["experience_id"].nunique()) if len(out) else 0
    print(f"Wrote {len(out)} dict tags across {tagged} experiences to {OUTPUT}")


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    return str(value).strip()


if __name__ == "__main__":
    main()
