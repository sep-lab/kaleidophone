'use strict';
/* ============================================================================
   kaleidophone canvas lib -- ink.js
   The ink-on-paper cartoon kit, lifted from ( - ) and SAME AS YOU.

   The Flash look is a rule, not a filter: animate on twos (12 drawings a second,
   delivered at 24 fps), and BOIL every line -- seed a hash from the drawing
   number and jitter every point of every polyline by a pixel or two, more when
   the music is louder. Round caps and joins, flat fills, no gradients, three
   greys + paper + one accent. Cheap to render, and the crudeness reads as
   intentional (docs/TECHNIQUES.md #29).

   On twos is everything drawn, not only the boil: draw at the drawing's time
   (G.onTwos(t)) and read the music there too (heldEnv); only a camera move
   stays on the frame's own t.

   Also here: stroke-by-stroke draw-on (a scene sketches itself in; run it
   backwards and it un-draws itself, #43), a shakier "sketch" hand for the
   characters who are not quite real, a dry-run mode to measure a pose without
   drawing it, the contact log behind ?qa=1 (#35), glow() (a light that fades
   to its own colour), and a hand-lettered alphabet: word(), wordW(), and
   wordFit() to size a title to a width (proportionally spaced; a missing
   glyph warns and fails QA).

   Needs: core.js, live.js (the stage: ctx, S, W, H). Recolour by mutating C:
     Object.assign(C, { accent: '#2255aa' });
   ============================================================================ */

const C = {
  paper: '#ede6d6', ink: '#17140f', grey: '#8f887c', grey2: '#cbc3b2', dark: '#2b2723',
  night: '#1a1714', black: '#0d0c0a', red: '#c9301c', accent: '#c9301c',
  sketch: '#5e584f', frame: '#ddd6c6', bob: '#3f3a34', beanie: '#4a463f',
  wood: '#5a4431', woodLt: '#8c6c4c',
};

// ---- boil: per-drawing jitter -----------------------------------------------
let seed = 0, amp = 1.3, ji = 0;
function J() { ji++; return (hsh(seed, ji) * 2 - 1) * amp; }
// Call once per frame: the drawing number (not the frame number) seeds the boil, so on twos
// every drawing is held for two frames and the lines crawl at 12 fps like hand-drawn cels.
function boilFrame(t, loudness = 0, fps = 12) { seed = Math.floor(t * fps) + 1; ji = 0; amp = 1.2 + 0.7 * loudness; }
// On twos is everything that is DRAWN, not only the boil: draw poses, draw-ons and titles at the
// drawing's time tq = G.onTwos(t), and read the music they react to there too -- heldEnv re-samples
// the song pack at tq (render mode; live mode has no pack and keeps the analyser's value). A camera
// move -- a zoom, a pan, a dissolve -- is not a drawing: keep it on the frame's own t, smooth.
function heldEnv(env, tq) {
  if (!ENV.pack) return env;
  const e = {}; for (const k in env) e[k] = envAt(k, tq); return e;
}
function LW(k = 1) { return 6.4 * k; }

// ---- draw-on: every scene sketches itself in, stroke by stroke ---------------
let DRAWON = null;             // { t: seconds since the scene started, dur, stagger, k }
function revealU() {
  if (!DRAWON) return 1;
  const k = DRAWON.k++;
  return clamp((DRAWON.t - k * DRAWON.stagger) / DRAWON.dur, 0, 1);
}
function noDraw(fn) { const d = DRAWON; DRAWON = null; try { fn(); } finally { DRAWON = d; } }
// drawOn(sinceSceneStart) before drawing a scene; drawOn(null) after. Erase = drawOn((1 - e) * total).
function drawOn(t, { dur = 0.2, stagger = 0.0042 } = {}) { DRAWON = t == null ? null : { t, dur, stagger, k: 0 }; }

// ---- sketch style (drawn by a less certain hand) -------------------------------
let SKETCH = 0;
// ---- dry run: compute a pose without drawing it (seat a body on a sill, then draw) ----
let DRY = false;
function measure(fn) { const d = DRY, a = ji; DRY = true; try { return fn(); } finally { DRY = d; ji = a; } }

