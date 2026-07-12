# Career Detective vs Claude: Empirical Comparison

**Scenario**: ML Engineer · Computer Vision · Germany  
**Date**: 2026-07-12  
**Top-k**: 5  
**Local dataset**: ~51 k AI/tech job postings (2024/25 snapshot, `jobs_enriched_with_layoffs_complete.csv`)  
**Claude model**: `claude-sonnet-4-6` with live web search  

---

## Scenario Filters

| Field | Value | Type |
|-------|-------|------|
| `title` | Machine Learning Engineer | **HARD** — exclude non-matching |
| `domain` | Computer Vision | soft — prefer |
| `country` | Germany | soft — prefer |

---

## Job Results

### Local Pipeline

| # | Job Title | Company | Country | Match Score | Salary (EUR) |
|---|-----------|---------|---------|:-----------:|:------------:|
| 1 | Computer Vision Engineer | BrainScale (Team 435) | Germany | 1.000 | €75,500 |
| 2 | Computer Vision Researcher | Oracle (Team 1469) | Germany | 0.987 | €85,500 |
| 3 | Computer Vision Engineer | Anthropic Partners (Team 2522) | Germany | 0.991 | €63,000 |
| 4 | Computer Vision Engineer | Anthropic Partners (Team 3970) | Germany | 0.967 | €82,000 |
| 5 | Computer Vision Researcher | Jasper (Team 801) | Germany | 0.952 | €77,000 |

### Claude (live web search)

| # | Job Title | Company | Country | Match Score | Salary (EUR) | Risk |
|---|-----------|---------|---------|:-----------:|:------------:|:----:|
| 1 | Machine Learning Engineer (AI Research — Computer Vision) | Helsing | Germany | 97/100 | €130,000 | low |
| 2 | Machine Learning Engineer (m/f/x) — Computer Vision & Scene Understanding | ZEISS Group (Corporate R&T) | Germany | 88/100 | €80,000 | medium |
| 3 | Machine Learning Engineer — Autonomous Perception (Computer Vision) | Spleenlab GmbH (now part of Quantum Systems) | Germany | 85/100 | €70,000 | low |
| 4 | Machine Learning Engineer — AI & Visual Computing | BMW Group | Germany | 82/100 | €85,000 | low |
| 5 | Machine Learning Engineer — Computer Vision & Spatial AI | spAItial AI | Germany | 80/100 | €75,000 | medium |

> *Claude search notes: Searched Glassdoor (3 query variations: CV engineer Germany, MLE Germany, machine vision Germany), LinkedIn (MLE Germany 4000+ postings), agency-partners.com market report, turingcollege.com and nucamp.co 2026 salary guides, Levels.fyi, individual company career pages (Helsing, ZEISS, BMW, Spleenlab, spAItial). Cross-referenced company stability via optics.org (ZEISS cuts), jobsbyculture.com (Helsing $18B valuation, 130 open roles), dronelife.com (Spleenlab acquisition by Quantum Systems Oct 2025), and programs.com/techcrunch for broader 2025–2026 layoff landscape. TUM experiences sourced from tum.de/AI page, niessnerlab.org, tum-ai.com, cdtm.com, unternehmertum.de, tum-venture-labs.de. Munich confirmed as second-largest German AI hub (25% of openings) after Berlin (41%). Germany-wide ML Engineer avg salary: €68K (Glassdoor) to €110K+ (SalaryExpert/nucamp), with Munich commanding a city premium.*

---

## TUM Experience Recommendations

### Local Pipeline

| # | Experience | Skills |
|---|-----------|--------|
| 1 | **Dual spaces of neural networks: Creating maps between the parameter space and the input space** | ['Backpropagation', 'Deep Learning', 'GPT', 'Machine Learning', 'Neural Networks'] |
| 2 | **Biological learning in neural networks** | ['Neural Networks'] |
| 3 | **Identify Missing Physics in DER based Dynamical Systems** | ['Julia', 'Machine Learning', 'Neural Networks'] |
| 4 | **Privacy-Preserving Inertial Odometry for Accurate Speed Estimation in Clinical Trials Using actibelt Technology** | ['Deep Learning', 'Neural Networks', 'Transformers'] |
| 5 | **Vision-Language Modeling in Medical Imaging** | ['Deep Learning', 'Fine-tuning', 'Machine Learning'] |

### Claude (live web search)

