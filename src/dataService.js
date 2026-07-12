// Geographic centroids — aligned with country positions on the globe
const COUNTRY_COORDS = {
  Australia: { lat: -25.27, lon: 133.78 },
  Canada: { lat: 56.13, lon: -106.35 },
  France: { lat: 46.23, lon: 2.21 },
  Germany: { lat: 51.17, lon: 10.45 },
  India: { lat: 20.59, lon: 78.96 },
  Ireland: { lat: 53.14, lon: -7.69 },
  Japan: { lat: 36.2, lon: 138.25 },
  Netherlands: { lat: 52.13, lon: 5.29 },
  Singapore: { lat: 1.35, lon: 103.82 },
  Switzerland: { lat: 46.82, lon: 8.23 },
  "United Kingdom": { lat: 55.38, lon: -3.44 },
  "United States": { lat: 39.83, lon: -98.58 },
};

const COUNTRY_NAME_MAP = {
  Australia: "Australia",
  Canada: "Canada",
  France: "France",
  Germany: "Germany",
  India: "India",
  Ireland: "Ireland",
  Japan: "Japan",
  Netherlands: "Netherlands",
  Singapore: "Singapore",
  Switzerland: "Switzerland",
  "United Kingdom": "United Kingdom",
  "United States": "United States of America",
};

// EU members actually present in the dataset's 12 countries.
// (Switzerland and the United Kingdom are NOT EU members and were
// previously included in error — fixed here.)
const EU_COUNTRIES_IN_DATA = ["Germany", "France", "Netherlands", "Ireland"];

// NOTE: DOMAIN_TO_INDUSTRY is a CURATED pairing for app variety, not a
// statistical finding. Checked against the real dataset: AI specialization
// and industry show no meaningful relationship (each specialization's most
// common industry accounts for only ~10-11% of its postings, barely above
// the ~10% baseline you'd expect from 10 industries by pure chance). Do not
// present this mapping as data-derived if referenced elsewhere in the app.
const DOMAIN_TO_INDUSTRY = {
  "🤖 Machine Learning": "Technology",
  "🧠 Deep Learning": "Automotive & Robotics",
  "📊 Data Science": "Finance & Banking",
  "💬 NLP": "Information Services",
  "👁️ Computer Vision": "Healthcare & Biotech",
  "✨ Generative AI": "Marketing & Creative Tech",
  "⚙️ MLOps": "Cybersecurity",
};

export { ROLE_BY_DOMAIN };

// Curated role-title suggestions per specialization (not a direct
// extraction from the Job Title column — this is app-authored content).
const ROLE_BY_DOMAIN = {
  "🤖 Machine Learning": ["ML Engineer", "Applied Scientist", "ML Platform Engineer"],
  "🧠 Deep Learning": ["Deep Learning Engineer", "Research Engineer", "AI Research Scientist"],
  "📊 Data Science": ["Data Scientist", "ML Analyst", "Quantitative Analyst"],
  "💬 NLP": ["NLP Engineer", "Conversational AI Engineer", "Language AI Researcher"],
  "👁️ Computer Vision": ["Computer Vision Engineer", "Perception Engineer", "Imaging AI Engineer"],
  "✨ Generative AI": ["Generative AI Engineer", "LLM Engineer", "AI Product Engineer"],
  "⚙️ MLOps": ["MLOps Engineer", "Platform Engineer", "ML Infrastructure Engineer"],
};

function parseCsv(text) {
  const lines = text.trim().split("\n");
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    return headers.reduce((row, header, i) => {
      row[header.trim()] = values[i]?.trim() ?? "";
      return row;
    }, {});
  });
}

