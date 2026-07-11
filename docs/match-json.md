# Match output — JSON contract

`match_experiences.py --json` (`just match … --json`) prints a single JSON
object to stdout: the job set it was given and the TUM experiences it matched.
This is the integration surface for the frontend.

```bash
just match --jobs job-1,job-2,job-3,job-4,job-5 --top 5 --json
just match --jobs job-1,job-2 --prefs prefs.json --json   # prefs reshape ranking, not the shape
```

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
