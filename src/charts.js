import * as d3 from "d3";

const TUM_BLUE = "#0065BD";
const TUM_LIGHT = "#64A0C8";
const CHART_MUTED = "rgba(255, 255, 255, 0.42)";
const CHART_GRID = "rgba(0, 101, 189, 0.12)";

function baseSvg(container, height = 200) {
  d3.select(container).selectAll("*").remove();
  const width = container.clientWidth || 400;
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("class", "chart-svg");
  return { svg, width, height };
}

function truncate(value, max = 10) {
  const text = String(value);
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

/** Bar chart — best for comparing salary across countries */
export function renderSalaryChart(container, data) {
  const { svg, width, height } = baseSvg(container, 210);
  const margin = { top: 12, right: 12, bottom: 32, left: 44 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(data.map((d) => d.country)).range([0, innerW]).padding(0.28);
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.salaryMedian) * 1.1]).nice().range([innerH, 0]);

  const defs = svg.append("defs");
  const grad = defs.append("linearGradient").attr("id", "tumBarGrad").attr("x1", "0").attr("y1", "0").attr("x2", "0").attr("y2", "1");
  grad.append("stop").attr("offset", "0%").attr("stop-color", TUM_LIGHT).attr("stop-opacity", 0.9);
  grad.append("stop").attr("offset", "100%").attr("stop-color", TUM_BLUE).attr("stop-opacity", 0.55);

  g.selectAll("rect")
    .data(data)
    .join("rect")
    .attr("x", (d) => x(d.country))
    .attr("y", (d) => y(d.salaryMedian))
    .attr("width", x.bandwidth())
    .attr("height", (d) => innerH - y(d.salaryMedian))
    .attr("rx", 5)
    .attr("fill", "url(#tumBarGrad)")
    .attr("opacity", 0.88);

  g.append("g")
    .call(d3.axisLeft(y).ticks(4).tickSize(-innerW).tickFormat((d) => `$${d / 1000}k`))
    .call((a) => a.select(".domain").remove())
    .call((a) => a.selectAll(".tick line").attr("stroke", CHART_GRID))
    .selectAll("text")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 9);

  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(x).tickSize(0).tickFormat((d) => truncate(d, 3)))
    .call((a) => a.select(".domain").remove())
    .selectAll("text")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 9);
}

/** Horizontal bar — best for long industry labels */
export function renderIndustryChart(container, data) {
  const { svg, width, height } = baseSvg(container, Math.max(180, data.length * 32));
  const margin = { top: 8, right: 16, bottom: 8, left: 108 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const y = d3.scaleBand().domain(data.map((d) => d.industry)).range([0, innerH]).padding(0.22);
  const x = d3.scaleLinear().domain([0, d3.max(data, (d) => d.jobCount)]).nice().range([0, innerW]);

  g.selectAll("rect")
    .data(data)
    .join("rect")
    .attr("y", (d) => y(d.industry))
    .attr("x", 0)
    .attr("height", y.bandwidth())
    .attr("width", (d) => x(d.jobCount))
    .attr("rx", 4)
    .attr("fill", TUM_BLUE)
    .attr("fill-opacity", 0.55);

  g.append("g")
    .call(d3.axisLeft(y).tickSize(0).tickFormat((d) => truncate(d, 14)))
    .call((a) => a.select(".domain").remove())
    .selectAll("text")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 9);

  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(3).tickFormat((d) => `${Math.round(d / 1000)}k`))
    .call((a) => a.select(".domain").remove())
    .selectAll("text")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 9);
}

/** Donut — best for role fit proportions */
export function renderRoleFitChart(container, data) {
  const { svg, width, height } = baseSvg(container, 200);
  const margin = 12;
  const radius = Math.min(width, height) / 2 - margin;
  const g = svg.append("g").attr("transform", `translate(${width / 2},${height / 2})`);

  const pie = d3.pie().value((d) => d.score).sort(null).padAngle(0.04);
  const arc = d3.arc().innerRadius(radius * 0.62).outerRadius(radius);
  const colors = [TUM_BLUE, "#1a7fd4", TUM_LIGHT, "#4d8ec4"];

  const arcs = g
    .selectAll("path")
    .data(pie(data))
    .join("path")
    .attr("d", arc)
    .attr("fill", (_, i) => colors[i % colors.length])
    .attr("fill-opacity", 0.75)
    .attr("stroke", "rgba(255,255,255,0.15)")
    .attr("stroke-width", 1);

  g.append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "-0.1em")
    .attr("fill", "rgba(255,255,255,0.9)")
    .attr("font-size", 18)
    .attr("font-weight", 700)
    .text(`${Math.round(data.reduce((s, d) => s + d.score, 0) / data.length)}%`);

  g.append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "1.1em")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 9)
    .text("avg fit");

  const legend = svg
    .selectAll(".role-legend")
    .data(data)
    .join("text")
    .attr("class", "role-legend")
    .attr("x", width / 2)
    .attr("y", (_, i) => height - 8 - (data.length - 1 - i) * 12)
    .attr("text-anchor", "middle")
    .attr("fill", CHART_MUTED)
    .attr("font-size", 8)
    .text((d) => `${truncate(d.role, 16)} · ${d.score}%`);

  void legend;
  void arcs;
}
