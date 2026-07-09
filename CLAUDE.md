# career-detective

AI powered job search tool for German tech industry

## Setup

After cloning:

```bash
just setup          # creates .venv, installs deps, and sets up pre-commit hooks
```

## Commands

```bash
just check          # full CI mirror: lint + test
just lint           # ruff check + format check
just fix            # auto-fix lint and formatting issues
just test           # pytest with coverage


```

## Architecture

- `src/career_detective/` — main package (src-layout)
- `tests/` — pytest tests; shared fixtures in `conftest.py`
- `notebooks/` — Jupyter notebooks for exploration
- `data/` — datasets (not committed; use DVC if `init_dvc=true`)


## Conventions

- All code must pass `mypy --strict` (disabled in this project — enable by adding `use_typecheck=true`)
- Format and lint: ruff (line length 88, Python 3.14+)
- Tests: pytest, fixtures in `conftest.py`
- Commits: Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, etc.
- PRs: squash-merge to main, delete branch after merge

