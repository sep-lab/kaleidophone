// ============================================================================
// SHOULD I ?  —  Sep The Concept · بول شت استودیو
// A film seen through his viewfinder. 80 BPM, bar = 3.0 s, bar 0 at t = 0.
// 00_core: constants, math, hash/noise, envelopes, canvas + sprite helpers
// ============================================================================
'use strict';
const BPM = 80, BEAT = 0.75, BAR = 3.0, DUR = 182.0;
const T_DROP = 54.0, T_ROLL0 = 54.75, T_ROLL_END = 107.25;
const T_CALL = 125.246, T_REWIND = 126.0, T_DARK = 129.0, T_PENCIL = 156.0, T_END = 168.0;
const T_LAST = 179.64, T_CLICK = 180.08;  // the song's last vocal line (final master) starts at 179.64; the last shutter lands just after it
const VW = 1080, VH = 1920;                        // virtual frame
const VF = { x: 90, y: 262, w: 900, h: 1350, r: 22 }; // viewfinder image rect (2:3)
VF.cx = VF.x + VF.w / 2; VF.cy = VF.y + VF.h / 2;
const SPLIT_R = 118, PRISM_R0 = 122, PRISM_R1 = 176;

const TAU = Math.PI * 2;
const clamp = (v, a = 0, b = 1) => v < a ? a : v > b ? b : v;
const lerp = (a, b, k) => a + (b - a) * k;
const smooth = (a, b, x) => { const k = clamp((x - a) / (b - a)); return k * k * (3 - 2 * k); };
const easeOut = k => 1 - Math.pow(1 - clamp(k), 3);
const easeIn = k => Math.pow(clamp(k), 3);
const easeInOut = k => { k = clamp(k); return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; };
const pulse = (t, t0, a, d) => (t < t0 ? 0 : t < t0 + a ? (t - t0) / a : Math.exp(-(t - t0 - a) / d)); // attack a, decay d

// deterministic hash / noise
function hash(n) { n = Math.sin(n * 127.1 + 311.7) * 43758.5453123; return n - Math.floor(n); }
function hash2(a, b) { return hash(a * 12.9898 + b * 78.233); }
function vnoise(x, seed = 0) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i + seed * 57.3), hash(i + 1 + seed * 57.3), u); }
function fbm(x, seed = 0) { return 0.55 * vnoise(x, seed) + 0.3 * vnoise(x * 2.03, seed + 3) + 0.15 * vnoise(x * 4.1, seed + 7); }
function jit(t, seed, amp) { return (vnoise(t, seed) - 0.5) * 2 * amp; }

// ---------------------------------------------------------------- envelopes
// ENV arrays at 100 Hz, frame i labelled i/100 but centred ~21 ms later (window centre).
const ENV = { fps: 100, off: 0.021, n: 0 };
function envAt(name, t) {
  const a = ENV[name]; if (!a || !a.length) return 0;
  const x = (t - ENV.off) * ENV.fps; if (x <= 0) return a[0];
  const i = Math.floor(x); if (i >= a.length - 1) return a[a.length - 1];
  const f = x - i; return a[i] * (1 - f) + a[i + 1] * f;
}
function envAvg(name, t, w) { let s = 0, n = 0; for (let d = -w; d <= w; d += 0.02) { s += envAt(name, t + d); n++; } return s / n; }
const VOC = { fps: 100, off: 0.0 };
function vocAt(t) { const a = ENV.voc; if (!a) return 0; const x = t * 100; const i = Math.floor(x); if (i < 0 || i >= a.length - 1) return 0; const f = x - i; return a[i] * (1 - f) + a[i + 1] * f; }

// grid helpers
const barOf = t => t / BAR;
const beatOf = t => t / BEAT;
function lastBeat(t) { return Math.floor(t / BEAT + 1e-6) * BEAT; }
function sinceBeat(t) { return t - lastBeat(t); }
function isSnareBeat(b) { const k = ((b % 4) + 4) % 4; return k === 1 || k === 3; }
function lastSnare(t) { let b = Math.floor(t / BEAT + 1e-6); while (!isSnareBeat(b)) b--; return b * BEAT; }
function lastKick(t) { let b = Math.floor(t / BEAT + 1e-6); while (isSnareBeat(b)) b--; return b * BEAT; }

