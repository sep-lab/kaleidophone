// ---- the exposure ------------------------------------------------------------------
// expo(open): the exposure that opens at song time `open` and closes on the 32nd snare after it. Everything
// else is derived from it, once, and memoised: the 32 steps of the sky, the meteors (one per sung line), the
// moon and the dawn, and their light integrated over time (the photograph is an integral of light).
const XCACHE = {};
function expo(open) {
  const key = open.toFixed(3);
  if (XCACHE[key]) return XCACHE[key];
  let sn = sEv('snare').map(e => e[0]).filter(t => t > open + 1e-6);
  if (sn.length < STEPS) {                 // no snares in the pack (a dropped track): the grid's backbeats
    sn = [];
    for (let b = Math.ceil((open - G.downbeat) / G.beat); sn.length < STEPS; b++) {
      const t = G.downbeat + b * G.beat;
      if (t > open + 0.05 && ((b % 2) + 2) % 2 === 1) sn.push(t);
    }
  }
  sn = sn.slice(0, STEPS);
  const cut = cutFor(open) || { name: 'free', frames: 60 * FPS };
  const X = { open, close: sn[STEPS - 1], snares: sn, starts: [open, ...sn.slice(0, STEPS - 1)], ends: sn, cut };
  X.Tx = X.close - X.open;
  X.end = open + cut.frames / FPS;
  X.night = cut.name !== 'dawn';
  X.moon = cut.name === 'night' ? cueTime('moon', CUTS.night.moon) : null;
  X.dawn = cut.name === 'dawn' ? cueTime('dawn', CUTS.dawn.dawn) : null;
  X.leave = cut.name === 'dawn' ? cueTime('leave', CUTS.dawn.leave) : null;
  X.meteors = meteorsFor(X, cut.name === 'dawn' ? 7 : 3);
  X.plane = cut.name === 'dawn'
    ? { t0: 95.2, t1: 117.6, a: [1130, 700], b: [-60, 300] }
    : { t0: 19.6, t1: 43.0, a: [-60, 352], b: [1140, 268] };
  tabulateLight(X);
  return (XCACHE[key] = X);
}
// The sky's angle at t: step k runs from the step's start (the shutter, then each snare) to the next snare,
// 55% of its angle eased out over the first 28% of its time and the rest steady. Closed: one full turn.
const stepProg = u => KICK_SHARE * easeOut(clamp(u / KICK_U)) + (1 - KICK_SHARE) * clamp(u);
function stepIndex(X, t) {
  let lo = 0, hi = STEPS - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (X.starts[m] <= t) lo = m; else hi = m - 1; }
  return lo;
}
function thetaAt(X, t) {
  if (t <= X.open) return 0;
  if (t >= X.close) return TAU;
  const k = stepIndex(X, t);
  return STEP_A * (k + stepProg((t - X.starts[k]) / (X.ends[k] - X.starts[k])));
}
// How far into the exposure, 0..1 (held after it closes).
const expoU = (X, t) => clamp((t - X.open) / X.Tx);

// ---- light over time: the moon, the dawn ----------------------------------------------
// moonL / dawnL: how bright each is at t, in units of the night sky's own light; tabulated at 100 Hz and
// summed, so the integral of any of them over any span is two lookups.
const MOON = { r: 600, a0: rad(97), R: 9 };            // the moon's circle about the pole; where it is when it starts to rise (behind them)
function moonPos(X, t) {
  const a = MOON.a0 - (thetaAt(X, t) - thetaAt(X, X.moon));
  return [POLE.x + MOON.r * Math.cos(a), POLE.y + MOON.r * Math.sin(a)];
}
function moonUp(X, t) {                                 // how much of the disc is above the ridge, 0..1
  if (X.moon == null || t < X.moon) return 0;
  const [x, y] = moonPos(X, t);
  if (x < -MOON.R || x > W + MOON.R) return 0;
  return clamp((ridgeY(x) - y + MOON.R) / (2 * MOON.R)) * ease((t - X.moon) / 1.6);   // out of the haze
}
const DAWN_GAIN = 7.5;
function dawnL(X, t) { return X.dawn == null || t < X.dawn ? 0 : DAWN_GAIN * Math.pow(clamp((t - X.dawn) / (X.close - X.dawn)), 2.2); }
function tabulateLight(X) {
  const n = Math.ceil(X.Tx * 100) + 2, M = new Float64Array(n), D = new Float64Array(n);
  for (let i = 1; i < n; i++) {
    const t = X.open + (i - 0.5) / 100;
    M[i] = M[i - 1] + 0.01 * 1.6 * moonUp(X, t);
    D[i] = D[i - 1] + 0.01 * dawnL(X, t);
  }
  X.M = M; X.D = D;
}
function integ(X, A, t) {                               // the integral of a tabulated light from the opening to t
  const x = clamp(t - X.open, 0, X.Tx) * 100, i = Math.floor(x), f = x - i;
  if (i >= A.length - 1) return A[A.length - 1];
  return A[i] * (1 - f) + A[i + 1] * f;
}

