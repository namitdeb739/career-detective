"""Merge the dict + LLM tag passes into one unified experience_tags table.

Combines the high-precision verbatim tags (experience_tags_dict.csv,
confidence 1.0) with the inferential LLM tags (experience_tags_llm.csv, which
carry no confidence). Deduped on (experience_id, tag, tag_type), matching tags
case-insensitively: a tag found by both passes keeps the verbatim confidence
and gets method="both"; an LLM-only tag gets LLM_CONFIDENCE. The LLM output is
optional — with only the dict pass this still produces a valid table.

    uv run python scripts/merge_experience_tags.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DICT_TAGS = Path("data/processed/experience_tags_dict.csv")
LLM_TAGS = Path("data/processed/experience_tags_llm.csv")
OUTPUT = Path("data/processed/experience_tags.csv")

LLM_CONFIDENCE = 0.7

COLUMNS = ["experience_id", "tag", "tag_type", "confidence", "method", "canonical"]


def _load() -> pd.DataFrame:
    frames = [pd.read_csv(DICT_TAGS)]
    if LLM_TAGS.exists():
        llm = pd.read_csv(LLM_TAGS)
        llm["confidence"] = LLM_CONFIDENCE
        frames.append(llm)
    return pd.concat(frames, ignore_index=True)


def merge_tags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_tag_key"] = df["tag"].str.strip().str.lower()

    rows: list[dict[str, object]] = []
    for _, group in df.groupby(["experience_id", "_tag_key", "tag_type"], sort=False):
        methods = set(group["method"])
        dict_rows = group[group["method"] == "dict"]
        display = (dict_rows if len(dict_rows) else group).iloc[0]["tag"]
        rows.append(
            {
                "experience_id": group.iloc[0]["experience_id"],
                "tag": display,
                "tag_type": group.iloc[0]["tag_type"],
                "confidence": float(group["confidence"].max()),
                "method": "both" if len(methods) > 1 else next(iter(methods)),
                "canonical": bool(group["canonical"].any()),
            }
        )

    return (
        pd.DataFrame(rows, columns=COLUMNS)
        .sort_values(
            ["experience_id", "tag_type", "confidence", "tag"],
            ascending=[True, True, False, True],
        )
        .reset_index(drop=True)
    )


def main() -> None:
    merged = merge_tags(_load())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT, index=False)
    by_method = {str(k): int(v) for k, v in merged["method"].value_counts().items()}
    print(f"Wrote {len(merged)} tags to {OUTPUT}: {by_method}")


if __name__ == "__main__":
    main()
