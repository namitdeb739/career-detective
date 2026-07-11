# Data pipeline: raw TUM sources → entity schema

How four scraped TUM datasets become one standardized, tagged **entity** schema
that matches student clubs / programmes / research projects to AI-tech jobs.

The whole thing regenerates with **`just data`** (+ `just tag-llm` for the
local-LLM step). See the [README](../README.md#data-pipeline) for commands.

---

## 1. At a glance

```mermaid
flowchart TB
    subgraph raw ["Raw TUM sources — data/raw/"]
        clubs["tum_clubs.csv<br>200"]
        groups["tum_student_groups.csv<br>140"]
        progs["tum_programmes.csv<br>188"]
        prep["tum_prep_projects.csv<br>83"]
    end

    jobsraw["data/cleaned/<br>ai_jobs_2026_cleaned.csv<br>51,932"]

    clubs --> BE
    groups --> BE
    progs --> BE
    prep --> BE
    BE["build_entities.py<br>union + dedupe by name"] --> entities["entities.csv<br>402"]

    jobsraw --> BV["build_vocabulary.py"] --> vocab["vocabulary.csv<br>91 tags"]

    entities --> TD["tag_entities_dict.py<br>verbatim match"] --> tdict["entity_tags_dict.csv"]
    entities --> TL["tag_entities_llm.py<br>Ollama inference"] --> tllm["entity_tags_llm.csv"]
    TL --> titles["entity_job_titles.csv"]
    vocab -.canonical.-> TD
    vocab -.canonical.-> TL

    jobsraw --> BJ["build_jobs.py"]
    BJ --> jobs["jobs.csv"]
    BJ --> jtags["job_tags.csv"]
    vocab -.filter.-> BJ

    tdict -. shared tag .-> jtags
    tllm -. shared tag .-> jtags
```

The **vocabulary** is the linchpin: the TUM side and the jobs side draw tags
from the *same* controlled set, so matching is an exact join, not fuzzy NLP.

---

## 2. Consolidating the raw TUM sources

The four sources overlap heavily but none is a superset — programmes covers only
**72/200** clubs, so all four are **unioned and deduped by normalized name**
rather than treating any one as canonical.

| Source | Rows | Key columns |
| --- | --- | --- |
| `tum_clubs.csv` | 200 | name, description, **focus_areas** |
| `tum_student_groups.csv` | 140 | name, description |
| `tum_programmes.csv` | 188 | sub-program, program, description, **tags** |
| `tum_prep_projects.csv` | 83 | project_name, department, keyword, research_area, chair_institute, student_background, further_disciplines, description |

**Field folding.** Every skill/industry-relevant field is concatenated into one
`search_text` field, so the downstream tagging reads a single field and nothing
is missed:

| Source | Folded into `search_text` |
| --- | --- |
| clubs | name · description · focus_areas |
| groups | name · description |
| programmes | sub-program · program · description · tags |
| prep | project_name · department · keyword · research_area · chair_institute · student_background · further_disciplines · description |

Result — `entities.csv` (402 rows; 137 appear in >1 source):

```text
entity_id    slug of the name (PK)
name         display name
sources      provenance, e.g. "clubs|groups|programmes"
category     best-effort (programme category / focus area / dept)
description  longest description across sources
search_text  all folded text — the field tagging reads
url          first non-empty link
```

---

## 3. Tagging entities

Two passes write to long/tidy tag tables. Both reference `vocabulary.csv`
(`tag, tag_type, job_count`), whose `tag_type` ∈ `skill | language |
specialization | industry`.

- **`tag_entities_dict.py`** → `entity_tags_dict.csv` — high-precision
  **verbatim** matches of canonical terms (`method=dict`, `confidence=1.0`).
- **`tag_entities_llm.py`** → `entity_tags_llm.csv` — **inferential** local-LLM
  tags: a robotics club yields ROS / Control Systems even if unstated
  (`method=llm`). Also emits `entity_job_titles.csv`.

```text
entity_tags_dict   entity_id, tag, tag_type, confidence, method, canonical
entity_tags_llm    entity_id, tag, tag_type, method, canonical
entity_job_titles  entity_id, proposed_title, matched_job_title, similarity
```

`canonical = True` means the tag is in the vocabulary (joins to jobs);
`False` is an open enrichment term (ROS, "Culture & the Arts"). Current split is
~70 % canonical / 30 % open.

Job titles are kept **separate** because titles are *not* a controlled
vocabulary — they are free-text LLM proposals fuzzy-mapped to the 37 real job
titles, so they don't fit the `(tag, tag_type)` shape.

---

## 4. The schema

```mermaid
erDiagram
    ENTITIES ||--o{ ENTITY_TAGS_DICT : has
    ENTITIES ||--o{ ENTITY_TAGS_LLM : has
    ENTITIES ||--o{ ENTITY_JOB_TITLES : has
    VOCABULARY ||--o{ ENTITY_TAGS_DICT : constrains
    VOCABULARY ||--o{ ENTITY_TAGS_LLM : constrains
    VOCABULARY ||--o{ JOB_TAGS : constrains
    JOBS ||--o{ JOB_TAGS : has
    ENTITY_TAGS_LLM }o--o{ JOB_TAGS : "match on tag+tag_type"

    ENTITIES {
        string entity_id PK
        string name
        string sources
        string category
        string description
        string search_text
        string url
    }
    ENTITY_TAGS_LLM {
        string entity_id FK
        string tag
        string tag_type
        string method
        bool canonical
    }
    ENTITY_TAGS_DICT {
        string entity_id FK
        string tag
        string tag_type
        float confidence
        string method
        bool canonical
    }
    ENTITY_JOB_TITLES {
        string entity_id FK
        string proposed_title
        string matched_job_title
        float similarity
    }
    VOCABULARY {
        string tag PK
        string tag_type
        int job_count
    }
    JOBS {
        string job_id PK
        string title
        string company
        string industry
        string country
        string salary_mid_usd
    }
    JOB_TAGS {
        string job_id FK
        string tag
        string tag_type
    }
```

An entity matches a job by **overlap of shared canonical `(tag, tag_type)`**;
`jobs` supplies salary / geography / demand context.

---

## 5. Why it's shaped this way

- **Dimension + long tag tables, not one wide table.** The four sources have
  very different columns; a wide table would be mostly NULLs. Long tables
  (`entity_id, tag, tag_type`) are the tidy form that powers filtering and joins.
- **Union, not "pick the richest source".** programmes misses 128/200 clubs, so
  every source contributes; `sources` records where each entity came from.
- **One `search_text` field** guarantees the tagger sees every relevant signal
  from every source in one place.
- **`canonical` flag = the hybrid vocabulary decision** — canonical tags join to
  jobs, open tags enrich the profile without forcing everything into an AI/ML
  taxonomy.
- **Split tag tables by `method`** (dict vs llm) preserve provenance and trust;
  they are merged into a single `entity_tags` in step 6.

---

## 6. Not yet built (step 6+)

- A unified `entity_tags` (merge dict + llm, dedupe on `entity_id, tag,
  tag_type`; reconcile the `confidence` column — present on dict, absent on llm).
- Entity ↔ job matching on shared canonical tags, ranked and enriched with
  `jobs` fields.
