// ---- the two of them, from behind, in two armchairs ----------------------------------------
// Silhouettes against the sky. He is opaque: he never moves, so the exposure keeps all of him. She is drawn
// as an occupancy: every pose she held, weighted by the share of the sky's light she blocked while she held it
// (a mean stack is exactly that), summed -- where two poses overlap she was there all along.

function curveInto(p, pts, closed) {             // Catmull-Rom through pts, into a Path2D
  const n = pts.length, P = i => closed ? pts[(i + n) % n] : pts[clamp(i, 0, n - 1)], k = 1 / 6;
  p.moveTo(pts[0][0], pts[0][1]);
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    p.bezierCurveTo(p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k, p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k, p2[0], p2[1]);
  }
  if (closed) p.closePath();
}
const pathOf = (pts, closed = true) => { const p = new Path2D(); curveInto(p, pts, closed); return p; };

// The back of a head, from the left of the neck over the crown to the right of it (canvas angles: 90 is
// down, 180 left, 270 the crown). Fuller at the crown, narrower at the nape; ears as small bumps; hair(a):
// extra radius at angle a.
function headArc(hx, hy, rx, ry, hair, a0 = 118, a1 = 422, n = 64) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const deg = a0 + (a1 - a0) * i / n, a = rad(deg), s = Math.sin(a), c = Math.cos(a);
    const kx = s > 0 ? 1 - 0.22 * s * s : 1;
    const ear = 0.07 * (Math.exp(-(((deg - 172) / 11) ** 2)) + Math.exp(-(((deg - 368) / 11) ** 2)));
    const e = hair ? hair(a) : 0;
    pts.push([hx + c * (rx * (kx + ear) + e), hy + s * (ry * (s > 0 ? 0.96 : 1) + e)]);
  }
  return pts;
}
// ---- the chairs: tall upholstered backs, rounded on top, armrests low at the sides ----
const CHAIR_W = 268;
function chairPaths(cx) {
  const top = CHAIR_TOP, bot = H + 20, w = CHAIR_W, xl = cx - w / 2, xr = cx + w / 2, r = 40;
  const back = new Path2D();
  back.moveTo(xl + 2, top + r);
  back.quadraticCurveTo(xl + 3, top + 1, xl + r, top - 3);
  back.bezierCurveTo(cx - 0.25 * w, top - 9, cx + 0.25 * w, top - 9, xr - r, top - 3);
  back.quadraticCurveTo(xr - 3, top + 1, xr - 2, top + r);
  back.lineTo(xr + 10, bot); back.lineTo(xl - 10, bot); back.closePath();
  const arms = new Path2D();
  for (const [x0, x1] of [[xl - 36, xl + 16], [xr - 16, xr + 36]]) {
    arms.moveTo(x0, 1400); arms.quadraticCurveTo(x0 + 1, 1378, x0 + 20, 1376); arms.lineTo(x1 - 8, 1376);
    arms.quadraticCurveTo(x1, 1378, x1, 1396); arms.lineTo(x1 + 4, bot); arms.lineTo(x0 - 4, bot); arms.closePath();
  }
  return [arms, back];
}
const CHAIRS = { him: null, her: null };
function chairsFor() { if (!CHAIRS.him) { CHAIRS.him = chairPaths(HIM.x); CHAIRS.her = chairPaths(HER.x + 2); } return CHAIRS; }

// ---- him: short hair, a hoodie with its hood bunched round his neck, broad shoulders: one outline ----
const HIM_PATHS = (() => {
  const x = HIM.x, [hx, hy] = HIM.head, rx = HIM.hr, ry = HIM.hry, top = CHAIR_TOP, sh = 128;
  const hair = a => {                                   // short hair: a fine ragged edge over the crown, a cowlick
    const k = Math.max(0, -Math.sin(a));
    return k * (1.3 + 0.75 * Math.sin(23 * a + 0.7) + 0.45 * Math.sin(41 * a + 2.1) + 3.2 * Math.exp(-(((a - rad(250)) / 0.09) ** 2)));
  };
  const left = [[x - sh - 6, top + 70], [x - sh, top + 6], [x - sh * 0.9, top - 24], [x - sh * 0.7, top - 42], [x - sh * 0.48, top - 52],
    [x - 84, top - 58], [x - 74, top - 76], [x - 54, top - 88], [x - 34, hy + ry * 0.98]];
  const right = left.map(([px, py]) => [2 * x - px, py]).reverse();
  return [pathOf([...left, ...headArc(hx, hy, rx, ry, hair), ...right])];
})();

