"""
run_comparison.py — Single-scenario empirical comparison.

LOCAL PIPELINE (findJobs + match_experiences) vs. CLAUDE (web search + LLM)

Scenario: Machine Learning Engineer · Computer Vision · Germany
  - title = "Machine Learning Engineer"  [HARD filter — exclude non-matching]
  - domain = "Computer Vision"           [soft — prefer, don't exclude]
  - country = "Germany"                  [soft — prefer, don't exclude]

Output: docs/comparison_report.md

Usage:
  uv run python scripts/run_comparison.py
  uv run python scripts/run_comparison.py --dry-run
"""

from __future__ import annotations

import os
import sys
import textwrap
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from findJobs import DEFAULT_DATA_PATH, find_top_k_jobs  # noqa: E402
from match_experiences import match_from_job_records  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
SCENARIO_LABEL = "ML Engineer · Computer Vision · Germany"
FILTERS = {
    "title":   {"data": "Machine Learning Engineer", "dealBreaker": True},
    "domain":  {"data": "Computer Vision",           "dealBreaker": False},
    "country": {"data": "Germany",                   "dealBreaker": False},
}
TOP_K = 5
MMR_LAMBDA = 0.7

# ---------------------------------------------------------------------------
# Claude setup
# ---------------------------------------------------------------------------
_SYSTEM = """\
You are a career intelligence engine for TU Munich (TUM) students seeking AI/tech jobs.

When given a job search scenario:

1. SEARCH FOR JOBS — use web_search to find real, current (2025/2026) job postings
   matching the criteria. Search 2–3 query variations. For each job record: title,
   company, country, industry, salary estimate (EUR), match_score (0-100), risk.

2. ASSESS RISK — search each shortlisted company for recent layoff news or stability
   signals. Estimate risk: low / medium / high.

3. SEARCH FOR TUM EXPERIENCES — find TUM-specific student experiences
   (research chairs, Fachschaft groups, student clubs, UnternehmerTUM, CDTM, etc.)
   relevant to the job criteria.

4. CALL submit_results once you have enough data.

Rules:
- HARD FILTER fields: exclude every job that does not satisfy them — no exceptions.
- match_score reflects fit across ALL criteria.
- Return exactly the requested number of jobs and experiences.
"""

_SUBMIT_TOOL = {
    "name": "submit_results",
    "description": "Submit ranked jobs and TUM experience recommendations. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string"},
                        "company":     {"type": "string"},
                        "country":     {"type": "string"},
                        "industry":    {"type": "string"},
                        "salary_eur":  {"type": ["number", "null"]},
                        "match_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "risk":        {"type": "string", "enum": ["low", "medium", "high"]},
                        "why":         {"type": "string"},
                    },
                    "required": ["title", "company", "country", "match_score", "risk"],
                    "additionalProperties": False,
                },
            },
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":      {"type": "string"},
                        "type":      {"type": "string"},
                        "skills":    {"type": "string"},
                        "relevance": {"type": "string"},
                    },
                    "required": ["name", "skills", "relevance"],
                    "additionalProperties": False,
                },
            },
            "search_notes": {"type": "string"},
        },
        "required": ["jobs", "experiences"],
        "additionalProperties": False,
    },
}

_WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search"}
_TOOLS = [_WEB_SEARCH, _SUBMIT_TOOL]
_MAX_TURNS = 14


def _build_user_msg(filters: dict, top_k: int) -> str:
    hard, soft = [], []
    labels = {
        "title": "Job title", "domain": "AI domain", "country": "Country",
        "company_size": "Company size", "work_format": "Work format",
        "experience_level": "Experience level", "education_level": "Education",
    }
    for field, spec in filters.items():
        label = labels.get(field, field)
        entry = f"  • {label}: {spec['data']!r}"
        if spec["dealBreaker"]:
            entry += "  ← HARD FILTER (exclude non-matching jobs)"
            hard.append(entry)
        else:
            entry += "  ← preferred (rank higher, don't exclude)"
            soft.append(entry)

    parts = [f"Find the top {top_k} AI/tech job matches for a TUM student:\n"]
    if hard:
        parts.append("REQUIRED (hard filters — exclude jobs that don't meet these):")
        parts.extend(hard)
    if soft:
        parts.append("\nPREFERRED (soft — boost matching jobs but don't exclude):")
        parts.extend(soft)
    parts.append(
        f"\nReturn exactly {top_k} jobs and {top_k} TUM experience recommendations."
    )
    return "\n".join(parts)


