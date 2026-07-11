import { getAnswer, ROLE_BY_DOMAIN } from "./dataService.js";

export const PREFERENCE_KEYS = [
  "title",
  "domain",
  "country",
  "company_size",
  "work_format",
  "experience_level",
  "education_level",
];

export const PREFERENCE_LABELS = {
  title: "Job title",
  domain: "Domain",
  country: "Country / region",
  company_size: "Company size",
  work_format: "Work format",
  experience_level: "Experience level",
  education_level: "Education",
};

function stripEmoji(value) {
  return value.replace(/^[^\s]+\s*/, "").trim();
}

export function answersToPreferenceValues(answers) {
  const jobDomain = getAnswer(answers, "jobDomain");
  const roles = ROLE_BY_DOMAIN[jobDomain] || ["ML Engineer"];

  const countryByRelocate = {
    "🇩🇪 Germany only": "Germany",
    "🇪🇺 EU countries (in data)": "European Union",
    "🌍 Global": "Global",
    "💻 Remote-first anywhere": "Remote-first",
  };

  // Keys match the 5 real company_size_category tiers from the cleaning
  // pipeline (Micro <25 / Startup 25-200 / Small-Mid 200-500 /
  // Mid-sized 500-5,000 / Mega 5,000+), plus a "flexible" no-preference option.
  const sizeByAnswer = {
    "🌱 Micro (under 25 people)": "micro",
    "🚀 Startup (25–200)": "startup",
    "📈 Small-Mid (200–500)": "small_mid",
    "🏢 Mid-sized (500–5,000)": "mid_sized",
    "🏛️ Mega Corporation (5,000+)": "mega",
    "🔀 Flexible on company size": "flexible",
  };

  const formatByAnswer = {
    "🏢 Mostly on-site": "onsite",
    "🔁 Hybrid": "hybrid",
    "🏠 Fully remote": "remote",
    "🧩 Flexible by project": "flexible",
  };

  // Only 3 real experience levels exist in the data (Entry/Mid/Senior) —
  // "Lead/Principal" was dropped since it doesn't exist as a category.
  const experienceByAnswer = {
    "🌱 Entry": "entry",
    "📈 Mid-level": "mid",
    "🎯 Senior": "senior",
    "🔀 Flexible": "flexible",
  };

  const educationByAnswer = {
    "🎓 Bachelor": "bachelor",
    "📘 Master (TUM)": "master",
    "🔬 PhD": "phd",
    "📚 Flexible": "flexible",
  };

  const relocate = getAnswer(answers, "relocate");
  const workMode = getAnswer(answers, "workMode");
  const companySize = getAnswer(answers, "companySize");
  const experience = getAnswer(answers, "experienceLevel");
  const education = getAnswer(answers, "educationLevel");

  return {
    title: roles[0],
    // Domain label is now derived directly from the real AI Specialization
    // value (emoji stripped), since quiz options match the dataset exactly —
    // no separate lookup dict needed for this one.
    domain: stripEmoji(jobDomain) || "Technology",
    country: countryByRelocate[relocate] || stripEmoji(relocate),
    company_size: sizeByAnswer[companySize] || "flexible",
    work_format: formatByAnswer[workMode] || "flexible",
    experience_level: experienceByAnswer[experience] || "mid",
    education_level: educationByAnswer[education] || "master",
  };
}

export function buildUserProfile(answers, orderedKeys, dealBreakers) {
  const values = answersToPreferenceValues(answers);
  const preferences = {};

  orderedKeys.forEach((key, index) => {
    preferences[key] = {
      data: values[key],
      dealBreaker: Boolean(dealBreakers[key]),
      priority: index + 1,
    };
  });

  return {
    version: 1,
    createdAt: new Date().toISOString(),
    answers,
    preferences,
  };
}

export function formatProfileForApi(preferences) {
  const output = {};
  Object.entries(preferences).forEach(([key, pref]) => {
    output[key] = {
      data: pref.data,
      dealBreaker: pref.dealBreaker,
    };
  });
  return output;
}