// ---------------------------------------------------------------- canvas helpers
function mkCanvas(w, h) {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
  const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c;
}
function rrect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}
// smooth closed/open curve through points (Catmull-Rom -> Bezier)
function curve(ctx, pts, closed = true, tension = 0.5) {
  const n = pts.length; if (n < 2) return;
  const P = i => closed ? pts[(i + n) % n] : pts[clamp(i, 0, n - 1)];
  ctx.moveTo(pts[0][0], pts[0][1]);
  const last = closed ? n : n - 1;
  for (let i = 0; i < last; i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    const k = tension / 3;
    ctx.bezierCurveTo(p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k, p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k, p2[0], p2[1]);
  }
  if (closed) ctx.closePath();
}
function blobPath(ctx, pts, closed = true) { ctx.beginPath(); curve(ctx, pts, closed); }
// tapered capsule between two points
function limb(ctx, x1, y1, x2, y2, w1, w2) {
  const a = Math.atan2(y2 - y1, x2 - x1), nx = Math.cos(a + Math.PI / 2), ny = Math.sin(a + Math.PI / 2);
  ctx.beginPath();
  ctx.moveTo(x1 + nx * w1 / 2, y1 + ny * w1 / 2);
  ctx.lineTo(x2 + nx * w2 / 2, y2 + ny * w2 / 2);
  ctx.arc(x2, y2, w2 / 2, a + Math.PI / 2, a - Math.PI / 2, true);
  ctx.lineTo(x1 - nx * w1 / 2, y1 - ny * w1 / 2);
  ctx.arc(x1, y1, w1 / 2, a - Math.PI / 2, a + Math.PI / 2, true);
  ctx.closePath(); ctx.fill();
}
function ell(ctx, x, y, rx, ry, rot = 0) { ctx.beginPath(); ctx.ellipse(x, y, Math.max(0.01, rx), Math.max(0.01, ry), rot, 0, TAU); }
function rgba(r, g, b, a = 1) { return `rgba(${r | 0},${g | 0},${b | 0},${a})`; }
function mix3(c1, c2, k) { return [lerp(c1[0], c2[0], k), lerp(c1[1], c2[1], k), lerp(c1[2], c2[2], k)]; }
function col(c, a = 1) { return rgba(c[0], c[1], c[2], a); }

// ---------------------------------------------------------------- sprites (cached)
const SPR = {};
function glowSprite(r, g, b, key) {
  key = key || `g${r},${g},${b}`; if (SPR[key]) return SPR[key];
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  const gr = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  gr.addColorStop(0, rgba(r, g, b, 1)); gr.addColorStop(0.18, rgba(r, g, b, 0.55)); gr.addColorStop(0.45, rgba(r, g, b, 0.16)); gr.addColorStop(1, rgba(r, g, b, 0));
  x.fillStyle = gr; x.fillRect(0, 0, s, s); return (SPR[key] = c);
}
// photographic bokeh disc: flat-ish with a brighter rim
function bokehSprite(r, g, b, key) {
  key = key || `b${r},${g},${b}`; if (SPR[key]) return SPR[key];
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  const gr = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2 - 2);
  gr.addColorStop(0, rgba(r, g, b, 0.42)); gr.addColorStop(0.72, rgba(r, g, b, 0.5)); gr.addColorStop(0.9, rgba(r, g, b, 0.78)); gr.addColorStop(0.97, rgba(r, g, b, 0.25)); gr.addColorStop(1, rgba(r, g, b, 0));
  x.fillStyle = gr; x.beginPath(); x.arc(s / 2, s / 2, s / 2 - 1, 0, TAU); x.fill(); return (SPR[key] = c);
}
function drawSprite(ctx, spr, x, y, r, a = 1) { if (a <= 0.002 || r <= 0.3) return; ctx.globalAlpha = a; ctx.drawImage(spr, x - r, y - r, r * 2, r * 2); ctx.globalAlpha = 1; }
// grain / ground-glass tiles
function noiseTile(size, seed, amp, key) {
  if (SPR[key]) return SPR[key];
  const c = mkCanvas(size, size), x = c.getContext('2d'); const im = x.createImageData(size, size), d = im.data;
  let s = seed * 9301 + 49297;
  for (let i = 0; i < d.length; i += 4) { s = (s * 9301 + 49297) % 233280; const v = 128 + (s / 233280 - 0.5) * 2 * amp; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
  x.putImageData(im, 0, 0); return (SPR[key] = c);
}
function overlayTile(ctx, tile, w, h, ox, oy, alpha, mode) {
  ctx.save(); ctx.globalAlpha = alpha; ctx.globalCompositeOperation = mode;
  const ts = tile.width; ox = ((ox % ts) + ts) % ts; oy = ((oy % ts) + ts) % ts;
  for (let y = -oy; y < h; y += ts) for (let x = -ox; x < w; x += ts) ctx.drawImage(tile, x, y);
  ctx.restore();
}
