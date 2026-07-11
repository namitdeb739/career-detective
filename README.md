# career-detective

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Our project analyzes AI and Tech job market trends to help people better understand career opportunities in Germany compared to other developed countries. We aim to build an interactive web app or art visualization to demonstrate AI job availability, salary distributions, entry-level opportunities, and regional demand across countries. Rather than relying on fragmented job boards, we will use machine learning to aggregate and analyze large scale job posting data. This project will help graduates and job seekers to better navigate the current job market as well as help students to familiarize with ongoing trends to prepare earlier.

## Common commands

```bash
just check       # lint + test (mirrors CI)
just fix         # auto-fix lint and formatting
just test        # run tests
just release X   # bump version (patch/minor/major), tag, push
just             # list all available recipes
```

## Data pipeline

Turns the raw TUM sources and the AI-jobs dataset into a standardized set of
tables that match student clubs/programmes/projects to relevant skills,
industries, and job titles. See
[docs/data-pipeline.md](docs/data-pipeline.md) for the full flow, schema, and
diagrams.

**Inputs** (in `data/`):

- `data/raw/tum_clubs.csv`, `tum_student_groups.csv`, `tum_programmes.csv`,
  `tum_prep_projects.csv` — scraped TUM sources (`scripts/scrape_tum_*.py`)
- `data/cleaned/ai_jobs_2026_cleaned.csv` — the jobs dataset

**One command for the whole thing** (needs Ollama running — see setup below):

```bash
just pipeline      # build-vocab → build-experiences → build-jobs → tag-dict → tag-llm → merge-tags
```

Or the no-Ollama subset (everything except the LLM tagging):

```bash
just data          # build-vocab → build-experiences → build-jobs → tag-dict → merge-tags
```

Stages also run individually: `just build-vocab`, `just build-experiences`,
`just build-jobs`, `just tag-dict`, `just merge-tags`.

**LLM inferential tagging** (skills, industries, titles, regions, transversal skills) runs **locally and
free via [Ollama](https://ollama.com)** — no API key, no data leaves your
machine. One-time setup, then run:

```bash
brew install ollama            # or download from https://ollama.com
ollama serve &                 # start the local server
ollama pull qwen2.5:7b         # ~4.7 GB — tagging model (default)
ollama pull nomic-embed-text   # ~0.3 GB — semantic title matching

just tag-llm --limit 10   # quick check first
just tag-llm              # all experiences
# pick a bigger model: OLLAMA_MODEL=qwen2.5:14b just tag-llm
```

**Match experiences to a job set** (no LLM needed once tags exist):

```bash
just match --sample 5 --top 5                # 5 random jobs → top 5 experiences
just match --jobs job-1,job-2 --top 10
just match --jobs job-1,job-2 --prefs prefs.json   # bias by career preferences
just match --jobs job-1,job-2 --broaden 3          # + opt-in "broaden" picks
just match --jobs job-1,job-2 --json               # machine-readable output
```

`--json` emits the received job set (verbatim) and the matched experiences
(`name`, `description`, `skills`, `score`) for downstream consumers (e.g. the app).

The default is a single skills-forward list (MMR-diversified). `--broaden N`
adds an opt-in *broaden your profile* lane (transferable-skill clubs). `--prefs`
takes a JSON career profile (desired country/title/domain/company-size/education,
each with a `dealBreaker` flag) that sharpens the experience search.

**Outputs** (in `data/`):

| File | Committed? | Produced by |
| --- | --- | --- |
| `data/reference/vocabulary.csv` | ✅ | `build-vocab` |
| `data/processed/tum_student_experiences.csv` | regenerated | `build-experiences` |
| `data/processed/jobs.csv`, `job_tags.csv` | regenerated | `build-jobs` |
| `data/processed/job_titles.csv` | ✅ | `build-jobs` |
| `data/processed/experience_tags_dict.csv` | ✅ | `tag-dict` |
| `data/processed/experience_tags_llm.csv`, `experience_job_titles.csv`, `experience_regions.csv` | regenerated | `tag-llm` |
| `data/processed/experience_tags.csv` (unified dict + llm) | regenerated | `merge-tags` |

Large derived tables (`tum_student_experiences.csv`, `jobs.csv`, `job_tags.csv`) are
gitignored — regenerate them with `just data`. The scripts are their
provenance.

## Project structure

```text
src/career_detective/   Source package (src layout)
src/career_detective/app.py   streamlit app — run with `just app`
scripts/                  Scrapers + data-pipeline scripts (see Data pipeline)
tests/                    Test suite (pytest)
notebooks/                Jupyter notebooks
data/raw, data/cleaned, data/processed, data/reference   Datasets
```

## License

[MIT](LICENSE) — Namit Deb
