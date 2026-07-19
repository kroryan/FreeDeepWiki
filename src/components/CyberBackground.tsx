"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";

export default function CyberBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const isDark = resolvedTheme === "dark";

    let animationId: number;
    let W = (canvas.width = window.innerWidth);
    let H = (canvas.height = window.innerHeight);

    // ── Mouse ──────────────────────────────────────────────────────────────
    const mouse = { x: -9999, y: -9999 };
    const onMove = (e: MouseEvent) => { mouse.x = e.clientX; mouse.y = e.clientY; };
    const onLeave = () => { mouse.x = -9999; mouse.y = -9999; };
    window.addEventListener("mousemove", onMove);
    document.addEventListener("mouseleave", onLeave);

    // ── Resize ─────────────────────────────────────────────────────────────
    const onResize = () => {
      W = canvas.width = window.innerWidth;
      H = canvas.height = window.innerHeight;
      initMatrix();
    };
    window.addEventListener("resize", onResize);

    // ── Colours ────────────────────────────────────────────────────────────
    const C = {
      cyan:   isDark ? "0,240,255"   : "79,70,229",
      pink:   isDark ? "255,0,127"   : "168,85,247",
      green:  isDark ? "0,255,102"   : "16,185,129",
      matrix: isDark ? "0,255,102"   : "79,70,229",
    };

    // ── Matrix rain ────────────────────────────────────────────────────────
    const FONT_SZ = 13;
    const CHARS   = "01アイウエオカキクケコサシスセソタチツテトナニヌネノ<>{}[]|/\\#@$%&";

    let cols: number[] = [];
    const initMatrix = () => {
      const n = Math.floor(W / FONT_SZ);
      cols = Array.from({ length: n }, () => Math.random() * -H);
    };
    initMatrix();

    // ── Particle network ───────────────────────────────────────────────────
    const PCOUNT = Math.min(70, Math.floor((W * H) / 20000));
    interface P { x: number; y: number; vx: number; vy: number; r: number; hue: number }
    const particles: P[] = Array.from({ length: PCOUNT }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      r: Math.random() * 1.8 + 0.8,
      hue: Math.random() > 0.5 ? 0 : 1, // 0=cyan, 1=pink
    }));

    // ── Cursor trail ───────────────────────────────────────────────────────
    interface Trail { x: number; y: number; age: number }
    const trail: Trail[] = [];
    const MAX_TRAIL = 28;

    // ── Draw loop ──────────────────────────────────────────────────────────
    let frame = 0;
    const draw = () => {
      frame++;
      animationId = requestAnimationFrame(draw);

      // Semi-transparent clear → leaves ghost trails for matrix
      ctx.fillStyle = isDark
        ? "rgba(3,7,18,0.18)"   // deep space fade
        : "rgba(241,245,249,0.22)";
      ctx.fillRect(0, 0, W, H);

      // ── Matrix columns ───────────────────────────────────────────────────
      ctx.font = `${FONT_SZ}px 'Geist Mono', monospace`;
      for (let i = 0; i < cols.length; i++) {
        const y = cols[i];
        const char = CHARS[Math.floor(Math.random() * CHARS.length)];
        // Head glyph – bright
        const headAlpha = isDark ? 0.55 : 0.22;
        ctx.fillStyle = `rgba(${C.matrix},${headAlpha})`;
        ctx.fillText(char, i * FONT_SZ, y);

        // Advance column
        cols[i] += FONT_SZ;
        // Random reset to top with variable speed
        if (cols[i] > H && Math.random() > 0.975) {
          cols[i] = Math.random() * -H * 0.5;
        }
      }

      // ── Particles ────────────────────────────────────────────────────────
      for (const p of particles) {
        // Mouse repulsion
        const dx = p.x - mouse.x;
        const dy = p.y - mouse.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 160) {
          const f = (160 - d) / 160;
          const a = Math.atan2(dy, dx);
          p.x += Math.cos(a) * f * 2.5;
          p.y += Math.sin(a) * f * 2.5;
        }

        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > W) p.vx *= -1;
        if (p.y < 0 || p.y > H) p.vy *= -1;

        const col = p.hue === 0 ? C.cyan : C.pink;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${col},${isDark ? 0.45 : 0.2})`;
        ctx.fill();
      }

      // Connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i], b = particles[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < 120) {
            const alpha = ((120 - d) / 120) * (isDark ? 0.12 : 0.06);
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(${C.cyan},${alpha})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
        // Connect to mouse
        const dx = particles[i].x - mouse.x;
        const dy = particles[i].y - mouse.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 200) {
          const alpha = ((200 - d) / 200) * (isDark ? 0.22 : 0.10);
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.strokeStyle = `rgba(${C.pink},${alpha})`;
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
      }

      // ── Cursor neon trail ─────────────────────────────────────────────────
      if (mouse.x > -1000) {
        trail.push({ x: mouse.x, y: mouse.y, age: 0 });
        if (trail.length > MAX_TRAIL) trail.shift();
      }
      for (let i = 0; i < trail.length; i++) {
        trail[i].age++;
        const ratio = i / trail.length;
        const alpha = ratio * (isDark ? 0.55 : 0.28);
        const r = ratio * 5;
        ctx.beginPath();
        ctx.arc(trail[i].x, trail[i].y, r, 0, Math.PI * 2);
        // Alternate cyan/pink along trail
        const col = i % 2 === 0 ? C.cyan : C.pink;
        ctx.fillStyle = `rgba(${col},${alpha})`;
        ctx.fill();
      }

      // ── Corner HUD decorations (every 120 frames) ─────────────────────────
      if (frame % 2 === 0) {
        const hud = isDark ? `rgba(${C.cyan},0.12)` : `rgba(${C.cyan},0.06)`;
        ctx.strokeStyle = hud;
        ctx.lineWidth = 1;
        // Top-left bracket
        ctx.beginPath(); ctx.moveTo(10,30); ctx.lineTo(10,10); ctx.lineTo(30,10); ctx.stroke();
        // Top-right bracket
        ctx.beginPath(); ctx.moveTo(W-30,10); ctx.lineTo(W-10,10); ctx.lineTo(W-10,30); ctx.stroke();
        // Bottom-left
        ctx.beginPath(); ctx.moveTo(10,H-30); ctx.lineTo(10,H-10); ctx.lineTo(30,H-10); ctx.stroke();
        // Bottom-right
        ctx.beginPath(); ctx.moveTo(W-30,H-10); ctx.lineTo(W-10,H-10); ctx.lineTo(W-10,H-30); ctx.stroke();
      }
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
    };
  }, [resolvedTheme]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: -10 }}
    />
  );
}