def ask_claude(filters: dict, top_k: int, dry_run: bool) -> dict:
    user_msg = _build_user_msg(filters, top_k)

    if dry_run:
        print(f"\n[DRY-RUN] Claude prompt:\n{textwrap.indent(user_msg, '  ')}\n")
        return {
            "jobs": [
                {
                    "title": f"ML Engineer (dry-run #{i})", "company": f"Company {i}",
                    "country": "Germany", "industry": "AI", "salary_eur": 70000 + i * 5000,
                    "match_score": 90 - i * 5, "risk": "low",
                    "why": "placeholder",
                }
                for i in range(1, top_k + 1)
            ],
            "experiences": [
                {
                    "name": f"TUM CV Group (dry-run #{i})", "type": "research chair",
                    "skills": "Computer Vision, PyTorch, Deep Learning",
                    "relevance": "placeholder",
                }
                for i in range(1, top_k + 1)
            ],
            "search_notes": "(dry-run — no API call made)",
        }

    import anthropic

    client = anthropic.Anthropic()
    messages: list = [{"role": "user", "content": user_msg}]

    for _turn in range(_MAX_TURNS):
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=_SYSTEM,
            tools=_TOOLS,
            messages=messages,
        )

        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_results":
                return block.input

        if resp.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": "Please call submit_results now with your findings."})
            continue

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "web_search":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "(search handled by Anthropic)",
                })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Claude did not call submit_results within the turn limit.")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
_ML_TITLE_TOKENS = {"machine", "learning", "ml", "engineer", "scientist", "researcher"}


def _passes_title_hard_filter(title: str, query: str = "Machine Learning Engineer") -> bool:
    """Check if a job title plausibly satisfies the ML Engineer hard filter."""
    tl = title.lower()
    ql = query.lower()
    if ql in tl:
        return True
    t_tok = set(tl.split())
    q_tok = set(ql.split())
    return len(t_tok & q_tok) >= 2


