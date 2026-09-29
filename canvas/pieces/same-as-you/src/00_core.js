'use strict';
/* ============================================================
   SAME AS YOU   —   Sep The Concept · بول شت استودیو
   The sequel to ( - ).  In ( - ) she was never drawn.
   Here she is — on the other half of the same torn page,
   doing the same things at the same time.  Same as you.

   The page is torn down the middle.  Every scene is ONE thing
   torn in half (a window, a café, a street, a bed): his half on
   the left, hers on the right, mirror images of each other.
   They never see it.  Only we do.

   One file, three modes:
     live    : click → procedural pad, or drop the WAV → AnalyserNode drives it.
     render  : ?render=1&w=1080&h=1920   → window.__frame({t, bass, mid, high, air, rms, flux, bflux, hflux})
     cover   : ?cover=1&size=3000         → window.__cover(variant)
   ============================================================ */
const Q = new URLSearchParams(location.search);
const RENDER = Q.get('render') === '1';
const COVER = Q.get('cover') === '1';
const QA = Q.get('qa') === '1';

// ---- the track grid (FINAL master, 2026-09-27): 120 BPM, first downbeat 0.25 s, 140.245 s (music ends 137.0, tail to 138.3) ----
const DUR = 140.245, T0 = 0.255, BEAT = 0.5, BAR = 2.0;
const bt = b => T0 + b * BAR;              // song time of (fractional) bar b
const REEL_END = bt(36);                   // 72.255 — the reel loops here
const DRAW_FPS = 12;                       // characters on twos (the Flash look); rain & camera on ones

// ---- palette: the ( - ) paper and ink, a rainy night, one red ----
const C = {
  paper: '#ede6d6', ink: '#17140f', grey: '#8f887c', grey2: '#cbc3b2', dark: '#2b2723',
  night: '#1a1714', black: '#0d0c0a', red: '#c9301c',
  sky: '#bebcb3', skyDk: '#8f8e88', facade: '#4d4e4c', facadeDk: '#383938', facadeLt: '#5d5e5b',
  room: '#bba886', roomDk: '#8c7d62', roomOff: '#262523', lamp: '#f3e4bc', frame: '#ddd6c6',
  sketch: '#5e584f', bob: '#3f3a34', beanie: '#4a463f', street: '#2d2e2e', wet: '#3a3b3b'
};

