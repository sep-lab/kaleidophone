'use strict';
/* ============================================================================
   kaleidophone canvas lib -- core.js
   The helpers every piece re-derived: math and easing, keyframes, deterministic
   hashes and noise, the bar grid, the song-pack envelope sampler, sprites.

   No DOM access at load time (so node can test it); canvas helpers only touch
   the DOM when called. Plain script, not a module: a piece is one <script>, and
   tools/build.mjs concatenates the lib files a piece lists ahead of its own.
   ============================================================================ */

// ---------------------------------------------------------------- math
const TAU = Math.PI * 2;
const rad = d => d * Math.PI / 180;
const clamp = (v, a = 0, b = 1) => v < a ? a : v > b ? b : v;
const lerp = (a, b, u) => a + (b - a) * u;
const invLerp = (a, b, v) => (v - a) / (b - a || 1);
const remap = (v, a0, a1, b0, b1) => lerp(b0, b1, clamp(invLerp(a0, a1, v)));
const fract = x => x - Math.floor(x);
const ease = u => { u = clamp(u); return u * u * (3 - 2 * u); };          // smoothstep of u
const easeIn = u => { u = clamp(u); return u * u * u; };
const easeOut = u => { u = clamp(u); return 1 - (1 - u) * (1 - u) * (1 - u); };
const easeInOut = u => { u = clamp(u); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
const step = (t, a, b) => ease((t - a) / (b - a));                          // 0 before a, 1 after b
const smooth = (a, b, x) => ease((x - a) / (b - a));
// a hit: linear attack over `a` seconds, exponential decay with time constant `d`
const pulse = (t, t0, a, d) => (t < t0 ? 0 : t < t0 + a ? (t - t0) / a : Math.exp(-(t - t0 - a) / d));

// piecewise-smooth keyframes: kf(x, [[x0, v0], [x1, v1], ...], easing)
function kf(x, keys, fn = ease) {
  if (x <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) if (x <= keys[i][0]) {
    const [a, va] = keys[i - 1], [b, vb] = keys[i];
    return lerp(va, vb, fn((x - a) / (b - a || 1)));
  }
  return keys[keys.length - 1][1];
}

// ---------------------------------------------------------------- hashes and noise
// Integer hash -> [0, 1). Same inputs, same number, on every machine: the boil, the rain,
// the spots are all hashed from (frame, index), never drawn from Math.random().
function hsh(a, b) {
  let h = Math.imul(a ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul(b + 0x7F4A7C15, 0xC2B2AE35);
  h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; return (h >>> 0) / 4294967296;
}
const HS = (a, b = 0) => hsh(a * 131 + 7 | 0, b * 977 + 3 | 0);            // stable per-object hash
function hash(n) { n = Math.sin(n * 127.1 + 311.7) * 43758.5453123; return n - Math.floor(n); }
function hash2(a, b) { return hash(a * 12.9898 + b * 78.233); }
function vnoise(x, seed = 0) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i + seed * 57.3), hash(i + 1 + seed * 57.3), u); }
function fbm(x, seed = 0) { return 0.55 * vnoise(x, seed) + 0.3 * vnoise(x * 2.03, seed + 3) + 0.15 * vnoise(x * 4.1, seed + 7); }
// mulberry32: a seeded generator for the rare state that must be random but repeatable
function mulberry32(a) {
  return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}

// ---------------------------------------------------------------- the grid
// Count the grid before inventing anything: bars, beats and backbeats are where the music
// already put its accents (docs/TECHNIQUES.md, "grid arithmetic").
function makeGrid({ bpm, downbeat = 0, beatsPerBar = 4 }) {
  const beat = 60 / bpm, bar = beat * beatsPerBar;
  const G = {
    bpm, beat, bar, downbeat, beatsPerBar,
    bt: b => downbeat + b * bar,                                   // song time of (fractional) bar b
    barOf: t => (t - downbeat) / bar,
    beatOf: t => (t - downbeat) / beat,
    lastBeat: t => downbeat + Math.floor((t - downbeat) / beat + 1e-6) * beat,
    sinceBeat: t => t - G.lastBeat(t),
    beatInBar: t => ((Math.floor((t - downbeat) / beat + 1e-6) % beatsPerBar) + beatsPerBar) % beatsPerBar,
    isBackbeat: t => { const k = G.beatInBar(t); return k === 1 || k === 3; },   // beats 2 and 4
    // animation time quantised to `fps` -- the drawn Flash look ("on twos" at 12 fps)
    onTwos: (t, fps = 12) => Math.floor(t * fps + 1e-6) / fps,
  };
  return G;
}