// ---- her: long wavy hair over her shoulders: one outline ----
function herOutline() {
  const x = HER.x, [hx, hy] = HER.head, rx = HER.hr, ry = HER.hry, top = CHAIR_TOP, sh = 108, out = [];
  // the hair's half-width at height y: the head plus volume, a little in at the neck, spreading on the shoulders
  const yC = hy - ry - 8, yE = top - 34;
  const half = (y, side) => {
    const v = (y - hy) / (ry + 8);
    let w;
    if (y < hy + 0.15 * ry) w = (rx + 10) * Math.sqrt(Math.max(0, 1 - Math.min(1, v * v)));
    else {
      const u = (y - (hy + 0.15 * ry)) / (yE - (hy + 0.15 * ry));
      w = rx + 10 + kf(u, [[0, 0], [0.35, -5], [0.7, 14], [1, 26]]) + 5 * u * Math.sin(u * 9 + (side > 0 ? 0.9 : 2.4));
    }
    return w;
  };
  out.push([x - sh - 6, top + 70], [x - sh, top + 8], [x - sh * 0.9, top - 18], [x - sh * 0.74, top - 32]);
  const N = 40;
  for (let i = 0; i <= N; i++) { const y = lerp(yE, yC + 1, i / N); out.push([hx - half(y, -1), y]); }     // up the left
  for (let i = 0; i <= N; i++) { const y = lerp(yC + 1, yE, i / N); out.push([hx + half(y, 1), y]); }      // down the right
  out.push([x + sh * 0.74, top - 32], [x + sh * 0.9, top - 18], [x + sh, top + 8], [x + sh + 6, top + 70]);
  // the crown: smooth the two halves' meeting point
  return out.filter((p, i, a) => !i || Math.hypot(p[0] - a[i - 1][0], p[1] - a[i - 1][1]) > 2);
}
const HER_PATHS = [pathOf(herOutline())];
// strands, for her hair's sheen (rim light, faint)
const HER_STRANDS = (() => {
  const [hx, hy] = HER.head, out = [];
  for (let i = 0; i < 12; i++) {
    const s = (i / 11) * 2 - 1, pts = [];
    for (let j = 0; j <= 14; j++) {
      const v = j / 14, y = hy - HER.hry - 2 + v * (CHAIR_TOP - 30 - (hy - HER.hry - 2));
      pts.push([hx + s * (HER.hr * Math.sin(Math.min(1, v * 1.6) * Math.PI / 2) + 22 * v) + 4 * Math.sin(v * 9 + i * 1.7) * v, y]);
    }
    out.push(pathOf(pts, false));
  }
  return out;
})();
// The poses. up: as drawn (the dawn). lean: tipped 24 degrees towards the other chair about the hips
// (the night).
const LEAN = (() => { const p = [HER.x + 30, 1452]; return new DOMMatrix().translate(p[0], p[1]).rotate(-24).translate(-p[0], -p[1]); })();
const POSE_M = { up: new DOMMatrix(), lean: LEAN };
function herPaths(pose) {
  const M = POSE_M[pose] || POSE_M.up;
  return HER_PATHS.map(p => { const q = new Path2D(); q.addPath(p, M); return q; });
}
const HER_POSE_CACHE = {};
const herPose = pose => HER_POSE_CACHE[pose] || (HER_POSE_CACHE[pose] = herPaths(pose));

// Her eras: which pose she held when, and how much of her the exposure kept (the light she blocked, over all
// the light that reached the film at her head, so far).
function herEras(X, t) {
  const tc = Math.min(t, X.close), [hx, hy] = HER.head, eras = [];
  const pose = X.night ? 'lean' : 'up';                  // the night: leaning, all night
  if (X.leave != null) {
    eras.push({ pose, a: X.open, b: Math.min(tc, X.leave) });
    if (tc > X.leave) eras.push({ pose: null, a: X.leave, b: tc });      // gone: nothing of her blocks the sky
  } else eras.push({ pose, a: X.open, b: tc });
  const total = skyLightBehind(X, hx, hy, X.open, tc);
  for (const e of eras) e.alpha = e.pose ? (total > 1e-9 ? skyLightBehind(X, hx, hy, e.a, e.b) / total : 1) : 0;
  return eras;
}

