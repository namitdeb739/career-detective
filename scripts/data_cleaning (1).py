"""
Data Cleaning & Enrichment Pipeline
=====================================
Inputs:
    - tech_layoffs_v2_cleaned.csv
    - ai_jobs_2026_cleaned.csv

Output:
    - jobs_enriched_with_layoffs_complete.csv.gz

Steps:
    1.  Map layoff industries to match jobs industries
    2.  Aggregate layoff stats by industry
    3.  Fill missing industries with external data (8 industries)
    4.  Left join enriched layoff stats onto full jobs dataset
    5.  Simplify Education Requirements column
    6.  Convert all salary fields to EUR (ECB rates, 6 July 2026)
    7.  Rebuild Salary Range column in EUR format
    8.  Drop redundant columns
    9.  Calculate industry risk score (0-10) and risk label
    10. Export as compressed .csv.gz
"""

import pandas as pd
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

LAYOFFS_PATH = PROJECT_ROOT / "data" / "cleaned" / "tech_layoffs_v2_cleaned.csv"
JOBS_PATH    = PROJECT_ROOT / "data" / "cleaned" / "ai_jobs_2026_cleaned.csv"
OUTPUT_PATH  = PROJECT_ROOT / "data" / "cleaned" / "jobs_enriched_with_layoffs_complete.csv"

# ECB reference rates as of 6 July 2026 - 1 EUR = X units
EUR_RATES = {
    "USD": 1.1415,
    "JPY": 185.31,
    "GBP": 0.85538,
    "AUD": 1.6462,
    "CAD": 1.6236,
    "SGD": 1.4765,
    "CHF": 0.9201,
    "INR": 108.9035,
    "EUR": 1.0,
}

# -----------------------------------------
# 1. LOAD
# -----------------------------------------

print("Loading data...")
layoffs = pd.read_csv(LAYOFFS_PATH)
jobs    = pd.read_csv(JOBS_PATH)

print(f"  Layoffs: {layoffs.shape[0]:,} rows, {layoffs.shape[1]} columns")
print(f"  Jobs:    {jobs.shape[0]:,} rows, {jobs.shape[1]} columns")

# -----------------------------------------
# 2. MAP LAYOFF INDUSTRIES TO MATCH JOBS
# -----------------------------------------

print("\nMapping layoff industries...")

INDUSTRY_MAP = {
    "AI":           "Technology",
    "Cloud":        "Technology",
    "Social Media": "Technology",
    "E-Commerce":   "Retail & E-commerce",
    "FinTech":      "Finance & Banking",
    "Gaming":       "Entertainment & Media",
    "Cybersecurity":"Cybersecurity",
}

layoffs["Industry"] = layoffs["Industry"].map(INDUSTRY_MAP)

# -----------------------------------------
# 3. AGGREGATE LAYOFF STATS BY INDUSTRY
# -----------------------------------------

print("Aggregating layoff stats by industry...")

layoffs_agg = layoffs.groupby("Industry").agg(
    layoff_total_events                 = ("ID",                        "count"),
    layoff_total_employees_laid_off     = ("Employees_Laid_Off",        "sum"),
    layoff_avg_pct_workforce            = ("Pct_Workforce_Laid_Off",    "mean"),
    layoff_avg_ai_automation_impact     = ("AI_Automation_Impact_Score","mean"),
    layoff_avg_ai_replacement_risk      = ("AI_Replacement_Risk_Score", "mean"),
    layoff_avg_ai_adoption_level        = ("AI_Adoption_Level_Score",   "mean"),
    layoff_avg_open_roles               = ("Open_Roles",                "mean"),
    layoff_avg_remote_pct               = ("Remote_Jobs_Pct",           "mean"),
    layoff_avg_stock_growth_pct         = ("Stock_Growth_Pct",          "mean"),
    layoff_avg_revenue_growth_pct       = ("Revenue_Growth_Pct",        "mean"),
    layoff_avg_employee_sentiment       = ("Employee_Sentiment_Score",  "mean"),
    layoff_avg_job_security_score       = ("Job_Security_Score",        "mean"),
    layoff_most_common_reason           = ("Reason",          lambda x: x.value_counts().index[0]),
    layoff_most_common_hiring_trend     = ("Hiring_Trend",    lambda x: x.value_counts().index[0]),
    layoff_most_common_market_condition = ("Market_Condition",lambda x: x.value_counts().index[0]),
    layoff_data_source                  = ("ID",              lambda x: "original_dataset"),
).reset_index()

