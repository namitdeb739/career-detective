"""Consolidate the raw TUM datasets into one standardized entities table.

Unions clubs, student groups, programmes, and PREP research projects, deduped
by normalized name, into `data/processed/entities.csv`. Every
skill/industry-relevant text field from each source is folded into
`search_text` — the single field downstream tagging reads — so nothing is
missed (PREP keyword/research_area/department, club focus_areas, programme
tags, etc.). programmes covers only ~72/200 clubs, so all four sources are
unioned rather than treating any one as canonical.

Run:
    uv run python scripts/build_entities.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

OUTPUT = Path("data/processed/entities.csv")


@dataclass(frozen=True)
class Source:
    key: str
    path: Path
    name_col: str
    text_cols: tuple[str, ...]
    desc_col: str
    url_col: str
    cat_col: str | None


SOURCES: tuple[Source, ...] = (
    Source(
        "clubs",
        Path("data/raw/tum_clubs.csv"),
        "name",
        ("name", "description", "focus_areas"),
        "description",
        "website",
        "focus_areas",
    ),
    Source(
        "groups",
        Path("data/raw/tum_student_groups.csv"),
        "name",
        ("name", "description"),
        "description",
        "website",
        None,
    ),
    Source(
        "programmes",
        Path("data/raw/tum_programmes.csv"),
        "sub-program",
        ("sub-program", "program", "description", "tags"),
        "description",
        "url",
        "program",
    ),
    Source(
        "prep",
        Path("data/raw/tum_prep_projects.csv"),
        "project_name",
        (
            "project_name",
            "department",
            "keyword",
            "research_area",
            "chair_institute",
            "student_background",
            "further_disciplines",
            "description",
        ),
        "description",
        "page_url",
        "department",
    ),
)


@dataclass
class Entity:
    name: str
    sources: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)
    description: str = ""
    category: str = ""
    url: str = ""


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    text = str(value).strip()
    return "" if text in {"-", "nan"} else text


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "entity"


def build_entities() -> pd.DataFrame:
    entities: dict[str, Entity] = {}
    order: list[str] = []

    for src in SOURCES:
        df = pd.read_csv(src.path)
        for _, row in df.iterrows():
            name = _clean(row[src.name_col])
            if not name:
                continue
            key = _norm(name)
            ent = entities.get(key)
            if ent is None:
                ent = Entity(name=name)
                entities[key] = ent
                order.append(key)
            if src.key not in ent.sources:
                ent.sources.append(src.key)
            for col in src.text_cols:
                frag = _clean(row[col])
                if frag and frag not in ent.fragments:
                    ent.fragments.append(frag)
            desc = _clean(row[src.desc_col])
            if len(desc) > len(ent.description):
                ent.description = desc
            if not ent.category and src.cat_col:
                ent.category = _clean(row[src.cat_col])
            if not ent.url:
                ent.url = _clean(row[src.url_col])

    rows: list[dict[str, str]] = []
    used_slugs: set[str] = set()
    for key in order:
        ent = entities[key]
        base = _slug(ent.name)
        slug = base
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        rows.append(
            {
                "entity_id": slug,
                "name": ent.name,
                "sources": "|".join(ent.sources),
                "category": ent.category,
                "description": ent.description,
                "search_text": " | ".join(ent.fragments),
                "url": ent.url,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "entity_id",
            "name",
            "sources",
            "category",
            "description",
            "search_text",
            "url",
        ],
    )


def main() -> None:
    entities = build_entities()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    entities.to_csv(OUTPUT, index=False)
    merged = int(entities["sources"].str.contains("|", regex=False).sum())
    print(f"Wrote {len(entities)} entities to {OUTPUT} ({merged} multi-source)")


if __name__ == "__main__":
    main()
