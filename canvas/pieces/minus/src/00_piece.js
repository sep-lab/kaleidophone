'use strict';
/* ============================================================
   ( - )   —   Sep The Concept · بول شت استودیو
   A Flash-quality cartoon about a space nobody is in.
   One file, three modes:
     live    : click → procedural pad, or drop a WAV → AnalyserNode drives it. Loops forever.
     render  : ?render=1&w=1080&h=1920   → window.__frame({t,bass,mid,high,rms,flux})
     cover   : ?cover=1&size=3000        → window.__cover(variant)
   Rule of the film: she is never drawn. Wherever she would be, the
   picture is cut back to bare paper. Anything that enters the cut stops.
   ============================================================ */
const Q = new URLSearchParams(location.search);
const RENDER = Q.get('render') === '1';
const COVER  = Q.get('cover') === '1';

// ---- the track grid (final master, 2026-09-24) -------------------------
const DUR = 177.6;           // seconds
const T0  = 5.95;            // first downbeat
const BAR = 2.4;             // 100 BPM, 4/4 — 69 full bars, fade-out from ~166.75
const SCENE = 8 * BAR;       // 19.2 s per scene, eight scenes = one day
const CODA_T = T0 + 8 * SCENE;   // 159.55: the next sunrise, under the fade
const DRAW_FPS = 12;         // animation on twos — the Flash look

// ---- palette: ink on paper, one red -----------------------------------
const C = {
  paper: '#ede6d6', ink: '#17140f', grey: '#8f887c', grey2: '#cbc3b2',
  dark: '#2b2723', night: '#1a1714', red: '#c9301c', black: '#0d0c0a'
};

const cv = document.getElementById('c');
const ctx = cv.getContext('2d', { alpha: false });
let W = 1080, H = 1920, S = 1;
function setSize(w, h) { W = w; H = h; cv.width = w; cv.height = h; S = Math.min(W / 1080, H / 1920); }

// ---- boil: every point of every line wobbles, freshly, 12 times a second
let seed = 0, amp = 1.4, ji = 0;
function hsh(a, b) {
  let h = Math.imul(a ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul(b + 0x7F4A7C15, 0xC2B2AE35);
  h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; return (h >>> 0) / 4294967296;
}
function J() { ji++; return (hsh(seed, ji) * 2 - 1) * amp * S; }
function R(k) { return hsh(seed * 7919 + 13, k); }          // per-frame random, stable within frame
function LW(k = 1) { return 7 * S * k; }
const TAU = Math.PI * 2, rad = d => d * Math.PI / 180;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, u) => a + (b - a) * u;
const ease = u => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
const step = (t, a, b) => ease((t - a) / (b - a));          // 0→1 between a and b
const stepT = t => Math.floor(t * DRAW_FPS) / DRAW_FPS;     // quantise to twos

// ---- primitives -------------------------------------------------------
function ink(color = C.ink, lw = LW()) { ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; }
function path(pts, close) {
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) { const x = pts[i][0] + J(), y = pts[i][1] + J(); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  if (close) ctx.closePath();
}
function stroke(pts, color, lw) { ink(color, lw); path(pts, false); ctx.stroke(); }
function poly(pts, fill, strokeC, lw) {
  path(pts, true);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (strokeC) { ink(strokeC, lw); ctx.stroke(); }
}
function circ(cx, cy, r, fill, strokeC, lw, n) {
  n = n || clamp(Math.round(r / (6 * S)) + 10, 10, 40);
  const pts = []; for (let i = 0; i < n; i++) { const a = i / n * TAU; pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); }
  poly(pts, fill, strokeC, lw);
}
function ell(cx, cy, rx, ry, fill, strokeC, lw, n = 20) {
  const pts = []; for (let i = 0; i < n; i++) { const a = i / n * TAU; pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]); }
  poly(pts, fill, strokeC, lw);
}
function rect(x, y, w, h, fill, strokeC, lw) { poly([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], fill, strokeC, lw); }
function flat(x, y, w, h, fill) { ctx.fillStyle = fill; ctx.fillRect(x, y, w, h); }   // no boil: sky, floors
function capsule(x1, y1, x2, y2, r, fill, strokeC, lw) {
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, px = -uy, py = ux;
  const pts = [], n = 7;
  // bottom cap: from the right side, around the far end, to the left side
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x2 + (px * Math.cos(a) + ux * Math.sin(a)) * r, y2 + (py * Math.cos(a) + uy * Math.sin(a)) * r]); }
  // top cap: from the left side, around the near end, back to the right side
  for (let i = 0; i <= n; i++) { const a = i / n * Math.PI; pts.push([x1 - (px * Math.cos(a) + ux * Math.sin(a)) * r, y1 - (py * Math.cos(a) + uy * Math.sin(a)) * r]); }
  poly(pts, fill, strokeC, lw);
}
function arcPts(cx, cy, r, a0, a1, n) { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; p.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return p; }

