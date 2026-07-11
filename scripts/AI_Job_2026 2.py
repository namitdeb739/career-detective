"""
Country x Industry analysis for AI Jobs 2026 dataset.

For each country, shows:
  - how many distinct industries are represented
  - how many job postings per industry
  - salary range (min/median/max, approx USD) per industry
  - typical company size per industry

Run: python3 country_industry_analysis.py
Outputs:
  - country_industry_summary.csv (the full table, one row per country+industry)
  - country_summary.csv (one row per country, industry count)
  - heatmap chart of job counts by country x industry
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys

sns.set_theme(style="whitegrid")

SCRIPT_DIR = Path(__file__).parent
DATA_PATH = SCRIPT_DIR.parent / "data" / "cleaned" / "ai_jobs_2026_cleaned.csv"
OUT_DIR = SCRIPT_DIR.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

if not DATA_PATH.exists():
    sys.exit(f"ERROR: Could not find CSV at:\n  {DATA_PATH}")

df = pd.read_csv(DATA_PATH)

# Exclude the 3 rows belonging to broken/near-empty industry categories
# (n=1 each) — see earlier cleaning notes. Not statistically meaningful.
if "industry_low_sample_flag" in df.columns:
    df = df[~df["industry_low_sample_flag"]].copy()

# ---------------------------------------------------------------
# 1. How many distinct industries per country
# ---------------------------------------------------------------
country_summary = (
    df.groupby("Country")["Company Industry"]
    .nunique()
    .reset_index(name="num_industries")
    .sort_values("num_industries", ascending=False)
)
print("=== Number of distinct industries per country ===")
print(country_summary.to_string(index=False))
country_summary.to_csv(OUT_DIR / "country_summary.csv", index=False)

# ---------------------------------------------------------------
# 2. Full breakdown: country x industry -> job count, salary range,
#    company size
# ---------------------------------------------------------------
summary = (
    df.groupby(["Country", "Company Industry"])
    .agg(
        job_count=("Job Title", "count"),
        salary_min_usd=("salary_mid_usd_approx", "min"),
        salary_median_usd=("salary_mid_usd_approx", "median"),
        salary_max_usd=("salary_mid_usd_approx", "max"),
        avg_company_size=("company_size_midpoint", "mean"),
    )
    .reset_index()
    .sort_values(["Country", "job_count"], ascending=[True, False])
)

# round for readability
for col in ["salary_min_usd", "salary_median_usd", "salary_max_usd", "avg_company_size"]:
    summary[col] = summary[col].round(0)

print("\n=== Country x Industry summary (first 20 rows) ===")
print(summary.head(20).to_string(index=False))

summary.to_csv(OUT_DIR / "country_industry_summary.csv", index=False)
print(f"\nFull table ({len(summary)} rows) saved to:")
print(f"  {OUT_DIR / 'country_industry_summary.csv'}")

# ---------------------------------------------------------------
# 3. Heatmap: job count by country x industry
# ---------------------------------------------------------------
pivot = df.pivot_table(
    index="Country", columns="Company Industry", values="Job Title", aggfunc="count", fill_value=0
)
plt.figure(figsize=(14, 8))
sns.heatmap(pivot, annot=True, fmt="d", cmap="Blues", cbar_kws={"label": "Job postings"})
plt.title("Job Postings by Country x Industry")
plt.tight_layout()
plt.savefig(OUT_DIR / "country_industry_heatmap.png", dpi=150)
plt.close()
print(f"\nHeatmap saved to: {OUT_DIR / 'country_industry_heatmap.png'}")

# ---------------------------------------------------------------
# 4. Heatmap: median salary by country x industry
# ---------------------------------------------------------------
pivot_salary = df.pivot_table(
    index="Country", columns="Company Industry", values="salary_mid_usd_approx", aggfunc="median"
)
plt.figure(figsize=(14, 8))
sns.heatmap(pivot_salary, annot=True, fmt=".0f", cmap="Greens", cbar_kws={"label": "Median salary, USD (approx.)"})
plt.title("Median Approx. Salary (USD) by Country x Industry")
plt.tight_layout()
plt.savefig(OUT_DIR / "country_industry_salary_heatmap.png", dpi=150)
plt.close()
print(f"Salary heatmap saved to: {OUT_DIR / 'country_industry_salary_heatmap.png'}")

print("\nDone.")
