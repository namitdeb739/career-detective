"""
explore_filters_claude.py — run the exact same filter scenarios as
explore_filters.py, but through Claude (claude-sonnet-4-6) with web search.

Claude acts as a FULL PIPELINE REPLACEMENT:
  1. Searches the web for real, current job postings matching the criteria
  2. Searches for company layoff / stability risk data
  3. Searches for TUM (TU Munich) clubs, programs, and research groups as
     relevant student experiences
  4. Returns structured results in the same schema as our local pipeline

What this compares
──────────────────
  LOCAL PIPELINE  →  static CSV (51k jobs, 2024/2025 snapshot)
                     embedding cosine similarity + MMR re-ranking
                     TUM experience matching via tag overlap
  CLAUDE          →  live web data (current job postings, recent layoff news)
                     holistic LLM judgment for ranking
                     direct TUM knowledge + web search for clubs/programs

Output for every scenario: side-by-side table + overlap / agreement score.

Usage:
  uv run python scripts/explore_filters_claude.py
  uv run python scripts/explore_filters_claude.py --group dealbreaker
  uv run python scripts/explore_filters_claude.py --group lambda --top 8
  uv run python scripts/explore_filters_claude.py --dry-run   # skip API, show prompts

Requires: ANTHROPIC_API_KEY in env or .env file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from findJobs import DEFAULT_DATA_PATH, find_top_k_jobs  # noqa: E402

# ── Anthropic client (lazy) ───────────────────────────────────────────────────
_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError("Run: uv sync") from e

        if not os.environ.get("ANTHROPIC_API_KEY"):
            env_file = ROOT / ".env"
            if env_file.exists():
                from dotenv import load_dotenv
                load_dotenv(env_file)

        _CLIENT = anthropic.Anthropic()
    return _CLIENT


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a career intelligence engine for TU Munich (TUM) students seeking AI/tech jobs.

When given a job search scenario you will:

1. SEARCH FOR JOBS — use web_search to find real, current (2025/2026) job postings
   that match the criteria. Search for 2–3 different query variations to broaden
   coverage. For each job found, note title, company, country, industry, and
   estimated salary range (EUR if possible).

2. ASSESS RISK — for each shortlisted company, search for recent layoff news,
   funding status, or stability signals. Estimate a risk level: low / medium / high.

3. SEARCH FOR TUM EXPERIENCES — use web_search to find TUM-specific student
   experiences (Fachschaft groups, research chairs, TUM programs, student clubs,
   initiatives like UnternehmerTUM, CDTM, etc.) that would be directly relevant
   to the job criteria. These are real TUM institutions the student could join.

4. CALL submit_results — once you have enough information, call the submit_results
   tool exactly once with all findings structured as required.

Guidelines:
- For HARD-FILTER criteria: only include jobs that genuinely match — treat as
  non-negotiable exclusion criteria (same as a database WHERE clause).
- For SOFT/PREFERRED criteria: include jobs that match and rank them higher, but
  also include close alternatives if they score well overall.
- match_score: 0–100. Reflect how well this specific job matches ALL criteria.
- Diversity hint: when asked for diverse results, include jobs from different
  companies, countries, and industries. When asked for pure relevance, cluster
  tightly around the best matches.
- Always return exactly the requested number of jobs (top_k).
"""

# ── Tool: structured result submission ───────────────────────────────────────
_JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "title":       {"type": "string", "description": "Exact job title from the posting"},
        "company":     {"type": "string"},
        "country":     {"type": "string"},
        "industry":    {"type": "string"},
        "salary_eur":  {"type": ["number", "null"], "description": "Mid salary estimate in EUR, null if unknown"},
        "match_score": {"type": "number", "minimum": 0, "maximum": 100,
                        "description": "0–100 match quality vs the search criteria"},
        "risk":        {"type": "string", "enum": ["low", "medium", "high"],
                        "description": "Company/role stability risk based on layoff data"},
        "why":         {"type": "string", "description": "One sentence: why this job matches"},
    },
    "required": ["title", "company", "country", "match_score", "risk"],
    "additionalProperties": False,
}

