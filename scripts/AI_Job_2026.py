"""
EDA for AI Jobs 2026 dataset.
Reads the cleaned CSV produced in the earlier cleaning step and generates
exploratory charts covering: sector/industry, geography, salary, remote mix,
experience level, AI specialization, and required skills.

Run: python3 01_eda.py
Outputs: PNG charts written to ./charts/
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

sns.set_theme(style="whitegrid")
OUT = Path("charts")
OUT.mkdir(exist_ok=True)

df = pd.read_csv("ai_jobs_2026_cleaned.csv", parse_dates=["Posting Date"])

# Exclude the 3 rows flagged as belonging to broken/near-empty industry
# categories (n=1 each) from any industry-level aggregation. See cleaning
# step notes: these categories are not statistically meaningful.
df_industry = df[~df["industry_low_sample_flag"]].copy()

# ---------------------------------------------------------------
# 1. Postings by industry
# ---------------------------------------------------------------
plt.figure(figsize=(10, 6))
order = df_industry["Company Industry"].value_counts().index
sns.countplot(data=df_industry, y="Company Industry", order=order, color="#4C72B0")
plt.title("AI Job Postings by Industry (Apr\u2013Jun 2026)")
plt.xlabel("Number of postings")
plt.ylabel("")
plt.tight_layout()
plt.savefig(OUT / "01_postings_by_industry.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 2. Median salary by industry
# ---------------------------------------------------------------
plt.figure(figsize=(10, 6))
med = (
    df_industry.groupby("Company Industry")["salary_mid_usd_approx"]
    .median()
    .sort_values(ascending=False)
)
sns.barplot(x=med.values, y=med.index, color="#55A868")
plt.title("Median Approx. Salary (USD) by Industry")
plt.xlabel("Median salary, USD (approx. FX conversion)")
plt.ylabel("")
plt.tight_layout()
plt.savefig(OUT / "02_median_salary_by_industry.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 3. Median salary by country
# ---------------------------------------------------------------
plt.figure(figsize=(10, 6))
med_c = df.groupby("Country")["salary_mid_usd_approx"].median().sort_values(ascending=False)
sns.barplot(x=med_c.values, y=med_c.index, color="#C44E52")
plt.title("Median Approx. Salary (USD) by Country")
plt.xlabel("Median salary, USD (approx. FX conversion)")
plt.ylabel("")
plt.tight_layout()
plt.savefig(OUT / "03_median_salary_by_country.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 4. Remote / Hybrid / On-site mix
# ---------------------------------------------------------------
plt.figure(figsize=(6, 6))
mix = df["Remote / Hybrid / On-site"].value_counts()
plt.pie(mix.values, labels=mix.index, autopct="%1.0f%%", colors=["#4C72B0", "#DD8452", "#55A868"])
plt.title("Work Arrangement Mix")
plt.tight_layout()
plt.savefig(OUT / "04_remote_mix.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 5. Experience level distribution
# ---------------------------------------------------------------
plt.figure(figsize=(7, 5))
exp_order = ["Entry", "Mid", "Senior"]
sns.countplot(data=df, x="Experience Level", order=exp_order, color="#8172B2")
plt.title("Postings by Experience Level")
plt.tight_layout()
plt.savefig(OUT / "05_experience_level.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 6. AI specialization demand
# ---------------------------------------------------------------
plt.figure(figsize=(9, 5))
spec = df["AI Specialization"].value_counts()
sns.barplot(x=spec.values, y=spec.index, color="#64B5CD")
plt.title("Demand by AI Specialization")
plt.xlabel("Number of postings")
plt.tight_layout()
plt.savefig(OUT / "06_ai_specialization.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 7. Top required skills (parses comma-separated skill lists)
# ---------------------------------------------------------------
skills = (
    df["Required Skills"].dropna().str.split(",").explode().str.strip()
)
top_skills = skills.value_counts().head(15)
plt.figure(figsize=(9, 6))
sns.barplot(x=top_skills.values, y=top_skills.index, color="#4C72B0")
plt.title("Top 15 Required Skills")
plt.xlabel("Mentions across postings")
plt.tight_layout()
plt.savefig(OUT / "07_top_skills.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 8. Weekly posting volume (trend within the window)
# ---------------------------------------------------------------
weekly = df.set_index("Posting Date").resample("W").size()
# Drop first/last partial weeks for a fairer trend read
weekly_full = weekly.iloc[1:-1]
plt.figure(figsize=(10, 5))
weekly_full.plot(marker="o", color="#4C72B0")
plt.title("Weekly Posting Volume (partial first/last weeks excluded)")
plt.ylabel("Postings")
plt.xlabel("Week ending")
plt.tight_layout()
plt.savefig(OUT / "08_weekly_volume.png", dpi=150)
plt.close()

# ---------------------------------------------------------------
# 9. Applicants vs salary (competitiveness)
# ---------------------------------------------------------------
plt.figure(figsize=(8, 6))
sample = df.dropna(subset=["salary_mid_usd_approx", "Number of Applicants"]).sample(
    n=min(4000, len(df)), random_state=1
)
sns.scatterplot(
    data=sample, x="salary_mid_usd_approx", y="Number of Applicants",
    hue="Experience Level", alpha=0.4, s=20,
)
plt.title("Applicants vs. Approx. Salary")
plt.xlabel("Median salary, USD (approx.)")
plt.tight_layout()
plt.savefig(OUT / "09_applicants_vs_salary.png", dpi=150)
plt.close()

print("EDA charts written to", OUT.resolve())
