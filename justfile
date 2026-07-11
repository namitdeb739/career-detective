# List available recipes
default:
    @just --list

# Create GitHub repo and push (run once)
init-remote visibility="public":
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v gh &>/dev/null || ! gh auth status &>/dev/null 2>&1; then
        echo "gh CLI not found or not authenticated — run: gh auth login"
        exit 1
    fi

    # Create repo if it doesn't exist yet
    if ! gh repo view namitdeb739/career-detective &>/dev/null 2>&1; then
        gh repo create namitdeb739/career-detective \
            --{{visibility}} \
            --description "AI powered job search tool for German tech industry" \
            --source . \
            --remote origin \
            --push
        echo "✓ Created namitdeb739/career-detective and pushed"
    else
        # Repo exists — ensure remote is set and push
        if ! git remote get-url origin &>/dev/null 2>&1; then
            git remote add origin https://github.com/namitdeb739/career-detective.git
        fi
        git push -u origin main
        echo "✓ Pushed to existing repo namitdeb739/career-detective"
    fi

# Install dependencies and set up dev environment
setup:
    git config core.longpaths true
    uv sync --dev
    uv run pre-commit install

# Run all checks (mirrors CI)
check: lint test

# Lint and check formatting
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Auto-fix lint and formatting issues
fix:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/


# Run tests
test *args:
    uv run pytest -v {{ args }}


# Run tests with coverage

coverage:
    uv run pytest --cov=src --cov-report=term-missing


# --- Data pipeline ----------------------------------------------------------

# Build the controlled tag vocabulary from the jobs dataset
build-vocab:
    uv run python scripts/build_vocabulary.py

# Consolidate raw TUM sources into data/processed/tum_student_experiences.csv
build-experiences:
    uv run python scripts/build_experiences.py

# Standardize the jobs dataset (jobs, job_tags, job_titles)
build-jobs:
    uv run python scripts/build_jobs.py

# Dictionary-tag experiences against the vocabulary (free, no API)
tag-dict:
    uv run python scripts/tag_experiences_dict.py

# Regenerate every processed CSV except the LLM tags (no API key needed)
data: build-vocab build-experiences build-jobs tag-dict

# LLM tags: skills/industries/titles via local Ollama (try --limit 10)
tag-llm *args:
    uv run python scripts/tag_experiences_llm.py {{ args }}




# Launch Jupyter notebook server
notebook:
    uv run jupyter notebook notebooks/






# Audit dependencies for vulnerabilities
audit:
    uv run pip-audit


# Build package
build:
    uv build

# Bump version + changelog, create git tag, and push (usage: just release patch|minor|major)
release bump:
    #!/usr/bin/env bash
    set -euo pipefail
    just check
    uv run cz bump --increment "$(echo {{ bump }} | tr '[:lower:]' '[:upper:]')" --yes
    git push --follow-tags


# Initialize DVC (run once)
dvc-init:
    uv run dvc init
    uv run dvc config core.autostage true







# Run the Streamlit app
app:
    uv run streamlit run src/career_detective/app.py




# Clean build artifacts
clean:
    rm -rf dist/ build/ .pytest_cache/ .ruff_cache/ htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} +