_EXP_SCHEMA = {
    "type": "object",
    "properties": {
        "name":        {"type": "string", "description": "TUM club, program, or experience name"},
        "type":        {"type": "string", "description": "e.g. research chair, student club, program, initiative"},
        "skills":      {"type": "string", "description": "Key skills this experience develops"},
        "relevance":   {"type": "string", "description": "One sentence: why relevant to the job criteria"},
    },
    "required": ["name", "skills", "relevance"],
    "additionalProperties": False,
}

SUBMIT_TOOL = {
    "name": "submit_results",
    "description": (
        "Submit the final ranked job results and TUM experience recommendations. "
        "Call this tool ONCE when your research is complete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "items": _JOB_SCHEMA,
                "description": "Ranked list of jobs, best match first.",
            },
            "experiences": {
                "type": "array",
                "items": _EXP_SCHEMA,
                "description": "TUM experiences most relevant to the job criteria.",
            },
            "search_notes": {
                "type": "string",
                "description": "Brief note on data sources / search quality (1–2 sentences).",
            },
        },
        "required": ["jobs", "experiences"],
        "additionalProperties": False,
    },
}

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

TOOLS = [WEB_SEARCH_TOOL, SUBMIT_TOOL]

MAX_SEARCH_TURNS = 12  # safety cap on the agentic loop


# ── Build user message from filter dict ──────────────────────────────────────
def _filters_to_prompt(filters: dict, top_k: int, diversity_hint: str) -> str:
    hard, soft = [], []
    field_labels = {
        "title":            "Job title",
        "domain":           "AI domain / specialization",
        "country":          "Country",
        "company_size":     "Company size",
        "work_format":      "Work format",
        "experience_level": "Experience level",
        "education_level":  "Education requirement",
    }
    for field, spec in filters.items():
        label = field_labels.get(field, field)
        val   = spec["data"]
        if spec["dealBreaker"]:
            hard.append(f"  • {label}: {val!r}  ← HARD FILTER (exclude non-matching jobs)")
        else:
            soft.append(f"  • {label}: {val!r}  ← preferred (rank higher, don't exclude)")

    lines = [f"Find the top {top_k} job matches for a TUM student with these criteria:\n"]
    if hard:
        lines.append("REQUIRED (hard filters — exclude jobs that don't meet these):")
        lines.extend(hard)
    if soft:
        lines.append("\nPREFERRED (soft — boost matching jobs but don't exclude others):")
        lines.extend(soft)
    lines.append(f"\nDiversity preference: {diversity_hint}")
    lines.append(
        f"\nPlease return exactly {top_k} jobs and {top_k} TUM experience recommendations."
    )
    return "\n".join(lines)


# ── Agentic loop ──────────────────────────────────────────────────────────────
def ask_claude(filters: dict, top_k: int, diversity_hint: str, dry_run: bool) -> dict:
    """Run Claude with web search and return the submit_results payload."""
    user_msg = _filters_to_prompt(filters, top_k, diversity_hint)

    if dry_run:
        print(f"\n  [DRY-RUN PROMPT]\n{textwrap.indent(user_msg, '    ')}")
        return {"jobs": [], "experiences": [], "search_notes": "(dry-run)"}

    import anthropic

    messages: list = [{"role": "user", "content": user_msg}]

    for _turn in range(MAX_SEARCH_TURNS):
        response = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Check for submit_results call first
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_results":
                return block.input

        # If Claude finished without submitting, nudge it
        if response.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": (
                    "You haven't called submit_results yet. "
                    "Please call it now with your findings."
                ),
            })
            continue

        # tool_use turn: append assistant response and supply tool results
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "web_search":
                # Anthropic executes web_search server-side; results are already
                # embedded in the response as web_search_tool_result blocks.
                # We only need to ack the tool_use id so the loop continues.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "(search handled by Anthropic)",
                })
            elif block.name == "submit_results":
                # Already handled above; shouldn't reach here
                return block.input

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Claude did not call submit_results within the turn limit.")


