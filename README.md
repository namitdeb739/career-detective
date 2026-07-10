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