export async function loadMarketData() {
  const [summaryText, industryText, insightsText, tumText] = await Promise.all([
    fetch("/data/country-summary.csv").then((r) => r.text()),
    fetch("/data/country-industry-summary.csv").then((r) => r.text()),
    fetch("/data/job-insights-summary.csv").then((r) => r.text()),
    fetch("/data/tum-experience-summary.csv").then((r) => r.text()),
  ]);

  const summaryRows = parseCsv(summaryText).map((row) => ({
    country: row.Country,
    numIndustries: Number(row.num_industries),
  }));

  const industryRows = parseCsv(industryText).map((row) => ({
    country: row.Country,
    industry: row["Company Industry"],
    jobCount: Number(row.job_count),
    salaryMin: Number(row.salary_min_usd),
    salaryMedian: Number(row.salary_median_usd),
    salaryMax: Number(row.salary_max_usd),
    avgCompanySize: Number(row.avg_company_size),
  }));

  const insightRows = parseCsv(insightsText).map((row) => ({
    country: row.country,
    industry: row.industry,
    specialization: row.specialization,
    jobCount: Number(row.job_count),
    salaryMedianEur: Number(row.salary_median_eur),
    riskScore: Number(row.risk_score),
    riskLabel: row.risk_label,
    sentimentScore: Number(row.sentiment_score),
    topSkills: row.top_skills ? row.top_skills.split(";").filter(Boolean) : [],
  }));

  const tumExperienceRows = parseCsv(tumText).map((row) => ({
    id: row.experience_id,
    name: row.name,
    skills: row.top_skills ? row.top_skills.split(";").filter(Boolean) : [],
    specializations: row.specializations ? row.specializations.split(";").filter(Boolean) : [],
    industries: row.industries ? row.industries.split(";").filter(Boolean) : [],
  }));

  const countrySalaries = {};
  industryRows.forEach((row) => {
    if (!countrySalaries[row.country]) {
      countrySalaries[row.country] = { medians: [], jobs: 0 };
    }
    countrySalaries[row.country].medians.push(row.salaryMedian);
    countrySalaries[row.country].jobs += row.jobCount;
  });

  const countrySummaries = Object.entries(countrySalaries).map(([country, data]) => ({
    country,
    mapName: COUNTRY_NAME_MAP[country] || country,
    salaryMedian: Math.round(
      data.medians.reduce((sum, value) => sum + value, 0) / data.medians.length,
    ),
    jobCount: data.jobs,
    numIndustries: summaryRows.find((r) => r.country === country)?.numIndustries ?? 0,
  }));

  const globeCountries = countrySummaries
    .filter((d) => COUNTRY_COORDS[d.country])
    .map((d) => ({
      ...d,
      coords: COUNTRY_COORDS[d.country],
      topIndustry: industryRows
        .filter((r) => r.country === d.country)
        .sort((a, b) => b.jobCount - a.jobCount)[0],
    }));

  return {
    industryRows,
    insightRows,
    tumExperienceRows,
    countrySummaries,
    globeCountries,
    countryNameMap: COUNTRY_NAME_MAP,
  };
}


export function getAnswer(answers, id) {
  return answers.find((a) => a.id === id)?.value ?? "";
}

