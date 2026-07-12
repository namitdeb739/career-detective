import { jsPDF } from "jspdf";
import html2canvas from "html2canvas";
import careerOrbitLogo from "./assets/career-orbit-logo.svg";
import { renderSalaryChart, renderIndustryChart } from "./charts.js";
import { initSalaryMap } from "./salaryMap.js";

const formatEur = (value) =>
  Number(value || 0).toLocaleString("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });

export function renderResultsPage(container, recommendations, userProfile = null) {
  const preferences = userProfile?.preferences ?? {};
  const sortedPrefs = Object.entries(preferences).sort(([, a], [, b]) => a.priority - b.priority);

  const inputsHtml = sortedPrefs.length
    ? sortedPrefs
        .map(
          ([key, pref]) =>
            `<span class="input-chip${pref.dealBreaker ? " dealbreaker-chip" : ""}"><span class="chip-rank">#${pref.priority}</span> ${pref.data}${pref.dealBreaker ? '<span class="chip-bolt">⚡</span>' : ""}</span>`,
        )
        .join("")
    : (recommendations.pills || [])
        .map((pill) => `<span class="input-chip">${pill}</span>`)
        .join("");

  const clubsHtml = recommendations.topClubs
    .map(
      (club, i) => `
      <article class="club-card glass">
        <div class="club-card-head">
          <span class="club-rank">${i + 1}</span>
          <h4>${club.name}</h4>
        </div>
        ${
          club.description
            ? `<p class="club-desc">${
                club.description.length > 180
                  ? `${club.description.slice(0, 180).trim()}…`
                  : club.description
              }</p>`
            : ""
        }
        <div class="club-skill-list">
          ${(club.skills || []).map((s) => `<span class="skill-tag">${s}</span>`).join("")}
        </div>
      </article>`,
    )
    .join("");

  const jobsHtml = recommendations.topJobs
    .map(
      (job, i) => `
      <article class="job-card glass">
        <div class="job-card-head">
          <span class="job-rank">#${i + 1}</span>
          <h4>${job.title}</h4>
        </div>
        <div class="job-hover-panel">
          <span class="job-match">${job.match}% match</span>
          <span>${job.country}</span>
          <span>${job.currency === "EUR" ? formatEur(job.salary) : `$${Number(job.salary || 0).toLocaleString()}`} / yr</span>
          <span>${job.industry}</span>
          ${job.risk != null ? `<span>Risk: ${Math.round(job.risk * 100)} / 100</span>` : ""}
          ${job.skills?.length ? `<span>${job.skills.slice(0, 3).join(" · ")}</span>` : ""}
        </div>
      </article>`,
    )
    .join("");

  const marketsDetailHtml = recommendations.topMarkets
    .map(
      (m) => `
      <article class="market-detail-card glass">
        <h4>${m.country}</h4>
        <p class="market-salary">$${Math.round(m.salaryMedian / 1000)}k</p>
        <p class="market-jobs">${m.jobCount.toLocaleString()} roles</p>
      </article>`,
    )
    .join("");

  const salaryComparison = recommendations.salaryComparison;
  const salaryChartData = salaryComparison?.countries?.length
    ? salaryComparison.countries
    : recommendations.salaryByCountry;
  const salarySummaryHtml = salaryComparison
    ? `
      <div class="salary-summary">
        <span>${salaryComparison.selectedCountry}</span>
        <strong>${formatEur(salaryComparison.selectedMedian)}</strong>
        <small>median salary from matched dataset slice</small>
      </div>`
    : "";

  const skillSetHtml = (recommendations.skillSet || [])
    .map((skill) => `<span class="insight-skill">${skill}</span>`)
    .join("");

  const risk = recommendations.riskProfile || {};
  const sentiment = recommendations.sentimentProfile || {};

  container.innerHTML = `
    <div class="inputs-float-card glass">
      <img class="inputs-float-icon" src="${careerOrbitLogo}" alt="" />
      <div class="inputs-float-body">
        <p class="inputs-float-title">Your inputs</p>
        <div class="inputs-float-chips">${inputsHtml}</div>
      </div>
    </div>

    <div class="results-top-row fade-up" style="animation-delay:80ms">
      <section class="glass results-panel compact-panel">
        <h3>Top 5 TUM Clubs</h3>
        <p class="block-sub">Skills are matched to your answers</p>
        <div class="clubs-grid">${clubsHtml}</div>
      </section>

      <section class="glass results-panel compact-panel">
        <h3>Top 5 Job Matches</h3>
        <p class="block-sub">Hover for details</p>
        <div class="jobs-grid">${jobsHtml}</div>
      </section>
    </div>

    <section class="glass insight-section compact-section fade-up" style="animation-delay:120ms">
      <h3>Dataset insights for your answers</h3>
      <div class="insight-grid">
        <article class="insight-card">
          <span class="insight-label">Risk score</span>
          <strong>${risk.score ?? 0}/100</strong>
          <p>${risk.label ?? "Not available"}</p>
          <div class="risk-meter"><span style="width:${Math.min(100, risk.score ?? 0)}%"></span></div>
        </article>
        <article class="insight-card sentiment-card">
          <span class="insight-label">Employee sentiment</span>
          <div class="sentiment-grade">
            <span class="sentiment-emoji">${sentiment.emoji ?? "😐"}</span>
            <strong>${sentiment.status ?? sentiment.label ?? "Neutral"}</strong>
          </div>
          <p>${sentiment.score ?? 0}/10 employee sentiment score</p>
          <div class="sentiment-scale"><span>☹️</span><span>😊</span></div>
        </article>
        <article class="insight-card skill-card">
          <span class="insight-label">Skill set</span>
          <div class="insight-skills">${skillSetHtml || "<span class='insight-muted'>No skills found</span>"}</div>
        </article>
      </div>
    </section>

    <div class="salary-industry-row fade-up" style="animation-delay:160ms">
      <section class="chart-card glass compact-panel salary-panel">
        <h4>Salary comparison</h4>
        ${salarySummaryHtml}
        <div id="salaryChart" class="chart-host chart-host-sm"></div>
      </section>

      <section class="chart-card glass compact-panel">
        <h3>Industry volume in selected market</h3>
        <div id="industryChart" class="chart-host chart-host-sm"></div>
      </section>
    </div>

    <section class="glass market-section compact-section fade-up" style="animation-delay:220ms">
      <h3>Global markets</h3>
      <p class="block-sub">Median salary and available roles by country</p>
      <div class="market-detail-grid">${marketsDetailHtml}</div>

      <div class="salary-map-wrap glass-inner">
        <div id="salaryDotsMap" class="salary-dots-map"></div>
        <div id="salaryMapTooltip" class="map-tooltip"></div>
      </div>
    </section>

    <section class="glass final-summary-section compact-section fade-up" style="animation-delay:280ms">
      <h3>Short summary</h3>
      <p>${recommendations.decisionSummary || recommendations.summary}</p>
    </section>

    <div class="results-actions fade-up" style="animation-delay:320ms">
      <button id="savePdfBtn" class="primary-btn">Save as PDF</button>
      <button id="backHomeBtn" class="ghost-btn">Back to home</button>
    </div>
  `;

  requestAnimationFrame(() => {
    initSalaryMap(
      document.querySelector("#salaryDotsMap"),
      document.querySelector("#salaryMapTooltip"),
      recommendations.salaryByCountry,
    );
    renderSalaryChart(document.querySelector("#salaryChart"), salaryChartData, "EUR");
    renderIndustryChart(document.querySelector("#industryChart"), recommendations.industryBreakdown);
  });
}

export async function saveResultsPdf(element) {
  const canvas = await html2canvas(element, {
    backgroundColor: "#000000",
    scale: 2,
  });
  const img = canvas.toDataURL("image/png");
  const pdf = new jsPDF("p", "mm", "a4");
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const ratio = Math.min(pageWidth / canvas.width, pageHeight / canvas.height);
  const w = canvas.width * ratio;
  const h = canvas.height * ratio;
  pdf.addImage(img, "PNG", (pageWidth - w) / 2, 10, w, h);
  pdf.save("career-orbit-results.pdf");
}