// ---- the figure rig ---------------------------------------------------
// f = { x, y (feet) | hy (hips), r (head radius), view:'side'|'front'|'back', dir:±1,
//       legN,legF,armN,armF: [a1,a2] radians (a1 from straight-down toward 'forward', a2 = joint bend),
//       handN,handF:'fist'|'open', eyes:'open'|'closed'|'down', sil:bool (paper cut-out), she:bool (long hair),
//       fill (body), lean, headTurn: 0..1 (back view → side view), item:{kind,ang} on near hand }
function fig(f) {
  const r = f.r, view = f.view || 'side', dir = f.dir == null ? 1 : f.dir, sil = !!f.sil;
  const inkC = sil ? C.paper : (f.ink || C.ink);
  const lw = sil ? LW(2.6) : LW(f.lw || 1);
  const legL = 1.5 * r, armL = 1.22 * r, bodyH = 2.3 * r;
  const x = f.x;
  const hipY = f.hy != null ? f.hy : f.y - 2 * legL * 0.97;
  const shY = hipY - bodyH, headY = shY - 1.3 * r;
  const legN = f.legN || [0, 0], legF = f.legF || [0, 0], armN = f.armN || [0.08, 0.05], armF = f.armF || [0.08, 0.05];
  const seg = (ox, oy, len, a, sg) => [ox + Math.sin(a) * sg * len, oy + Math.cos(a) * len];
  function limb(ox, oy, angs, len, sg) {
    const m = seg(ox, oy, len, angs[0], sg), e = seg(m[0], m[1], len, angs[0] + angs[1], sg);
    stroke([[ox, oy], m, e], inkC, lw); return { m, e, a: angs[0] + angs[1] };
  }
  function hand(p, kind, a, sg) {
    if (sil) { circ(p[0], p[1], 0.36 * r, C.paper, null, 0, 10); return; }
    circ(p[0], p[1], 0.24 * r, C.paper, inkC, lw * 0.9, 10);
    if (kind === 'open') { for (let k = -1; k <= 1; k++) { const b = a + k * 0.5; const e = seg(p[0], p[1], 0.42 * r, b, sg); stroke([[p[0] + (e[0] - p[0]) * 0.55, p[1] + (e[1] - p[1]) * 0.55], e], inkC, lw * 0.75); } }
  }
  function item(p, a, sg) {
    const it = f.item; if (!it) return;
    if (it.kind === 'flower') {
      const ang = it.ang == null ? Math.PI : it.ang;          // from straight-down; PI = straight up
      const tip = seg(p[0], p[1], (it.len || 1.7) * r, ang, sg);
      stroke([p, [lerp(p[0], tip[0], 0.5) + 0.1 * r, lerp(p[1], tip[1], 0.5)], tip], sil ? C.paper : C.ink, lw * 0.8);
      const leaf = seg(lerp(p[0], tip[0], 0.45), lerp(p[1], tip[1], 0.45), 0.5 * r, ang + 1.1, sg);
      stroke([[lerp(p[0], tip[0], 0.45), lerp(p[1], tip[1], 0.45)], leaf], sil ? C.paper : C.ink, lw * 0.8);
      for (let k = 0; k < 5; k++) { const b = k / 5 * TAU + 0.3; circ(tip[0] + Math.cos(b) * 0.3 * r, tip[1] + Math.sin(b) * 0.3 * r, 0.26 * r, sil ? C.paper : C.red, sil ? null : C.ink, lw * 0.7, 10); }
      circ(tip[0], tip[1], 0.2 * r, sil ? C.paper : C.ink, null, 0, 10);
    } else if (it.kind === 'phone') {
      const w = 0.9 * r, h = 1.5 * r; rect(p[0] - w / 2, p[1] - h * 0.8, w, h, sil ? C.paper : C.paper, sil ? null : C.ink, lw * 0.8);
    } else if (it.kind === 'plate') {
      ell(p[0], p[1], 0.95 * r, 0.28 * r, sil ? C.paper : C.paper, sil ? null : C.ink, lw * 0.8);
    }
  }
  const bodyFill = sil ? C.paper : (f.fill || C.grey2);
  const headFill = sil ? C.paper : C.paper;

  if (view === 'side') {
    // far arm, far leg, body, near leg, head, near arm (+hand +item)
    const sh = [x - dir * 0.05 * r, shY + 0.15 * r], hp = [x, hipY];
    const fa = limb(sh[0], sh[1], armF, armL, dir); hand(fa.e, f.handF, fa.a, dir);
    limb(hp[0], hp[1], legF, legL, dir);
    capsule(x, shY + 0.1 * r, x, hipY, 0.78 * r, bodyFill, sil ? null : inkC, lw);
    limb(hp[0], hp[1], legN, legL, dir);
    // head
    if (sil) {
      circ(x, headY, 1.08 * r, C.paper, null, 0, 16);
      if (f.she) { // long hair down the back
        const pts = arcPts(x, headY, 1.12 * r, rad(-95), rad(-95) - Math.PI * dir, 8);
        pts.push([x - dir * 1.1 * r, shY + 0.9 * r], [x - dir * 0.2 * r, shY + 0.9 * r], [x + dir * 0.1 * r, shY - 0.2 * r]);
        poly(pts, C.paper, null, 0);
      }
    } else {
      circ(x, headY, r, headFill, inkC, lw, 16);
      // hair cap
      const hp2 = arcPts(x, headY, 1.03 * r, dir > 0 ? rad(-200) : rad(20), dir > 0 ? rad(-40) : rad(-140), 10);
      hp2.push([x - dir * 0.15 * r, headY - 0.35 * r], [x - dir * 0.75 * r, headY + 0.25 * r]);
      poly(hp2, inkC, null, 0);
      if (f.she) { const pts = arcPts(x, headY, 1.05 * r, rad(-95), rad(-95) - Math.PI * dir, 8); pts.push([x - dir * 1.0 * r, shY + 0.8 * r], [x - dir * 0.2 * r, shY + 0.8 * r]); poly(pts, inkC, null, 0); }
      // face
      const ex = x + dir * 0.42 * r, ey = headY - 0.08 * r;
      if (f.eyes === 'closed') stroke([[ex - 0.14 * r, ey], [ex + 0.14 * r, ey]], inkC, lw * 0.8);
      else if (f.eyes === 'down') circ(ex + dir * 0.02 * r, ey + 0.12 * r, 0.09 * r, inkC, null, 0, 8);
      else circ(ex, ey, 0.1 * r, inkC, null, 0, 8);
      stroke([[x + dir * 0.35 * r, headY + 0.45 * r], [x + dir * 0.7 * r, headY + 0.45 * r]], inkC, lw * 0.8);   // the dash
    }
    const na = limb(sh[0] + dir * 0.1 * r, sh[1], armN, armL, dir); hand(na.e, f.handN, na.a, dir); item(na.e, na.a, dir);
  } else {
    // front / back : arms fall to either side; 'forward' for arm L is screen-left in front view, screen-right in back view
    const sgnR = view === 'front' ? -1 : 1;
    const hipL = [x - 0.35 * r, hipY], hipR = [x + 0.35 * r, hipY];
    const legLa = f.legF || [0.04, 0], legRa = f.legN || [0.04, 0];
    // legs: a1 measured outward
    if (!f.noLegs) { limb(hipL[0], hipL[1], legLa, legL, -1); limb(hipR[0], hipR[1], legRa, legL, 1); }
    capsule(x, shY + 0.05 * r, x, hipY, 0.95 * r, bodyFill, sil ? null : inkC, lw);
    const shL = [x - 0.9 * r, shY + 0.2 * r], shR = [x + 0.9 * r, shY + 0.2 * r];
    const armLa = view === 'front' ? (f.armN || [0.12, 0]) : (f.armF || [0.12, 0]);   // figure's right arm = screen-left in front view
    const armRa = view === 'front' ? (f.armF || [0.12, 0]) : (f.armN || [0.12, 0]);
    // head
    if (sil) {
      circ(x, headY, 1.08 * r, C.paper, null, 0, 16);
      if (f.she) { poly([[x - 1.15 * r, headY - 0.2 * r], [x - 1.2 * r, shY + 0.9 * r], [x + 1.2 * r, shY + 0.9 * r], [x + 1.15 * r, headY - 0.2 * r], [x, headY - 1.2 * r]], C.paper, null, 0); }
    } else {
      circ(x, headY, r, headFill, inkC, lw, 16);
      const cap = arcPts(x, headY, 1.03 * r, rad(-195), rad(15), 12); cap.push([x + 0.85 * r, headY - 0.05 * r], [x + 0.35 * r, headY - 0.5 * r], [x - 0.35 * r, headY - 0.5 * r], [x - 0.85 * r, headY - 0.05 * r]);
      poly(cap, inkC, null, 0);
      if (f.she) { poly([[x - 1.1 * r, headY - 0.1 * r], [x - 1.15 * r, shY + 0.8 * r], [x - 0.7 * r, shY + 0.8 * r], [x - 0.75 * r, headY + 0.2 * r]], inkC, null, 0); poly([[x + 1.1 * r, headY - 0.1 * r], [x + 1.15 * r, shY + 0.8 * r], [x + 0.7 * r, shY + 0.8 * r], [x + 0.75 * r, headY + 0.2 * r]], inkC, null, 0); }
      if (view === 'front') {
        const ey = headY - 0.05 * r;
        if (f.eyes === 'closed') { stroke([[x - 0.45 * r, ey], [x - 0.2 * r, ey]], inkC, lw * 0.8); stroke([[x + 0.2 * r, ey], [x + 0.45 * r, ey]], inkC, lw * 0.8); }
        else { const dy = f.eyes === 'down' ? 0.12 * r : 0; circ(x - 0.33 * r, ey + dy, 0.1 * r, inkC, null, 0, 8); circ(x + 0.33 * r, ey + dy, 0.1 * r, inkC, null, 0, 8); }
        stroke([[x - 0.22 * r, headY + 0.45 * r], [x + 0.22 * r, headY + 0.45 * r]], inkC, lw * 0.8);   // the dash
      }
    }
    const la = limb(shL[0], shL[1], armLa, armL, -1); hand(la.e, view === 'front' ? f.handN : f.handF, la.a, -1);
    const ra = limb(shR[0], shR[1], armRa, armL, 1); hand(ra.e, view === 'front' ? f.handF : f.handN, ra.a, 1);
    if (f.item) { const p = f.itemSide === 'L' ? la : ra; item(p.e, p.a, f.itemSide === 'L' ? -1 : 1); }
  }
  return { headY, shY, hipY };
}
// walking cycle helper: phase φ → limbs
function walk(phi, k = 1) {
  const s = Math.sin(phi), c = Math.cos(phi);
  return {
    legN: [0.5 * s * k, -0.75 * Math.max(0, -s) * k], legF: [-0.5 * s * k, -0.75 * Math.max(0, s) * k],
    armN: [-0.4 * s * k, 0.35 * k], armF: [0.4 * s * k, 0.35 * k], bob: Math.abs(c) * 0.12 * k
  };
}

