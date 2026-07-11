"""LLM inferential tagging (step 5): skills, industries, titles, and regions.

Runs locally and free via Ollama — no API key, no data leaves the machine.
For each consolidated experience, a local model (default qwen2.5:7b) infers
applicable skills and industries from the controlled vocabulary (canonical
tags, plus open terms where nothing fits), proposes plausible job titles, and
notes any cultural/linguistic country affinity (`regions`). Proposed titles are
mapped to the real job titles by *semantic* similarity (a local embedding
model), so "Aerospace Engineer" no longer collapses onto "Prompt Engineer".

One-time setup:

    brew install ollama            # or download from https://ollama.com
    ollama serve &                 # start the local server
    ollama pull qwen2.5:7b         # ~4.7 GB  — the tagging model
    ollama pull nomic-embed-text   # ~0.3 GB  — title-matching embeddings

Run:

    uv run python scripts/tag_experiences_llm.py              # all experiences
    uv run python scripts/tag_experiences_llm.py --limit 10   # quick check
    OLLAMA_MODEL=qwen2.5:14b uv run python scripts/tag_experiences_llm.py
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import ollama
import pandas as pd
from pydantic import BaseModel

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EXPERIENCES = Path("data/processed/tum_student_experiences.csv")
VOCAB = Path("data/reference/vocabulary.csv")
JOB_TITLES = Path("data/processed/job_titles.csv")
JOBS = Path("data/processed/jobs.csv")
OUT_TAGS = Path("data/processed/experience_tags_llm.csv")
OUT_TITLES = Path("data/processed/experience_job_titles.csv")
OUT_REGIONS = Path("data/processed/experience_regions.csv")

# Cosine threshold on nomic-embed-text vectors; calibrate on the first run.
TITLE_MATCH_CUTOFF = 0.65

# ESCO-style transversal (transferable) skills — a small controlled set. These
# apply across all jobs, so they let non-tech experiences earn a real score.
TRANSVERSAL_SKILLS = [
    "Communication",
    "Teamwork",
    "Leadership",
    "Public Speaking",
    "Project Management",
    "Problem Solving",
    "Critical Thinking",
    "Adaptability",
    "Intercultural Competence",
    "Event Organization",
    "Networking",
    "Time Management",
]


class ExperienceTags(BaseModel):
    skills: list[str]
    industries: list[str]
    job_titles: list[str]
    regions: list[str]
    transversal: list[str]


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


def _system_prompt(
    skills: list[str], industries: list[str], countries: list[str]
) -> str:
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
        "For `regions`: only cultural, national, or language experiences qualify "
        "(a Japanese culture club -> Japan; a Portuguese-speaking club -> Brazil, "
        "Portugal). Use these exact country names where they apply:\n"
        + ", ".join(countries)
        + "\nLeave `regions` empty for the vast majority.\n\n"
        "For `transversal`: the transferable skills the experience builds, from "
        "this exact list (most experiences build a few — a debate club builds "
        "Public Speaking, Critical Thinking; a sports club builds Teamwork):\n"
        + ", ".join(TRANSVERSAL_SKILLS)
        + "\n\n"
        "Tag only skills the experience ITSELF develops through its own core "
        "activity. A broad umbrella, incubator, or connector that merely links "
        "students to external projects across many fields does NOT itself build "
        "those fields' skills — tag only what its own work involves, never the "
        "union of everything its members might touch. List at most 8 skills, the "
        "most central ones.\n\n"
        "Return only tags genuinely supported by the experience — an unrelated club "
        "(hiking, choir) may yield empty technical skills but still has transversal "
        "ones. Propose 0-4 job titles."
    )


def _embed(texts: list[str]) -> list[list[float]]:
    response = ollama.embed(model=EMBED_MODEL, input=texts)
    return [list(vector) for vector in (response.embeddings or [])]


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class _TitleMatcher:
    """Maps a proposed job title to the nearest real title by embedding cosine."""

    def __init__(self, titles: list[str]) -> None:
        self.titles = titles
        self.matrix = [_unit(vector) for vector in _embed(titles)]

    def map_many(self, proposed: list[str]) -> list[tuple[str, str]]:
        if not proposed:
            return []
        results: list[tuple[str, str]] = []
        for vector in (_unit(v) for v in _embed(proposed)):
            best_i, best_score = -1, 0.0
            for i, row in enumerate(self.matrix):
                score = sum(a * b for a, b in zip(row, vector, strict=True))
                if score > best_score:
                    best_i, best_score = i, score
            if best_i >= 0 and best_score >= TITLE_MATCH_CUTOFF:
                results.append((self.titles[best_i], f"{best_score:.3f}"))
            else:
                results.append(("", ""))
        return results


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


def _ensure_models(models: list[str]) -> None:
    try:
        available = {m.model for m in ollama.list().models}
    except Exception as err:  # server unreachable / not installed
        raise SystemExit(
            f"Cannot reach Ollama ({err}). Install it (brew install ollama) and "
            "start it (ollama serve)."
        ) from err
    missing = [
        m for m in models if m not in available and f"{m}:latest" not in available
    ]
    if missing:
        pulls = "; ".join(f"ollama pull {m}" for m in missing)
        raise SystemExit(
            f"Missing Ollama model(s): {', '.join(missing)} — run: {pulls}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="tag only the first N")
    args = parser.parse_args()

    _ensure_models([MODEL, EMBED_MODEL])
    tag_type_of, skills, industries = _load_vocab()
    industry_set = {i.lower() for i in industries}
    countries = sorted({str(c) for c in pd.read_csv(JOBS)["country"]})
    matcher = _TitleMatcher([str(t) for t in pd.read_csv(JOB_TITLES)["title"]])
    system = _system_prompt(skills, industries, countries)

    experiences = pd.read_csv(EXPERIENCES)
    if args.limit:
        experiences = experiences.head(args.limit)

    tag_rows: list[dict[str, object]] = []
    title_rows: list[dict[str, str]] = []
    region_rows: list[dict[str, str]] = []

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
        for transversal in tags.transversal:
            if transversal.strip():
                tag_rows.append(
                    {
                        "experience_id": experience_id,
                        "tag": transversal.strip(),
                        "tag_type": "transversal",
                        "method": "llm",
                        "canonical": False,
                    }
                )
        proposed = [p.strip() for p in tags.job_titles if p.strip()]
        mapped = matcher.map_many(proposed)
        for title, (matched, similarity) in zip(proposed, mapped, strict=True):
            title_rows.append(
                {
                    "experience_id": experience_id,
                    "proposed_title": title,
                    "matched_job_title": matched,
                    "similarity": similarity,
                }
            )
        for region in tags.regions:
            if region.strip():
                region_rows.append(
                    {"experience_id": experience_id, "country": region.strip()}
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
    pd.DataFrame(region_rows, columns=["experience_id", "country"]).to_csv(
        OUT_REGIONS, index=False
    )
    print(
        f"Wrote {len(tag_rows)} tags, {len(title_rows)} title suggestions, "
        f"{len(region_rows)} regions"
    )


if __name__ == "__main__":
    main()