export function buildRecommendations(userProfile, industryRows, insightRows = [], tumExperienceRows = []) {
  const preferences = userProfile?.preferences ?? {};
  const answers = userProfile?.answers ?? [];

  const pref = (key) => preferences[key]?.data ?? "";
  const isDealBreaker = (key) => preferences[key]?.dealBreaker ?? false;

  const domainLabel = pref("domain");
  const title = pref("title");
  const country = pref("country");
  const companySize = pref("company_size");
  const workFormat = pref("work_format");
  const experienceLevel = pref("experience_level");
  const educationLevel = pref("education_level");

  const domainKey = answers.find((a) => a.id === "jobDomain")?.value ?? "";
  const salaryTarget = getAnswer(answers, "salary");
  const workMode = getAnswer(answers, "workMode");

  const industry = DOMAIN_TO_INDUSTRY[domainKey] || "Technology";
  const roles = ROLE_BY_DOMAIN[domainKey] || [title || "ML Engineer"];
  const insightMatches = selectInsightRows(insightRows, {
    domain: domainLabel,
    country,
    industry,
  });

  // NOTE: avgCompanySize thresholds below are a placeholder mapped onto
  // the OLD single-average company size field from country-industry-summary.csv.
  // That CSV does not yet reflect the new 5-tier company_size_category
  // (Micro/Startup/Small-Mid/Mid-sized/Mega) built in the cleaning pipeline.
  // For this filter to be accurate against the real tiers, regenerate that
  // CSV to include category breakdowns per country x industry, and replace
  // this numeric-threshold approach with a direct category match.
  const sizeFilter = (row) => {
    if (companySize === "micro") return row.avgCompanySize < 25;
    if (companySize === "startup") return row.avgCompanySize >= 25 && row.avgCompanySize < 200;
    if (companySize === "small_mid") return row.avgCompanySize >= 200 && row.avgCompanySize < 500;
    if (companySize === "mid_sized") return row.avgCompanySize >= 500 && row.avgCompanySize < 5000;
    if (companySize === "mega") return row.avgCompanySize >= 5000;
    return true;
  };

  const countryFilter = (row) => {
    if (country === "Germany") return row.country === "Germany";
    if (country === "European Union") {
      return EU_COUNTRIES_IN_DATA.includes(row.country);
    }
    if (country === "United States") return row.country === "United States";
    if (country === "Global" || country === "Remote-first") return true;
    return true;
  };

  let filtered = industryRows.filter((row) => row.industry === industry);

  if (isDealBreaker("company_size")) filtered = filtered.filter(sizeFilter);
  else filtered = filtered.filter((row) => sizeFilter(row) || companySize === "flexible");

  if (isDealBreaker("country")) filtered = filtered.filter(countryFilter);
  else if (country !== "Global" && country !== "Remote-first") {
    filtered = filtered.filter(countryFilter);
  }

  const sortedKeys = Object.entries(preferences)
    .sort(([, a], [, b]) => a.priority - b.priority)
    .map(([key]) => key);

  const topPriority = sortedKeys[0];
  if (topPriority === "country" || preferences.country?.priority <= 2) {
    filtered = [...filtered].sort((a, b) => b.salaryMedian - a.salaryMedian);
  } else if (topPriority === "domain" || topPriority === "title") {
    filtered = [...filtered].sort((a, b) => b.jobCount - a.jobCount);
  }

  const topMarkets = filtered.slice(0, 5);
  const experienceBonus = { entry: 0, mid: 4, senior: 8, flexible: 2 }[experienceLevel] ?? 0;
  const educationBonus = { bachelor: 0, master: 4, phd: 8, flexible: 2 }[educationLevel] ?? 0;

  const topJobs = [];
  roles.forEach((role, ri) => {
    topMarkets.slice(0, 2).forEach((market, mi) => {
      if (topJobs.length < 5) {
        let match = Math.max(72, 96 - ri * 6 - mi * 4) + experienceBonus + educationBonus;
        if (isDealBreaker("title") && role !== title) match -= 25;
        if (isDealBreaker("experience_level") && experienceLevel === "senior") match += 5;
        topJobs.push({
          title: role,
          country: market.country,
          salary: market.salaryMedian,
          match: Math.min(99, match),
          industry,
        });
      }
    });
  });
  while (topJobs.length < 5 && roles.length) {
    topJobs.push({
      title: roles[topJobs.length % roles.length],
      country: topMarkets[0]?.country || "Germany",
      salary: topMarkets[0]?.salaryMedian || 90000,
      match: 80 - topJobs.length * 3,
      industry,
    });
  }

  const salaryByCountry = [...aggregateSalariesByCountry(industryRows)]
    .sort((a, b) => b.salaryMedian - a.salaryMedian)
    .slice(0, 12)
    .map((d) => ({ ...d, coords: COUNTRY_COORDS[d.country] }))
    .filter((d) => d.coords);

  const industryBreakdown = industryRows
    .filter((r) => r.country === (topMarkets[0]?.country || "Germany"))
    .sort((a, b) => b.jobCount - a.jobCount)
    .slice(0, 6);

  const roleFit = roles.map((role, i) => ({
    role,
    score: Math.min(98, 92 - i * 8 + experienceBonus + (topMarkets.length > 0 ? 4 : 0)),
  }));

  const salaryComparison = buildSalaryComparison(insightMatches, domainLabel, country);
  const riskProfile = buildRiskProfile(insightMatches);
  const skillSet = buildSkillSet(insightMatches);
  const sentimentProfile = buildSentimentProfile(insightMatches);
  const topClubs = buildTumClubFallback(tumExperienceRows, {
    domain: domainLabel,
    industry,
    skillSet,
  });
  const decisionSummary = buildDecisionSummary({
    title,
    domain: domainLabel,
    country,
    salaryComparison,
    riskProfile,
    sentimentProfile,
    skillSet,
  });

  const dealBreakerList = Object.entries(preferences)
    .filter(([, p]) => p.dealBreaker)
    .map(([key]) => PREFERENCE_LABELS_EXPORT[key] || key);

  const trends = [
    {
      label: "Top priority",
      value: `${PREFERENCE_LABELS_EXPORT[sortedKeys[0]] || sortedKeys[0]}: ${preferences[sortedKeys[0]]?.data}`,
    },
    {
      label: "Deal breakers",
      value: dealBreakerList.length ? dealBreakerList.join(", ") : "None set",
    },
    {
      label: "Target role",
      value: `${title} · ${domainLabel}`,
    },
    {
      label: "Work format",
      value: workFormat || workMode.replace(/^[^\s]+\s/, ""),
    },
  ];

  return {
    roles,
    topMarkets,
    topClubs,
    topJobs,
    trends,
    salaryByCountry,
    salaryComparison,
    riskProfile,
    skillSet,
    sentimentProfile,
    decisionSummary,
    industryBreakdown,
    roleFit,
    domain: domainKey,
    industry,
    userProfile,
    summary: `Prioritizing ${preferences[sortedKeys[0]]?.data} with ${dealBreakerList.length ? dealBreakerList.length + " deal breaker(s)" : "flexible filters"} for ${title} roles in ${domainLabel}.`,
    pills: sortedKeys.map((key) => {
      const p = preferences[key];
      const tag = p.dealBreaker ? " ⚡" : "";
      return `${PREFERENCE_LABELS_EXPORT[key]}: ${p.data}${tag}`;
    }),
  };
}