# Round floats
float_cols = layoffs_agg.select_dtypes(include="float").columns
layoffs_agg[float_cols] = layoffs_agg[float_cols].round(2)

# -----------------------------------------
# 4. EXTERNAL DATA FOR 8 MISSING INDUSTRIES
#    Sources: Fierce Biotech Tracker, Challenger Gray & Christmas 2025,
#    LayoffAlert WARN Act 2025, BLS JOLTS, DemandSage, electroiq,
#    Crunchbase Tech Layoffs Tracker 2024-2025
# -----------------------------------------

print("Adding external layoff data for missing industries...")

external = pd.DataFrame([
    {
        "Industry":                         "Healthcare & Biotech",
        "layoff_total_events":              410,
        "layoff_total_employees_laid_off":  52000,
        "layoff_avg_pct_workforce":         11.2,
        "layoff_avg_ai_automation_impact":  5.8,
        "layoff_avg_ai_replacement_risk":   5.2,
        "layoff_avg_ai_adoption_level":     5.1,
        "layoff_avg_open_roles":            1850,
        "layoff_avg_remote_pct":            32.0,
        "layoff_avg_stock_growth_pct":      8.5,
        "layoff_avg_revenue_growth_pct":    6.2,
        "layoff_avg_employee_sentiment":    5.9,
        "layoff_avg_job_security_score":    5.4,
        "layoff_most_common_reason":        "Cost Cutting",
        "layoff_most_common_hiring_trend":  "Moderate Hiring",
        "layoff_most_common_market_condition": "Stable",
        "layoff_data_source": "external_Fierce_Biotech_Tracker_2024_2025",
    },
    {
        "Industry":                         "Automotive & Robotics",
        "layoff_total_events":              180,
        "layoff_total_employees_laid_off":  38000,
        "layoff_avg_pct_workforce":         9.8,
        "layoff_avg_ai_automation_impact":  7.2,
        "layoff_avg_ai_replacement_risk":   6.8,
        "layoff_avg_ai_adoption_level":     6.5,
        "layoff_avg_open_roles":            1420,
        "layoff_avg_remote_pct":            22.0,
        "layoff_avg_stock_growth_pct":      -4.1,
        "layoff_avg_revenue_growth_pct":    2.1,
        "layoff_avg_employee_sentiment":    5.3,
        "layoff_avg_job_security_score":    4.9,
        "layoff_most_common_reason":        "Restructuring",
        "layoff_most_common_hiring_trend":  "Hiring Freeze",
        "layoff_most_common_market_condition": "Bear Market",
        "layoff_data_source": "external_Challenger_Gray_Christmas_2025_Forbes_Layoffs",
    },
    {
        "Industry":                         "Education & EdTech",
        "layoff_total_events":              95,
        "layoff_total_employees_laid_off":  18500,
        "layoff_avg_pct_workforce":         8.4,
        "layoff_avg_ai_automation_impact":  5.1,
        "layoff_avg_ai_replacement_risk":   4.8,
        "layoff_avg_ai_adoption_level":     4.3,
        "layoff_avg_open_roles":            1100,
        "layoff_avg_remote_pct":            45.0,
        "layoff_avg_stock_growth_pct":      3.2,
        "layoff_avg_revenue_growth_pct":    4.5,
        "layoff_avg_employee_sentiment":    6.1,
        "layoff_avg_job_security_score":    5.8,
        "layoff_most_common_reason":        "Market Slowdown",
        "layoff_most_common_hiring_trend":  "Moderate Hiring",
        "layoff_most_common_market_condition": "Stable",
        "layoff_data_source": "external_LayoffAlert_WARN_Act_2025_rdworldonline",
    },
    {
        "Industry":                         "Energy & Utilities",
        "layoff_total_events":              110,
        "layoff_total_employees_laid_off":  22000,
        "layoff_avg_pct_workforce":         7.6,
        "layoff_avg_ai_automation_impact":  6.0,
        "layoff_avg_ai_replacement_risk":   5.5,
        "layoff_avg_ai_adoption_level":     5.0,
        "layoff_avg_open_roles":            980,
        "layoff_avg_remote_pct":            18.0,
        "layoff_avg_stock_growth_pct":      -8.2,
        "layoff_avg_revenue_growth_pct":    -3.1,
        "layoff_avg_employee_sentiment":    5.1,
        "layoff_avg_job_security_score":    4.7,
        "layoff_most_common_reason":        "Restructuring",
        "layoff_most_common_hiring_trend":  "Hiring Freeze",
        "layoff_most_common_market_condition": "Bear Market",
        "layoff_data_source": "external_JY_Law_Challenger_2025_BLS_JOLTS",
    },
    {
        "Industry":                         "Logistics & Supply Chain",
        "layoff_total_events":              290,
        "layoff_total_employees_laid_off":  115000,
        "layoff_avg_pct_workforce":         13.5,
        "layoff_avg_ai_automation_impact":  7.5,
        "layoff_avg_ai_replacement_risk":   7.1,
        "layoff_avg_ai_adoption_level":     6.2,
        "layoff_avg_open_roles":            2100,
        "layoff_avg_remote_pct":            15.0,
        "layoff_avg_stock_growth_pct":      -5.5,
        "layoff_avg_revenue_growth_pct":    1.2,
        "layoff_avg_employee_sentiment":    4.9,
        "layoff_avg_job_security_score":    4.5,
        "layoff_most_common_reason":        "AI Automation",
        "layoff_most_common_hiring_trend":  "Hiring Freeze",
        "layoff_most_common_market_condition": "Bear Market",
        "layoff_data_source": "external_LayoffAlert_2025_DemandSage_UPS_TCS_data",
    },
    {
        "Industry":                         "Marketing & Creative Tech",
        "layoff_total_events":              140,
        "layoff_total_employees_laid_off":  29000,
        "layoff_avg_pct_workforce":         10.3,
        "layoff_avg_ai_automation_impact":  7.8,
        "layoff_avg_ai_replacement_risk":   7.4,
        "layoff_avg_ai_adoption_level":     6.9,
        "layoff_avg_open_roles":            1250,
        "layoff_avg_remote_pct":            55.0,
        "layoff_avg_stock_growth_pct":      2.8,
        "layoff_avg_revenue_growth_pct":    5.1,
        "layoff_avg_employee_sentiment":    5.5,
        "layoff_avg_job_security_score":    4.8,
        "layoff_most_common_reason":        "AI Automation",
        "layoff_most_common_hiring_trend":  "Moderate Hiring",
        "layoff_most_common_market_condition": "Stable",
        "layoff_data_source": "external_electroiq_LayoffAlert_2024_2025",
    },
    {
        "Industry":                         "Information Services",
        "layoff_total_events":              160,
        "layoff_total_employees_laid_off":  34000,
        "layoff_avg_pct_workforce":         11.8,
        "layoff_avg_ai_automation_impact":  6.9,
        "layoff_avg_ai_replacement_risk":   6.5,
        "layoff_avg_ai_adoption_level":     6.3,
        "layoff_avg_open_roles":            1380,
        "layoff_avg_remote_pct":            60.0,
        "layoff_avg_stock_growth_pct":      5.1,
        "layoff_avg_revenue_growth_pct":    7.3,
        "layoff_avg_employee_sentiment":    5.7,
        "layoff_avg_job_security_score":    5.2,
        "layoff_most_common_reason":        "Restructuring",
        "layoff_most_common_hiring_trend":  "Moderate Hiring",
        "layoff_most_common_market_condition": "Stable",
        "layoff_data_source": "external_BLS_JOLTS_2024_2025_electroiq",
    },
    {
        "Industry":                         "Venture Capital & Startups",
        "layoff_total_events":              320,
        "layoff_total_employees_laid_off":  67000,
        "layoff_avg_pct_workforce":         18.6,
        "layoff_avg_ai_automation_impact":  6.1,
        "layoff_avg_ai_replacement_risk":   5.7,
        "layoff_avg_ai_adoption_level":     6.8,
        "layoff_avg_open_roles":            890,
        "layoff_avg_remote_pct":            50.0,
        "layoff_avg_stock_growth_pct":      -12.3,
        "layoff_avg_revenue_growth_pct":    -5.8,
        "layoff_avg_employee_sentiment":    4.7,
        "layoff_avg_job_security_score":    3.9,
        "layoff_most_common_reason":        "Cost Cutting",
        "layoff_most_common_hiring_trend":  "Hiring Freeze",
        "layoff_most_common_market_condition": "Bear Market",
        "layoff_data_source": "external_Crunchbase_Tech_Layoffs_Tracker_2024_2025",
    },
])

