"""
explore_filters.py — interactive experiment runner for findJobs.py

Runs named filter experiments and prints side-by-side diff tables showing how
results change across:
  1. Different filter fields (minimal → comprehensive)
  2. Same value, dealBreaker True vs False (hard vs soft)
  3. Same filters, different MMR lambda (diversity vs relevance)

Usage:
  uv run python scripts/explore_filters.py
  uv run python scripts/explore_filters.py --group dealbreaker
  uv run python scripts/explore_filters.py --group lambda --top 8
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import pandas as pd

# ── Resolve project root so we can import from scripts/ ──────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from findJobs import DEFAULT_DATA_PATH, find_top_k_jobs  # noqa: E402

# ── Display helpers ───────────────────────────────────────────────────────────
RESULT_COLS = ["Job Title", "Company Name", "Country", "AI Specialization", "match_score"]
COL_WIDTHS   = [32, 22, 16, 24, 6]


def _trunc(s, n):
    s = str(s) if pd.notna(s) else ""
    return s[:n] if len(s) <= n else s[: n - 1] + "…"


def _header_line():
    parts = [f"{'#':>2}"] + [_trunc(c, w).ljust(w) for c, w in zip(RESULT_COLS, COL_WIDTHS)]
    return "  ".join(parts)


def _row_line(rank, row):
    vals = [row.get(c, "") for c in RESULT_COLS]
    # format match_score as 0.000
    vals[-1] = f"{float(vals[-1]):.3f}" if pd.notna(vals[-1]) else "—"
    parts = [f"{rank:>2}"] + [_trunc(v, w).ljust(w) for v, w in zip(vals, COL_WIDTHS)]
    return "  ".join(parts)


def _separator():
    widths = [2] + COL_WIDTHS
    return "  ".join("─" * w for w in widths)


def print_results(label: str, results: list[dict], filters: dict):
    """Pretty-print one experiment's results."""
    active = {
        k: ("HARD" if v["dealBreaker"] else "soft")
        for k, v in filters.items()
    }
    filter_summary = "  |  ".join(f"{k}={v['data']!r} [{active[k]}]" for k, v in filters.items())
    print(f"\n{'═' * 110}")
    print(f"  {label}")
    print(f"  Filters: {filter_summary}")
    print(f"  → {len(results)} results returned")
    print(_separator())
    print(_header_line())
    print(_separator())
    for rank, job in enumerate(results, 1):
        print(_row_line(rank, job))
    print(_separator())


def compare_two(label_a: str, results_a: list, label_b: str, results_b: list):
    """Show which jobs appear only in A, only in B, or in both (by Job Title)."""
    titles_a = {r.get("Job Title", "") for r in results_a}
    titles_b = {r.get("Job Title", "") for r in results_b}
    only_a = titles_a - titles_b
    only_b = titles_b - titles_a
    shared  = titles_a & titles_b

    w = 38
    print(f"\n  Diff: {label_a!r}  vs  {label_b!r}")
    print(f"  {'Shared':>{w}}   {'Only in A':>{w}}   {'Only in B':>{w}}")
    print(f"  {'─' * w}   {'─' * w}   {'─' * w}")
    rows = max(len(shared), len(only_a), len(only_b))
    shared_l, only_a_l, only_b_l = sorted(shared), sorted(only_a), sorted(only_b)
    for i in range(rows):
        s = _trunc(shared_l[i],  w) if i < len(shared_l)  else ""
        a = _trunc(only_a_l[i],  w) if i < len(only_a_l) else ""
        b = _trunc(only_b_l[i],  w) if i < len(only_b_l) else ""
        print(f"  {s:<{w}}   {a:<{w}}   {b:<{w}}")


# ── Experiment groups ─────────────────────────────────────────────────────────