// ---- paper grain ------------------------------------------------------
const grains = [];
function makeGrain() {
  // seeded (mulberry32) so two renders of the same frame are identical; the shipped film used
  // Math.random() here, which made its paper grain differ from render to render
  let rs = 0x2545F491;
  const rnd = () => { rs = rs + 0x6D2B79F5 | 0; let q = Math.imul(rs ^ rs >>> 15, 1 | rs); q = q + Math.imul(q ^ q >>> 7, 61 | q) ^ q; return ((q ^ q >>> 14) >>> 0) / 4294967296; };
  for (let g = 0; g < 3; g++) {
    const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d');
    const im = x.createImageData(256, 256); const d = im.data;
    for (let i = 0; i < d.length; i += 4) { const v = 128 + (rnd() * 2 - 1) * 60; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
    x.putImageData(im, 0, 0); grains.push(c);
  }
}
function grain(alpha) {
  if (!grains.length) makeGrain();
  const g = grains[seed % 3]; const pat = ctx.createPattern(g, 'repeat');
  ctx.save(); ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = alpha;
  ctx.translate((seed * 37) % 256, (seed * 91) % 256); ctx.fillStyle = pat; ctx.fillRect(-256, -256, W + 512, H + 512); ctx.restore();
}

// ============================================================
//  SCENES — each is a pure function of local time `u` (s) + env
// ============================================================
const bar = u => u / BAR;                        // local bar number (float)
const G = () => ({ r: 54 * S });                  // standard figure size

function scTitle(t, env) {
  flat(0, 0, W, H, C.paper);
  const cy = H * 0.5, Rr = W * 0.23, lw = LW(2.6);
  const k1 = step(t, 0.4, 1.5), k2 = step(t, 1.7, 2.8), k3 = step(t, 3.3, 3.9);
  const aSpan = rad(62);
  if (k1 > 0) { const pts = arcPts(W * 0.34 + Rr, cy, Rr, Math.PI - aSpan, Math.PI - aSpan + 2 * aSpan * k1, 14); stroke(pts, C.ink, lw); }
  if (k2 > 0) { const pts = arcPts(W * 0.66 - Rr, cy, Rr, -aSpan, -aSpan + 2 * aSpan * k2, 14); stroke(pts, C.ink, lw); }
  if (k3 > 0) { const L = W * 0.11 * k3; stroke([[W * 0.5 - L / 2, cy], [W * 0.5 + L / 2, cy]], C.ink, lw); }
}

// ---- 1 · SUNRISE (back view, rooftop) ----------------------------------
function scSunrise(u, env, opt = {}) {
  const b = bar(u);
  const horizon = H * 0.40;
  const sky = b < 2 ? C.dark : b < 5 ? C.grey : C.grey2;
  flat(0, 0, W, H, sky);
  // sun: a dash of light first, then a disc
  const sunR = 112 * S, sunX = W * 0.52;
  const rise = step(u, 1 * BAR, 7.5 * BAR);                       // 0..1
  const sunY = horizon + sunR * 1.05 - rise * sunR * 2.6;
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, horizon); ctx.clip();
  circ(sunX, sunY + (env.bass * 3 * S), sunR, C.paper, null, 0, 30);
  ctx.restore();
  // horizon: the first dash of the film
  stroke([[0, horizon], [W, horizon]], C.ink, LW(0.9));
  // far city: dark blocks, the middle left open for the sun
  const blocks = [[0.0, 0.10], [0.11, 0.06], [0.2, 0.13], [0.31, 0.045], [0.68, 0.04], [0.77, 0.11], [0.88, 0.07], [0.97, 0.05]];
  for (const [bx, bh] of blocks) rect(bx * W, horizon - bh * H, 0.1 * W, bh * H + 4, C.night, null, 0);
  // birds: a pair
  if (b > 4.6 && b < 6.4) {
    const k = (b - 4.6) / 1.8; const bx = W * (1.05 - k * 1.1), by = H * 0.14 + Math.sin(k * 9) * 12 * S;
    for (const o of [0, 70 * S]) { const fl = (Math.floor(u * 6) % 2) ? 10 * S : -8 * S; stroke([[bx + o - 22 * S, by + fl], [bx + o, by], [bx + o + 22 * S, by + fl]], C.ink, LW(0.8)); }
  }
  // roof floor beyond the parapet is hidden; figures stand behind the wall
  const feet = H * 0.72, r = 60 * S;
  const point = opt.noPoint ? 0 : step(u, 4 * BAR, 4 * BAR + 0.5) * (1 - step(u, 6 * BAR, 8 * BAR));   // arm up at bar 4, slowly down 6→8
  const turn = opt.noPoint ? 0 : step(u, 4 * BAR + 0.3, 4 * BAR + 0.55) * (1 - step(u, 5.4 * BAR, 5.4 * BAR + 0.3));
  const him = { x: W * 0.38, y: feet, r, view: turn > 0.5 ? 'side' : 'back', dir: 1, fill: C.grey2,
    armN: [lerp(0.1, rad(142), point), lerp(0, rad(-6), point)], armF: [0.1, 0], eyes: 'open' };
  fig(him);
  if (opt.withHer !== false) fig({ x: W * 0.63, y: feet, r: r * 0.96, view: 'back', sil: true, she: true });
  // parapet in front of them
  const wallY = H * 0.585;
  rect(-10, wallY, W + 20, H * 0.13, b < 2 ? C.dark : C.grey, C.ink, LW(0.9));
  flat(0, wallY + H * 0.13, W, H, b < 2 ? C.night : C.dark);
  stroke([[0, wallY + H * 0.13], [W, wallY + H * 0.13]], C.ink, LW(0.9));
}