const cv = document.getElementById('c');
let ctx = cv.getContext('2d', { alpha: false });
const MAINCTX = ctx;
function withCtx(c2, fn) { const o = ctx; ctx = c2; try { return fn(); } finally { ctx = o; } }
const W = 1080, H = 1920;                  // virtual space; everything is drawn in these units
let S = 1, PXW = 1080, PXH = 1920;
function setSize(pw, ph) { PXW = pw; PXH = ph; cv.width = pw; cv.height = ph; S = pw / W; }
function base() { ctx.setTransform(S, 0, 0, S, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none'; }

// ---- math ----
const TAU = Math.PI * 2, rad = d => d * Math.PI / 180;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, u) => a + (b - a) * u;
const ease = u => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
const easeOut = u => { u = clamp(u, 0, 1); return 1 - (1 - u) * (1 - u) * (1 - u); };
const easeIn = u => { u = clamp(u, 0, 1); return u * u * u; };
const step = (t, a, b) => ease((t - a) / (b - a));
const fract = x => x - Math.floor(x);
// piecewise-smooth keyframes: kf(x, [[x0,v0],[x1,v1],...])
function kf(x, keys, fn = ease) {
  if (x <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) if (x <= keys[i][0]) {
    const [a, va] = keys[i - 1], [b, vb] = keys[i]; return lerp(va, vb, fn((x - a) / (b - a || 1)));
  }
  return keys[keys.length - 1][1];
}

// ---- hashing: per-frame boil + stable hashes ----
let seed = 0, amp = 1.3, ji = 0;
function hsh(a, b) {
  let h = Math.imul(a ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul(b + 0x7F4A7C15, 0xC2B2AE35);
  h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; return (h >>> 0) / 4294967296;
}
function J() { ji++; return (hsh(seed, ji) * 2 - 1) * amp; }
const HS = (a, b = 0) => hsh(a * 131 + 7 | 0, b * 977 + 3 | 0);      // stable, not per frame
function LW(k = 1) { return 6.4 * k; }

// ---- draw-on: every scene sketches itself in, stroke by stroke ----
let DRAWON = null;             // { t: seconds since the scene started, dur, stagger, k }
function revealU() {
  if (!DRAWON) return 1;
  const k = DRAWON.k++;
  return clamp((DRAWON.t - k * DRAWON.stagger) / DRAWON.dur, 0, 1);
}
function noDraw(fn) { const d = DRAWON; DRAWON = null; try { fn(); } finally { DRAWON = d; } }

// ---- sketch style (the new partners are drawn by a less certain hand) ----
let SKETCH = 0;
// ---- dry run: compute a pose without drawing it (used to seat bodies on sills) ----
let DRY = false;
function measure(fn) { const d = DRY, a = ji; DRY = true; try { return fn(); } finally { DRY = d; ji = a; } }

// ---- primitives (boiled, optionally partially revealed) ----
function ink(color = C.ink, lw = LW()) { ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; }
function jit(pts) { const q = new Array(pts.length); for (let i = 0; i < pts.length; i++) q[i] = [pts[i][0] + J(), pts[i][1] + J()]; return q; }
function trace(q, close, u) {
  ctx.beginPath();
  if (!q.length) return;
  if (u >= 1) { ctx.moveTo(q[0][0], q[0][1]); for (let i = 1; i < q.length; i++) ctx.lineTo(q[i][0], q[i][1]); if (close) ctx.closePath(); return; }
  const pts = close ? q.concat([q[0]]) : q;
  let L = 0; const seg = [];
  for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); L += d; }
  let rem = L * u; ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) {
    const d = seg[i - 1];
    if (rem >= d) { ctx.lineTo(pts[i][0], pts[i][1]); rem -= d; }
    else { const f = rem / (d || 1); ctx.lineTo(lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)); break; }
  }
}
function stroke(pts, color = C.ink, lw = LW(), u) {
  if (DRY) return;
  if (u === undefined) u = revealU(); if (u <= 0) return;
  if (SKETCH) {
    const c2 = SKETCH > 1 ? color : C.sketch;
    trace(jit(pts), false, u); ink(c2, lw * 0.72); ctx.stroke();
    const a0 = amp; amp *= 1.8; trace(jit(pts), false, u); ink(c2, lw * 0.42); ctx.stroke(); amp = a0; return;
  }
  trace(jit(pts), false, u); ink(color, lw); ctx.stroke();
}
function poly(pts, fill, strokeC, lw = LW(), u) {
  if (DRY) return;
  if (u === undefined) u = revealU(); if (u <= 0) return;
  const q = jit(pts);
  if (fill && u >= 1) { trace(q, true, 1); ctx.fillStyle = fill; ctx.fill(); }
  if (strokeC) {
    if (SKETCH) {
      const c2 = C.sketch; trace(q, true, u); ink(c2, lw * 0.72); ctx.stroke();
      const a0 = amp; amp *= 1.8; trace(jit(pts), true, u); ink(c2, lw * 0.42); ctx.stroke(); amp = a0;
    } else { trace(q, true, u); ink(strokeC, lw); ctx.stroke(); }
  }
}
function circPts(cx, cy, r, n) { n = n || clamp(Math.round(r / 6) + 10, 10, 44); const p = []; for (let i = 0; i < n; i++) { const a = i / n * TAU; p.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return p; }
function circ(cx, cy, r, fill, strokeC, lw, n, u) { poly(circPts(cx, cy, r, n), fill, strokeC, lw, u); }
function ellPts(cx, cy, rx, ry, n = 22, rot = 0) { const p = []; const c = Math.cos(rot), s = Math.sin(rot); for (let i = 0; i < n; i++) { const a = i / n * TAU, x = Math.cos(a) * rx, y = Math.sin(a) * ry; p.push([cx + x * c - y * s, cy + x * s + y * c]); } return p; }
function ell(cx, cy, rx, ry, fill, strokeC, lw, n = 22, rot = 0, u) { poly(ellPts(cx, cy, rx, ry, n, rot), fill, strokeC, lw, u); }
function rectPts(x, y, w, h) { return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]; }
function rect(x, y, w, h, fill, strokeC, lw, u) { poly(rectPts(x, y, w, h), fill, strokeC, lw, u); }
function rrPts(x, y, w, h, r, n = 5) {
  const p = []; r = Math.min(r, w / 2, h / 2);
  const cs = [[x + w - r, y + r, -Math.PI / 2], [x + w - r, y + h - r, 0], [x + r, y + h - r, Math.PI / 2], [x + r, y + r, Math.PI]];
  for (const [cx, cy, a0] of cs) for (let i = 0; i <= n; i++) { const a = a0 + i / n * Math.PI / 2; p.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); }
  return p;
}
function rrect(x, y, w, h, r, fill, strokeC, lw, u) { poly(rrPts(x, y, w, h, r), fill, strokeC, lw, u); }
function flat(x, y, w, h, fill) { if (DRY) return; ctx.fillStyle = fill; ctx.fillRect(x, y, w, h); }   // no boil: skies, walls
function arcPts(cx, cy, r, a0, a1, n) { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; p.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return p; }
function capsulePts(x1, y1, x2, y2, r, n = 7) {
  // a pill from (x1,y1) to (x2,y2): the cap at each end curves AWAY from the other end
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, px = -uy, py = ux;
  const pts = [];
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x2 + (px * Math.cos(a) + ux * Math.sin(a)) * r, y2 + (py * Math.cos(a) + uy * Math.sin(a)) * r]); }
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x1 + (-px * Math.cos(a) - ux * Math.sin(a)) * r, y1 + (-py * Math.cos(a) - uy * Math.sin(a)) * r]); }
  return pts;
}
function glow(x, y, r, rgba0, rgba1 = 'rgba(0,0,0,0)', op = 'source-over') {
  if (DRY) return;
  const g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, rgba0); g.addColorStop(1, rgba1);
  const o = ctx.globalCompositeOperation; ctx.globalCompositeOperation = op; ctx.fillStyle = g; ctx.fillRect(x - r, y - r, 2 * r, 2 * r); ctx.globalCompositeOperation = o;
}