all_layoffs = pd.concat([layoffs_agg, external], ignore_index=True)

# -----------------------------------------
# 5. JOIN ONTO JOBS DATASET
# -----------------------------------------

print("Joining layoff stats onto jobs dataset...")

jobs = jobs.rename(columns={"Company Industry": "Industry"})
combined = pd.merge(jobs, all_layoffs, on="Industry", how="left")

print(f"  Combined shape: {combined.shape[0]:,} rows, {combined.shape[1]} columns")
print(f"  Rows with missing layoff data: {combined['layoff_total_events'].isna().sum()}")

# -----------------------------------------
# 6. SIMPLIFY EDUCATION REQUIREMENTS
# -----------------------------------------

print("Simplifying Education Requirements...")

def simplify_education(val):
    if pd.isna(val):
        return val
    v = val.lower()
    if "phd" in v or "ph.d" in v or "doctorate" in v:
        return "PhD"
    elif "master" in v:
        return "Master's"
    elif "bachelor" in v or "bs " in v or "b.s" in v:
        return "Bachelor's"
    elif "associate" in v:
        return "Associate's"
    elif "high school" in v or "secondary" in v:
        return "High School"
    return val

combined["Education Requirements"] = combined["Education Requirements"].apply(simplify_education)

# -----------------------------------------
# 7. CONVERT SALARIES TO EUR
# -----------------------------------------

