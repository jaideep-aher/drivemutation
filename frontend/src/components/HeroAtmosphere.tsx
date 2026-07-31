/** Abstract lidar / roadway atmosphere for the homepage hero. */
import { useEffect, useRef } from "react";

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
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    type Particle = {
      x: number;
      y: number;
      z: number;
      vx: number;
      kind: "return" | "dust";
    };

    const particles: Particle[] = [];
    const beams: { angle: number; speed: number; life: number; width: number }[] = [];
    let scanAngle = -0.9;

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
      const count = Math.min(380, Math.floor((w * h) / 3000));
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          z: 0.18 + Math.random() * 0.82,
          vx: (Math.random() - 0.5) * 0.12,
          kind: Math.random() > 0.72 ? "return" : "dust",
        });
      }
      beams.length = 0;
      for (let i = 0; i < 5; i++) {
        beams.push({
          angle: -1.05 + (i / 4) * 1.55,
          speed: 0.0012 + Math.random() * 0.0008,
          life: Math.random(),
          width: 0.07 + Math.random() * 0.05,
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

    const drawStaticFrame = () => {
      draw(0);
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);

      const horizon = h * 0.4;
      const vanishingX = w * 0.58;

      // Atmospheric depth wash
      const sky = ctx.createLinearGradient(0, 0, 0, horizon);
      sky.addColorStop(0, "rgba(5, 15, 30, 0.45)");
      sky.addColorStop(1, "rgba(5, 15, 30, 0)");
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, w, horizon + 2);

      // Distant grid (survey plane)
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, w, horizon);
      ctx.clip();
      ctx.strokeStyle = "rgba(0, 232, 157, 0.08)";
      ctx.lineWidth = 1;
      for (let i = 0; i < 12; i++) {
        const y = horizon * (0.2 + (i / 12) * 0.8);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      for (let i = 0; i < 16; i++) {
        const x = (i / 15) * w;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(vanishingX + (x - vanishingX) * 0.15, horizon);
        ctx.stroke();
      }
      ctx.restore();

      // Road plane
      const roadGrad = ctx.createLinearGradient(0, horizon, 0, h);
      roadGrad.addColorStop(0, "rgba(19, 34, 55, 0)");
      roadGrad.addColorStop(0.12, "rgba(31, 42, 57, 0.7)");
      roadGrad.addColorStop(1, "rgba(5, 15, 30, 0.95)");
      ctx.fillStyle = roadGrad;
      ctx.beginPath();
      ctx.moveTo(vanishingX - 28, horizon);
      ctx.lineTo(vanishingX + 28, horizon);
      ctx.lineTo(w * 1.12, h);
      ctx.lineTo(-w * 0.12, h);
      ctx.closePath();
      ctx.fill();

      // Road edge lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(vanishingX - 26, horizon);
      ctx.lineTo(-w * 0.05, h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(vanishingX + 26, horizon);
      ctx.lineTo(w * 1.05, h);
      ctx.stroke();

      // Center lane dashes with perspective motion
      const dashPhase = reduced ? 0 : (t * 0.00009) % 1;
      ctx.strokeStyle = "rgba(0, 111, 238, 0.55)";
      ctx.lineWidth = 2;
      for (let i = 0; i < 16; i++) {
        const p = (i / 16 + dashPhase) % 1;
        const y = horizon + p * p * (h - horizon);
        const len = 5 + p * 32;
        ctx.globalAlpha = 0.2 + p * 0.7;
        ctx.beginPath();
        ctx.moveTo(vanishingX, y);
        ctx.lineTo(vanishingX, Math.min(h, y + len));
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Shoulder markers
      ctx.strokeStyle = "rgba(0, 232, 157, 0.2)";
      ctx.lineWidth = 1;
      for (let i = 0; i < 10; i++) {
        const p = (i / 10 + dashPhase * 0.5) % 1;
        const y = horizon + p * p * (h - horizon);
        const spread = 22 + p * p * w * 0.4;
        ctx.globalAlpha = 0.15 + p * 0.45;
        ctx.beginPath();
        ctx.moveTo(vanishingX - spread, y);
        ctx.lineTo(vanishingX - spread * 1.01, y + 6 + p * 10);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(vanishingX + spread, y);
        ctx.lineTo(vanishingX + spread * 1.01, y + 6 + p * 10);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      const originX = vanishingX;
      const originY = horizon + 6;

      // Primary sweep beam (range finder)
      if (!reduced) {
        scanAngle = -1.1 + ((Math.sin(t * 0.00035) + 1) / 2) * 1.7;
      } else {
        scanAngle = -0.25;
      }
      const sweepReach = Math.min(w, h) * 0.62;
      const sweep = ctx.createRadialGradient(originX, originY, 0, originX, originY, sweepReach);
      sweep.addColorStop(0, "rgba(0, 111, 238, 0.16)");
      sweep.addColorStop(0.4, "rgba(0, 111, 238, 0.04)");
      sweep.addColorStop(1, "rgba(0, 111, 238, 0)");
      ctx.fillStyle = sweep;
      ctx.beginPath();
      ctx.moveTo(originX, originY);
      ctx.arc(originX, originY, sweepReach, scanAngle - 0.08, scanAngle + 0.08);
      ctx.closePath();
      ctx.fill();

      // Secondary lidar wedges
      for (const beam of beams) {
        if (!reduced) beam.life = (beam.life + beam.speed) % 1;
        const a = beam.angle + (reduced ? 0 : Math.sin(t * 0.00035 + beam.angle) * 0.06);
        const reach = 70 + beam.life * Math.min(w, h) * 0.5;
        const grad = ctx.createRadialGradient(originX, originY, 0, originX, originY, reach);
        grad.addColorStop(0, "rgba(0, 232, 157, 0.14)");
        grad.addColorStop(0.5, "rgba(0, 232, 157, 0.04)");
        grad.addColorStop(1, "rgba(0, 232, 157, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(originX, originY);
        ctx.arc(originX, originY, reach, a - beam.width, a + beam.width);
        ctx.closePath();
        ctx.fill();
      }

      // Ego marker at scan origin
      ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
      ctx.beginPath();
      ctx.moveTo(originX, originY - 5);
      ctx.lineTo(originX + 4, originY + 4);
      ctx.lineTo(originX - 4, originY + 4);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "rgba(0, 232, 157, 0.7)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(originX, originY, 10, 0, Math.PI * 2);
      ctx.stroke();

      // Point cloud returns
      for (const p of particles) {
        if (!reduced) {
          p.x += p.vx * p.z;
          if (p.x < -10) p.x = w + 10;
          if (p.x > w + 10) p.x = -10;
        }
        const pulse = reduced
          ? 0.75
          : 0.55 + 0.45 * Math.sin(t * 0.0018 + p.x * 0.01 + p.y * 0.008);
        const size = (p.kind === "return" ? 1.1 : 0.55) + p.z * (p.kind === "return" ? 1.6 : 1.2);
        const alpha = (p.kind === "return" ? 0.35 : 0.18) + p.z * 0.45;
        if (p.kind === "return") {
          ctx.fillStyle = `rgba(0, 111, 238, ${alpha * pulse})`;
        } else {
          ctx.fillStyle = `rgba(0, 232, 157, ${alpha * pulse})`;
        }
        ctx.fillRect(p.x, p.y, size * pulse, size * pulse);
      }

      // Range arcs
      ctx.strokeStyle = "rgba(0, 232, 157, 0.12)";
      ctx.lineWidth = 1;
      for (let r = 40; r < Math.min(w, h) * 0.55; r += 55) {
        ctx.beginPath();
        ctx.arc(originX, originY, r, -1.15, 0.55);
        ctx.stroke();
      }

      // Horizon cue (subtle, no bloom)
      const cue = ctx.createLinearGradient(vanishingX - 80, horizon, vanishingX + 80, horizon);
      cue.addColorStop(0, "rgba(0, 111, 238, 0)");
      cue.addColorStop(0.5, "rgba(0, 111, 238, 0.22)");
      cue.addColorStop(1, "rgba(0, 111, 238, 0)");
      ctx.strokeStyle = cue;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(vanishingX - 90, horizon);
      ctx.lineTo(vanishingX + 90, horizon);
      ctx.stroke();

      if (!reduced) raf = requestAnimationFrame(draw);
    };

    if (reduced) {
      drawStaticFrame();
    } else {
      raf = requestAnimationFrame(draw);
    }

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
