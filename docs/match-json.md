# Match output — JSON contract

`match_experiences.py --json` (`just match … --json`) prints a single JSON
object to stdout: the job set it was given and the TUM experiences it matched.
This is the integration surface for the frontend.

```bash
just match --jobs job-1,job-2,job-3,job-4,job-5 --top 5 --json
just match --jobs job-1,job-2 --prefs prefs.json --json   # prefs reshape ranking, not the shape
```

## Programmatic bridge (findJobs → experiences)

The CLI reads a job set out of the project's own `jobs.csv`. To match against a
job set produced **at runtime** by `findJobs.search_jobs(answers)` — a different
dataset with no `job_id` — call the in-memory bridge instead:

```python
import sys
sys.path.insert(0, "scripts")  # match_experiences lives in scripts/, not a package
from career_detective.job_matching import search_jobs
from match_experiences import match_from_job_records

answers = {
    "title":   {"data": "Machine Learning Engineer", "dealBreaker": True},
    "domain":  {"data": "Computer Vision",            "dealBreaker": False},
    "country": {"data": "Japan",                      "dealBreaker": True},
    # …the same answer set that drove job selection
}

jobs = search_jobs(answers, top_k=5)          # findJobs' ranked job dicts
payload = match_from_job_records(jobs, answers, top=5)
# payload == {"jobs": [...verbatim...], "experiences": [...]}  (JSON-safe)
```

`match_from_job_records(records, answers=None, top=5)` tags each job record on
the fly (using the same controlled vocabulary the offline pipeline uses), scores
every experience against that job set, applies the answer-set preferences
(including the dealbreaker reserved slot), and returns the **same payload shape**
documented below. `records` may be any list of job dicts carrying the enriched
columns (`Job Title`, `Industry`, `Country`, `Required Skills`,
`Programming Languages Required`, `AI Specialization`); the `jobs` block echoes
them back **verbatim** (numpy/NaN coerced to JSON-native types).

## Shape

```jsonc
{
  "jobs": [
    {
      "job_id": "job-1",
      "title": "AI Engineer",
      "company": "Casumo",
      "industry": "Technology",
      "country": "United States",
      "remote": "Hybrid",
      "experience_level": "Senior",
      "salary_mid_usd": 160000.0,
      "job_url": "https://…"
    }
    // …one object per requested job
  ],
  "experiences": [
    {
      "name": "AI, Society and Governance",
      "description": "Examines generative AI's societal impact; students conduct red-teaming …",
      "skills": ["BERT", "GPT", "Generative AI", "LLMs", "Prompt Engineering"],
      "score": 0.584
    }
    // …up to --top objects, best first
  ]
}
```

## Fields

### `jobs[]` — the job set, echoed verbatim

Each object is a row from the jobs dataset, passed through **exactly as
received**, in the **same order as the requested `job_id`s**. Columns:

| Field | Type | Notes |
| --- | --- | --- |
| `job_id` | string | e.g. `"job-1"` |
| `title` | string | |
| `company` | string | |
| `industry` | string | |
| `country` | string | |
| `remote` | string | e.g. `"Hybrid"`, `"Remote"`, `"On-site"` |
| `experience_level` | string | e.g. `"Senior"` |
| `salary_mid_usd` | number \| null | midpoint USD; `null` if unknown |
| `job_url` | string | |

Any missing cell is `null` (not `NaN`), so the payload is always valid JSON.

### `experiences[]` — the matched experiences, best first

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | display name of the club / programme / project |
| `description` | string | may be long (full research-project briefs run to paragraphs) or `""` |
| `skills` | string[] | the experience's **canonical** skill tags, alphabetically sorted; may be `[]` |
| `score` | number | composite match score, rounded to 3 dp; **descending** down the list |

## Guarantees

- `jobs` order = requested `job_id` order.
- `experiences` order = descending `score` (index 0 is the top match).
- `experiences` length ≤ `--top` (default 5); a dealbreaker preference can
  reserve a slot for a low-`score` but non-negotiable match (e.g. a cultural
  club for `country=Japan`), so a trailing low score is expected, not a bug.
- `score` is **relative to this job set** — compare within one response, not
  across different job sets.
- Missing values are `null`; strings may be empty (`""`); `skills` may be `[]`.
- The `--broaden` lane is **not** included in JSON output — `experiences` is the
  single ranked list.