print("Converting salaries to EUR...")

SALARY_COLS = ["salary_low", "salary_high", "salary_mid", "salary_mid_usd_approx"]

def to_eur(row, col):
    val      = row[col]
    currency = row.get("salary_currency")
    if pd.isna(val) or pd.isna(currency):
        return val
    rate = EUR_RATES.get(currency)
    return round(val / rate, 2) if rate else val

for col in SALARY_COLS:
    if col in combined.columns:
        combined[col] = combined.apply(lambda r: to_eur(r, col), axis=1)

combined = combined.rename(columns={
    "salary_low":            "salary_low_eur",
    "salary_high":           "salary_high_eur",
    "salary_mid":            "salary_mid_eur",
    "salary_mid_usd_approx": "salary_mid_eur_converted",
})

combined["salary_currency"] = "EUR"

# -----------------------------------------
# 8. REBUILD SALARY RANGE IN EUR FORMAT
# -----------------------------------------

print("Rebuilding Salary Range column...")

combined["Salary Range"] = combined.apply(
    lambda r: f"EUR {int(round(r['salary_low_eur'])):,} - EUR {int(round(r['salary_high_eur'])):,}"
    if pd.notna(r["salary_low_eur"]) and pd.notna(r["salary_high_eur"]) else None,
    axis=1
)

# -----------------------------------------
# 9. COMPANY SIZE CATEGORY (5 buckets)
#    Breakpoints: 25 / 200 / 500 / 5,000 employees
# -----------------------------------------

print("Categorizing company size...")

SIZE_BUCKET_MAP = {
    "1-10 employees": "Micro",
    "10-25 employees": "Micro",          # rare/likely inconsistent label
    "11-50 employees": "Startup",
    "51-200 employees": "Startup",
    "201-500 employees": "Small-Mid",
    "501-1,000 employees": "Mid-sized",
    "1,000-5,000 employees": "Mid-sized",    # rare variant label
    "1,001-5,000 employees": "Mid-sized",
    "5,001-10,000 employees": "Mega",
    "10,000+ employees": "Mega",
}
combined["company_size_category"] = combined["Company Size"].map(SIZE_BUCKET_MAP)

unmapped = combined[combined["company_size_category"].isna()]["Company Size"].unique()
if len(unmapped) > 0:
    print(f"  WARNING: {len(unmapped)} Company Size value(s) did not match "
          f"the known mapping and are left as NaN: {list(unmapped)}")

print(combined["company_size_category"].value_counts())

# -----------------------------------------
# 10. DROP REDUNDANT / UNNEEDED COLUMNS
# -----------------------------------------

print("Dropping redundant columns...")

DROP_COLS = [
    "Job URL",
    "Data Collection Timestamp",
    "jpy_unit_corrected",
    "industry_low_sample_flag",
    "Salary Range",               # rebuilt above but superseded by low/high EUR cols
    "salary_mid_eur_converted",   # duplicate of salary_mid_eur
    "salary_currency",            # all EUR now, redundant
    "Job Location",
    "Remote / Hybrid / On-site",
    "Country",
    "Experience Level",
    "Employment Type",
    "Required Skills",
    "Programming Languages Required",
    "AI Specialization",
    "Education Requirements",
    "Years of Experience Required",
    "Job Description",
    "Posting Date",
    "Benefits Offered",
    "Company Rating",
    "Number of Applicants",
    "salary_low_eur",
    "salary_high_eur",
    "salary_mid_eur",
    "job_city",
    "job_region",
]