const PREFERENCE_LABELS_EXPORT = {
  title: "Title",
  domain: "Domain",
  country: "Country",
  company_size: "Company size",
  work_format: "Work format",
  experience_level: "Experience",
  education_level: "Education",
};

function selectInsightRows(insightRows, { domain, country, industry }) {
  if (!insightRows.length) return [];

  const countrySet =
    country === "European Union"
      ? new Set(EU_COUNTRIES_IN_DATA)
      : country && country !== "Global"
        ? new Set([country])
        : null;

  const exact = insightRows.filter(
    (row) =>
      row.specialization === domain &&
      (!countrySet || countrySet.has(row.country)) &&
      (!industry || row.industry === industry),
  );
  if (exact.length) return exact;

  const domainOnly = insightRows.filter(
    (row) => row.specialization === domain && (!countrySet || countrySet.has(row.country)),
  );
  if (domainOnly.length) return domainOnly;

  return insightRows.filter((row) => row.specialization === domain);
}

function weightedAverage(rows, valueKey) {
  const usable = rows.filter((row) => Number.isFinite(row[valueKey]) && row.jobCount > 0);
  const weight = usable.reduce((sum, row) => sum + row.jobCount, 0);
  if (!weight) return 0;
  return usable.reduce((sum, row) => sum + row[valueKey] * row.jobCount, 0) / weight;
}

function buildSalaryComparison(rows, domain, country) {
  const byCountry = new Map();
  rows.forEach((row) => {
    if (!Number.isFinite(row.salaryMedianEur)) return;
    const current = byCountry.get(row.country) ?? { salaries: [], jobs: 0 };
    current.salaries.push(row.salaryMedianEur);
    current.jobs += row.jobCount;
    byCountry.set(row.country, current);
  });

  const countries = [...byCountry.entries()]
    .map(([name, data]) => ({
      country: name,
      salaryMedian: Math.round(data.salaries.reduce((sum, v) => sum + v, 0) / data.salaries.length),
      jobCount: data.jobs,
    }))
    .sort((a, b) => b.salaryMedian - a.salaryMedian)
    .slice(0, 6);

  const selected =
    country && country !== "Global" && country !== "European Union"
      ? countries.find((item) => item.country === country)
      : countries[0];

  return {
    title: `${domain || "AI"} salary comparison`,
    selectedCountry: selected?.country ?? country ?? "Global",
    selectedMedian: selected?.salaryMedian ?? countries[0]?.salaryMedian ?? 0,
    countries,
  };
}

