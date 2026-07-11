"""LLM inferential tagging (step 5): skills, industries, and job titles.

Runs locally and free via Ollama — no API key, no data leaves the machine.
For each consolidated experience, a local model (default qwen2.5:7b) infers
applicable skills and industries from the controlled vocabulary (canonical
tags, plus open terms where nothing fits) and proposes plausible job titles,
which are fuzzy-mapped to real postings in the distinct-title index.

One-time setup:

    brew install ollama       # or download from https://ollama.com
    ollama serve &            # start the local server
    ollama pull qwen2.5:7b    # ~4.7 GB

Run:

    uv run python scripts/tag_experiences_llm.py              # all experiences
    uv run python scripts/tag_experiences_llm.py --limit 10   # quick check
    OLLAMA_MODEL=qwen2.5:14b uv run python scripts/tag_experiences_llm.py
"""

from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path

import ollama
import pandas as pd
from pydantic import BaseModel

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
EXPERIENCES = Path("data/processed/tum_student_experiences.csv")
VOCAB = Path("data/reference/vocabulary.csv")
JOB_TITLES = Path("data/processed/job_titles.csv")
OUT_TAGS = Path("data/processed/experience_tags_llm.csv")
OUT_TITLES = Path("data/processed/experience_job_titles.csv")

TITLE_MATCH_CUTOFF = 0.6


class ExperienceTags(BaseModel):
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
        "Infer from what the experience actually does, not only literal wording: a "
        "robotics club implies C++, ROS, control systems and a Robotics Engineer "
        "path even if unstated.\n\n"
        "Prefer these canonical SKILLS (use the exact spelling); add other terms "
        "only when none fit:\n" + ", ".join(skills) + "\n\n"
        "Prefer these canonical INDUSTRIES (use the exact spelling):\n"
        + ", ".join(industries)
        + "\n\n"
        "Return only tags genuinely supported by the experience — an unrelated club "
        "(hiking, choir) may yield an empty skills list. Propose 0-4 job titles."
    )


def _map_title(proposed: str, titles: list[str]) -> tuple[str, str]:
    match = difflib.get_close_matches(proposed, titles, n=1, cutoff=TITLE_MATCH_CUTOFF)
    if not match:
        return "", ""
    ratio = difflib.SequenceMatcher(None, proposed.lower(), match[0].lower()).ratio()
    return match[0], f"{ratio:.3f}"


def _ensure_model(model: str) -> None:
    try:
        available = {m.model for m in ollama.list().models}
    except Exception as err:  # server unreachable / not installed
        raise SystemExit(
            f"Cannot reach Ollama ({err}). Install it (brew install ollama), "
            f"start it (ollama serve), then: ollama pull {model}"
        ) from err
    if model not in available:
        raise SystemExit(f"Model {model!r} not found — run: ollama pull {model}")


def _tag(system: str, user: str) -> ExperienceTags | None:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        format=ExperienceTags.model_json_schema(),
        options={"temperature": 0},
    )
    content = response.message.content
    return ExperienceTags.model_validate_json(content) if content else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="tag only the first N")
    args = parser.parse_args()

    _ensure_model(MODEL)
    tag_type_of, skills, industries = _load_vocab()
    industry_set = {i.lower() for i in industries}
    titles = [str(t) for t in pd.read_csv(JOB_TITLES)["title"]]
    system = _system_prompt(skills, industries)

    experiences = pd.read_csv(EXPERIENCES)
    if args.limit:
        experiences = experiences.head(args.limit)

    tag_rows: list[dict[str, object]] = []
    title_rows: list[dict[str, str]] = []

    for i, (_, experience) in enumerate(experiences.iterrows()):
        experience_id = _clean(experience["experience_id"])
        user = (
            f"Name: {_clean(experience['name'])}\n"
            f"Details: {_clean(experience['search_text'])}"
        )
        try:
            tags = _tag(system, user)
        except Exception as err:  # one bad experience shouldn't abort the run
            print(f"  {experience_id}: skipped ({err})")
            continue
        if tags is None:
            continue

        for skill in tags.skills:
            key = skill.strip().lower()
            tag_rows.append(
                {
                    "experience_id": experience_id,
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
                    "experience_id": experience_id,
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
                    "experience_id": experience_id,
                    "proposed_title": proposed.strip(),
                    "matched_job_title": matched,
                    "similarity": similarity,
                }
            )

        if (i + 1) % 25 == 0:
            print(f"  tagged {i + 1}/{len(experiences)}")

    OUT_TAGS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        tag_rows, columns=["experience_id", "tag", "tag_type", "method", "canonical"]
    ).to_csv(OUT_TAGS, index=False)
    pd.DataFrame(
        title_rows,
        columns=["experience_id", "proposed_title", "matched_job_title", "similarity"],
    ).to_csv(OUT_TITLES, index=False)
    print(
        f"Wrote {len(tag_rows)} tags to {OUT_TAGS} and "
        f"{len(title_rows)} title suggestions to {OUT_TITLES}"
    )


if __name__ == "__main__":
    main()