# ── Display helpers ───────────────────────────────────────────────────────────
def _trunc(s, n):
    s = str(s) if pd.notna(s) else ""
    return s[:n] if len(s) <= n else s[: n - 1] + "…"


def _filter_summary(filters: dict) -> str:
    parts = []
    for k, v in filters.items():
        tag = "HARD" if v.get("dealBreaker") else "soft"
        parts.append(f"{k}={v['data']!r}[{tag}]")
    return "  |  ".join(parts) if parts else "(none)"


# Columns for LOCAL results (from find_top_k_jobs)
LOCAL_COLS   = ["Job Title", "Company Name", "Country", "match_score"]
LOCAL_WIDTHS = [30, 22, 16, 6]

# Columns for CLAUDE results (from submit_results)
CLAUDE_COLS   = ["title", "company", "country", "match_score"]
CLAUDE_WIDTHS = [30, 22, 16, 6]


def _local_row(rank, row):
    vals = [row.get(c, "") for c in LOCAL_COLS]
    vals[-1] = f"{float(vals[-1]):.2f}" if pd.notna(vals[-1]) else "—"
    parts = [f"{rank:>2}"] + [_trunc(v, w).ljust(w) for v, w in zip(vals, LOCAL_WIDTHS)]
    return "  ".join(parts)


def _claude_row(rank, job: dict):
    vals = [job.get(c, "") for c in CLAUDE_COLS]
    score = vals[-1]
    vals[-1] = f"{float(score) / 100:.2f}" if score != "" else "—"
    risk = job.get("risk", "?")
    parts = [f"{rank:>2}"] + [_trunc(v, w).ljust(w) for v, w in zip(vals, CLAUDE_WIDTHS)]
    parts.append(f"[{risk[:3]}]")
    return "  ".join(parts)


def _header(cols, widths, extra=""):
    parts = [f"{'#':>2}"] + [_trunc(c, w).ljust(w) for c, w in zip(cols, widths)]
    if extra:
        parts.append(extra)
    return "  ".join(parts)


def _sep(widths, extra_w=0):
    w_list = [2] + widths
    if extra_w:
        w_list.append(extra_w)
    return "  ".join("─" * w for w in w_list)


def print_side_by_side(label: str, filters: dict, local_results: list, claude_payload: dict):
    """Print local pipeline and Claude results side-by-side with overlap stats."""
    claude_jobs = claude_payload.get("jobs", [])
    notes       = claude_payload.get("search_notes", "")
    experiences = claude_payload.get("experiences", [])

    W = 110
    col = (W - 4) // 2

    def _pad(s, w):
        return s[:w].ljust(w)

    print(f"\n{'═' * W}")
    print(f"  {label}")
    print(f"  Filters: {_filter_summary(filters)}")
    if notes:
        print(f"  Claude notes: {_trunc(notes, W - 18)}")

    print(f"\n  {'LOCAL PIPELINE':<{col}}  |  CLAUDE (web search)")
    print(f"  {_sep(LOCAL_WIDTHS):<{col}}  |  {_sep(CLAUDE_WIDTHS, 5)}")

    hdr_local  = _header(LOCAL_COLS,  LOCAL_WIDTHS)
    hdr_claude = _header(CLAUDE_COLS, CLAUDE_WIDTHS, "risk")
    print(f"  {_pad(hdr_local, col)}  |  {hdr_claude}")
    print(f"  {_sep(LOCAL_WIDTHS):<{col}}  |  {_sep(CLAUDE_WIDTHS, 5)}")

    n = max(len(local_results), len(claude_jobs))
    for i in range(n):
        left  = _local_row(i + 1, local_results[i])  if i < len(local_results)  else ""
        right = _claude_row(i + 1, claude_jobs[i])    if i < len(claude_jobs)    else ""
        print(f"  {_pad(left, col)}  |  {right}")

    print(f"  {_sep(LOCAL_WIDTHS):<{col}}  |  {_sep(CLAUDE_WIDTHS, 5)}")

    # ── TUM experiences ───────────────────────────────────────────────────────
    if experiences:
        print(f"\n  TUM Experiences (Claude):")
        for i, exp in enumerate(experiences, 1):
            name = _trunc(exp.get("name", ""), 30)
            skills = _trunc(exp.get("skills", ""), 40)
            rel  = _trunc(exp.get("relevance", ""), 50)
            print(f"    {i:>2}. {name:<30}  {skills:<40}  {rel}")

    # ── Overlap stats ─────────────────────────────────────────────────────────
    local_titles  = {r.get("Job Title", "").lower().strip() for r in local_results}
    claude_titles = {j.get("title",     "").lower().strip() for j in claude_jobs}
    # fuzzy overlap: count claude title that appears as substring in any local title or vice versa
    soft_matches = sum(
        1 for ct in claude_titles
        if any(ct[:20] in lt or lt[:20] in ct for lt in local_titles)
    )
    exact = local_titles & claude_titles
    print(f"\n  Overlap: exact_title={len(exact)}  fuzzy={soft_matches}"
          f"  out of top {max(len(local_results), len(claude_jobs))}")