// ---- 2 · THE CROSSING (front view, across the road) --------------------
function scCrossing(u, env) {
  const b = bar(u);
  flat(0, 0, W, H, C.grey2);                                   // day sky
  // far buildings
  const bl = [[0, 0.30, 0.16], [0.16, 0.22, 0.14], [0.30, 0.34, 0.2], [0.5, 0.26, 0.18], [0.68, 0.36, 0.17], [0.85, 0.24, 0.16]];
  for (const [bx, bh, bw] of bl) {
    rect(bx * W, H * 0.52 - bh * H, bw * W, bh * H + 6, C.grey, C.ink, LW(0.8));
    for (let wy = 0; wy < 3; wy++) for (let wx = 0; wx < 2; wx++) { const lit = hsh(1, bx * 100 + wy * 7 + wx) > 0.6; rect((bx + 0.03 + wx * 0.07) * W, H * 0.52 - bh * H + (0.04 + wy * 0.06) * H, 0.04 * W, 0.035 * H, lit ? C.paper : C.dark, null, 0); }
  }
  // far sidewalk + curb
  flat(0, H * 0.52, W, H * 0.06, C.grey2); stroke([[0, H * 0.52], [W, H * 0.52]], C.ink, LW(0.8)); stroke([[0, H * 0.58], [W, H * 0.58]], C.ink, LW(0.9));
  // road
  flat(0, H * 0.58, W, H * 0.30, C.grey);
  // zebra: - - - - (perspective dashes)
  for (let i = 0; i < 6; i++) {
    const k = i / 5; const y = H * (0.605 + k * 0.245), h = H * (0.018 + k * 0.02), w = W * (0.56 + k * 0.5);
    rect(W / 2 - w / 2, y, w, h, C.paper, C.ink, LW(0.7));
  }
  // near curb
  stroke([[0, H * 0.88], [W, H * 0.88]], C.ink, LW(0.9)); flat(0, H * 0.88, W, H * 0.12, C.grey2);
  // pedestrians on the far sidewalk: pairs
  const pairs = [[1.4, 1], [5.3, -1]];
  for (const [pb, pd] of pairs) {
    const k = (b - pb) / 2.2; if (k < 0 || k > 1) continue;
    const px = pd > 0 ? W * (-0.1 + k * 1.2) : W * (1.1 - k * 1.2); const phi = u * TAU / 1.2;
    for (const off of [0, 1.9]) { const wk = walk(phi + off * 2); fig({ x: px + off * 34 * S, y: H * 0.58 - 2 * S + wk.bob * 20 * S, r: 30 * S, view: 'side', dir: pd, fill: C.grey, ...wk, she: off > 0 }); }
  }
  // signal pole
  const px = W * 0.86; stroke([[px, H * 0.58], [px, H * 0.30]], C.ink, LW(1.1));
  rect(px - 0.055 * W, H * 0.24, 0.11 * W, 0.075 * H, C.dark, C.ink, LW(0.9));
  const go = b >= 5;
  const icon = { x: px, y: H * 0.305, r: 9 * S, view: 'side', dir: 1, ink: C.paper, fill: C.dark, lw: 0.55 };
  if (go) { const wk = walk(u * TAU / 0.8, 1.2); Object.assign(icon, wk); }
  fig(icon);
  // him, facing us; her void on his right (screen-left)
  const feet = H * 0.86, r = 60 * S;
  const reach = step(u, 3 * BAR, 3 * BAR + 1.0) * (1 - step(u, 5 * BAR, 5 * BAR + 0.7));
  const open = reach > 0.15 ? 'open' : 'fist';
  fig({ x: W * 0.56, y: feet, r, view: 'front', fill: C.grey2, eyes: b > 6.8 ? 'down' : 'open',
    armN: [lerp(0.12, rad(86), reach), 0], handN: open, armF: [0.12, 0] });
  fig({ x: W * 0.383, y: feet, r: r * 0.96, view: 'front', sil: true, she: true });
  // a car passing (in front, on the road) at bar 1 and 3.6
  for (const cb of [0.8, 3.6]) {
    const k = (b - cb) / 1.1; if (k < 0 || k > 1) continue;
    const cx = W * (-0.4 + k * 1.8), cy = H * 0.80, cw = W * 0.42, ch = H * 0.055;
    poly([[cx, cy], [cx + cw * 0.12, cy - ch * 0.9], [cx + cw * 0.55, cy - ch * 1.0], [cx + cw * 0.75, cy - ch * 0.5], [cx + cw, cy - ch * 0.45], [cx + cw, cy + ch * 0.2], [cx, cy + ch * 0.2]], C.dark, C.ink, LW(0.9));
    circ(cx + cw * 0.22, cy + ch * 0.25, ch * 0.32, C.ink, C.ink, LW(0.5), 12); circ(cx + cw * 0.8, cy + ch * 0.25, ch * 0.32, C.ink, C.ink, LW(0.5), 12);
  }
}

// ---- 3 · THE FLOWER (street, then the door) ----------------------------
function scFlower(u, env) {
  const b = bar(u);
  if (b < 3) {
    // evening street, side-scroll
    flat(0, 0, W, H, C.dark);
    const scroll = (u * 160 * S) % (W * 0.5);
    for (let i = -1; i < 4; i++) {
      const bx = i * W * 0.5 - scroll; const bh = H * (0.28 + 0.08 * ((i + 5) % 3));
      rect(bx, H * 0.70 - bh, W * 0.46, bh + 6, C.night, C.ink, LW(0.8));
      for (let wy = 0; wy < 4; wy++) for (let wx = 0; wx < 3; wx++) {
        const lit = hsh(2, i * 31 + wy * 7 + wx) > 0.45; const wxp = bx + W * (0.05 + wx * 0.13), wyp = H * 0.70 - bh + H * (0.04 + wy * 0.065);
        rect(wxp, wyp, W * 0.08, H * 0.04, lit ? C.paper : C.dark, null, 0);
        if (lit && hsh(3, i * 31 + wy * 7 + wx) > 0.7) { // a couple in the window
          circ(wxp + W * 0.028, wyp + H * 0.028, 7 * S, C.ink, null, 0, 8); circ(wxp + W * 0.052, wyp + H * 0.026, 7 * S, C.ink, null, 0, 8);
          rect(wxp + W * 0.018, wyp + H * 0.032, W * 0.044, H * 0.012, C.ink, null, 0);
        }
      }
    }
    stroke([[0, H * 0.70], [W, H * 0.70]], C.ink, LW(0.9)); flat(0, H * 0.70, W, H * 0.30, C.grey);
    const phi = u * TAU / 1.2, r = 60 * S, feet = H * 0.86;
    const wk = walk(phi, 1);
    fig({ x: W * 0.36, y: feet + wk.bob * 22 * S, r, view: 'side', dir: 1, fill: C.grey2, legN: wk.legN, legF: wk.legF, armF: wk.armF,
      armN: [rad(70), rad(70)], handN: 'fist', item: { kind: 'flower', ang: rad(165) } });
    const wk2 = walk(phi + 2.4, 1);
    fig({ x: W * 0.66, y: feet + wk2.bob * 22 * S, r: r * 0.96, view: 'side', dir: 1, sil: true, she: true, ...wk2 });
  } else {
    // inside: the hall. door on the left opens; she would be there to meet him.
    flat(0, 0, W, H, C.grey);
    flat(0, H * 0.80, W, H * 0.20, C.dark); stroke([[0, H * 0.80], [W, H * 0.80]], C.ink, LW(0.9));
    // door frame + door
    const dx = W * 0.05, dy = H * 0.26, dw = W * 0.30, dh = H * 0.54;
    rect(dx, dy, dw, dh, C.night, C.ink, LW(1));                         // the dark landing outside
    const open = step(u, 3 * BAR + 0.2, 3 * BAR + 1.2);
    rect(dx, dy, dw * (1 - open * 0.92), dh, C.grey2, C.ink, LW(1));      // the door swinging away
    // coat hooks: two. one coat.
    for (const hx of [0.60, 0.70]) { stroke([[W * hx, H * 0.33], [W * hx, H * 0.36]], C.ink, LW(1)); circ(W * hx, H * 0.365, 6 * S, C.ink, null, 0, 8); }
    poly([[W * 0.575, H * 0.37], [W * 0.625, H * 0.37], [W * 0.64, H * 0.52], [W * 0.56, H * 0.52]], C.grey2, C.ink, LW(0.9));   // his coat
    const r = 66 * S, feet = H * 0.80;
    const enter = step(u, 3 * BAR + 0.8, 4 * BAR + 0.6);
    const x = lerp(W * 0.10, W * 0.40, enter);
    const extend = step(u, 4.5 * BAR, 5 * BAR) * (1 - step(u, 6 * BAR, 6 * BAR + 0.5));
    const wk = enter < 1 ? walk(u * TAU / 1.2, 1) : { legN: [0, 0], legF: [0, 0], armF: [0.1, 0], bob: 0 };
    fig({ x, y: feet + (wk.bob || 0) * 22 * S, r, view: 'side', dir: 1, fill: C.grey2, legN: wk.legN, legF: wk.legF, armF: wk.armF,
      eyes: b > 6.5 ? 'down' : 'open', armN: [lerp(rad(70), rad(90), extend), lerp(rad(70), 0, extend)], handN: 'fist',
      item: { kind: 'flower', ang: lerp(rad(165), rad(80), extend), len: lerp(1.7, 1.5, extend) } });
    fig({ x: W * 0.632, y: feet, r: r * 0.96, view: 'side', dir: -1, sil: true, she: true });
  }
}