// ---- offscreen layers the size of the frame, worked on only inside a box (stage units) ----
const LAYER = { cv: null, c: null }, OCC = { cv: null, c: null };
const BOX = { him: [240, 930, 575, 1270], her: [400, 930, 840, 1275], chairsTop: [220, 1150, 880, 1240], chairsArms: [220, 1355, 880, 1415], all: null };
function devBox(b) {                                    // a stage box -> device pixels [x, y, w, h], clamped to the canvas
  if (!b) return [0, 0, PXW, PXH];
  const m = MAINCTX.getTransform();
  const x0 = clamp(Math.floor(m.a * b[0] + m.e) - 2, 0, PXW), y0 = clamp(Math.floor(m.d * b[1] + m.f) - 2, 0, PXH);
  const x1 = clamp(Math.ceil(m.a * b[2] + m.e) + 2, 0, PXW), y1 = clamp(Math.ceil(m.d * b[3] + m.f) + 2, 0, PXH);
  return [x0, y0, Math.max(0, x1 - x0), Math.max(0, y1 - y0)];
}
function fresh(L, box) {
  if (!L.cv || L.cv.width !== PXW || L.cv.height !== PXH) { L.cv = mkCanvas(PXW, PXH); L.c = L.cv.getContext('2d'); }
  const c = L.c, r = devBox(box); L.r = r;
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.globalCompositeOperation = 'source-over'; c.clearRect(r[0], r[1], r[2], r[3]);
  c.setTransform(MAINCTX.getTransform());
  return c;
}
function blit(L, alpha = 1, op = 'source-over') {
  const r = L.r || [0, 0, PXW, PXH];
  if (r[2] <= 0 || r[3] <= 0) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = alpha; ctx.globalCompositeOperation = op;
  ctx.drawImage(L.cv, r[0], r[1], r[2], r[3], r[0], r[1], r[2], r[3]); ctx.restore();
}
// her ghost: occupancy (each pose's paths, white at its alpha, summed), inked, laid on the sky
function drawHerGhost(X, t, eras) {
  const c = fresh(LAYER, BOX.her), r = LAYER.r;
  for (const e of eras) {
    if (!e.pose || e.alpha <= 0.003) continue;
    const o = fresh(OCC, BOX.her); o.fillStyle = '#fff';
    for (const p of herPose(e.pose)) o.fill(p);
    c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'lighter'; c.globalAlpha = e.alpha;
    c.drawImage(OCC.cv, r[0], r[1], r[2], r[3], r[0], r[1], r[2], r[3]); c.restore();
  }
  c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'source-in'; c.fillStyle = INK; c.fillRect(r[0], r[1], r[2], r[3]); c.restore();
  blit(LAYER);
}
// a rim of light along the edges of a silhouette that face the light (they are backlit by the sky): the
// shape minus itself shifted away from the light, as a crescent, laid on at `alpha` -- so it works on a ghost
function rim(paths, col, alpha, dx, dy, box) {
  if (alpha <= 0.004) return;
  const c = fresh(OCC, box);
  c.fillStyle = col;
  for (const p of paths) c.fill(p);
  c.globalCompositeOperation = 'destination-out'; c.translate(dx, dy); c.fillStyle = '#000';
  for (const p of paths) c.fill(p);
  blit(OCC, alpha);
}
// the same, straight onto the frame, for what is opaque (him, the chairs): fill the shape with the light, then
// the shape shifted away from the light in its own colour
function rimSolid(paths, fill, col, alpha, dx, dy) {
  for (const p of paths) {
    ctx.save(); ctx.clip(p);
    ctx.globalAlpha = alpha; ctx.fillStyle = col; ctx.fill(p);
    ctx.globalAlpha = 1; ctx.fillStyle = fill; ctx.translate(dx, dy); ctx.fill(p);
    ctx.restore();
  }
}
function rimLight(X, t) {
  const u = expoU(X, t), dev = develop(u), m = integ(X, X.M, t) / X.Tx, d = integ(X, X.D, t) / X.Tx;
  const c = [0.22 * dev + 0.35 * m + 0.95 * d, 0.16 * dev + 0.42 * m + 0.58 * d, 0.14 * dev + 0.58 * m + 0.42 * d].map(v => Math.round(255 * tone(v)));
  const side = clamp(1.3 * (m + d));                    // the moon and the dawn come from the right
  return { col: `rgb(${c})`, a: clamp(0.5 + 0.35 * side), dx: -2.2 * side, dy: 2.6 - 0.8 * side };
}
function drawHerRim(X, t, eras) {
  const R = rimLight(X, t);
  for (const e of eras) if (e.pose) {
    const P = herPose(e.pose);
    rim(P, R.col, R.a * e.alpha, R.dx, R.dy, BOX.her);
    // the sheen of her hair: strands, faint, inside it
    const c = fresh(OCC, BOX.her), m = POSE_M[e.pose] || POSE_M.up;
    c.save(); c.clip(P[0]); c.transform(m.a, m.b, m.c, m.d, m.e, m.f);
    c.strokeStyle = R.col; c.lineWidth = 1.3; c.globalAlpha = 0.55;
    for (const s of HER_STRANDS) c.stroke(s);
    c.restore();
    blit(OCC, 0.16 * e.alpha);
  }
}
function drawHim(X, t) {
  const R = rimLight(X, t);
  ctx.save(); ctx.fillStyle = INK;
  for (const p of HIM_PATHS) ctx.fill(p);
  ctx.restore();
  rimSolid(HIM_PATHS, INK, R.col, R.a, R.dx, R.dy);
}
function drawChairs(X, t) {
  const C2 = chairsFor(), R = rimLight(X, t);
  for (const k of ['him', 'her']) {
    ctx.save(); ctx.fillStyle = '#06070b';
    for (const p of C2[k]) ctx.fill(p);
    ctx.restore();
    ctx.save(); ctx.beginPath(); ctx.rect(-20, CHAIR_TOP - 30, W + 40, 64); ctx.rect(-20, 1360, W + 40, 44); ctx.clip();
    rimSolid([C2[k][1]], '#06070b', R.col, 0.42 * R.a, 0.6 * R.dx, 2.2);
    rimSolid([C2[k][0]], '#06070b', R.col, 0.25 * R.a, 0.6 * R.dx, 1.8);
    ctx.restore();
  }
}
// Lights recorded during one era, with whatever of her blocked them cut out (she was in front of them): the
// era's finished steps from their bitmap, the rest drawn now -- through a clip that leaves her out only for what
// can pass behind her (the stars whose circles cross her box; the near lights), the rest without one.
const POSE_RING = {};
function poseRing(pose) {                               // the radii from the pole that her box spans
  if (POSE_RING[pose]) return POSE_RING[pose];
  const b = BOX.her, cx = clamp(POLE.x, b[0], b[2]), cy = clamp(POLE.y, b[1], b[3]);
  const rmin = Math.hypot(cx - POLE.x, cy - POLE.y);
  const rmax = Math.max(...[[b[0], b[1]], [b[2], b[1]], [b[0], b[3]], [b[2], b[3]]].map(([x, y]) => Math.hypot(x - POLE.x, y - POLE.y)));
  return (POSE_RING[pose] = [rmin - 6, rmax + 6]);
}
function eraLights(X, e, key, tc, free, near, opts) {
  const th0 = thetaAt(X, e.a), th1 = thetaAt(X, e.b), done = e.b < tc - 1e-9 || tc >= X.close;
  const thEnd = done ? th1 : Math.max(th0, Math.floor(th1 / STEP_A + 1e-9) * STEP_A);
  const noTrails = !!(opts && opts.noTrails);
  if (!noTrails) {
    const bm = trailBitmap(key, th0, thEnd, e.pose);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'lighter'; ctx.drawImage(bm, 0, 0); ctx.restore();
  }
  const ring = e.pose ? poseRing(e.pose) : null;
  if (!noTrails && th1 > thEnd + 1e-9) drawTrails(thEnd, th1, ring ? { skip: ring } : {});
  free();
  if (!e.pose) { near(); return; }
  ctx.save();
  const inv = new Path2D(); inv.rect(-W, -H, 3 * W, 3 * H);
  for (const p of herPose(e.pose)) inv.addPath(p);
  ctx.clip(inv, 'evenodd');
  if (!noTrails && th1 > thEnd + 1e-9) drawTrails(thEnd, th1, { only: ring });
  near();
  ctx.restore();
}
