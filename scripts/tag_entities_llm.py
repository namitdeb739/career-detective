"""LLM inferential tagging (step 5): skills, industries, and job titles.

For each consolidated entity, Claude (Haiku 4.5 — the cheapest model) infers
applicable skills and industries from the controlled vocabulary (canonical
tags, plus open terms where nothing fits) and proposes plausible job titles,
which are fuzzy-mapped to real postings in the distinct-title index. One small
structured-output call per entity; the vocabulary is cached in the system
prompt across calls.

Requires an API key:

    export ANTHROPIC_API_KEY=sk-ant-...
    uv run python scripts/tag_entities_llm.py              # all entities
    uv run python scripts/tag_entities_llm.py --limit 10   # cheap dry run
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic
import pandas as pd
from pydantic import BaseModel

if TYPE_CHECKING:
    from anthropic.types import TextBlockParam

MODEL = "claude-haiku-4-5"
ENTITIES = Path("data/processed/entities.csv")
VOCAB = Path("data/reference/vocabulary.csv")
JOB_TITLES = Path("data/processed/job_titles.csv")
OUT_TAGS = Path("data/processed/entity_tags_llm.csv")
OUT_TITLES = Path("data/processed/entity_job_titles.csv")

TITLE_MATCH_CUTOFF = 0.6


class EntityTags(BaseModel):
    skills: list[str]
    industries: list[str]
    job_titles: list[str]


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip()


def _load_vocab() -> tuple[dict[str, str], list[str], list[str]]:
    tag_type_of: dict[str, str] = {}
    skills: list[str] = []
    industries: list[str] = []
    for _, row in pd.read_csv(VOCAB).iterrows():
        tag, tag_type = str(row["tag"]), str(row["tag_type"])
        tag_type_of[tag.lower()] = tag_type
        (industries if tag_type == "industry" else skills).append(tag)
    return tag_type_of, skills, industries


def _system_prompt(skills: list[str], industries: list[str]) -> str:
    return (
        "You tag TUM student clubs, programmes, and research projects with the "
        "skills, industries, and job roles they could plausibly lead to, to match "
        "students with AI/tech jobs.\n\n"
        "Infer from what the entity actually does, not only literal wording: a "
        "robotics club implies C++, ROS, control systems and a Robotics Engineer "
        "path even if unstated.\n\n"
        "Prefer these canonical SKILLS (use the exact spelling); add other terms "
        "only when none fit:\n" + ", ".join(skills) + "\n\n"
        "Prefer these canonical INDUSTRIES (use the exact spelling):\n"
        + ", ".join(industries)
        + "\n\n"
        "Return only tags genuinely supported by the entity — an unrelated club "
        "(hiking, choir) may yield an empty skills list. Propose 0-4 job titles."
    )


def _map_title(proposed: str, titles: list[str]) -> tuple[str, str]:
    match = difflib.get_close_matches(proposed, titles, n=1, cutoff=TITLE_MATCH_CUTOFF)
    if not match:
        return "", ""
    ratio = difflib.SequenceMatcher(None, proposed.lower(), match[0].lower()).ratio()
    return match[0], f"{ratio:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="tag only the first N")
    args = parser.parse_args()

    tag_type_of, skills, industries = _load_vocab()
    industry_set = {i.lower() for i in industries}
    titles = [str(t) for t in pd.read_csv(JOB_TITLES)["title"]]
    system: list[TextBlockParam] = [
        {
            "type": "text",
            "text": _system_prompt(skills, industries),
            "cache_control": {"type": "ephemeral"},
        }
    ]

    entities = pd.read_csv(ENTITIES)
    if args.limit:
        entities = entities.head(args.limit)

    client = anthropic.Anthropic()
    tag_rows: list[dict[str, object]] = []
    title_rows: list[dict[str, str]] = []

    for i, (_, entity) in enumerate(entities.iterrows()):
        entity_id = _clean(entity["entity_id"])
        user = (
            f"Name: {_clean(entity['name'])}\nDetails: {_clean(entity['search_text'])}"
        )
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=EntityTags,
            )
        except anthropic.APIError as err:
            print(f"  {entity_id}: skipped ({err})")
            continue

        tags = response.parsed_output
        if tags is None:
            continue

        for skill in tags.skills:
            key = skill.strip().lower()
            tag_rows.append(
                {
                    "entity_id": entity_id,
                    "tag": skill.strip(),
                    "tag_type": tag_type_of.get(key, "skill"),
                    "method": "llm",
                    "canonical": key in tag_type_of,
                }
            )
        for industry in tags.industries:
            key = industry.strip().lower()
            tag_rows.append(
                {
                    "entity_id": entity_id,
                    "tag": industry.strip(),
                    "tag_type": "industry",
                    "method": "llm",
                    "canonical": key in industry_set,
                }
            )
        for proposed in tags.job_titles:
            matched, similarity = _map_title(proposed.strip(), titles)
            title_rows.append(
                {
                    "entity_id": entity_id,
                    "proposed_title": proposed.strip(),
                    "matched_job_title": matched,
                    "similarity": similarity,
                }
            )

        if (i + 1) % 25 == 0:
            print(f"  tagged {i + 1}/{len(entities)}")

    OUT_TAGS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        tag_rows, columns=["entity_id", "tag", "tag_type", "method", "canonical"]
    ).to_csv(OUT_TAGS, index=False)
    pd.DataFrame(
        title_rows,
        columns=["entity_id", "proposed_title", "matched_job_title", "similarity"],
    ).to_csv(OUT_TITLES, index=False)
    print(
        f"Wrote {len(tag_rows)} tags to {OUT_TAGS} and "
        f"{len(title_rows)} title suggestions to {OUT_TITLES}"
    )


if __name__ == "__main__":
    main()