// ---- QA: contact pairs collected per frame (?qa=1 draws them) ----
const CONTACTS = [];
function contact(name, a, b, tol = 2.5) { if (DRY) return; CONTACTS.push({ name, a: a.slice(), b: b.slice(), d: Math.hypot(a[0] - b[0], a[1] - b[1]), tol }); }

// ---- hand-lettered title: SAME AS YOU (strokes in a 60×84 box) ----
const GLYPH = {
  S: [[[54, 12], [42, 2], [26, 0], [10, 6], [5, 20], [12, 33], [30, 41], [48, 50], [56, 64], [50, 79], [32, 85], [14, 81], [3, 70]]],
  A: [[[1, 84], [30, 0], [59, 84]], [[13, 54], [47, 54]]],
  M: [[[3, 84], [7, 0], [30, 58], [53, 0], [57, 84]]],
  E: [[[55, 1], [5, 1], [5, 84], [56, 84]], [[5, 42], [45, 42]]],
  Y: [[[2, 0], [30, 42], [58, 0]], [[30, 42], [30, 84]]],
  O: [ellPts(30, 42, 28, 42, 24).concat([[58, 42]])],
  U: [[[4, 0], [4, 56], [12, 76], [30, 84], [48, 76], [56, 56], [56, 0]]]
};
function word(str, x, y, hgt, color, lw, u = 1) {
  // draws str with its left edge at x, cap-top at y; returns width
  const k = hgt / 84, adv = 60 * k, gap = 17 * k, sp = 34 * k;
  let cx = x, n = 0; const total = str.replace(/ /g, '').length;
  for (const ch of str) {
    if (ch === ' ') { cx += sp; continue; }
    const g = GLYPH[ch]; if (!g) { cx += adv + gap; continue; }
    const uu = clamp(u * total - n, 0, 1); n++;
    for (const s of g) stroke(s.map(p => [cx + p[0] * k, y + p[1] * k]), color, lw, uu);
    cx += adv + gap;
  }
  return cx - x - gap;
}
function wordW(str, hgt) { const k = hgt / 84; let w = 0; for (const ch of str) w += ch === ' ' ? 34 * k : (60 + 17) * k; return w - 17 * k; }