// ---- primitives (boiled, optionally partially revealed) ----------------------
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
  // a pill from (x1,y1) to (x2,y2): the cap at each end curves AWAY from the other end.
  // (Check this with a still before trusting it: the first version drew its caps on the wrong
  // sides and every torso came out as an S-shaped blob.)
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, px = -uy, py = ux;
  const pts = [];
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x2 + (px * Math.cos(a) + ux * Math.sin(a)) * r, y2 + (py * Math.cos(a) + uy * Math.sin(a)) * r]); }
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x1 + (-px * Math.cos(a) - ux * Math.sin(a)) * r, y1 + (-py * Math.cos(a) - uy * Math.sin(a)) * r]); }
  return pts;
}
// A light fades to its OWN colour at alpha 0. Canvas gradients interpolate un-premultiplied RGBA,
// so a fade to transparent black passes through dark grey half way out and darkens what it lights
// (the template's lamp threw a dark ring onto its wall).
function glow(x, y, r, rgba0, rgba1 = withAlpha(rgba0, 0), op = 'source-over') {
  if (DRY) return;
  const g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, rgba0); g.addColorStop(1, rgba1);
  const o = ctx.globalCompositeOperation; ctx.globalCompositeOperation = op; ctx.fillStyle = g; ctx.fillRect(x - r, y - r, 2 * r, 2 * r); ctx.globalCompositeOperation = o;
}
// the same colour at alpha a: rgb()/rgba() and #hex directly, any other CSS colour via the canvas
function withAlpha(color, a) {
  const s = String(color).replace(/\s+/g, '');
  const m = /^rgba?\(([-\d.]+),([-\d.]+),([-\d.]+)[,)]/i.exec(s);
  if (m) return `rgba(${+m[1]},${+m[2]},${+m[3]},${a})`;
  const h = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(s);
  if (h) {
    const x = h[1], n = x.length < 6 ? 1 : 2;                 // #rgb(a) or #rrggbb(aa)
    const v = [0, 1, 2].map(i => { const d = x.slice(i * n, i * n + n); return parseInt(n === 1 ? d + d : d, 16); });
    return `rgba(${v[0]},${v[1]},${v[2]},${a})`;
  }
  if (typeof ctx !== 'undefined' && ctx) {           // named, hsl(), ...: the canvas normalises it to #hex or rgba()
    const o = ctx.fillStyle; ctx.fillStyle = color; const c = ctx.fillStyle; ctx.fillStyle = o;
    if (c !== color && /^(#|rgb)/.test(c)) return withAlpha(c, a);
  }
  return `rgba(0,0,0,${a})`;
}

// ---- paper grain: three seeded tiles, one per drawing, shifted --------------------
const INK_GRAINS = [];
function paperGrain(alpha = 0.06) {
  if (DRY) return;
  if (!INK_GRAINS.length) for (let g = 0; g < 3; g++) INK_GRAINS.push(noiseTile(256, 101 + g, 60, `ink-grain-${g}`));
  const pat = ctx.createPattern(INK_GRAINS[seed % 3], 'repeat');
  ctx.save(); ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = alpha;
  ctx.translate((seed * 37) % 256, (seed * 91) % 256); ctx.fillStyle = pat; ctx.fillRect(-256, -256, W + 512, H + 512); ctx.restore();
}

// ---- contact QA: every body<->furniture contact is declared, measured, and drawn with ?qa=1 ----
// "Is the chair fitted?" becomes a number. (SAME AS YOU passed every contact at 0 px.)
const CONTACTS = [];
function contact(name, a, b, tol = 2.5) { if (DRY) return; CONTACTS.push({ name, a: a.slice(), b: b.slice(), d: Math.hypot(a[0] - b[0], a[1] - b[1]), tol }); }
function drawContacts() {
  base();
  for (const c of CONTACTS) {
    const bad = c.d > c.tol;
    ctx.strokeStyle = bad ? '#ff0040' : '#00e070'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(c.a[0], c.a[1], 7, 0, TAU); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(c.b[0] - 9, c.b[1]); ctx.lineTo(c.b[0] + 9, c.b[1]); ctx.stroke();
  }
}
function contactReport() {
  if (!CONTACTS.length) return null;
  const worst = CONTACTS.reduce((m, c) => c.d > m.d ? c : m, { d: 0, name: '-' });
  return { n: CONTACTS.length, worst: worst.name, d: +worst.d.toFixed(2), failing: CONTACTS.filter(c => c.d > c.tol).length };
}

// ---- hand-lettered titles: strokes in a 60x84 box, boiled like everything else ----
const E_ = (cx, cy, rx, ry, n = 24) => ellPts(cx, cy, rx, ry, n).concat([[cx + rx, cy]]);
const GLYPH = {
  A: [[[1, 84], [30, 0], [59, 84]], [[13, 54], [47, 54]]],
  B: [[[6, 84], [6, 0], [38, 0], [52, 8], [54, 20], [48, 34], [34, 40], [6, 40]], [[34, 40], [50, 46], [57, 60], [54, 74], [42, 84], [6, 84]]],
  C: [[[56, 14], [44, 3], [28, 0], [12, 6], [4, 22], [3, 42], [5, 62], [13, 78], [29, 84], [45, 81], [57, 70]]],
  D: [[[6, 0], [6, 84], [30, 84], [48, 76], [57, 58], [58, 42], [56, 24], [46, 8], [30, 0], [6, 0]]],
  E: [[[55, 1], [5, 1], [5, 84], [56, 84]], [[5, 42], [45, 42]]],
  F: [[[56, 1], [6, 1], [6, 84]], [[6, 42], [44, 42]]],
  G: [[[56, 16], [45, 4], [29, 0], [13, 6], [4, 22], [3, 42], [5, 62], [14, 78], [30, 84], [46, 80], [56, 68], [56, 48], [34, 48]]],
  H: [[[5, 0], [5, 84]], [[55, 0], [55, 84]], [[5, 42], [55, 42]]],
  I: [[[30, 0], [30, 84]], [[14, 0], [46, 0]], [[14, 84], [46, 84]]],
  J: [[[48, 0], [48, 62], [42, 78], [28, 84], [14, 80], [6, 68]]],
  K: [[[6, 0], [6, 84]], [[54, 0], [6, 52]], [[20, 38], [56, 84]]],
  L: [[[6, 0], [6, 84], [54, 84]]],
  M: [[[3, 84], [7, 0], [30, 58], [53, 0], [57, 84]]],
  N: [[[5, 84], [5, 0], [55, 84], [55, 0]]],
  O: [E_(30, 42, 28, 42)],
  P: [[[6, 84], [6, 0], [40, 0], [53, 9], [56, 22], [52, 36], [38, 44], [6, 44]]],
  Q: [E_(30, 42, 28, 42), [[36, 62], [58, 86]]],
  R: [[[6, 84], [6, 0], [40, 0], [53, 9], [56, 22], [52, 36], [38, 44], [6, 44]], [[32, 44], [56, 84]]],
  S: [[[54, 12], [42, 2], [26, 0], [10, 6], [5, 20], [12, 33], [30, 41], [48, 50], [56, 64], [50, 79], [32, 85], [14, 81], [3, 70]]],
  T: [[[2, 1], [58, 1]], [[30, 1], [30, 84]]],
  U: [[[4, 0], [4, 56], [12, 76], [30, 84], [48, 76], [56, 56], [56, 0]]],
  V: [[[2, 0], [30, 84], [58, 0]]],
  W: [[[1, 0], [14, 84], [30, 24], [46, 84], [59, 0]]],
  X: [[[4, 0], [56, 84]], [[56, 0], [4, 84]]],
  Y: [[[2, 0], [30, 42], [58, 0]], [[30, 42], [30, 84]]],
  Z: [[[4, 1], [56, 1], [4, 84], [57, 84]]],
  0: [E_(30, 42, 24, 42)],
  1: [[[16, 16], [32, 0], [32, 84]], [[16, 84], [48, 84]]],
  2: [[[6, 18], [14, 5], [30, 0], [46, 5], [54, 18], [50, 34], [6, 84], [56, 84]]],
  3: [[[6, 8], [20, 1], [38, 1], [52, 10], [54, 24], [44, 36], [26, 40]], [[26, 40], [46, 46], [56, 60], [52, 76], [36, 84], [18, 84], [4, 74]]],
  4: [[[42, 84], [42, 0], [4, 58], [58, 58]]],
  5: [[[52, 1], [10, 1], [6, 38], [24, 32], [42, 34], [54, 46], [56, 62], [48, 78], [30, 84], [14, 80], [4, 70]]],
  6: [[[50, 6], [36, 0], [20, 4], [8, 20], [4, 44], [6, 66], [16, 80], [30, 84], [46, 80], [55, 64], [52, 48], [40, 40], [24, 40], [10, 48], [5, 60]]],
  7: [[[4, 1], [56, 1], [22, 84]]],
  8: [E_(30, 20, 20, 20, 18), E_(30, 62, 25, 22, 20)],
  9: [[[52, 26], [46, 12], [30, 4], [14, 10], [6, 24], [10, 38], [24, 44], [40, 42], [52, 30], [54, 48], [50, 68], [40, 80], [26, 84], [10, 78]]],
  '?': [[[8, 18], [16, 5], [30, 0], [46, 5], [54, 18], [50, 32], [32, 44], [30, 58]], [[30, 74], [30, 84]]],
  '!': [[[30, 0], [30, 58]], [[30, 74], [30, 84]]],
  '-': [[[12, 46], [48, 46]]],
  '.': [[[30, 78], [30, 84]]],
  ',': [[[32, 76], [26, 92]]],
  "'": [[[30, 0], [28, 18]]],
  '(': [[[42, -4], [26, 12], [18, 42], [26, 72], [42, 88]]],
  ')': [[[18, -4], [34, 12], [42, 42], [34, 72], [18, 88]]],
  '/': [[[52, -2], [8, 86]]],
  ':': [[[30, 30], [30, 36]], [[30, 78], [30, 84]]],
  '&': [[[56, 50], [50, 66], [40, 78], [27, 85], [14, 82], [6, 72], [6, 60], [14, 50], [28, 40], [37, 31], [41, 19], [37, 7],
    [27, 1], [17, 5], [13, 16], [16, 29], [24, 42], [40, 64], [57, 84]]],
};
// Spacing: every glyph advances by its OWN ink width plus the same track, so I, 1 and punctuation
// sit as close as the wide letters (a fixed 60-unit cell left holes round them). In glyph units.
const GLYPH_TRACK = 24, GLYPH_SPACE = 36, GLYPH_NONE = 60;
function glyphSpan(ch) {                    // [left ink edge, ink width] of a glyph, or null if there is none
  const g = GLYPH[ch]; if (!g) return null;
  let a = Infinity, b = -Infinity;
  for (const s of g) for (const p of s) { if (p[0] < a) a = p[0]; if (p[0] > b) b = p[0]; }
  return [a, b - a];
}
// A character with no glyph is left as a gap the width of a letter -- never silently: it warns
// once on the console, and logs a failing contact so `still.mjs --qa` reports it and ?qa=1 marks it.
const GLYPH_MISSING = new Set();
// draws str with its left ink edge at x, cap-top at y, `u` 0..1 writes it on letter by letter; returns width
function word(str, x, y, hgt, color, lw, u = 1) {
  const k = hgt / 84, s = String(str).toUpperCase();
  let cx = x, n = 0; const total = s.replace(/ /g, '').length;
  for (const ch of s) {
    if (ch === ' ') { cx += GLYPH_SPACE * k; continue; }
    const uu = clamp(u * total - n, 0, 1); n++;
    const sp = glyphSpan(ch);
    if (!sp) {
      if (!GLYPH_MISSING.has(ch)) { GLYPH_MISSING.add(ch); console.warn(`ink.js word(): no glyph for "${ch}" in "${str}" -- drawn as a gap; add it to GLYPH`); }
      contact(`glyph "${ch}" missing`, [cx, y + hgt / 2], [cx + GLYPH_NONE * k, y + hgt / 2], 0);
      cx += (GLYPH_NONE + GLYPH_TRACK) * k; continue;
    }
    const ox = cx - sp[0] * k;
    for (const st of GLYPH[ch]) stroke(st.map(p => [ox + p[0] * k, y + p[1] * k]), color, lw, uu);
    cx += (sp[1] + GLYPH_TRACK) * k;
  }
  return Math.max(0, cx - x - GLYPH_TRACK * k);
}
function wordW(str, hgt) {
  let w = 0;
  for (const ch of String(str).toUpperCase()) { if (ch === ' ') { w += GLYPH_SPACE; continue; } const sp = glyphSpan(ch); w += (sp ? sp[1] : GLYPH_NONE) + GLYPH_TRACK; }
  return Math.max(0, (w - GLYPH_TRACK) * hgt / 84);
}
// Fit a title into maxW: one line, as tall as `max` allows -- unless that would take it under `min`
// (still legible), then two lines, broken at the space that balances them. -> { lines, hgt }
function wordFit(str, maxW, { max = 92, min = 64 } = {}) {
  const s = String(str).trim().replace(/\s+/g, ' '), one = maxW / (wordW(s, 1) || 1);
  if (one >= min || !s.includes(' ')) return { lines: [s], hgt: Math.min(max, one) };
  const ws = s.split(' '); let best = null;
  for (let i = 1; i < ws.length; i++) {
    const lines = [ws.slice(0, i).join(' '), ws.slice(i).join(' ')], w = Math.max(wordW(lines[0], 1), wordW(lines[1], 1));
    if (!best || w < best.w) best = { lines, w };
  }
  return { lines: best.lines, hgt: Math.min(max, maxW / best.w) };
}
