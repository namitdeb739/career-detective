# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Career-Detective matches TUM student experiences (clubs, programs, research projects) with AI/tech job postings using a two-pass tagging pipeline (dictionary + local LLM) and a five-field weighted scoring system. The core output is a ranked list of student experiences relevant to specific job postings, consumable as JSON for the frontend.

## Setup

```bash
just setup          # creates .venv, installs deps, and sets up pre-commit hooks
```

The LLM pipeline requires [Ollama](https://ollama.com/) running locally with:
```bash
ollama pull qwen2.5:7b          # ~4.7 GB, used for tag inference
ollama pull nomic-embed-text    # ~0.3 GB, used for job title similarity
```

## Commands

```bash
just check          # full CI mirror: lint + test
just lint           # ruff check + format check
just fix            # auto-fix lint and formatting issues
just test           # pytest with coverage
just coverage       # coverage report with missing lines
just app            # launch Streamlit dashboard
just notebook       # Jupyter server

# Run a single test file or test
uv run pytest tests/test_config.py
uv run pytest tests/test_main.py::test_name
```

## Data Pipeline

The pipeline transforms 4 TUM source CSVs + 51k AI job postings into tagged experience-job matches.

```bash
just data           # all stages except LLM (no Ollama needed)
just pipeline       # full pipeline including LLM tagging

# Individual stages (run in order):
just build-vocab        # extract 91 canonical tags from jobs → data/reference/vocabulary.csv
just build-experiences  # consolidate 4 TUM sources → data/processed/tum_student_experiences.csv
just build-jobs         # standardize jobs → jobs.csv, job_tags.csv, job_titles.csv
just tag-dict           # verbatim tag matching (high-precision, confidence=1.0)
just tag-llm            # LLM inferential tagging (set OLLAMA_MODEL=qwen2.5:14b to override)
just merge-tags         # unify dict + LLM tags → experience_tags.csv

# Matching (final output):
just match --sample 5 --top 5                       # random 5 jobs, top 5 experiences
just match --jobs job-1,job-2 --top 10              # specific job IDs
just match --jobs job-1 --broaden 3 --json          # JSON output with diversity lane
just match --jobs job-1 --prefs prefs.json          # with career preferences
```

## Architecture

```
data/raw/           # 4 TUM source CSVs (committed)
data/reference/     # vocabulary.csv — 91 canonical tags (committed, the join key)
data/cleaned/       # pre-processed job postings (not committed)
data/processed/     # pipeline outputs (regenerated, not committed)
src/career_detective/
  app.py            # Streamlit dashboard (placeholder, expand here)
  config.py         # typed dataclass config with .env support
  data.py           # load_csv() helper
  main.py           # CLI entry point (career-detective command)
scripts/            # data pipeline (13 files, see below)
docs/               # data-pipeline.md, match-json.md, diversity design
public/data/        # static data assets for frontend
```

### Pipeline Stage Files (`scripts/`)

| File | Stage | Input → Output |
|------|-------|----------------|
| `build_vocabulary.py` | 1 | cleaned jobs → `vocabulary.csv` |
| `build_experiences.py` | 2 | 4 TUM CSVs → `tum_student_experiences.csv` |
| `build_jobs.py` | 3 | cleaned jobs → `jobs.csv`, `job_tags.csv`, `job_titles.csv` |
| `tag_experiences_dict.py` | 4 | experiences + vocab → `experience_tags_dict.csv` |
| `tag_experiences_llm.py` | 5 | experiences + vocab + titles → `experience_tags_llm.csv`, `experience_job_titles.csv`, `experience_regions.csv` |
| `merge_experience_tags.py` | 6 | dict + llm tags → `experience_tags.csv` |
| `match_experiences.py` | 7 | all above → ranked JSON or console output |

### Job Matching Layer (`scripts/findJobs.py`)

A separate job-ranking engine that operates on `jobs_enriched_with_layoffs_complete.csv` (the enriched raw dataset, not the processed `jobs.csv`). Entry point is `search_jobs(filters, top_k, ...)` or `find_top_k_jobs(df, filters, ...)`.

**Filter format:**
```python
{"title": {"data": "AI Engineer", "dealBreaker": True}, ...}
# Supported fields: title, domain, country, company_size, work_format, experience_level, education_level
# dealBreaker=True → hard exclusion filter; False → soft scoring input
```

**Scoring flow:**
1. Hard filters eliminate jobs below threshold (NLP fields: cosine ≥ 0.35; others: exact/alias match)
2. Remaining jobs are scored by embedding similarity of a combined job text vs combined query text
3. MMR (`mmr_lambda=0.7` default) re-ranks the top-200 candidates for semantic diversity
4. `max_per_company=1` and `max_per_title=1` caps prevent duplicate results

**Tunable constants** (top of file): `NLP_HARD_THRESHOLD`, `MMR_CANDIDATE_POOL`, `MMR_LAMBDA_DEFAULT`, `DOMAIN_PRIMARY_WEIGHT`.

Sentence embeddings use `all-MiniLM-L6-v2` (lazy-loaded, cached at module level). Corpus embeddings are cached by content — calling `search_jobs` repeatedly on the same dataset only re-encodes the short query string.

### End-to-End Pipeline (`scripts/run_pipeline.py`)

Chains `findJobs.py` → `match_experiences.py` in one call:
1. Filters the 51k job postings → top N jobs via `find_top_k_jobs`
2. Feeds those job IDs into `match_clubs` → ranked TUM club recommendations

```bash
uv run python scripts/run_pipeline.py --top-jobs 5 --top-clubs 5 --broaden 3
uv run python scripts/run_pipeline.py --json   # JSON output
```

Edit `DEFAULT_FILTERS` in `run_pipeline.py` to change the active query.

### Matching Scoring Weights

`skills` (55%) + `title` (17%) + `transversal` (13%) + `industry` (8%) + `geo` (7%)

Club results use MMR to produce two lanes: a skills-focused lane (λ=0.6) and a "broaden your profile" diversity lane (λ=0.5). Career preferences (`--prefs`) apply multiplicative boosts without overriding the skills-driven baseline.

### Key Data Contracts

- `vocabulary.csv` is the single join key — all tag matching is exact (no fuzzy NLP). Tags not in vocabulary are ignored in scoring.
- `experience_tags.csv` is long/tidy format: `(experience_id, tag, tag_type, confidence, method, canonical)`
- JSON output shape is documented in `docs/match-json.md`

### Frontend

Vite + D3.js project (named "career-orbit"). The backend produces JSON via `just match --json`; the frontend consumes it. See `docs/match-json.md` for the exact contract.

## Conventions

- Format and lint: ruff (line length 88, Python 3.14+)
- Tests: pytest, fixtures in `conftest.py`
- Commits: Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, etc.
- PRs: squash-merge to main, delete branch after merge
- mypy is disabled (enable with `use_typecheck=true` if needed)