// ---- 4 · TWO PLATES (side view, night kitchen) -------------------------
function scPlates(u, env) {
  const b = bar(u);
  flat(0, 0, W, H, C.night);
  // lamp + cone of light
  const lx = W * 0.5, ly = H * 0.22;
  stroke([[lx, 0], [lx, ly]], C.grey, LW(0.8));
  poly([[lx - W * 0.16, H * 0.90], [lx + W * 0.16, H * 0.90], [lx + W * 0.5, H * 1.0], [lx - W * 0.5, H * 1.0]], C.night, null, 0);
  poly([[lx - W * 0.06, ly], [lx + W * 0.06, ly], [lx + W * 0.62, H * 0.98], [lx - W * 0.62, H * 0.98]], C.dark, null, 0);
  poly([[lx - W * 0.06, ly], [lx + W * 0.06, ly], [lx + W * 0.48, H * 0.86], [lx - W * 0.48, H * 0.86]], C.grey, null, 0);
  poly([[lx - W * 0.07, ly - H * 0.01], [lx + W * 0.07, ly - H * 0.01], [lx + W * 0.11, ly + H * 0.04], [lx - W * 0.11, ly + H * 0.04]], C.dark, C.ink, LW(0.9));
  // floor
  stroke([[0, H * 0.84], [W, H * 0.84]], C.ink, LW(0.9));
  // table: the long dash
  const ty = H * 0.60, tx0 = W * 0.22, tx1 = W * 0.78;
  const r = 58 * S, seatY = H * 0.655;
  // chairs
  for (const cx of [W * 0.22, W * 0.78]) {
    const d = cx < W / 2 ? -1 : 1;
    stroke([[cx + d * 0.05 * W, seatY], [cx + d * 0.05 * W, H * 0.84]], C.ink, LW(1)); stroke([[cx - d * 0.05 * W, seatY], [cx - d * 0.05 * W, H * 0.84]], C.ink, LW(1));
    stroke([[cx + d * 0.06 * W, seatY], [cx + d * 0.06 * W, H * 0.44]], C.ink, LW(1));
    rect(cx - 0.065 * W, seatY - 6 * S, 0.13 * W, 12 * S, C.grey2, C.ink, LW(0.9));
  }
  // plate motion: push / pull on the hits (bars 3,4,5,6), she'd be on the right
  let slide = 0;
  slide += step(u, 3 * BAR, 3 * BAR + 0.35); slide -= step(u, 4 * BAR, 4 * BAR + 0.35);
  slide += step(u, 5 * BAR, 5 * BAR + 0.35); slide -= step(u, 6 * BAR, 6 * BAR + 0.35);
  const stand = step(u, 7 * BAR, 7 * BAR + 0.6);
  const leave = step(u, 7 * BAR + 0.7, 8 * BAR);
  // him
  const eatPhi = Math.floor(u * 4) % 2;
  const eating = b < 2;
  const hisX = lerp(W * 0.33, W * 0.14, leave);
  const pushArm = [lerp(rad(30), rad(95), Math.max(0, Math.min(1, slide + (step(u, 3 * BAR, 3 * BAR + 0.35) > 0 ? 0 : 0)))), rad(-5)];
  const armN = eating ? [eatPhi ? rad(65) : rad(40), eatPhi ? rad(85) : rad(60)] : (b < 3 ? [rad(30), rad(20)] : pushArm);
  if (stand < 1) {
    fig({ x: hisX, hy: seatY - 4 * S + stand * -H * 0.06, r, view: 'side', dir: 1, fill: C.grey2, eyes: b >= 2 ? 'down' : 'open',
      legN: [lerp(rad(88), 0, stand), lerp(rad(-88), 0, stand)], legF: [lerp(rad(84), 0, stand), lerp(rad(-84), 0, stand)],
      armN, armF: [rad(35), rad(30)] });
  } else {
    const wk = leave > 0 ? walk(u * TAU / 1.2, 1) : { legN: [0, 0], legF: [0, 0], armF: [0.1, 0], bob: 0 };
    fig({ x: hisX, y: H * 0.84 + (wk.bob || 0) * 20 * S, r, view: 'side', dir: -1, fill: C.grey2, eyes: 'down', legN: wk.legN, legF: wk.legF,
      armN: [rad(70), rad(30)], handN: 'fist', item: { kind: 'plate' }, armF: wk.armF });
  }
  // table top drawn over his lap
  rect(tx0, ty - 10 * S, tx1 - tx0, 20 * S, C.grey2, C.ink, LW(1));
  stroke([[tx0 + 0.03 * W, ty + 10 * S], [tx0 + 0.03 * W, H * 0.84]], C.ink, LW(1)); stroke([[tx1 - 0.03 * W, ty + 10 * S], [tx1 - 0.03 * W, H * 0.84]], C.ink, LW(1));
  // his plate + steam
  ell(W * 0.40, ty - 12 * S, 0.075 * W, 0.022 * W, C.paper, C.ink, LW(0.9));
  ell(W * 0.40, ty - 16 * S, 0.045 * W, 0.012 * W, C.grey, C.ink, LW(0.6));
  for (let k = 0; k < 3; k++) {
    const sx = W * (0.375 + k * 0.025); const ph = u * 2 + k; const pts = [];
    for (let i = 0; i <= 4; i++) pts.push([sx + Math.sin(ph + i * 1.3) * 9 * S * (1 + env.mid), ty - 30 * S - i * 22 * S]);
    stroke(pts, C.grey2, LW(0.6));
  }
  // her plate (empty) — slides toward her and back
  if (stand < 1) ell(W * (0.60 + 0.07 * slide), ty - 12 * S, 0.075 * W, 0.022 * W, C.paper, C.ink, LW(0.9));
  // the flower in a glass, centre
  rect(W * 0.5 - 12 * S, ty - 88 * S, 24 * S, 78 * S, C.grey2, C.ink, LW(0.8));
  stroke([[W * 0.5, ty - 80 * S], [W * 0.5 + 6 * S, ty - 150 * S]], C.ink, LW(0.8));
  for (let k = 0; k < 5; k++) { const a = k / 5 * TAU + 0.3; circ(W * 0.5 + 6 * S + Math.cos(a) * 15 * S, ty - 150 * S + Math.sin(a) * 15 * S, 13 * S, C.red, C.ink, LW(0.7), 10); }
  circ(W * 0.5 + 6 * S, ty - 150 * S, 10 * S, C.ink, null, 0, 10);
  // her: seated on the right, facing him
  fig({ x: W * 0.67, hy: seatY - 4 * S, r: r * 0.96, view: 'side', dir: -1, sil: true, she: true,
    legN: [rad(88), rad(-88)], legF: [rad(84), rad(-84)], armN: [rad(35), rad(30)], armF: [rad(35), rad(30)] });
}

