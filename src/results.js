import { jsPDF } from "jspdf";
import html2canvas from "html2canvas";
import careerOrbitLogo from "./assets/career-orbit-logo.svg";
import { renderSalaryChart, renderIndustryChart, renderRoleFitChart } from "./charts.js";
import { initSalaryMap } from "./salaryMap.js";

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
        <div class="club-hover-panel">
          ${club.skills.map((s) => `<span class="skill-tag">${s}</span>`).join("")}
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
          <span>$${job.salary.toLocaleString()} / yr</span>
          <span>${job.industry}</span>
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

  const trendsHtml = recommendations.trends
    .map((t) => `<li><strong>${t.label}</strong><span>${t.value}</span></li>`)
    .join("");

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
        <p class="block-sub">Hover for skills</p>
        <div class="clubs-grid">${clubsHtml}</div>
      </section>

      <section class="glass results-panel compact-panel">
        <h3>Top 5 Job Matches</h3>
        <p class="block-sub">Hover for details</p>
        <div class="jobs-grid">${jobsHtml}</div>
      </section>
    </div>

    <section class="glass market-section compact-section fade-up" style="animation-delay:140ms">
      <h3>Global markets</h3>
      <div class="market-detail-grid">${marketsDetailHtml}</div>

      <div class="salary-map-wrap glass-inner">
        <div id="salaryDotsMap" class="salary-dots-map"></div>
        <div id="salaryMapTooltip" class="map-tooltip"></div>
      </div>

      <div class="salary-chart-section">
        <h4>Salary comparison</h4>
        <div id="salaryChart" class="chart-host chart-host-sm"></div>
      </div>
    </section>

    <div class="results-charts fade-up" style="animation-delay:200ms">
      <section class="chart-card glass compact-panel">
        <h3>Industry volume</h3>
        <div id="industryChart" class="chart-host chart-host-sm"></div>
      </section>

      <section class="chart-card glass compact-panel">
        <h3>Role fit</h3>
        <div id="roleFitChart" class="chart-host chart-host-sm"></div>
      </section>
    </div>

    <section class="glass trends-section compact-section fade-up" style="animation-delay:260ms">
      <h3>Market signals</h3>
      <ul class="trend-list-modern">${trendsHtml}</ul>
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
    renderSalaryChart(document.querySelector("#salaryChart"), recommendations.salaryByCountry);
    renderIndustryChart(document.querySelector("#industryChart"), recommendations.industryBreakdown);
    renderRoleFitChart(document.querySelector("#roleFitChart"), recommendations.roleFit);
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