# ── Scenario definitions ──────────────────────────────────────────────────────
# Each scenario mirrors a row in explore_filters.py.
# "diversity_hint" becomes part of the Claude prompt so the lambda intent
# is communicated without using the numeric MMR parameter.

GROUP_FILTERS = [
    {
        "label": "A — title only (HARD)",
        "canonical": {"title": {"data": "Machine Learning Engineer", "dealBreaker": True}},
        "mmr_lambda": 0.7,
        "diversity_hint": "Balanced — some variety across companies and countries is fine.",
    },
    {
        "label": "B — title HARD + domain soft",
        "canonical": {
            "title":  {"data": "Machine Learning Engineer", "dealBreaker": True},
            "domain": {"data": "Computer Vision",           "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Balanced — prefer Computer Vision but show range of companies.",
    },
    {
        "label": "C — title HARD + domain soft + country soft",
        "canonical": {
            "title":   {"data": "Machine Learning Engineer", "dealBreaker": True},
            "domain":  {"data": "Computer Vision",           "dealBreaker": False},
            "country": {"data": "Germany",                   "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Prefer Germany but show some international options too.",
    },
    {
        "label": "D — full soft basket (no HARD filters)",
        "canonical": {
            "domain":           {"data": "NLP",    "dealBreaker": False},
            "company_size":     {"data": "mid",    "dealBreaker": False},
            "work_format":      {"data": "remote", "dealBreaker": False},
            "experience_level": {"data": "mid",    "dealBreaker": False},
            "education_level":  {"data": "msc",    "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Balanced — no title restriction, show varied NLP/AI roles.",
    },
    {
        "label": "E — title soft + domain soft",
        "canonical": {
            "title":  {"data": "Machine Learning Engineer", "dealBreaker": False},
            "domain": {"data": "Computer Vision",           "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Balanced — related titles and domains welcome.",
    },
]

GROUP_DEALBREAKER = [
    {
        "label": "A — title soft, country soft",
        "canonical": {
            "title":   {"data": "Data Scientist",  "dealBreaker": False},
            "country": {"data": "United States",   "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Balanced — include close title variants, prefer US but show others.",
    },
    {
        "label": "B — title HARD, country soft",
        "canonical": {
            "title":   {"data": "Data Scientist",  "dealBreaker": True},
            "country": {"data": "United States",   "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Prefer US but include international Data Scientist roles.",
    },
    {
        "label": "C — title soft, country HARD",
        "canonical": {
            "title":   {"data": "Data Scientist",  "dealBreaker": False},
            "country": {"data": "United States",   "dealBreaker": True},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Only US jobs. Title variants OK.",
    },
    {
        "label": "D — title HARD + country HARD",
        "canonical": {
            "title":   {"data": "Data Scientist",  "dealBreaker": True},
            "country": {"data": "United States",   "dealBreaker": True},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Only US Data Scientist roles. No exceptions.",
    },
    {
        "label": "E — title HARD + country HARD + experience soft",
        "canonical": {
            "title":            {"data": "Data Scientist",  "dealBreaker": True},
            "country":          {"data": "United States",   "dealBreaker": True},
            "experience_level": {"data": "senior",          "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Only US Data Scientist roles; prefer senior but show all levels.",
    },
    {
        "label": "F — title HARD + country HARD + experience HARD",
        "canonical": {
            "title":            {"data": "Data Scientist",  "dealBreaker": True},
            "country":          {"data": "United States",   "dealBreaker": True},
            "experience_level": {"data": "senior",          "dealBreaker": True},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Only senior US Data Scientist roles. All three are mandatory.",
    },
]

GROUP_LAMBDA = [
    {
        "label": "λ=1.0  pure relevance",
        "canonical": {
            "title":            {"data": "AI Engineer",   "dealBreaker": True},
            "domain":           {"data": "Generative AI", "dealBreaker": False},
            "work_format":      {"data": "hybrid",        "dealBreaker": False},
            "experience_level": {"data": "mid",           "dealBreaker": False},
        },
        "mmr_lambda": 1.0,
        "diversity_hint": (
            "Pure relevance — give me the MOST RELEVANT results, tightly clustered. "
            "I don't care if all jobs are from similar companies or the same specialization."
        ),
    },
    {
        "label": "λ=0.7  default",
        "canonical": {
            "title":            {"data": "AI Engineer",   "dealBreaker": True},
            "domain":           {"data": "Generative AI", "dealBreaker": False},
            "work_format":      {"data": "hybrid",        "dealBreaker": False},
            "experience_level": {"data": "mid",           "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": (
            "Relevance-leaning with mild variety — "
            "good matches first, but avoid showing the exact same company twice."
        ),
    },
    {
        "label": "λ=0.5  balanced",
        "canonical": {
            "title":            {"data": "AI Engineer",   "dealBreaker": True},
            "domain":           {"data": "Generative AI", "dealBreaker": False},
            "work_format":      {"data": "hybrid",        "dealBreaker": False},
            "experience_level": {"data": "mid",           "dealBreaker": False},
        },
        "mmr_lambda": 0.5,
        "diversity_hint": (
            "Equal weight on relevance AND variety — spread results across "
            "different companies, countries, and GenAI sub-domains."
        ),
    },
    {
        "label": "λ=0.3  diversity-leaning",
        "canonical": {
            "title":            {"data": "AI Engineer",   "dealBreaker": True},
            "domain":           {"data": "Generative AI", "dealBreaker": False},
            "work_format":      {"data": "hybrid",        "dealBreaker": False},
            "experience_level": {"data": "mid",           "dealBreaker": False},
        },
        "mmr_lambda": 0.3,
        "diversity_hint": (
            "Maximum diversity — I want to explore the FULL landscape. "
            "Include jobs from very different companies, industries, countries, "
            "and GenAI sub-fields even if some are less directly relevant."
        ),
    },
]

GROUP_BONUS = [
    {
        "label": "startup + remote + entry",
        "canonical": {
            "title":            {"data": "Software Engineer", "dealBreaker": True},
            "company_size":     {"data": "small",             "dealBreaker": False},
            "work_format":      {"data": "remote",            "dealBreaker": False},
            "experience_level": {"data": "start",             "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Prefer startups and small companies with remote roles for entry-level.",
    },
    {
        "label": "large corp + in-person + senior",
        "canonical": {
            "title":            {"data": "Software Engineer", "dealBreaker": True},
            "company_size":     {"data": "large",             "dealBreaker": False},
            "work_format":      {"data": "in-person",         "dealBreaker": False},
            "experience_level": {"data": "senior",            "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Large enterprise companies with on-site senior roles.",
    },
    {
        "label": "mid corp + hybrid + PhD pref",
        "canonical": {
            "title":           {"data": "Software Engineer", "dealBreaker": True},
            "company_size":    {"data": "mid",               "dealBreaker": False},
            "work_format":     {"data": "hybrid",            "dealBreaker": False},
            "education_level": {"data": "phd",               "dealBreaker": False},
        },
        "mmr_lambda": 0.7,
        "diversity_hint": "Mid-size companies, hybrid, roles where a PhD is valued.",
    },
]

GROUPS = {
    "filters":     GROUP_FILTERS,
    "dealbreaker": GROUP_DEALBREAKER,
    "lambda":      GROUP_LAMBDA,
    "bonus":       GROUP_BONUS,
}

GROUP_TITLES = {
    "filters":     "GROUP 1: Different filter fields",
    "dealbreaker": "GROUP 2: DealBreaker True vs False",
    "lambda":      "GROUP 3: Same filters, different MMR lambda / diversity hint",
    "bonus":       "GROUP 4 (bonus): Same title, different context",
}


# ── Group summary ─────────────────────────────────────────────────────────────
def _summarise(records: list[tuple]):
    print(f"\n  {'Scenario':<44}  {'Overlap':>7}  {'Fuzzy':>5}  {'Top-k':>5}")
    print(f"  {'─' * 44}  {'─' * 7}  {'─' * 5}  {'─' * 5}")
    for label, local_r, claude_r in records:
        lt = {r.get("Job Title", "").lower().strip() for r in local_r}
        ct = {j.get("title", "").lower().strip() for j in claude_r}
        exact = len(lt & ct)
        fuzzy = sum(
            1 for x in ct
            if any(x[:20] in y or y[:20] in x for y in lt)
        )
        n = max(len(lt), len(ct), 1)
        print(
            f"  {label[:44]:<44}  {exact}/{n:>1}  ({exact / n:>4.0%})"
            f"  {fuzzy:>5}  {n:>5}"
        )
    print(f"  {'─' * 44}")


# ── Runner ────────────────────────────────────────────────────────────────────
def run_group(group_name: str, df: pd.DataFrame, top_k: int, dry_run: bool):
    scenarios = GROUPS[group_name]
    title = GROUP_TITLES[group_name]
    print(f"\n{'▶' * 3}  {title}  {'◀' * 3}")

    records = []
    for scenario in scenarios:
        label   = scenario["label"]
        filters = scenario["canonical"]
        lam     = scenario["mmr_lambda"]
        hint    = scenario["diversity_hint"]

        print(f"\n{'─' * 90}")
        print(f"  Scenario : {label}")
        print(f"  Filters  : {_filter_summary(filters)}")
        print(f"  Lambda   : {lam}  |  Diversity hint: {hint[:70]}")

        # ── Local pipeline ────────────────────────────────────────────────────
        local_results = find_top_k_jobs(df, filters, top_k=top_k, mmr_lambda=lam)

        # ── Claude (web search) ───────────────────────────────────────────────
        claude_payload = ask_claude(filters, top_k, hint, dry_run=dry_run)

        if not dry_run:
            print_side_by_side(label, filters, local_results, claude_payload)
            records.append((label, local_results, claude_payload.get("jobs", [])))

    if not dry_run and records:
        print(f"\n{'═' * 90}")
        print(f"  Summary — {title}")
        _summarise(records)


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--group", choices=list(GROUPS) + ["all"], default="all",
        help="Experiment group to run (default: all)",
    )
    parser.add_argument("--top", type=int, default=5, help="Results per scenario (default: 5)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show prompts and run local pipeline only; skip Claude API",
    )
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        env_file = ROOT / ".env"
        if env_file.exists():
            from dotenv import load_dotenv
            load_dotenv(env_file)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ERROR: ANTHROPIC_API_KEY not set. Add it to .env or export it.\n"
                "Use --dry-run to skip API calls.",
                file=sys.stderr,
            )
            sys.exit(1)

    print(f"\nLoading data from: {args.data}")
    df = pd.read_csv(args.data)
    print(f"Loaded {len(df):,} jobs.\n")

    groups_to_run = list(GROUPS) if args.group == "all" else [args.group]
    for name in groups_to_run:
        run_group(name, df, args.top, dry_run=args.dry_run)

    print(f"\n{'═' * 90}")
    print("  Done.\n")


if __name__ == "__main__":
    main()
