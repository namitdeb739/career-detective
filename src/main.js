import "./style.css";
import tumLogo from "./assets/tum-logo.png";
import careerOrbitLogo from "./assets/career-orbit-logo.svg";
import { initAntigravity } from "./antigravity.js";
import { initPlanet } from "./planet.js";
import { loadMarketData, buildRecommendations } from "./dataService.js";
import { fetchJobMatches } from "./apiService.js";
import { renderResultsPage, saveResultsPdf } from "./results.js";
import {
  PREFERENCE_KEYS,
  PREFERENCE_LABELS,
  answersToPreferenceValues,
  buildUserProfile,
} from "./profileBuilder.js";

initAntigravity();

// Quiz options below are grounded in the actual dataset:
//   - relocate: "EU countries (in data)" = Germany, France, Netherlands,
//     Ireland only (the actual EU members present in the 12-country data —
//     Switzerland and UK are NOT in the EU and were fixed from a prior bug)
//   - salary: brackets approximate the real EUR salary distribution
//     (25th/median/75th percentile), not arbitrary round numbers
//   - jobDomain: the 7 real AI Specialization values from the dataset
//     (dropped "Product and Strategy", which doesn't exist as a category)
//   - companySize: the 5 real company_size_category tiers from the
//     cleaning pipeline (Micro/Startup/Small-Mid/Mid-sized/Mega)
//   - experienceLevel: only 3 real values exist (Entry/Mid/Senior) —
//     dropped "Lead/Principal", which isn't a category in the data
const quizQuestions = [
  {
    id: "relocate",
    title: "Where are you open to relocate?",
    subtitle: "Pick one option for your next 1-2 years.",
    options: ["🇩🇪 Germany", "🇪🇺 EU Countries", "🌍 Global",],
  },
  {
    id: "workMode",
    title: "What work format fits your lifestyle?",
    subtitle: "Your preferred rhythm matters.",
    options: ["🏢 On-site", "🔁 Hybrid", "🏠 Remote", "🧩 Flexible"],
  },
  {
    id: "jobDomain",
    title: "Most attractive AI specialization?",
    subtitle: "We'll map this to trend signals.",
    options: [
      "🤖 Machine Learning",
      "🧠 Deep Learning",
      "📊 Data Science",
      "💬 NLP",
      "👁️ Computer Vision",
      "✨ Generative AI",
      "⚙️ MLOps",
    ],
  },
  {
    id: "companySize",
    title: "What scale of work environment fits you best?",
    subtitle: "Think company size and company stage.",
    options: [
      "🌱 Micro (under 25 people)",
      "🚀 Startup (25–200)",
      "📈 Small-Mid (200–500)",
      "🏢 Mid-sized (500–5,000)",
      "🏛️ Mega Corporation (5,000+)",
      "🔀 Flexible on company size",
    ],
  },
  {
    id: "experienceLevel",
    title: "What experience level are you targeting?",
    subtitle: "Helps us match seniority expectations.",
    options: ["🌱 Entry", "📈 Mid-level", "🎯 Senior", "🔀 Flexible"],
  },
  {
    id: "educationLevel",
    title: "Highest education level?",
    subtitle: "TUM students often hold Master or PhD.",
    options: ["🎓 Bachelor", "📘 Master", "🔬 PhD"],
  },
];

let marketData = null;