def group_filter_fields(df: pd.DataFrame, top_k: int):
    """How does adding more filter fields expand / narrow results?"""
    print("\n" + "▶" * 3 + "  GROUP 1: Different filter fields  " + "◀" * 3)

    experiments = {
        "A — title only (HARD)": {
            "title": {"data": "Machine Learning Engineer", "dealBreaker": True},
        },
        "B — title (HARD) + domain (soft)": {
            "title":  {"data": "Machine Learning Engineer", "dealBreaker": True},
            "domain": {"data": "Computer Vision",          "dealBreaker": False},
        },
        "C — title (HARD) + domain (soft) + country (soft)": {
            "title":   {"data": "Machine Learning Engineer", "dealBreaker": True},
            "domain":  {"data": "Computer Vision",           "dealBreaker": False},
            "country": {"data": "Germany",                   "dealBreaker": False},
        },
        "D — full soft basket (no HARD filters)": {
            "domain":           {"data": "NLP",     "dealBreaker": False},
            "company_size":     {"data": "mid",     "dealBreaker": False},
            "work_format":      {"data": "remote",  "dealBreaker": False},
            "experience_level": {"data": "mid",     "dealBreaker": False},
            "education_level":  {"data": "msc",     "dealBreaker": False},
        },
        "E — title (soft) + domain (soft) [no hard filter at all]": {
            "title":  {"data": "Machine Learning Engineer", "dealBreaker": False},
            "domain": {"data": "Computer Vision",           "dealBreaker": False},
        },
    }

    results_list = []
    for label, filters in experiments.items():
        res = find_top_k_jobs(df, filters, top_k=top_k)
        results_list.append((label, filters, res))
        print_results(label, res, filters)

    # pairwise diff: A vs B, B vs C
    compare_two("A", results_list[0][2], "B", results_list[1][2])
    compare_two("B", results_list[1][2], "C", results_list[2][2])
    compare_two("C", results_list[2][2], "D", results_list[3][2])


def group_dealbreaker(df: pd.DataFrame, top_k: int):
    """Same filter value — toggle dealBreaker.  Hard filter = fewer candidates."""
    print("\n" + "▶" * 3 + "  GROUP 2: DealBreaker True vs False  " + "◀" * 3)

    base = "Data Scientist"

    experiments = {
        "A — title as soft filter only": {
            "title":   {"data": base,    "dealBreaker": False},
            "country": {"data": "United States", "dealBreaker": False},
        },
        "B — title as HARD filter (cosine ≥ 0.35)": {
            "title":   {"data": base,    "dealBreaker": True},
            "country": {"data": "United States", "dealBreaker": False},
        },
        "C — title soft, country HARD (exact match)": {
            "title":   {"data": base,    "dealBreaker": False},
            "country": {"data": "United States", "dealBreaker": True},
        },
        "D — title HARD + country HARD (most restrictive)": {
            "title":   {"data": base,    "dealBreaker": True},
            "country": {"data": "United States", "dealBreaker": True},
        },
        "E — title HARD + country HARD + exp soft": {
            "title":            {"data": base,            "dealBreaker": True},
            "country":          {"data": "United States", "dealBreaker": True},
            "experience_level": {"data": "senior",        "dealBreaker": False},
        },
        "F — title HARD + country HARD + exp HARD (most restrictive)": {
            "title":            {"data": base,            "dealBreaker": True},
            "country":          {"data": "United States", "dealBreaker": True},
            "experience_level": {"data": "senior",        "dealBreaker": True},
        },
    }

    results_list = []
    for label, filters in experiments.items():
        res = find_top_k_jobs(df, filters, top_k=top_k)
        results_list.append((label, filters, res))
        print_results(label, res, filters)

    compare_two("A (title soft)", results_list[0][2], "B (title HARD)", results_list[1][2])
    compare_two("B (title HARD)", results_list[1][2], "D (title+country HARD)", results_list[3][2])
    compare_two("E (exp soft)",   results_list[4][2], "F (exp HARD)",           results_list[5][2])


