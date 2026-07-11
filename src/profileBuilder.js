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
  const roles = ROLE_BY_DOMAIN[jobDomain] || ["AI Engineer"];

  const domainByJob = {
    "🤖 AI Engineering": "Generative AI",
    "📊 Data Science": "Data Science",
    "🧭 Product and Strategy": "Product & Strategy",
    "⚙️ MLOps / Infrastructure": "MLOps & Infrastructure",
  };

  const countryByRelocate = {
    "🇩🇪 Germany only": "Germany",
    "🇪🇺 EU wide": "European Union",
    "🌍 Global": "Global",
    "💻 Remote-first anywhere": "Remote-first",
  };

  const sizeByAnswer = {
    "🌱 Startup vibe (under 200 people)": "startup",
    "🚀 Scaling team (200–2,000)": "mid",
    "🏢 Established corporation (2,000+)": "enterprise",
    "🔀 Flexible on company size": "flexible",
  };

  const formatByAnswer = {
    "🏢 Mostly on-site": "onsite",
    "🔁 Hybrid": "hybrid",
    "🏠 Fully remote": "remote",
    "🧩 Flexible by project": "flexible",
  };

  const experienceByAnswer = {
    "🌱 Junior / Entry": "junior",
    "📈 Mid-level": "mid",
    "🎯 Senior": "senior",
    "🔬 Lead / Principal": "lead",
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
    domain: domainByJob[jobDomain] || "Technology",
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
