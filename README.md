# career-detective

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

AI powered job search tool for German tech industry

## Common commands

```bash
just check       # lint + test (mirrors CI)
just fix         # auto-fix lint and formatting
just test        # run tests
just release X   # bump version (patch/minor/major), tag, push
just             # list all available recipes
```

## Project structure

```text
src/career_detective/   Source package (src layout)
src/career_detective/app.py   streamlit app — run with `just app`
tests/                    Test suite (pytest)
notebooks/                Jupyter notebooks
data/                     Datasets (gitignored, DVC-ready)
```


## License

[MIT](LICENSE) — Namit Deb