def group_lambda(df: pd.DataFrame, top_k: int):
    """Same filters — vary MMR lambda (relevance vs diversity trade-off)."""
    print("\n" + "▶" * 3 + "  GROUP 3: Same filters, different MMR lambda  " + "◀" * 3)

    filters = {
        "title":            {"data": "AI Engineer",    "dealBreaker": True},
        "domain":           {"data": "Generative AI",  "dealBreaker": False},
        "work_format":      {"data": "hybrid",         "dealBreaker": False},
        "experience_level": {"data": "mid",            "dealBreaker": False},
    }

    lambdas = {
        "λ=1.0  pure relevance":             1.0,
        "λ=0.7  default (relevance-leaning)": 0.7,
        "λ=0.5  balanced":                    0.5,
        "λ=0.3  diversity-leaning":           0.3,
    }

    results_list = []
    for label, lam in lambdas.items():
        res = find_top_k_jobs(df, filters, top_k=top_k, mmr_lambda=lam)
        results_list.append((label, lam, res))
        print_results(f"{label}", res, filters)

    # show rank changes for jobs shared between λ=1.0 and λ=0.3
    print("\n  Rank-shift: λ=1.0 vs λ=0.3")
    pure_rel = {r["Job Title"]: i + 1 for i, r in enumerate(results_list[0][2])}
    diverse  = {r["Job Title"]: i + 1 for i, r in enumerate(results_list[-1][2])}
    all_titles = sorted(set(pure_rel) | set(diverse))
    print(f"  {'Job Title':<38}  {'λ=1.0':>6}  {'λ=0.3':>6}  {'Δ rank':>7}")
    print(f"  {'─' * 38}  {'─' * 6}  {'─' * 6}  {'─' * 7}")
    for t in all_titles:
        r1 = pure_rel.get(t, "—")
        r2 = diverse.get(t, "—")
        delta = (r2 - r1) if isinstance(r1, int) and isinstance(r2, int) else "n/a"
        sign  = f"+{delta}" if isinstance(delta, int) and delta > 0 else str(delta)
        print(f"  {_trunc(t, 38):<38}  {str(r1):>6}  {str(r2):>6}  {sign:>7}")


def group_bonus(df: pd.DataFrame, top_k: int):
    """Extra contrast: same title but very different secondary filters."""
    print("\n" + "▶" * 3 + "  GROUP 4 (bonus): Same title, wildly different context  " + "◀" * 3)

    base_title = {"title": {"data": "Software Engineer", "dealBreaker": True}}
    experiments = {
        "startup + remote + entry": {
            **base_title,
            "company_size":     {"data": "small",   "dealBreaker": False},
            "work_format":      {"data": "remote",  "dealBreaker": False},
            "experience_level": {"data": "start",   "dealBreaker": False},
        },
        "large corp + in-person + senior": {
            **base_title,
            "company_size":     {"data": "large",     "dealBreaker": False},
            "work_format":      {"data": "in-person", "dealBreaker": False},
            "experience_level": {"data": "senior",    "dealBreaker": False},
        },
        "mid corp + hybrid + PhD pref": {
            **base_title,
            "company_size":     {"data": "mid",    "dealBreaker": False},
            "work_format":      {"data": "hybrid", "dealBreaker": False},
            "education_level":  {"data": "phd",    "dealBreaker": False},
        },
    }
    results_list = []
    for label, filters in experiments.items():
        res = find_top_k_jobs(df, filters, top_k=top_k)
        results_list.append((label, res))
        print_results(label, res, filters)

    compare_two("startup+remote+entry", results_list[0][1],
                "large+in-person+senior", results_list[1][1])


# ── CLI ───────────────────────────────────────────────────────────────────────

GROUPS = {
    "filters":     group_filter_fields,
    "dealbreaker": group_dealbreaker,
    "lambda":      group_lambda,
    "bonus":       group_bonus,
}


def main():
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--group", choices=list(GROUPS) + ["all"], default="all",
        help="Which experiment group to run (default: all)",
    )
    parser.add_argument("--top", type=int, default=6, help="Results per experiment (default: 6)")
    parser.add_argument(
        "--data", type=Path, default=DEFAULT_DATA_PATH,
        help="Path to jobs CSV (default: project cleaned dataset)",
    )
    args = parser.parse_args()

    print(f"\nLoading data from: {args.data}")
    df = pd.read_csv(args.data)
    print(f"Loaded {len(df):,} jobs.\n")

    groups_to_run = list(GROUPS.items()) if args.group == "all" else [(args.group, GROUPS[args.group])]
    for name, fn in groups_to_run:
        fn(df, args.top)

    print(f"\n{'═' * 110}")
    print("  Done.\n")


if __name__ == "__main__":
    main()