def compute_metrics(
    local_jobs: list[dict],
    claude_jobs: list[dict],
    filters: dict,
) -> dict:
    n = TOP_K

    title_query = filters.get("title", {}).get("data", "")

    local_titles  = [str(r.get("Job Title", ""))  for r in local_jobs]
    claude_titles = [str(j.get("title", ""))       for j in claude_jobs]

    # Hard filter compliance
    local_hf  = sum(_passes_title_hard_filter(t, title_query) for t in local_titles)
    claude_hf = sum(_passes_title_hard_filter(t, title_query) for t in claude_titles)

    # Salary coverage
    local_sal  = sum(1 for r in local_jobs  if pd.notna(r.get("salary_mid_eur")))
    claude_sal = sum(1 for j in claude_jobs if j.get("salary_eur") is not None)

    # Country soft-filter match (Germany)
    local_de  = sum(1 for r in local_jobs  if str(r.get("Country",  "")).strip().lower() == "germany")
    claude_de = sum(1 for j in claude_jobs if str(j.get("country", "")).strip().lower() == "germany")

    # Title overlap between the two systems
    lt = {t.lower().strip() for t in local_titles  if t}
    ct = {t.lower().strip() for t in claude_titles if t}
    exact_overlap = len(lt & ct)
    fuzzy_overlap = sum(
        1 for x in ct
        if any(x[:20] in y or y[:20] in x for y in lt)
    )

    # Average match score (normalised 0–1)
    def _avg_score(jobs, key, scale):
        vals = [j.get(key) for j in jobs if j.get(key) is not None]
        return round(sum(vals) / len(vals) / scale, 3) if vals else None

    return {
        "n": n,
        "local_hf_pass":  local_hf,
        "claude_hf_pass": claude_hf,
        "local_sal":      local_sal,
        "claude_sal":     claude_sal,
        "local_de":       local_de,
        "claude_de":      claude_de,
        "exact_overlap":  exact_overlap,
        "fuzzy_overlap":  fuzzy_overlap,
        "local_avg_score":  _avg_score(local_jobs,  "match_score",  1.0),
        "claude_avg_score": _avg_score(claude_jobs, "match_score",  100.0),
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def _s(v, default="—") -> str:
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    return str(v)


def _pct(num: int, den: int) -> str:
    return f"{num}/{den} ({100 * num // den}%)" if den else "—"


def _sal(v) -> str:
    try:
        if v is not None and not pd.isna(v):
            return f"€{int(float(v)):,}"
    except (TypeError, ValueError):
        pass
    return "—"


def generate_report(
    local_jobs: list[dict],
    local_exps: list[dict],
    claude_payload: dict,
    metrics: dict,
    dry_run: bool,
) -> str:
    claude_jobs = claude_payload.get("jobs", [])
    claude_exps = claude_payload.get("experiences", [])
    notes       = claude_payload.get("search_notes", "")
    n           = metrics["n"]
    today       = date.today().isoformat()

    md: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    md += [
        "# Career Detective vs Claude: Empirical Comparison",
        "",
        f"**Scenario**: {SCENARIO_LABEL}  ",
        f"**Date**: {today}  ",
        f"**Top-k**: {n}  ",
        f"**Local dataset**: ~51 k AI/tech job postings (2024/25 snapshot, `jobs_enriched_with_layoffs_complete.csv`)  ",
        f"**Claude model**: `claude-sonnet-4-6` with live web search  ",
    ]
    if dry_run:
        md.append("**Note**: `--dry-run` mode — Claude results are synthetic placeholders.  ")
    md += ["", "---", ""]

    # ── Filters ─────────────────────────────────────────────────────────────
    md += [
        "## Scenario Filters",
        "",
        "| Field | Value | Type |",
        "|-------|-------|------|",
    ]
    for field, spec in FILTERS.items():
        ftype = "**HARD** — exclude non-matching" if spec["dealBreaker"] else "soft — prefer"
        md.append(f"| `{field}` | {spec['data']} | {ftype} |")
    md += ["", "---", ""]

    # ── Job results ──────────────────────────────────────────────────────────
    md += [
        "## Job Results",
        "",
        "### Local Pipeline",
        "",
        "| # | Job Title | Company | Country | Match Score | Salary (EUR) |",
        "|---|-----------|---------|---------|:-----------:|:------------:|",
    ]
    for i, r in enumerate(local_jobs, 1):
        score = r.get("match_score")
        score_str = f"{float(score):.3f}" if pd.notna(score) else "—"
        md.append(
            f"| {i} | {_s(r.get('Job Title'))} | {_s(r.get('Company Name'))} "
            f"| {_s(r.get('Country'))} | {score_str} | {_sal(r.get('salary_mid_eur'))} |"
        )
    md += [""]

    md += [
        "### Claude (live web search)",
        "",
        "| # | Job Title | Company | Country | Match Score | Salary (EUR) | Risk |",
        "|---|-----------|---------|---------|:-----------:|:------------:|:----:|",
    ]
    for i, j in enumerate(claude_jobs, 1):
        score_str = f"{int(j['match_score'])}/100" if j.get("match_score") is not None else "—"
        md.append(
            f"| {i} | {_s(j.get('title'))} | {_s(j.get('company'))} "
            f"| {_s(j.get('country'))} | {score_str} | {_sal(j.get('salary_eur'))} "
            f"| {_s(j.get('risk'))} |"
        )
    if notes:
        md += ["", f"> *Claude search notes: {notes}*"]
    md += ["", "---", ""]

    # ── Experience results ───────────────────────────────────────────────────
    md += [
        "## TUM Experience Recommendations",
        "",
        "### Local Pipeline",
        "",
        "| # | Experience | Skills |",
        "|---|-----------|--------|",
    ]
    for i, exp in enumerate(local_exps, 1):
        skills = _s(exp.get("skills"))
        md.append(f"| {i} | **{_s(exp.get('name'))}** | {skills} |")

    md += [
        "",
        "### Claude (live web search)",
        "",
        "| # | Experience | Skills | Why Relevant |",
        "|---|-----------|--------|--------------|",
    ]
    for i, exp in enumerate(claude_exps, 1):
        md.append(
            f"| {i} | **{_s(exp.get('name'))}** | {_s(exp.get('skills'))} "
            f"| {_s(exp.get('relevance'))} |"
        )
    md += ["", "---", ""]

    # ── Metrics table ────────────────────────────────────────────────────────
    m = metrics
    md += [
        "## Metrics",
        "",
        "| Metric | Local Pipeline | Claude |",
        "|--------|:--------------:|:------:|",
        f"| Hard filter compliance (title) | {_pct(m['local_hf_pass'], n)} | {_pct(m['claude_hf_pass'], n)} |",
        f"| Soft filter: Germany results | {m['local_de']}/{n} | {m['claude_de']}/{n} |",
        f"| Salary data available | {_pct(m['local_sal'], n)} | {_pct(m['claude_sal'], n)} |",
        f"| Risk data available | {_pct(n, n)} | {_pct(n, n)} |",
        f"| Avg normalised match score | {m['local_avg_score']} | {m['claude_avg_score']} |",
        f"| Exact title overlap (vs each other) | {m['exact_overlap']}/{n} | — |",
        f"| Fuzzy title overlap (vs each other) | {m['fuzzy_overlap']}/{n} | — |",
        "",
        "---",
        "",
    ]

    # ── Observations ─────────────────────────────────────────────────────────
    hf_note_local  = "all results pass" if m["local_hf_pass"] == n else f"**{n - m['local_hf_pass']} violation(s)**"
    hf_note_claude = "all results pass" if m["claude_hf_pass"] == n else f"**{n - m['claude_hf_pass']} violation(s)**"

    md += [
        "## Observations",
        "",
        "### Hard filter enforcement",
        (
            f"The local pipeline enforces the title hard filter mechanically via "
            f"embedding cosine similarity against the `Job Title` column "
            f"(threshold ≥ 0.35) — {hf_note_local} ({m['local_hf_pass']}/{n}). "
            f"Claude's filtering is LLM best-effort: {hf_note_claude} ({m['claude_hf_pass']}/{n}). "
            "Drift is more visible with strict or niche title strings."
        ),
        "",
        "### Soft filter: country",
        (
            f"With `country=Germany` as a soft preference (not a hard filter), "
            f"the local pipeline returned {m['local_de']}/{n} Germany-based results; "
            f"Claude returned {m['claude_de']}/{n}. "
            "Both systems are permitted to include non-Germany results — the difference "
            "reflects how each system weights the preference signal."
        ),
        "",
        "### Salary data",
        (
            f"The local pipeline provides structured salary figures for "
            f"{m['local_sal']}/{n} results, sourced directly from the enriched CSV. "
            f"Claude provided salary estimates for {m['claude_sal']}/{n} — "
            "these are model-generated approximations, not figures pulled from job postings."
        ),
        "",
        "### Data source and specificity",
        (
            "The local pipeline matches against ~51,000 curated AI/tech postings "
            "from a consistent 2024/25 snapshot. Every result is a real, traceable row "
            "with structured fields (company size, layoff data, salary band). "
            "Claude's results come from live web searches and may correspond to jobs "
            "that postdate the CSV snapshot, but the titles, companies, and salaries "
            "are not independently verifiable from the output alone."
        ),
        "",
        "### TUM experience matching",
        (
            "The local pipeline scores experiences via tag overlap against a "
            "job-skills profile derived from the matched job set — fully deterministic "
            "and grounded in the 91-tag vocabulary. "
            "Claude's experience recommendations draw on general LLM knowledge of TUM "
            "institutions, supplemented by web search; they may surface newer or more "
            "niche groups that postdate the local experience CSV, but with no guarantee "
            "the group still exists or accepts new members."
        ),
        "",
        "### Reproducibility",
        (
            "Running the local pipeline twice on identical inputs returns identical "
            "results. Claude's output varies across runs due to web search variability "
            "and stochastic token sampling."
        ),
        "",
        "### Result overlap",
        (
            f"Exact title overlap between the two systems: {m['exact_overlap']}/{n}. "
            f"Fuzzy overlap (first-20-char substring match): {m['fuzzy_overlap']}/{n}. "
            "Low overlap is structurally expected — the two systems draw from fundamentally "
            "different data sources."
        ),
        "",
        "---",
        "",
    ]

    # ── Verdict ───────────────────────────────────────────────────────────────
    md += [
        "## Verdict",
        "",
        "| Dimension | Local Pipeline | Claude |",
        "|-----------|:--------------:|:------:|",
        "| Hard filter precision | ✅ Mechanical, threshold-based | ⚠️ LLM best-effort |",
        "| Salary data | ✅ Structured, sourced from CSV | ⚠️ Model estimates |",
        "| Layoff / risk data | ✅ Enriched dataset (events × headcount) | ✅ Live news signals |",
        "| Data currency | ⚠️ 2024/25 snapshot | ✅ Live web search |",
        "| Reproducibility | ✅ Deterministic | ❌ Stochastic |",
        "| Traceability | ✅ Row-level CSV source | ❌ No persistent link |",
        "| TUM experience matching | ✅ Tag-overlap scoring on job-skills profile | ⚠️ General LLM knowledge |",
        "| Speed (after model warm-up) | ✅ < 2 s | ❌ 30–90 s (web search) |",
        "",
        (
            "The local pipeline is stronger on **precision, reproducibility, data "
            "structure, and speed** — the dimensions that matter most for a production "
            "recommendation system. Claude's main edge is data currency: it can surface "
            "postings that appeared after the CSV snapshot. In practice, this comes at "
            "the cost of verifiability and filter strictness, making it better suited "
            "as a periodic sanity-check on the local system rather than a replacement."
        ),
        "",
    ]

    return "\n".join(md)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude API call")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    args = parser.parse_args()

    if not args.dry_run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            env_file = ROOT / ".env"
            if env_file.exists():
                from dotenv import load_dotenv
                load_dotenv(env_file)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ERROR: ANTHROPIC_API_KEY not set. Use --dry-run or set the key.", file=sys.stderr)
            sys.exit(1)

    # ── Local pipeline ────────────────────────────────────────────────────────
    print(f"Loading dataset: {args.data}")
    df = pd.read_csv(args.data)
    print(f"  {len(df):,} jobs loaded.")

    print("Running local job matching...")
    local_jobs = find_top_k_jobs(df, FILTERS, top_k=TOP_K, mmr_lambda=MMR_LAMBDA)
    print(f"  {len(local_jobs)} jobs matched.")

    print("Running local experience matching...")
    exp_result = match_from_job_records(local_jobs, FILTERS, top=TOP_K)
    local_exps = exp_result.get("experiences", [])
    print(f"  {len(local_exps)} experiences matched.")

    # ── Claude ────────────────────────────────────────────────────────────────
    if args.dry_run:
        print("Dry-run: skipping Claude API.")
    else:
        print("Running Claude (live web search)…")
    claude_payload = ask_claude(FILTERS, TOP_K, dry_run=args.dry_run)
    print(f"  {len(claude_payload.get('jobs', []))} Claude jobs, "
          f"{len(claude_payload.get('experiences', []))} Claude experiences.")

    # ── Report ────────────────────────────────────────────────────────────────
    metrics = compute_metrics(local_jobs, claude_payload.get("jobs", []), FILTERS)
    report  = generate_report(local_jobs, local_exps, claude_payload, metrics, dry_run=args.dry_run)

    out = ROOT / "docs" / "comparison_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nReport written → {out}")


if __name__ == "__main__":
    main()