const app = document.querySelector("#app");
app.innerHTML = `
  <header class="topbar glass">
    <button id="homeLogoBtn" class="brand-left" aria-label="Go to home">
      <span class="logo-orbit-wrap">
        <img class="co-mark" src="${careerOrbitLogo}" alt="Career Orbit logo" />
      </span>
      <span class="project-name">Career Orbit</span>
    </button>
    <div class="brand-right">
      <img class="tum-logo-img tum-logo-compact" src="${tumLogo}" alt="TUM logo" />
    </div>
  </header>

  <main>
    <section id="home" class="page active">
      <div class="hero-section">
        <div class="hero-intro">
          <span class="hero-badge">TUM Career Intelligence</span>
          <h1 class="hero-title-gradient">Your AI career,<br />mapped.</h1>
          <p class="hero-lead">Compare salaries worldwide and get a clear next step in one minute.</p>
          <button id="startQuizBtn" class="primary-btn hero-quiz-btn">Start quiz</button>
          <p class="tum-context">Made for TUM students exploring AI and tech careers.</p>
        </div>

        <div class="hero-globe-stage">
          <div id="planetCanvas" aria-label="Interactive career globe"></div>
          <div id="jobTooltip" class="job-tooltip hidden"></div>
        </div>
      </div>

      <div class="interact-hint" aria-hidden="true">
        <span>Interact</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"/></svg>
      </div>
    </section>

    <section id="resultsPage" class="page">
      <div id="resultsContent" class="results-content"></div>
    </section>
  </main>

  <div id="quizOverlay" class="quiz-overlay">
    <div class="overlay-blur"></div>
    <section class="quiz-shell glass">
      <button id="closeQuizBtn" class="close-quiz-btn" aria-label="Close quiz">✕</button>
      <div id="quizStep">
        <div class="quiz-head">
          <p id="progressText">Question 1 / 7</p>
          <div class="progress-track"><div id="progressBar"></div></div>
        </div>
        <div class="quiz-body">
          <h2 id="questionTitle"></h2>
          <p id="questionSubtitle"></p>
          <div id="answers" class="answers"></div>
          <div id="answerPulse" class="answer-pulse"></div>
        </div>
        <div class="quiz-foot">
          <button id="nextBtn" class="primary-btn" disabled>Next</button>
        </div>
      </div>
      <div id="priorityStep" class="priority-step hidden-step">
        <div class="quiz-head">
          <p>Final step</p>
          <div class="progress-track"><div style="width:100%"></div></div>
        </div>
        <div class="quiz-body">
          <h2>Rank your priorities</h2>
          <p class="priority-sub">Order matters — top = most important. Toggle ⚡ for deal breakers (hard filters).</p>
          <div id="priorityList" class="priority-list"></div>
        </div>
        <div class="quiz-foot">
          <button id="priorityDoneBtn" class="primary-btn">Continue</button>
        </div>
      </div>
      <div id="quizCompleteStep" class="quiz-complete hidden-step">
        <h2>Quiz complete</h2>
        <p>Your profile is ready. Open your personalized career dashboard.</p>
        <button id="viewResultsBtn" class="primary-btn">View results</button>
      </div>
    </section>
  </div>
`;

const state = {
  currentQuestion: 0,
  selectedAnswers: [],
  selectedOption: null,
  userProfile: null,
  priorityOrder: [...PREFERENCE_KEYS],
  dealBreakers: {
    title: true,
    domain: false,
    country: true,
    company_size: false,
    work_format: false,
    experience_level: true,
    education_level: false,
  },
};

const homePage = document.querySelector("#home");
const resultsPage = document.querySelector("#resultsPage");
const overlay = document.querySelector("#quizOverlay");
const quizStep = document.querySelector("#quizStep");
const priorityStep = document.querySelector("#priorityStep");
const quizCompleteStep = document.querySelector("#quizCompleteStep");
const questionTitle = document.querySelector("#questionTitle");
const questionSubtitle = document.querySelector("#questionSubtitle");
const answersEl = document.querySelector("#answers");
const progressText = document.querySelector("#progressText");
const progressBar = document.querySelector("#progressBar");
const nextBtn = document.querySelector("#nextBtn");
const answerPulse = document.querySelector("#answerPulse");
const priorityList = document.querySelector("#priorityList");

function goHome() {
  homePage.classList.add("active");
  resultsPage.classList.remove("active");
  closeQuizOverlay();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function openResultsPage() {
  const recommendations = buildRecommendations(state.userProfile, marketData.industryRows);

  const viewResultsBtn = document.querySelector("#viewResultsBtn");
  viewResultsBtn.disabled = true;
  viewResultsBtn.textContent = "Finding matches…";
  try {
    const jobs = await fetchJobMatches(state.userProfile, 5);
    if (jobs.length) recommendations.topJobs = jobs;
  } catch (err) {
    console.warn("Job match API unavailable, using client-side estimate:", err);
  } finally {
    viewResultsBtn.disabled = false;
    viewResultsBtn.textContent = "View results";
  }

  const resultsContent = document.querySelector("#resultsContent");
  renderResultsPage(resultsContent, recommendations, state.userProfile);
  closeQuizOverlay();
  homePage.classList.remove("active");
  resultsPage.classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });

  document.querySelector("#savePdfBtn").addEventListener("click", () => {
    saveResultsPdf(resultsContent);
  });
  document.querySelector("#backHomeBtn").addEventListener("click", goHome);
}