// ---- 5 · THE GALLERY (bed from above, then the phone) ------------------
function miniPhoto(x, y, w, h, kind, zoomOn) {
  // a tiny drawn photo of the two of them; she is paper in every one
  ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  const s = w / 300;
  const r = 26 * s;
  if (kind === 0) { // sunrise from behind
    flat(x, y, w, h, C.grey); circ(x + w * 0.5, y + h * 0.36, w * 0.13, C.paper, null, 0, 16); stroke([[x, y + h * 0.5], [x + w, y + h * 0.5]], C.ink, LW(0.5));
    flat(x, y + h * 0.5, w, h * 0.5, C.dark);
    fig({ x: x + w * 0.4, y: y + h * 1.08, r, view: 'back', fill: C.grey2, lw: 0.5 }); fig({ x: x + w * 0.6, y: y + h * 1.08, r: r * 0.96, view: 'back', sil: true, she: true });
  } else if (kind === 1) { // beach
    flat(x, y, w, h, C.grey2); flat(x, y + h * 0.55, w, h * 0.45, C.grey); stroke([[x, y + h * 0.55], [x + w, y + h * 0.55]], C.ink, LW(0.5));
    fig({ x: x + w * 0.42, y: y + h * 0.95, r: r * 0.9, view: 'front', fill: C.grey2, lw: 0.5, armN: [rad(40), 0], armF: [rad(10), 0] }); fig({ x: x + w * 0.62, y: y + h * 0.95, r: r * 0.86, view: 'front', sil: true, she: true });
  } else { // a table, two cups
    flat(x, y, w, h, C.dark); rect(x + w * 0.1, y + h * 0.6, w * 0.8, h * 0.08, C.grey2, C.ink, LW(0.5));
    fig({ x: x + w * 0.35, hy: y + h * 0.66, r: r * 0.9, view: 'side', dir: 1, fill: C.grey2, lw: 0.5, legN: [rad(85), rad(-85)], legF: [rad(85), rad(-85)] });
    fig({ x: x + w * 0.66, hy: y + h * 0.66, r: r * 0.86, view: 'side', dir: -1, sil: true, she: true, legN: [rad(85), rad(-85)], legF: [rad(85), rad(-85)] });
  }
  ctx.restore();
  ink(C.ink, LW(0.6)); ctx.strokeRect(x + J(), y + J(), w, h);
}
function scGallery(u, env) {
  const b = bar(u);
  flat(0, 0, W, H, C.black);
  if (b < 2) {
    // the bed from above. the phone is the only light.
    rect(W * 0.1, H * 0.12, W * 0.8, H * 0.8, C.dark, C.grey, LW(1));
    rect(W * 0.14, H * 0.15, W * 0.32, H * 0.12, C.grey, C.ink, LW(0.8)); rect(W * 0.54, H * 0.15, W * 0.32, H * 0.12, C.grey, C.ink, LW(0.8));
    const r = 60 * S;
    fig({ x: W * 0.32, hy: H * 0.55, r, view: 'front', fill: C.grey, armN: [rad(38), rad(-150)], armF: [rad(38), rad(-150)], legN: [0.02, 0], legF: [0.02, 0] });
    // the phone over his chest, lit — his face stays visible above it
    rect(W * 0.255, H * 0.43, W * 0.13, H * 0.13, C.paper, C.ink, LW(0.9));
    // the sheet
    rect(W * 0.1, H * 0.62, W * 0.8, H * 0.3, C.grey2, C.ink, LW(0.9));
    fig({ x: W * 0.68, hy: H * 0.55, r: r * 0.96, view: 'front', sil: true, she: true });
  } else if (b < 7) {
    // the screen, full frame
    flat(0, 0, W, H, C.paper);
    const zoomOn = b >= 4;
    if (!zoomOn) {
      // grid, scrolling on the beats
      const scroll = Math.floor((u - 2 * BAR) / 0.6) * H * 0.11 + step(u % 0.6, 0.0, 0.25) * H * 0.11;
      const cw = W * 0.30, ch = W * 0.30, gap = W * 0.025;
      for (let row = -1; row < 12; row++) for (let col = 0; col < 3; col++) {
        const x = W * 0.035 + col * (cw + gap), y = H * 0.06 + row * (ch + gap) - scroll;
        if (y + ch < 0 || y > H) continue;
        miniPhoto(x, y, cw, ch, (row * 3 + col + 7) % 3);
      }
      flat(0, 0, W, H * 0.055, C.paper); stroke([[W * 0.05, H * 0.03], [W * 0.14, H * 0.03]], C.ink, LW(0.8));
    } else {
      // one photo opens, then zoom into her. by bar 6.5 the screen is all paper.
      const z = 1 + Math.pow(step(u, 4.3 * BAR, 6.6 * BAR), 1.6) * 26;
      const px = W * 0.05, py = H * 0.28, pw = W * 0.9, ph = W * 0.9;
      const fx = px + pw * 0.6, fy = py + ph * 0.55;  // where she is in photo 0
      ctx.save(); ctx.translate(fx, fy); ctx.scale(z, z); ctx.translate(-fx, -fy);
      miniPhoto(px, py, pw, ph, 0, true);
      ctx.restore();
    }
  } else {
    // the phone locks. dark.
  }
}

// ---- 3 · THE UMBRELLA (side view, rain) --------------------------------
function umbrella(hx, hy, cx, r, inkC) {
  // handle from the hand up to the canopy centre, canopy = scalloped dome
  stroke([[hx, hy], [cx, hy - 3.1 * r]], inkC, LW(0.9));
  const top = hy - 3.1 * r, R = 2.1 * r;
  const pts = arcPts(cx, top, R, Math.PI, TAU, 14);
  for (let k = 0; k < 6; k++) { const a = Math.PI + (k + 0.5) / 6 * Math.PI; pts.push([cx + Math.cos(a) * R * 0.94, top + Math.sin(a) * R * 0.94]); }
  // draw dome + a scalloped hem
  poly(arcPts(cx, top, R, Math.PI, TAU, 14).concat([[cx + R, top], [cx - R, top]]), C.dark, inkC, LW(0.9));
  for (let k = 0; k < 6; k++) { const x0 = cx - R + k / 6 * 2 * R, x1 = cx - R + (k + 1) / 6 * 2 * R; stroke([[x0, top], [(x0 + x1) / 2, top + 0.16 * r], [x1, top]], inkC, LW(0.8)); }
  return { cx, top, R };
}
function scUmbrella(u, env) {
  const b = bar(u);
  flat(0, 0, W, H, C.grey);
  // wet street, far buildings
  const scroll = (u * 150 * S) % (W * 0.5);
  for (let i = -1; i < 4; i++) {
    const bx = i * W * 0.5 - scroll; const bh = H * (0.22 + 0.07 * ((i + 4) % 3));
    rect(bx, H * 0.68 - bh, W * 0.46, bh + 6, C.dark, C.ink, LW(0.8));
    for (let wy = 0; wy < 3; wy++) for (let wx = 0; wx < 3; wx++) { const lit = hsh(4, i * 31 + wy * 7 + wx) > 0.55; rect(bx + W * (0.05 + wx * 0.13), H * 0.68 - bh + H * (0.04 + wy * 0.06), W * 0.08, H * 0.035, lit ? C.paper : C.night, null, 0); }
  }
  stroke([[0, H * 0.68], [W, H * 0.68]], C.ink, LW(0.9)); flat(0, H * 0.68, W, H * 0.32, C.grey2);
  // a couple under one umbrella, far side, walking the other way
  if (b > 1.5 && b < 5.5) {
    const k = (b - 1.5) / 4; const px = W * (1.15 - k * 1.35), phi = u * TAU / 1.2;
    for (const off of [0, 1.7]) { const wk = walk(phi + off * 2, 0.9); fig({ x: px + off * 34 * S, y: H * 0.68 - 2 * S + wk.bob * 16 * S, r: 34 * S, view: 'side', dir: -1, fill: C.grey, ...wk, she: off > 0 }); }
    umbrella(px + 30 * S, H * 0.68 - 2 * S - 34 * S * 5.5, px + 40 * S, 34 * S, C.ink);
  }
  const r = 60 * S, feet = H * 0.86, phi = u * TAU / 1.2;
  const tilt = step(u, 2 * BAR, 2 * BAR + 1.2);                  // umbrella slides over her
  const wk = walk(phi, 1), wk2 = walk(phi + 2.4, 1);
  const hisX = W * 0.33, herX = W * 0.62;
  // rain: short strokes, none under the canopy, fresh every frame
  const can = { cx: lerp(hisX + 0.3 * r, herX - 0.2 * r, tilt), top: feet - 2 * 1.5 * r * 0.97 - 2.3 * r - 1.3 * r - 2.2 * r - 0.1 * r, R: 2.1 * r };
  for (let i = 0; i < 260; i++) {
    const rx = R(i * 2) * W, ry = R(i * 2 + 1) * H * 0.98;
    if (Math.abs(rx - can.cx) < can.R && ry > can.top - 10 * S) continue;
    stroke([[rx, ry], [rx - 3 * S, ry + 26 * S]], C.grey2, LW(0.45));
  }
  fig({ x: hisX, y: feet + wk.bob * 22 * S, r, view: 'side', dir: 1, fill: C.grey2, legN: wk.legN, legF: wk.legF, armF: wk.armF,
    eyes: b > 5.5 ? 'open' : 'open', armN: [lerp(rad(35), rad(70), tilt), lerp(rad(60), rad(30), tilt)], handN: 'fist' });
  // the umbrella in his near hand
  const hy = feet + wk.bob * 22 * S - 2 * 1.5 * r * 0.97 - 2.3 * r + 0.15 * r;
  const a1 = lerp(rad(35), rad(70), tilt), a2 = lerp(rad(60), rad(30), tilt);
  const m = [hisX + 0.1 * r + Math.sin(a1) * 1.22 * r, hy + Math.cos(a1) * 1.22 * r];
  const hand = [m[0] + Math.sin(a1 + a2) * 1.22 * r, m[1] + Math.cos(a1 + a2) * 1.22 * r];
  umbrella(hand[0], hand[1], can.cx, r, C.ink);
  // once he's out from under it, the rain hits him: little splashes on his head
  if (tilt > 0.9) { const hy2 = feet - 2 * 1.5 * r * 0.97 - 2.3 * r - 1.3 * r - r; for (let k = 0; k < 3; k++) { const sx = hisX - 0.5 * r + k * 0.5 * r + (R(900 + k) - 0.5) * 20 * S; stroke([[sx - 8 * S, hy2 - 6 * S], [sx, hy2 - 16 * S], [sx + 8 * S, hy2 - 6 * S]], C.paper, LW(0.6)); } }
  fig({ x: herX, y: feet + wk2.bob * 22 * S, r: r * 0.96, view: 'side', dir: 1, sil: true, she: true, ...wk2 });
}