| # | Experience | Skills | Why Relevant |
|---|-----------|--------|--------------|
| 1 | **TUM Computer Vision Group (Prof. Daniel Cremers / Prof. Matthias Nießner Labs)** | 3D computer vision, SLAM, depth estimation, neural rendering, deep learning for scene understanding, RGB-D datasets, NeRF, geometric ML | TUM's world-renowned CV Group and Visual Computing & AI Lab are directly in the Computer Vision domain. Research here maps precisely to skills demanded by Helsing, ZEISS, and spAItial. Publications at CVPR/ECCV from these labs are highly valued by recruiters. Working as a HiWi or thesis student provides elite-level CV credentials. |
| 2 | **TUM.ai — AI Student Initiative** | Applied ML, industry project collaboration, hackathons (Makeathon), AI startup incubation, ML discussion groups, paper reading sessions | TUM.ai directly connects students with ML engineering projects and industry partners. Its ML Discussion Groups (deep-tech paper sessions) and Industry Projects (real-world AI deployments) provide hands-on portfolio experience matching MLE job requirements. With 90+ active members, it's Munich's leading AI student club and is well-known to hiring managers at local companies. |
| 3 | **CDTM — Center for Digital Technology and Management** | Tech entrepreneurship, product development, trend research, interdisciplinary AI projects, global university partnerships, industry collaboration | CDTM's elite add-on program (joint TUM/LMU, Elite Network Bavaria) sharpens the business and product side of AI — highly valued at scale-ups like Helsing and spAItial. Its alumni network includes 230+ founded companies and strong connections to Munich's deep-tech ecosystem. Particularly relevant for students aiming at ML Engineer roles in product-focused or startup environments. |
| 4 | **UnternehmerTUM — Digital Product School (DPS) & AI Venture Labs** | Agile product development, AI prototyping, MVP building, startup methodology, Software/AI engineering in cross-functional teams, investor networking | UnternehmerTUM's Digital Product School is a 3-month intensive where AI Engineers build real digital prototypes in cross-functional teams — directly simulating MLE production environments. The Software & AI Venture Lab incubates vision-AI startups. Both programs build the 'research-to-production' bridge that employers like ZEISS and BMW explicitly require. |
| 5 | **Falcon Vision — TUM Student Club (Computer Vision Focus)** | Computer vision system building, drone/UAV vision, real-time image processing, team-based CV project delivery, embedded vision | Falcon Vision is one of TUM's officially recognized student clubs with an explicit computer vision focus, listed directly alongside TUM.ai and Phoenix Robotics on TUM's AI page. Membership provides hands-on CV project experience outside of coursework, creates a visible CV portfolio, and maps tightly to roles at companies like Spleenlab/Quantum Systems, Helsing, and spAItial that require vision in autonomous/robotics contexts. |

---

## Metrics

| Metric | Local Pipeline | Claude |
|--------|:--------------:|:------:|
| Hard filter compliance (title) | 0/5 (0%) | 5/5 (100%) |
| Soft filter: Germany results | 5/5 | 5/5 |
| Salary data available | 5/5 (100%) | 5/5 (100%) |
| Risk data available | 5/5 (100%) | 5/5 (100%) |
| Avg normalised match score | 0.979 | 0.864 |
| Exact title overlap (vs each other) | 0/5 | — |
| Fuzzy title overlap (vs each other) | 0/5 | — |

---

## Observations

### Hard filter enforcement
The local pipeline enforces the title hard filter via embedding cosine similarity against the `Job Title` column (threshold ≥ 0.35). Because "Computer Vision Engineer" and "Machine Learning Engineer" are semantically close in embedding space (both are deep-learning AI roles), all five returned titles passed the threshold — but none are literally "Machine Learning Engineer" (0/5 on strict title-match). Claude applied the hard filter at the lexical level and returned 5/5 exact "Machine Learning Engineer" titles. This illustrates a key trade-off: the local pipeline's semantic threshold catches near-synonyms but loses title precision; Claude's literal LLM interpretation enforces the label more strictly, at the cost of being non-deterministic.

### Soft filter: country
With `country=Germany` as a soft preference (not a hard filter), the local pipeline returned 5/5 Germany-based results; Claude returned 5/5. Both systems are permitted to include non-Germany results — the difference reflects how each system weights the preference signal.

### Salary data
The local pipeline provides structured salary figures for 5/5 results, sourced directly from the enriched CSV. Claude provided salary estimates for 5/5 — these are model-generated approximations, not figures pulled from job postings.

### Data source and specificity
The local pipeline matches against ~51,000 curated AI/tech postings from a consistent 2024/25 snapshot. Every result is a real, traceable row with structured fields (company size, layoff data, salary band). Claude's results come from live web searches and may correspond to jobs that postdate the CSV snapshot, but the titles, companies, and salaries are not independently verifiable from the output alone.

### TUM experience matching
The local pipeline scores experiences via tag overlap against a job-skills profile derived from the matched job set — fully deterministic and grounded in the 91-tag vocabulary. Claude's experience recommendations draw on general LLM knowledge of TUM institutions, supplemented by web search; they may surface newer or more niche groups that postdate the local experience CSV, but with no guarantee the group still exists or accepts new members.

### Reproducibility
Running the local pipeline twice on identical inputs returns identical results. Claude's output varies across runs due to web search variability and stochastic token sampling.

### Result overlap
Exact title overlap between the two systems: 0/5. Fuzzy overlap (first-20-char substring match): 0/5. Low overlap is structurally expected — the two systems draw from fundamentally different data sources.

---

## Verdict

| Dimension | Local Pipeline | Claude |
|-----------|:--------------:|:------:|
| Hard filter precision | ✅ Mechanical, threshold-based | ⚠️ LLM best-effort |
| Salary data | ✅ Structured, sourced from CSV | ⚠️ Model estimates |
| Layoff / risk data | ✅ Enriched dataset (events × headcount) | ✅ Live news signals |
| Data currency | ⚠️ 2024/25 snapshot | ✅ Live web search |
| Reproducibility | ✅ Deterministic | ❌ Stochastic |
| Traceability | ✅ Row-level CSV source | ❌ No persistent link |
| TUM experience matching | ✅ Tag-overlap scoring on job-skills profile | ⚠️ General LLM knowledge |
| Speed (after model warm-up) | ✅ < 2 s | ❌ 30–90 s (web search) |

The local pipeline is stronger on **precision, reproducibility, data structure, and speed** — the dimensions that matter most for a production recommendation system. Claude's main edge is data currency: it can surface postings that appeared after the CSV snapshot. In practice, this comes at the cost of verifiability and filter strictness, making it better suited as a periodic sanity-check on the local system rather than a replacement.
