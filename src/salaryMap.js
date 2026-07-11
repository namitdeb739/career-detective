import * as d3 from "d3";
import { feature } from "topojson-client";

const TUM_BLUE = "#0065BD";

/** Manual nudges for countries that cluster on the map */
const COUNTRY_NUDGE = {
  Germany: { x: 14, y: -16 },
  Netherlands: { x: -16, y: 12 },
  Belgium: { x: -8, y: 8 },
  Switzerland: { x: 6, y: 10 },
  France: { x: -10, y: -6 },
  Ireland: { x: -12, y: -8 },
  "United Kingdom": { x: 10, y: -10 },
};

function resolveCollisions(nodes, minDist = 48, iterations = 24) {
  for (let k = 0; k < iterations; k++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.hypot(dx, dy) || 0.01;
        if (dist < minDist) {
          const push = (minDist - dist) / 2;
          a.x -= (dx / dist) * push;
          a.y -= (dy / dist) * push;
          b.x += (dx / dist) * push;
          b.y += (dy / dist) * push;
        }
      }
    }
  }
  return nodes;
}

export function initSalaryMap(container, tooltipEl, countries) {
  d3.select(container).selectAll("*").remove();

  const width = container.clientWidth || 800;
  const height = Math.max(240, width * 0.38);

  const svg = d3
    .select(container)
    .append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("class", "salary-map-svg");

  const g = svg.append("g");
  const projection = d3.geoNaturalEarth1().fitSize([width - 32, height - 32], { type: "Sphere" });
  projection.translate([width / 2, height / 2]);
  const path = d3.geoPath(projection);

  const radiusScale = d3
    .scaleSqrt()
    .domain(d3.extent(countries, (d) => d.salaryMedian) || [50000, 150000])
    .range([4, 9]);

  d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json").then((world) => {
    const land = feature(world, world.objects.countries);

    g.append("path")
      .datum({ type: "Sphere" })
      .attr("d", path)
      .attr("fill", "rgba(0, 101, 189, 0.04)")
      .attr("stroke", "rgba(255, 255, 255, 0.06)");

    g.selectAll(".land-path")
      .data(land.features)
      .join("path")
      .attr("class", "land-path")
      .attr("d", path)
      .attr("fill", "rgba(255, 255, 255, 0.02)")
      .attr("stroke", "rgba(255, 255, 255, 0.07)")
      .attr("stroke-width", 0.35);

    const nodes = countries
      .filter((d) => d.coords)
      .map((d, i) => {
        const projected = projection([d.coords.lon, d.coords.lat]);
        if (!projected) return null;
        const nudge = COUNTRY_NUDGE[d.country] || { x: 0, y: 0 };
        return {
          ...d,
          x: projected[0] + nudge.x,
          y: projected[1] + nudge.y,
          labelAbove: i % 2 === 0,
        };
      })
      .filter(Boolean);

    resolveCollisions(nodes, 52, 30);

    const dots = g.selectAll(".salary-dot-group").data(nodes).join("g").attr("class", "salary-dot-group");

    dots.attr("transform", (d) => `translate(${d.x},${d.y})`);

    dots
      .append("circle")
      .attr("class", "salary-dot")
      .attr("r", (d) => radiusScale(d.salaryMedian))
      .attr("fill", TUM_BLUE)
      .attr("fill-opacity", 0.7)
      .attr("stroke", "rgba(255,255,255,0.55)")
      .attr("stroke-width", 1);

    dots
      .append("text")
      .attr("class", "salary-dot-label")
      .attr("y", (d) => {
        const r = radiusScale(d.salaryMedian);
        return d.labelAbove ? -r - 10 : r + 16;
      })
      .attr("text-anchor", "middle")
      .attr("fill", "rgba(255,255,255,0.85)")
      .attr("font-size", 8)
      .attr("font-weight", 600)
      .text((d) => `$${Math.round(d.salaryMedian / 1000)}k`);

    dots
      .append("text")
      .attr("class", "salary-dot-country")
      .attr("y", (d) => {
        const r = radiusScale(d.salaryMedian);
        return d.labelAbove ? r + 12 : -r - 6;
      })
      .attr("text-anchor", "middle")
      .attr("fill", "rgba(255,255,255,0.45)")
      .attr("font-size", 7)
      .text((d) => (d.country === "United States" ? "USA" : d.country.slice(0, 3)));

    dots
      .on("mouseenter", function onEnter(event, d) {
        d3.select(this).select(".salary-dot").attr("fill-opacity", 1).attr("r", radiusScale(d.salaryMedian) * 1.15);
        const bounds = container.getBoundingClientRect();
        tooltipEl.classList.add("visible");
        tooltipEl.innerHTML = `<strong>${d.country}</strong><br>$${d.salaryMedian.toLocaleString()} median`;
        tooltipEl.style.left = `${event.clientX - bounds.left + 10}px`;
        tooltipEl.style.top = `${event.clientY - bounds.top + 10}px`;
      })
      .on("mousemove", (event) => {
        const bounds = container.getBoundingClientRect();
        tooltipEl.style.left = `${event.clientX - bounds.left + 10}px`;
        tooltipEl.style.top = `${event.clientY - bounds.top + 10}px`;
      })
      .on("mouseleave", function onLeave(_, d) {
        d3.select(this).select(".salary-dot").attr("fill-opacity", 0.7).attr("r", radiusScale(d.salaryMedian));
        tooltipEl.classList.remove("visible");
      });
  });
}