// ---- 6 · THE SOFA (front view, a film on, night) -----------------------
function scSofa(u, env) {
  const b = bar(u);
  // the screen is behind the camera: its light flickers on the room
  const fl = 0.35 + 0.65 * R(5) * (0.5 + env.high);
  const room = fl > 0.75 ? C.dark : C.night;
  flat(0, 0, W, H, room);
  // wall: a frame with a photo of two (she is paper in it too)
  rect(W * 0.62, H * 0.16, W * 0.22, W * 0.22, C.grey, C.ink, LW(0.8));
  fig({ x: W * 0.69, y: H * 0.16 + W * 0.215, r: 12 * S, view: 'front', fill: C.grey2, lw: 0.5 }); fig({ x: W * 0.77, y: H * 0.16 + W * 0.215, r: 11.5 * S, view: 'front', sil: true, she: true });
  // floor + rug
  stroke([[0, H * 0.80], [W, H * 0.80]], C.ink, LW(0.9)); flat(0, H * 0.80, W, H * 0.20, C.dark);
  // the sofa
  const sy = H * 0.60;
  rect(W * 0.08, sy - H * 0.16, W * 0.84, H * 0.16, C.grey, C.ink, LW(1));               // backrest
  rect(W * 0.04, sy, W * 0.92, H * 0.075, C.grey, C.ink, LW(1));                        // seat
  rect(W * 0.02, sy - H * 0.05, W * 0.07, H * 0.125, C.grey, C.ink, LW(1)); rect(W * 0.91, sy - H * 0.05, W * 0.07, H * 0.125, C.grey, C.ink, LW(1));
  const r = 60 * S, hisX = W * 0.40, herX = W * 0.62;
  const reach = step(u, 2 * BAR, 2 * BAR + 0.9);
  const eyes = b >= 7 ? 'down' : 'open';
  fig({ x: hisX, hy: sy + 4 * S, r, view: 'front', fill: C.grey2, eyes, legN: [0.16, 0], legF: [0.16, 0],
    armN: [0.15, 0], armF: [lerp(0.15, rad(96), reach), lerp(0, rad(-8), reach)], handF: 'open' });   // his left arm along the backrest, toward her
  // the blanket over both laps — it will end where she begins
  const by = sy - 6 * S; const pts = [];
  for (let i = 0; i <= 14; i++) pts.push([W * 0.16 + i / 14 * W * 0.68, by + Math.sin(i * 1.7) * 9 * S]);
  pts.push([W * 0.84, sy + H * 0.075], [W * 0.16, sy + H * 0.075]);
  poly(pts, C.grey2, C.ink, LW(0.9));
  // a bowl between them
  ell(W * 0.505, sy + 2 * S, 0.06 * W, 0.02 * W, C.paper, C.ink, LW(0.8));
  fig({ x: herX, hy: sy + 4 * S, r: r * 0.96, view: 'front', sil: true, she: true, noLegs: true });
}

// ---- 8 · THE NIGHT WINDOW (back view — the sunrise's rhyme) ------------
function scNightWindow(u, env) {
  const b = bar(u);
  flat(0, 0, W, H, C.night);
  // the window
  const wx = W * 0.10, wy = H * 0.16, ww = W * 0.80, wh = H * 0.46;
  ctx.save(); ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
  flat(wx, wy, ww, wh, C.dark);
  // moon: the same paper as her
  circ(W * 0.70, H * 0.26, 62 * S, C.paper, null, 0, 24);
  // buildings across the street, one lit window with a couple
  const bl = [[0.08, 0.20, 0.16], [0.26, 0.14, 0.14], [0.42, 0.24, 0.18], [0.62, 0.16, 0.14], [0.78, 0.22, 0.16]];
  for (const [bx, bh, bw] of bl) {
    rect(bx * W, H * 0.52 - bh * H, bw * W, bh * H + 6, C.night, C.ink, LW(0.8));
    for (let k = 0; k < 4; k++) { const lit = hsh(6, bx * 100 + k) > 0.62; const lx = (bx + 0.03 + (k % 2) * 0.06) * W, ly = H * 0.52 - bh * H + (0.03 + Math.floor(k / 2) * 0.05) * H; rect(lx, ly, 0.04 * W, 0.03 * H, lit ? C.paper : C.dark, null, 0);
      if (lit && k === 1) { circ(lx + 0.013 * W, ly + 0.02 * H, 6 * S, C.ink, null, 0, 8); circ(lx + 0.027 * W, ly + 0.019 * H, 6 * S, C.ink, null, 0, 8); } }
  }
  stroke([[wx, H * 0.52], [wx + ww, H * 0.52]], C.ink, LW(0.8)); flat(wx, H * 0.52, ww, H * 0.1, C.dark);
  // the street lamp: flickers, then dims (the lights went faint)
  const lx = W * 0.30, ly = H * 0.30;
  stroke([[lx, H * 0.52], [lx, ly]], C.ink, LW(1));
  const dim = step(u, 3 * BAR, 6 * BAR);
  const on = b < 3 ? true : (R(77) > 0.25 * (1 + dim));
  if (on) circ(lx + 14 * S, ly, (30 - 16 * dim) * S, C.paper, null, 0, 16);
  if (on) { ctx.save(); ctx.globalAlpha = 0.18 * (1 - dim); poly([[lx - W * 0.05, ly], [lx + W * 0.08, ly], [lx + W * 0.22, H * 0.52], [lx - W * 0.20, H * 0.52]], C.paper, null, 0); ctx.restore(); }
  // a couple passing under it
  if (b > 0.8 && b < 3.2) { const k = (b - 0.8) / 2.4; const px = W * (0.02 + k * 0.85), phi = u * TAU / 1.2;
    for (const off of [0, 1.7]) { const wk = walk(phi + off * 2, 0.9); fig({ x: px + off * 26 * S, y: H * 0.52 - 2 * S + wk.bob * 12 * S, r: 26 * S, view: 'side', dir: 1, fill: C.grey, ...wk, she: off > 0 }); } }
  ctx.restore();
  // frame + cross bars
  rect(wx, wy, ww, wh, null, C.ink, LW(1.3)); stroke([[wx + ww / 2, wy], [wx + ww / 2, wy + wh]], C.ink, LW(1.1)); stroke([[wx, wy + wh * 0.5], [wx + ww, wy + wh * 0.5]], C.ink, LW(1.1));
  // the sill, then the two of them from behind (waist up above the sill)
  const feet = H * 0.72, r = 60 * S;
  const hand = step(u, 4 * BAR, 4 * BAR + 0.7);                 // his palm goes to the glass at bar 4
  fig({ x: W * 0.38, y: feet, r, view: 'back', fill: C.grey2, armN: [lerp(0.1, rad(150), hand), lerp(0, rad(-25), hand)], armF: [0.1, 0], handN: hand > 0.5 ? 'open' : 'fist' });
  fig({ x: W * 0.63, y: feet, r: r * 0.96, view: 'back', sil: true, she: true });
  rect(-10, H * 0.62, W + 20, H * 0.04, C.dark, C.ink, LW(1));
  flat(0, H * 0.66, W, H, C.night);
}

