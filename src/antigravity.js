const PARTICLE_DENSITY = 0.00012;
const BG_PARTICLE_DENSITY = 0.00004;
const MOUSE_RADIUS = 180;
const RETURN_SPEED = 0.08;
const DAMPING = 0.9;
const REPULSION_STRENGTH = 1.2;

const randomRange = (min, max) => Math.random() * (max - min) + min;

export function initAntigravity() {
  const root = document.createElement("div");
  root.className = "antigravity-root";
  const canvas = document.createElement("canvas");
  canvas.className = "antigravity-canvas";
  root.appendChild(canvas);
  document.body.prepend(root);

  const context = canvas.getContext("2d");
  if (!context) return;

  let width = 0;
  let height = 0;
  let particles = [];
  let backgroundParticles = [];
  const mouse = { x: -1000, y: -1000, isActive: false };
  let frameId = 0;
  let lastTime = 0;

  function initParticles() {
    const particleCount = Math.floor(width * height * PARTICLE_DENSITY);
    particles = Array.from({ length: particleCount }, () => {
      const x = Math.random() * width;
      const y = Math.random() * height;
      return {
        x,
        y,
        originX: x,
        originY: y,
        vx: 0,
        vy: 0,
        size: randomRange(1, 2.5),
        color: Math.random() > 0.88 ? "#0065BD" : "#ffffff",
      };
    });

    const bgCount = Math.floor(width * height * BG_PARTICLE_DENSITY);
    backgroundParticles = Array.from({ length: bgCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.2,
      vy: (Math.random() - 0.5) * 0.2,
      size: randomRange(0.5, 1.5),
      alpha: randomRange(0.1, 0.4),
      phase: Math.random() * Math.PI * 2,
    }));
  }

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    initParticles();
  }

  function animate(time) {
    context.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height / 2;
    const pulseOpacity = Math.sin(time * 0.0008) * 0.035 + 0.085;
    const gradient = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(width, height) * 0.7);
    gradient.addColorStop(0, `rgba(0, 101, 189, ${pulseOpacity})`);
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);

    context.fillStyle = "#ffffff";
    backgroundParticles.forEach((p) => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;
      if (p.y > height) p.y = 0;

      const twinkle = Math.sin(time * 0.002 + p.phase) * 0.5 + 0.5;
      context.globalAlpha = p.alpha * (0.3 + 0.7 * twinkle);
      context.beginPath();
      context.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      context.fill();
    });
    context.globalAlpha = 1;

    particles.forEach((p) => {
      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (mouse.isActive && distance < MOUSE_RADIUS) {
        const forceDirectionX = dx / distance;
        const forceDirectionY = dy / distance;
        const force = (MOUSE_RADIUS - distance) / MOUSE_RADIUS;
        const repulsion = force * REPULSION_STRENGTH;
        p.vx -= forceDirectionX * repulsion * 5;
        p.vy -= forceDirectionY * repulsion * 5;
      }

      p.vx += (p.originX - p.x) * RETURN_SPEED;
      p.vy += (p.originY - p.y) * RETURN_SPEED;
    });

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const p1 = particles[i];
        const p2 = particles[j];
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const distSq = dx * dx + dy * dy;
        const minDist = p1.size + p2.size;

        if (distSq < minDist * minDist) {
          const dist = Math.sqrt(distSq);
          if (dist > 0.01) {
            const nx = dx / dist;
            const ny = dy / dist;
            const overlap = minDist - dist;
            const pushX = nx * overlap * 0.5;
            const pushY = ny * overlap * 0.5;
            p1.x -= pushX;
            p1.y -= pushY;
            p2.x += pushX;
            p2.y += pushY;

            const dvx = p1.vx - p2.vx;
            const dvy = p1.vy - p2.vy;
            const velocityAlongNormal = dvx * nx + dvy * ny;

            if (velocityAlongNormal > 0) {
              const m1 = p1.size;
              const m2 = p2.size;
              const restitution = 0.85;
              const impulseMagnitude = (-(1 + restitution) * velocityAlongNormal) / (1 / m1 + 1 / m2);
              const impulseX = impulseMagnitude * nx;
              const impulseY = impulseMagnitude * ny;
              p1.vx += impulseX / m1;
              p1.vy += impulseY / m1;
              p2.vx -= impulseX / m2;
              p2.vy -= impulseY / m2;
            }
          }
        }
      }
    }

    particles.forEach((p) => {
      p.vx *= DAMPING;
      p.vy *= DAMPING;
      p.x += p.vx;
      p.y += p.vy;

      context.beginPath();
      context.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      const velocity = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      const opacity = Math.min(0.3 + velocity * 0.1, 1);
      context.fillStyle = p.color === "#ffffff" ? `rgba(255, 255, 255, ${opacity})` : p.color;
      context.fill();
    });

    lastTime = time;
    frameId = requestAnimationFrame(animate);
  }

  function handleMouseMove(event) {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
    mouse.isActive = true;
  }

  function handleMouseLeave() {
    mouse.isActive = false;
  }

  resize();
  frameId = requestAnimationFrame(animate);
  window.addEventListener("resize", resize);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseleave", handleMouseLeave);

  return () => {
    cancelAnimationFrame(frameId);
    window.removeEventListener("resize", resize);
    window.removeEventListener("mousemove", handleMouseMove);
    window.removeEventListener("mouseleave", handleMouseLeave);
    root.remove();
  };
}