function openQuizOverlay() {
  overlay.classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeQuizOverlay() {
  overlay.classList.remove("open");
  document.body.style.overflow = "";
}

function triggerPulse() {
  answerPulse.classList.remove("active");
  void answerPulse.offsetWidth;
  answerPulse.classList.add("active");
}

function renderQuestion() {
  const q = quizQuestions[state.currentQuestion];
  questionTitle.textContent = q.title;
  questionSubtitle.textContent = q.subtitle;
  questionTitle.classList.remove("question-in");
  void questionTitle.offsetWidth;
  questionTitle.classList.add("question-in");
  progressText.textContent = `Question ${state.currentQuestion + 1} / ${quizQuestions.length}`;
  progressBar.style.width = `${((state.currentQuestion + 1) / quizQuestions.length) * 100}%`;
  nextBtn.disabled = true;
  state.selectedOption = null;
  answersEl.innerHTML = "";

  q.options.forEach((option, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "answer-btn";
    btn.style.animationDelay = `${index * 60}ms`;
    btn.textContent = option;
    btn.addEventListener("click", () => {
      document.querySelectorAll(".answer-btn").forEach((x) => x.classList.remove("selected"));
      btn.classList.add("selected");
      state.selectedOption = option;
      nextBtn.disabled = false;
      triggerPulse();
    });
    answersEl.appendChild(btn);
  });
}

function movePriority(index, direction) {
  const target = index + direction;
  if (target < 0 || target >= state.priorityOrder.length) return;
  const order = [...state.priorityOrder];
  [order[index], order[target]] = [order[target], order[index]];
  state.priorityOrder = order;
  renderPriorityStep();
}

function renderPriorityStep() {
  const values = answersToPreferenceValues(state.selectedAnswers);
  priorityList.innerHTML = "";

  state.priorityOrder.forEach((key, index) => {
    const row = document.createElement("div");
    row.className = "priority-row";
    row.innerHTML = `
      <span class="priority-rank">${index + 1}</span>
      <div class="priority-info">
        <span class="priority-label">${PREFERENCE_LABELS[key]}</span>
        <span class="priority-value">${values[key]}</span>
      </div>
      <div class="priority-actions">
        <button type="button" class="priority-move" data-dir="-1" aria-label="Move up">↑</button>
        <button type="button" class="priority-move" data-dir="1" aria-label="Move down">↓</button>
        <button type="button" class="dealbreaker-toggle ${state.dealBreakers[key] ? "active" : ""}" aria-label="Deal breaker" title="Deal breaker">
          ⚡
        </button>
      </div>
    `;

    row.querySelectorAll(".priority-move").forEach((btn) => {
      btn.addEventListener("click", () => movePriority(index, Number(btn.dataset.dir)));
    });

    row.querySelector(".dealbreaker-toggle").addEventListener("click", (e) => {
      state.dealBreakers[key] = !state.dealBreakers[key];
      e.currentTarget.classList.toggle("active", state.dealBreakers[key]);
    });

    priorityList.appendChild(row);
  });
}

function showPriorityStep() {
  quizStep.classList.add("hidden-step");
  priorityStep.classList.remove("hidden-step");
  renderPriorityStep();
}

function finishQuiz() {
  state.userProfile = buildUserProfile(
    state.selectedAnswers,
    state.priorityOrder,
    state.dealBreakers,
  );

  priorityStep.classList.add("hidden-step");
  quizCompleteStep.classList.remove("hidden-step");
}

function nextQuestion() {
  if (!state.selectedOption) return;
  const q = quizQuestions[state.currentQuestion];
  state.selectedAnswers.push({ id: q.id, value: state.selectedOption });
  if (state.currentQuestion === quizQuestions.length - 1) {
    showPriorityStep();
    return;
  }
  state.currentQuestion += 1;
  renderQuestion();
}

function resetQuiz() {
  state.currentQuestion = 0;
  state.selectedAnswers = [];
  state.selectedOption = null;
  state.userProfile = null;
  state.priorityOrder = [...PREFERENCE_KEYS];
  state.dealBreakers = {
    title: true,
    domain: false,
    country: true,
    company_size: false,
    work_format: false,
    experience_level: true,
    education_level: false,
  };
  quizStep.classList.remove("hidden-step");
  priorityStep.classList.add("hidden-step");
  quizCompleteStep.classList.add("hidden-step");
  renderQuestion();
}

document.querySelector("#homeLogoBtn").addEventListener("click", goHome);
document.querySelector("#closeQuizBtn").addEventListener("click", closeQuizOverlay);
document.querySelector("#nextBtn").addEventListener("click", nextQuestion);
document.querySelector("#priorityDoneBtn").addEventListener("click", finishQuiz);
document.querySelector("#viewResultsBtn").addEventListener("click", openResultsPage);

overlay.addEventListener("click", (event) => {
  if (event.target === overlay || event.target.classList.contains("overlay-blur")) {
    closeQuizOverlay();
  }
});

function startQuiz() {
  openQuizOverlay();
  resetQuiz();
}

document.querySelector("#startQuizBtn").addEventListener("click", startQuiz);

loadMarketData().then((data) => {
  marketData = data;
  initPlanet(
    document.querySelector("#planetCanvas"),
    document.querySelector("#jobTooltip"),
    data.globeCountries,
  );
});
