# Sample career-preference profiles

Test how the `--prefs` career profile reshapes the experience matching. Pair any
of these with a fixed job set so only the preferences change:

```bash
just match --jobs job-1,job-2,job-3,job-4,job-5 --prefs examples/prefs/japan-relocation.json
```

Each profile stresses a different lever (all use countries that have matching
cultural clubs, so the geo boosts actually fire):

| Profile | Stresses | Expect to see |
| --- | --- | --- |
| `research-academia.json` | `education=phd` **dealbreaker** + research title | research projects (PREP) and research-tagged clubs boosted (`research focus`) |
| `startup-generalist.json` | `company_size=startup` **dealbreaker** | transversal weight ↑ → soft-skill / leadership clubs rise |
| `japan-relocation.json` | `country=Japan` **dealbreaker** | Japanese culture clubs boosted (`Japan affinity`) |
| `genai-specialist.json` | `domain=Generative AI` + `title=LLM Software Developer` **dealbreakers** | GenAI/LLM-tagged experiences boosted (`Generative AI focus`), `Germany affinity` (soft) |

The `PREFERENCES` line echoes the profile (`!` marks dealbreakers) and each
result's `boosted` line shows which preferences fired. Flip a `dealBreaker` from
`true` to `false` to see the effect weaken (boost 0.20 → 0.05; weight ×1.9 → ×1.4).