// ---------------------------------------------------------------- the envelope
// A song pack (kaleidophone envelope / tools/synth.mjs): 100 Hz arrays, values ~0..1.
// Render mode passes the whole pack once (window.__init) or one sample per frame (__frame(p));
// both end up here, so a piece's draw code reads envelopes the same way in every mode.
const ENV = { fps: 100, off: 0, pack: null, now: {} };
function envInit(pack, { off = 0 } = {}) { ENV.pack = pack; ENV.fps = pack.fps || pack.sr || 100; ENV.off = off; }
function envAt(name, t) {
  const a = ENV.pack && ENV.pack[name];
  if (!a || !a.length) return ENV.now[name] || 0;
  const x = (t - ENV.off) * ENV.fps; if (x <= 0) return a[0];
  const i = Math.floor(x); if (i >= a.length - 1) return a[a.length - 1];
  const f = x - i; return a[i] * (1 - f) + a[i + 1] * f;
}
function envAvg(name, t, w) { let s = 0, n = 0; for (let d = -w; d <= w + 1e-9; d += 0.02) { s += envAt(name, t + d); n++; } return s / n; }

// ---------------------------------------------------------------- canvas helpers
function mkCanvas(w, h) {
  w = Math.max(1, Math.round(w)); h = Math.max(1, Math.round(h));
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(w, h);
  const c = document.createElement('canvas'); c.width = w; c.height = h; return c;
}
function rrectPath(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}
// smooth curve through points (Catmull-Rom -> Bezier)
function curvePath(ctx, pts, closed = true, tension = 0.5) {
  const n = pts.length; if (n < 2) return;
  const P = i => closed ? pts[(i + n) % n] : pts[clamp(i, 0, n - 1)];
  ctx.moveTo(pts[0][0], pts[0][1]);
  const last = closed ? n : n - 1, k = tension / 3;
  for (let i = 0; i < last; i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    ctx.bezierCurveTo(p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k, p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k, p2[0], p2[1]);
  }
  if (closed) ctx.closePath();
}
const rgba = (r, g, b, a = 1) => `rgba(${r | 0},${g | 0},${b | 0},${a})`;

// Every lineWidth and font size of a piece should be multiplied by this: a piece tuned at
// 1080p goes hairline on a 3000 px cover otherwise (the single biggest cover-quality fix).
const strokeScale = (subjectSize, ref = 200, min = 0.8) => Math.max(min, subjectSize / ref);

// ---------------------------------------------------------------- sprites (cached)
const SPR = {};
// Fire and glow are many soft sprites drawn with 'lighter', not stroked paths: paths read as twigs.
function glowSprite(r, g, b, key) {
  key = key || `g${r},${g},${b}`; if (SPR[key]) return SPR[key];
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  const gr = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  gr.addColorStop(0, rgba(r, g, b, 1)); gr.addColorStop(0.18, rgba(r, g, b, 0.55)); gr.addColorStop(0.45, rgba(r, g, b, 0.16)); gr.addColorStop(1, rgba(r, g, b, 0));
  x.fillStyle = gr; x.fillRect(0, 0, s, s); return (SPR[key] = c);
}
function drawSprite(ctx, spr, x, y, r, a = 1) { if (a <= 0.002 || r <= 0.3) return; ctx.globalAlpha = a; ctx.drawImage(spr, x - r, y - r, r * 2, r * 2); ctx.globalAlpha = 1; }
// A handful of pre-made grain tiles, rolled per frame: per-frame random noise at full
// resolution was the hottest operation in the python engines, and costs bitrate for nothing.
function noiseTile(size, seed, amp, key) {
  if (SPR[key]) return SPR[key];
  const c = mkCanvas(size, size), x = c.getContext('2d'), im = x.createImageData(size, size), d = im.data;
  const R = mulberry32(seed * 9301 + 49297);
  for (let i = 0; i < d.length; i += 4) { const v = 128 + (R() - 0.5) * 2 * amp; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
  x.putImageData(im, 0, 0); return (SPR[key] = c);
}
function overlayTile(ctx, tile, w, h, ox, oy, alpha, mode) {
  ctx.save(); ctx.globalAlpha = alpha; ctx.globalCompositeOperation = mode;
  const ts = tile.width; ox = ((ox % ts) + ts) % ts; oy = ((oy % ts) + ts) % ts;
  for (let y = -oy; y < h; y += ts) for (let x = -ox; x < w; x += ts) ctx.drawImage(tile, x, y);
  ctx.restore();
}
