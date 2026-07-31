import { useEffect, useRef } from "react";

/** Abstract lidar / roadway atmosphere for the homepage hero. */
export function HeroAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    type Particle = {
      x: number;
      y: number;
      z: number;
      vx: number;
      hue: number;
    };

    const particles: Particle[] = [];
    const beams: { angle: number; speed: number; life: number }[] = [];

    const resize = () => {
      const parent = canvas.parentElement;
      w = parent?.clientWidth ?? window.innerWidth;
      h = parent?.clientHeight ?? window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const seed = () => {
      particles.length = 0;
      const count = Math.min(420, Math.floor((w * h) / 2800));
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          z: 0.2 + Math.random() * 0.8,
          vx: (Math.random() - 0.5) * 0.15,
          hue: 175 + Math.random() * 40,
        });
      }
      beams.length = 0;
      for (let i = 0; i < 7; i++) {
        beams.push({
          angle: (i / 7) * Math.PI - Math.PI / 2.4,
          speed: 0.0015 + Math.random() * 0.001,
          life: Math.random(),
        });
      }
    };

    resize();
    seed();

    const onResize = () => {
      resize();
      seed();
    };
    window.addEventListener("resize", onResize);

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);

      // Road plane vanishing toward horizon
      const horizon = h * 0.42;
      const vanishingX = w * 0.62;

      const roadGrad = ctx.createLinearGradient(0, horizon, 0, h);
      roadGrad.addColorStop(0, "rgba(8, 18, 28, 0)");
      roadGrad.addColorStop(0.15, "rgba(12, 28, 42, 0.55)");
      roadGrad.addColorStop(1, "rgba(6, 14, 22, 0.9)");
      ctx.fillStyle = roadGrad;
      ctx.beginPath();
      ctx.moveTo(vanishingX - 40, horizon);
      ctx.lineTo(vanishingX + 40, horizon);
      ctx.lineTo(w * 1.15, h);
      ctx.lineTo(-w * 0.15, h);
      ctx.closePath();
      ctx.fill();

      // Lane dashes with perspective
      ctx.strokeStyle = "rgba(34, 211, 238, 0.18)";
      ctx.lineWidth = 1.5;
      for (let i = 0; i < 18; i++) {
        const p = (i / 18 + (t * 0.00008) % 1) % 1;
        const y = horizon + p * p * (h - horizon);
        const spread = 18 + p * p * w * 0.42;
        const len = 4 + p * 28;
        ctx.globalAlpha = 0.15 + p * 0.55;
        ctx.beginPath();
        ctx.moveTo(vanishingX, y);
        ctx.lineTo(vanishingX, Math.min(h, y + len));
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(vanishingX - spread, y);
        ctx.lineTo(vanishingX - spread * 1.02, y + len * 0.6);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(vanishingX + spread, y);
        ctx.lineTo(vanishingX + spread * 1.02, y + len * 0.6);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Scanning lidar wedges
      const originX = vanishingX;
      const originY = horizon + 8;
      for (const beam of beams) {
        beam.life = (beam.life + beam.speed) % 1;
        const a = beam.angle + Math.sin(t * 0.0004 + beam.angle) * 0.08;
        const reach = 80 + beam.life * Math.min(w, h) * 0.55;
        const grad = ctx.createRadialGradient(originX, originY, 0, originX, originY, reach);
        grad.addColorStop(0, "rgba(34, 211, 238, 0.22)");
        grad.addColorStop(0.45, "rgba(56, 189, 248, 0.06)");
        grad.addColorStop(1, "rgba(34, 211, 238, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(originX, originY);
        ctx.arc(originX, originY, reach, a - 0.12, a + 0.12);
        ctx.closePath();
        ctx.fill();
      }

      // Point cloud particles
      for (const p of particles) {
        p.x += p.vx * p.z;
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        const pulse = 0.55 + 0.45 * Math.sin(t * 0.002 + p.x * 0.01 + p.y * 0.008);
        const size = (0.6 + p.z * 1.8) * pulse;
        ctx.fillStyle = `hsla(${p.hue}, 85%, ${55 + p.z * 20}%, ${0.25 + p.z * 0.55})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
        ctx.fill();
      }

      // Soft horizon glow
      const glow = ctx.createRadialGradient(vanishingX, horizon, 0, vanishingX, horizon, w * 0.35);
      glow.addColorStop(0, "rgba(34, 211, 238, 0.12)");
      glow.addColorStop(0.5, "rgba(14, 165, 233, 0.04)");
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, h);

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <div className="hero-visual" aria-hidden="true">
      <canvas ref={canvasRef} className="hero-canvas" />
      <div className="hero-visual-fade" />
    </div>
  );
}