// ---- the sky's own light (linear RGB per second of exposure) ---------------------------
// night: deep blue at the top, the city's sodium glow at the horizon. moon: blue, from the right. dawn: warm at
// the horizon on the right (north-east), blue above.
function nightRad(x, y) {
  const h = clamp((1210 - y) / 1210);                   // 0 at the horizon, 1 at the top
  const glow = Math.exp(-(1210 - Math.min(y, 1210)) / 210) * (1 + 0.3 * Math.exp(-(((x - 560) / 430) ** 2)));
  return [0.010 + 0.016 * (1 - h) + 0.16 * glow, 0.012 + 0.018 * (1 - h) + 0.105 * glow, 0.026 + 0.03 * (1 - h) + 0.075 * glow];
}
function moonRad(x, y) {
  const d = Math.hypot(x - 1010, y - 990), k = 0.32 + 0.68 * Math.exp(-d / 430);
  return [0.20 * k, 0.27 * k, 0.43 * k];
}
function dawnRad(x, y) {
  const lowk = Math.exp(-Math.max(0, 1215 - y) / 240) * (0.3 + 0.7 * Math.exp(-(((x - 990) / 560) ** 2)));
  const up = 0.55 + 0.45 * clamp(y / 1200);
  return [0.95 * lowk + 0.10 * up, 0.50 * lowk + 0.22 * up, 0.30 * lowk + 0.44 * up];
}
const lum = c => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
// The display: how the accumulating exposure is shown. The static scene starts from a base exposure and develops
// (0.36 -> 1 over the exposure, fast at first); the moon and the dawn add their integrated light on top.
const develop = u => 0.62 + 0.38 * Math.sqrt(clamp(u));
const TONE_K = 2.7;
const tone = v => 1 - Math.exp(-TONE_K * v);
// The sky, drawn into a small buffer and scaled up (it is smooth; the grain dithers it).
const SKYBUF = { w: 108, h: 192, cv: null, img: null };
function drawSky(X, t, o = {}) {
  if (!SKYBUF.cv) { SKYBUF.cv = mkCanvas(SKYBUF.w, SKYBUF.h); SKYBUF.img = SKYBUF.cv.getContext('2d').createImageData(SKYBUF.w, SKYBUF.h); }
  const u = o.u != null ? o.u : expoU(X, t), dev = develop(u);
  const m = integ(X, X.M, t) / X.Tx, d = integ(X, X.D, t) / X.Tx;
  const px = SKYBUF.img.data, sx = W / SKYBUF.w, sy = H / SKYBUF.h;
  for (let j = 0; j < SKYBUF.h; j++) {
    const y = (j + 0.5) * sy;
    for (let i = 0; i < SKYBUF.w; i++) {
      const x = (i + 0.5) * sx, n = nightRad(x, y);
      let r = n[0] * dev, g = n[1] * dev, b = n[2] * dev;
      if (m > 0) { const c = moonRad(x, y); r += c[0] * m; g += c[1] * m; b += c[2] * m; }
      if (d > 0) { const c = dawnRad(x, y); r += c[0] * d; g += c[1] * d; b += c[2] * d; }
      const p = 4 * (j * SKYBUF.w + i);
      px[p] = 255 * tone(r); px[p + 1] = 255 * tone(g); px[p + 2] = 255 * tone(b); px[p + 3] = 255;
    }
  }
  SKYBUF.cv.getContext('2d').putImageData(SKYBUF.img, 0, 0);
  ctx.save(); stage(); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'low';
  ctx.drawImage(SKYBUF.cv, 0, 0, W, H);
  ctx.restore();
}
// The light of the sky behind a point, integrated over [a, b]: what a person sitting there blocked.
function skyLightBehind(X, x, y, a, b) {
  a = clamp(a, X.open, X.close); b = clamp(b, X.open, X.close);
  if (b <= a) return 0;
  return lum(nightRad(x, y)) * (b - a) + lum(moonRad(x, y)) * (integ(X, X.M, b) - integ(X, X.M, a)) + lum(dawnRad(x, y)) * (integ(X, X.D, b) - integ(X, X.D, a));
}

// ---- meteors: one per sung line ----------------------------------------------------------
// Each radiates from near the pole, so together they make rays round it. Directions follow the golden angle
// (spread evenly, never clumped), skipping the ones that would point down at the two of them.
function meteorsFor(X, seed) {
  const lines = sEv('line').filter(e => e[0] >= X.open - 0.05 && e[0] < X.close - 0.2);
  const out = [], GOLD = rad(137.508);
  let a = rad(-38 + 31 * seed), k = 0;
  for (const [t, s] of lines) {
    let ang;
    do { ang = ((a + k * GOLD) % TAU + TAU) % TAU; k++; } while (Math.abs(ang - Math.PI / 2) < rad(42));
    const down = Math.max(0, Math.sin(ang));            // 1 pointing straight down
    const r0 = 120 + 110 * HS(k, seed);
    const len = Math.min((200 + 250 * (s || 0.6)) * (0.85 + 0.3 * HS(k, seed + 1)), lerp(560, 290, down) - r0);
    out.push({ t: Math.max(X.open + 0.02, t - 1 / FPS), dur: 0.30 + 0.12 * HS(k, seed + 2), ang, r0, len, s: s || 0.6, w: 2.0 + 2.2 * (s || 0.6), hue: HS(k, seed + 3) });
  }
  return out;
}