function buildRiskProfile(rows) {
  const score = weightedAverage(rows, "riskScore");
  const labelCounts = rows.reduce((counts, row) => {
    if (row.riskLabel) counts[row.riskLabel] = (counts[row.riskLabel] ?? 0) + row.jobCount;
    return counts;
  }, {});
  const label =
    Object.entries(labelCounts).sort(([, a], [, b]) => b - a)[0]?.[0] ??
    (score >= 6.5 ? "High Risk" : score >= 4 ? "Medium Risk" : "Low Risk");

  return {
    score: Math.round(score * 10),
    rawScore: Number(score.toFixed(1)),
    label,
    description: "Dataset signal from layoffs, industry risk, job security and company context.",
  };
}

function buildSkillSet(rows) {
  const counts = new Map();
  rows.forEach((row) => {
    row.topSkills.forEach((skill, index) => {
      counts.set(skill, (counts.get(skill) ?? 0) + row.jobCount * (8 - index));
    });
  });
  return [...counts.entries()]
    .sort(([, a], [, b]) => b - a)
    .slice(0, 12)
    .map(([skill]) => skill);
}

function buildSentimentProfile(rows) {
  const score = weightedAverage(rows, "sentimentScore");
  const status =
    score >= 6.2
      ? "Very satisfied"
      : score >= 5.7
        ? "Satisfied"
        : score >= 5.1
          ? "Neutral"
          : score >= 4.5
            ? "Concerned"
            : "Unsatisfied";
  return {
    score: Number(score.toFixed(1)),
    status,
    emoji: score >= 5.7 ? "😊" : score >= 5.1 ? "😐" : "☹️",
    label: status,
  };
}

function buildTumClubFallback(tumExperienceRows, { domain, industry, skillSet }) {
  const targetSkills = new Set(skillSet.map((skill) => skill.toLowerCase()));
  const scored = tumExperienceRows.map((club) => {
    const specializationScore = club.specializations.some(
      (spec) => spec.toLowerCase() === domain.toLowerCase(),
    )
      ? 12
      : 0;
    const industryScore = club.industries.some((item) => item.toLowerCase() === industry.toLowerCase())
      ? 6
      : 0;
    const skillScore = club.skills.reduce(
      (sum, skill) => sum + (targetSkills.has(skill.toLowerCase()) ? 3 : 0),
      0,
    );
    return { ...club, score: specializationScore + industryScore + skillScore };
  });

  return scored
    .sort((a, b) => b.score - a.score || b.skills.length - a.skills.length)
    .slice(0, 5)
    .map((club) => ({
      name: club.name,
      skills: club.skills.slice(0, 6),
      description: club.specializations.length
        ? `Relevant for ${club.specializations.slice(0, 3).join(", ")}.`
        : "Relevant TUM experience based on your skill profile.",
    }));
}

function buildDecisionSummary({
  title,
  domain,
  country,
  salaryComparison,
  riskProfile,
  sentimentProfile,
  skillSet,
}) {
  const topSkills = skillSet.slice(0, 4).join(", ");
  return `${title} in ${domain} looks strongest around ${salaryComparison.selectedCountry || country}, with a median salary signal of €${Math.round(salaryComparison.selectedMedian || 0).toLocaleString()}. The dataset suggests ${riskProfile.label?.toLowerCase() || "medium risk"} and ${sentimentProfile.label?.toLowerCase() || "mixed"} employee sentiment, so focus your next step on ${topSkills || "the top matched skills"} while comparing companies carefully.`;
}

function aggregateSalariesByCountry(industryRows) {
  const countrySalaries = {};
  industryRows.forEach((row) => {
    if (!countrySalaries[row.country]) countrySalaries[row.country] = { medians: [], jobs: 0 };
    countrySalaries[row.country].medians.push(row.salaryMedian);
    countrySalaries[row.country].jobs += row.jobCount;
  });
  return Object.entries(countrySalaries).map(([country, data]) => ({
    country,
    salaryMedian: Math.round(data.medians.reduce((s, v) => s + v, 0) / data.medians.length),
    jobCount: data.jobs,
  }));
}
