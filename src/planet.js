import * as d3 from "d3";

const LAND_URL =
  "https://raw.githubusercontent.com/martynafford/natural-earth-geojson/refs/heads/master/110m/physical/ne_110m_land.json";

const TUM = { r: 0, g: 101, b: 189 };

function salaryColor(median, min = 25000, max = 150000) {
  const t = Math.max(0, Math.min(1, (median - min) / (max - min)));
  const r = Math.round(TUM.r + t * 60);
  const g = Math.round(TUM.g + t * 80);
  const b = Math.round(TUM.b + t * 50);
  return `rgb(${r}, ${g}, ${b})`;
}

function pointInPolygon(point, polygon) {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function pointInFeature(point, feature) {
  const { geometry } = feature;
  if (geometry.type === "Polygon") {
    if (!pointInPolygon(point, geometry.coordinates[0])) return false;
    for (let i = 1; i < geometry.coordinates.length; i++) {
      if (pointInPolygon(point, geometry.coordinates[i])) return false;
    }
    return true;
  }
  if (geometry.type === "MultiPolygon") {
    for (const polygon of geometry.coordinates) {
      if (pointInPolygon(point, polygon[0])) {
        for (let i = 1; i < polygon.length; i++) {
          if (pointInPolygon(point, polygon[i])) return false;
        }
        return true;
      }
    }
  }
  return false;
}

function generateDotsInPolygon(feature, dotSpacing = 18) {
  const dots = [];
  const bounds = d3.geoBounds(feature);
  const [[minLng, minLat], [maxLng, maxLat]] = bounds;
  const stepSize = dotSpacing * 0.08;
  for (let lng = minLng; lng <= maxLng; lng += stepSize) {
    for (let lat = minLat; lat <= maxLat; lat += stepSize) {
      if (pointInFeature([lng, lat], feature)) dots.push([lng, lat]);
    }
  }
  return dots;
}

function isVisible(lng, lat, rotation) {
  return d3.geoDistance([lng, lat], [-rotation[0], -rotation[1]]) < Math.PI / 2;
}

export function initPlanet(container, tooltip, globeCountries) {
  container.innerHTML = "";

  const canvas = document.createElement("canvas");
  canvas.className = "globe-canvas";
  container.appendChild(canvas);

  const loading = document.createElement("div");
  loading.className = "globe-loading";
  loading.textContent = "Loading globe…";
  container.appendChild(loading);

  const context = canvas.getContext("2d");
  if (!context) return;

  let containerWidth = 0;
  let containerHeight = 0;
  let radius = 0;
  let landFeatures = null;
  const allDots = [];
  const rotation = [0, -18];
  let autoRotate = true;
  const rotationSpeed = 0.35;
  let projection = null;
  let path = null;
  let animationTimer = null;
  let hoveredCountry = null;

  function setupDimensions() {
    containerWidth = container.clientWidth || 640;
    containerHeight = container.clientHeight || 480;
    radius = Math.min(containerWidth, containerHeight) / 2.35;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = `${containerHeight}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    projection = d3
      .geoOrthographic()
      .scale(radius)
      .translate([containerWidth / 2, containerHeight / 2])
      .clipAngle(90)
      .rotate(rotation);
    path = d3.geoPath().projection(projection).context(context);
  }

  function render() {
    if (!projection) return;
    context.clearRect(0, 0, containerWidth, containerHeight);
    const currentScale = projection.scale();
    const scaleFactor = currentScale / radius;

    context.beginPath();
    context.arc(containerWidth / 2, containerHeight / 2, currentScale, 0, 2 * Math.PI);
    context.fillStyle = "rgba(0, 20, 45, 0.85)";
    context.fill();
    context.strokeStyle = "rgba(0, 101, 189, 0.45)";
    context.lineWidth = 1.5 * scaleFactor;
    context.stroke();

    if (!landFeatures) return;

    const graticule = d3.geoGraticule10();
    context.beginPath();
    path(graticule);
    context.strokeStyle = "rgba(0, 101, 189, 0.15)";
    context.lineWidth = 0.6 * scaleFactor;
    context.stroke();

    context.beginPath();
    landFeatures.features.forEach((f) => path(f));
    context.strokeStyle = "rgba(100, 160, 200, 0.35)";
    context.lineWidth = 0.8 * scaleFactor;
    context.stroke();

    allDots.forEach(([lng, lat]) => {
      if (!isVisible(lng, lat, rotation)) return;
      const projected = projection([lng, lat]);
      if (!projected) return;
      context.beginPath();
      context.arc(projected[0], projected[1], 1 * scaleFactor, 0, 2 * Math.PI);
      context.fillStyle = "rgba(100, 160, 200, 0.55)";
      context.fill();
    });

    globeCountries.forEach((country) => {
      const { lon, lat } = country.coords;
      if (!isVisible(lon, lat, rotation)) return;
      const projected = projection([lon, lat]);
      if (!projected) return;

      const markerR = (4 + (country.jobCount / 6000) * 2.5) * scaleFactor;
      const hovered = hoveredCountry === country;
      const [x, y] = projected;

      context.beginPath();
      context.arc(x, y, markerR, 0, 2 * Math.PI);
      context.fillStyle = salaryColor(country.salaryMedian);
      context.fill();
      context.strokeStyle = hovered ? "#fff" : "rgba(255,255,255,0.6)";
      context.lineWidth = (hovered ? 2 : 1) * scaleFactor;
      context.stroke();
    });
  }

  function findCountryAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const scaleFactor = projection.scale() / radius;
    let closest = null;
    let closestDist = Infinity;

    globeCountries.forEach((country) => {
      const { lon, lat } = country.coords;
      if (!isVisible(lon, lat, rotation)) return;
      const projected = projection([lon, lat]);
      if (!projected) return;
      const markerR = (4 + (country.jobCount / 6000) * 2.5) * scaleFactor + 10;
      const dist = Math.hypot(projected[0] - x, projected[1] - y);
      if (dist <= markerR && dist < closestDist) {
        closest = country;
        closestDist = dist;
      }
    });
    return closest;
  }

  function showTooltip(country, clientX, clientY) {
    const rect = container.getBoundingClientRect();
    const top = country.topIndustry;
    tooltip.classList.remove("hidden");
    tooltip.classList.add("visible");
    tooltip.innerHTML = `<strong>${country.country}</strong><br>Median: $${country.salaryMedian.toLocaleString()}<br>Jobs: ${country.jobCount.toLocaleString()}${top ? `<br>Top: ${top.industry}` : ""}`;
    tooltip.style.left = `${clientX - rect.left + 12}px`;
    tooltip.style.top = `${clientY - rect.top + 12}px`;
  }

  function handlePointerMove(event) {
    const country = findCountryAt(event.clientX, event.clientY);
    canvas.style.cursor = country ? "pointer" : "grab";
    if (country !== hoveredCountry) {
      hoveredCountry = country;
      if (country) showTooltip(country, event.clientX, event.clientY);
      else {
        tooltip.classList.add("hidden");
        tooltip.classList.remove("visible");
      }
      render();
    } else if (country) {
      showTooltip(country, event.clientX, event.clientY);
    }
  }

  function handleMouseDown(event) {
    autoRotate = false;
    canvas.style.cursor = "grabbing";
    const startX = event.clientX;
    const startY = event.clientY;
    const startRotation = [...rotation];

    const onMove = (e) => {
      rotation[0] = startRotation[0] + (e.clientX - startX) * 0.45;
      rotation[1] = startRotation[1] - (e.clientY - startY) * 0.45;
      rotation[1] = Math.max(-60, Math.min(60, rotation[1]));
      projection.rotate(rotation);
      render();
      handlePointerMove(e);
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      canvas.style.cursor = hoveredCountry ? "pointer" : "grab";
      setTimeout(() => { autoRotate = true; }, 1200);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  async function loadWorldData() {
    try {
      const res = await fetch(LAND_URL);
      if (!res.ok) throw new Error();
      landFeatures = await res.json();
      landFeatures.features.forEach((f) => {
        generateDotsInPolygon(f, 18).forEach(([lng, lat]) => allDots.push([lng, lat]));
      });
      loading.remove();
      render();
    } catch {
      loading.textContent = "Could not load globe";
    }
  }

  setupDimensions();
  animationTimer = d3.timer(() => {
    if (autoRotate) {
      rotation[0] += rotationSpeed;
      projection.rotate(rotation);
    }
    render();
  });

  canvas.addEventListener("mousedown", handleMouseDown);
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    projection.scale(Math.max(radius * 0.65, Math.min(radius * 2.2, projection.scale() * factor)));
    render();
  }, { passive: false });
  canvas.addEventListener("mousemove", handlePointerMove);
  canvas.addEventListener("mouseleave", () => {
    hoveredCountry = null;
    tooltip.classList.add("hidden");
    tooltip.classList.remove("visible");
    canvas.style.cursor = "grab";
    render();
  });

  new ResizeObserver(() => setupDimensions()).observe(container);
  loadWorldData();
}