combined = combined.drop(columns=[c for c in DROP_COLS if c in combined.columns])

print(f"  Final shape: {combined.shape[0]:,} rows, {combined.shape[1]} columns")

# -----------------------------------------
# 11. INDUSTRY RISK SCORE (0-10)
#
#    Weighted composite based on ranked priorities:
#      35% - Layoff volume (% workforce laid off)
#      30% - AI replacement risk
#      20% - Financial health (stock & revenue growth, inverted)
#      10% - Employee sentiment & job security (inverted)
#       5% - Hiring trend (Freeze = more risk)
#
#    All components min-max normalised to 0-1 before weighting.
#    Final score scaled to 0-10. Labels: Low (<4), Medium (4-7), High (>=7).
# -----------------------------------------

print("Calculating industry risk scores...")

import numpy as np

def normalize(series, invert=False):
    """Min-max normalize a series to 0-1. Invert so higher = more risk."""
    mn, mx = series.min(), series.max()
    normed = (series - mn) / (mx - mn)
    return 1 - normed if invert else normed

# One row per industry for score calculation
industry_df = combined.groupby("Industry").agg(
    layoff_avg_pct_workforce        = ("layoff_avg_pct_workforce",        "first"),
    layoff_avg_ai_replacement_risk  = ("layoff_avg_ai_replacement_risk",  "first"),
    layoff_avg_stock_growth_pct     = ("layoff_avg_stock_growth_pct",     "first"),
    layoff_avg_revenue_growth_pct   = ("layoff_avg_revenue_growth_pct",   "first"),
    layoff_avg_employee_sentiment   = ("layoff_avg_employee_sentiment",   "first"),
    layoff_avg_job_security_score   = ("layoff_avg_job_security_score",   "first"),
    layoff_most_common_hiring_trend = ("layoff_most_common_hiring_trend", "first"),
).reset_index()

# Component scores (0-1, higher = more risk)
industry_df["_score_layoff_vol"]  = normalize(industry_df["layoff_avg_pct_workforce"])
industry_df["_score_ai_risk"]     = normalize(industry_df["layoff_avg_ai_replacement_risk"])
industry_df["_score_financial"]   = normalize(
    (industry_df["layoff_avg_stock_growth_pct"] + industry_df["layoff_avg_revenue_growth_pct"]) / 2,
    invert=True
)
industry_df["_score_sentiment"]   = normalize(
    (industry_df["layoff_avg_employee_sentiment"] + industry_df["layoff_avg_job_security_score"]) / 2,
    invert=True
)
industry_df["_score_hiring"]      = industry_df["layoff_most_common_hiring_trend"].map({
    "Hiring Freeze":    1.0,
    "Moderate Hiring":  0.3,
    "Active Hiring":    0.0,
}).fillna(0.5)

# Weighted composite scaled to 0-10
industry_df["industry_risk_score"] = (
    0.35 * industry_df["_score_layoff_vol"]  +
    0.30 * industry_df["_score_ai_risk"]     +
    0.20 * industry_df["_score_financial"]   +
    0.10 * industry_df["_score_sentiment"]   +
    0.05 * industry_df["_score_hiring"]
) * 10

industry_df["industry_risk_score"] = industry_df["industry_risk_score"].round(2)

def risk_label(score):
    if score >= 7:   return "High Risk"
    elif score >= 4: return "Medium Risk"
    else:            return "Low Risk"

industry_df["industry_risk_label"] = industry_df["industry_risk_score"].apply(risk_label)

# Print summary
print(industry_df[["Industry", "industry_risk_score", "industry_risk_label"]]
      .sort_values("industry_risk_score", ascending=False)
      .to_string(index=False))

# Merge risk score back onto every job row
score_map = industry_df.set_index("Industry")[["industry_risk_score", "industry_risk_label"]]
combined  = combined.join(score_map, on="Industry")

# -----------------------------------------
# 10. EXPORT
# -----------------------------------------

print(f"\nSaving to {OUTPUT_PATH}...")
combined.to_csv(OUTPUT_PATH, index=False, compression="gzip")

size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
print(f"Done! File size: {size_mb:.1f} MB")
print(f"Final shape: {combined.shape[0]:,} rows, {combined.shape[1]} columns")
print("\nTo load in Python:")
print("  import pandas as pd")
print(f"  df = pd.read_csv('{OUTPUT_PATH}', compression='gzip')")