// ---- coda: the next sunrise, under the fade-out ------------------------
function scCoda(t, env) {
  const u = (t - CODA_T) * 1.6;                                   // a faster dawn: 12 s instead of 19
  scSunrise(Math.min(u, 7.9 * BAR), env, { noPoint: true });
  const k = step(t, 171.0, 177.2);
  if (k > 0) { ctx.save(); ctx.globalAlpha = k; flat(0, 0, W, H, C.black); ctx.restore(); }
}

// ============================================================
//  the frame
// ============================================================
const SCENES = [scSunrise, scCrossing, scUmbrella, scFlower, scPlates, scSofa, scGallery, scNightWindow];
function drawFrame(t, env, card) {
  t = ((t % DUR) + DUR) % DUR;
  const ts = stepT(t);
  seed = Math.floor(t * DRAW_FPS); ji = 0;
  amp = (1.1 + 1.4 * env.rms) * 1.0;
  const e = env;
  if (card) scTitle(9, e);                                        // signature card for the cuts
  else if (ts < T0) scTitle(ts, e);
  else if (ts < CODA_T) {
    const u = ts - T0, i = Math.floor(u / SCENE), lu = u - i * SCENE;
    SCENES[Math.min(i, SCENES.length - 1)](lu, e);
  } else scCoda(ts, e);
  grain(0.05 + 0.04 * env.rms);
}

// ============================================================
//  modes
// ============================================================
if (RENDER) {
  setSize(+Q.get('w') || 1080, +Q.get('h') || 1920);
  window.__frame = p => { drawFrame(p.t, { bass: p.bass || 0, mid: p.mid || 0, high: p.high || 0, rms: p.rms || 0, flux: p.flux || 0 }, !!p.card); return true; };
  window.__ready = true;
} else if (COVER) {
  // covers are a square crop of the portrait composition, drawn at portrait scale
  const sz = +Q.get('size') || 3000;
  setSize(1080, 1920); cv.width = sz; cv.height = sz;
  const CROPS = { sunrise: 0.235, plates: 0.31, window: 0.15, title: 0.22, crossing: 0.36, flower: 0.36, umbrella: 0.36, sofa: 0.27, gallery: 0.22 };
  window.__cover = variant => {
    const e = { bass: 0.3, mid: 0.4, high: 0.3, rms: 0.4, flux: 0 };
    seed = 7; ji = 0; amp = 1.3;
    const k = sz / 1080, top = (CROPS[variant] == null ? 0.25 : CROPS[variant]) * 1920;
    ctx.setTransform(k, 0, 0, k, 0, -top * k);
    if (variant === 'plates') scPlates(2.5 * BAR, e);
    else if (variant === 'crossing') scCrossing(4.2 * BAR, e);
    else if (variant === 'flower') scFlower(5.2 * BAR, e);
    else if (variant === 'umbrella') scUmbrella(4.0 * BAR, e);
    else if (variant === 'sofa') scSofa(5.0 * BAR, e);
    else if (variant === 'window') scNightWindow(5.0 * BAR, e);
    else if (variant === 'gallery') scGallery(1.0 * BAR, e);
    else if (variant === 'title') scTitle(9, e);
    else scSunrise(4.6 * BAR, e);
    grain(0.06); ctx.setTransform(1, 0, 0, 1, 0, 0); return true;
  };
  window.__ready = true;
} else {
  // ---------------- live ----------------
  setSize(1080, 1920);
  const hint = document.getElementById('hint');
  let ac = null, analyser = null, buf = null, srcNode = null, startAt = 0, running = false, loopLen = DUR, pad = null;
  const env = { bass: 0, mid: 0, high: 0, rms: 0, flux: 0 };
  let prevSpec = null;
  const agc = { bass: 1e-3, mid: 1e-3, high: 1e-3, rms: 1e-3 };
  function bands() {
    if (!analyser) return;
    const n = analyser.frequencyBinCount, data = new Float32Array(n); analyser.getFloatFrequencyData(data);
    const sr = ac.sampleRate, hz = i => i * sr / 2 / n;
    let b = 0, m = 0, h = 0, tot = 0, fl = 0;
    for (let i = 1; i < n; i++) { const v = Math.pow(10, data[i] / 20); const f = hz(i); if (f < 150) b += v; else if (f < 2000) m += v; else if (f < 9000) h += v; tot += v; if (prevSpec) fl += Math.max(0, v - prevSpec[i]); }
    prevSpec = Float32Array.from(data, d => Math.pow(10, d / 20));
    const td = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(td); let s = 0; for (let i = 0; i < td.length; i++) s += td[i] * td[i]; const rms = Math.sqrt(s / td.length);
    const upd = (k, v) => { agc[k] = Math.max(agc[k] * 0.9995, v); env[k] = clamp(v / agc[k], 0, 1); };
    upd('bass', b); upd('mid', m); upd('high', h); upd('rms', rms); env.flux = clamp(fl / (agc.mid * 0.5 + 1e-6), 0, 1);
  }
  function procedural() {
    // a sad little pad + a sub hit every bar, so the piece is never silent
    pad = ac.createGain(); pad.connect(analyser);   // all of it goes through `pad`: a dropped track disconnects it
    const g = ac.createGain(); g.gain.value = 0.18; g.connect(pad); analyser.connect(ac.destination);
    const notes = [110, 130.81, 164.81, 220];       // A minor-ish
    notes.forEach((f, i) => { const o = ac.createOscillator(); o.type = i % 2 ? 'triangle' : 'sine'; o.frequency.value = f * (1 + (i - 1.5) * 0.0012);
      const lg = ac.createGain(); lg.gain.value = 0.25; const lfo = ac.createOscillator(); lfo.frequency.value = 0.07 + i * 0.023; const lgg = ac.createGain(); lgg.gain.value = 0.12; lfo.connect(lgg); lgg.connect(lg.gain); lfo.start();
      o.connect(lg); lg.connect(g); o.start(); });
    let next = ac.currentTime + 0.1;
    function tick() {
      while (next < ac.currentTime + 0.5) {
        const o = ac.createOscillator(); o.type = 'sine'; o.frequency.setValueAtTime(70, next); o.frequency.exponentialRampToValueAtTime(38, next + 0.25);
        const eg = ac.createGain(); eg.gain.setValueAtTime(0.0001, next); eg.gain.exponentialRampToValueAtTime(0.9, next + 0.01); eg.gain.exponentialRampToValueAtTime(0.0001, next + 0.5);
        o.connect(eg); eg.connect(pad); o.start(next); o.stop(next + 0.55); next += BAR;
      }
      if (pad) setTimeout(tick, 200);   // until a track is dropped (`running` is still false on the first call)
    }
    tick();
  }
  function start(withBuffer) {
    if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); analyser = ac.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.6; }
    if (ac.state === 'suspended') ac.resume();
    if (srcNode) { try { srcNode.stop(); } catch (e) { } srcNode.disconnect(); srcNode = null; }
    if (withBuffer) { if (pad) { pad.disconnect(); pad = null; } srcNode = ac.createBufferSource(); srcNode.buffer = buf; srcNode.loop = true; srcNode.connect(analyser); analyser.connect(ac.destination); srcNode.start(); loopLen = buf.duration; }
    else if (!running) procedural();
    startAt = ac.currentTime; running = true; hint.classList.add('off');
  }
  let lastSeed = -1;
  function loop() {
    requestAnimationFrame(loop);
    if (!running) { if (lastSeed !== -2) { lastSeed = -2; drawFrame(4.2, env); } return; }
    const t = ((ac.currentTime - startAt) % loopLen);
    const sd = Math.floor(t * DRAW_FPS);
    if (sd === lastSeed) return; lastSeed = sd;
    bands(); drawFrame(t, env);
  }
  cv.addEventListener('click', () => start(!!buf));
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', async e => {
    e.preventDefault(); const f = e.dataTransfer.files[0]; if (!f) return;
    if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); analyser = ac.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.6; }
    buf = await ac.decodeAudioData(await f.arrayBuffer()); start(true);
  });
  loop();
}
