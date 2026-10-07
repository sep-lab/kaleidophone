// ---- lights: everything that leaves a trail ---------------------------------------------
// All drawn additively ('lighter'): light adds up on the film. Each function draws what its source emitted
// during one era [a, b] of the exposure, so a person who blocked part of the sky can clip it out (40_people.js).
const DIM = 0.13;                                        // the snare's fast sweep, against the steady part of a step

// Star trails: the part of every star's circle recorded while the sky turned from th0 to th1.
function drawTrails(th0, th1, o = {}) {
  if (th1 <= th0 + 1e-7) return;
  const gain = o.gain == null ? 1 : o.gain;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'butt';
  const ph = ((th0 / STEP_A) % 1 - FAST + 1) % 1;       // where th0 falls in a step's dash pattern
  for (const s of STARS) {
    if (o.skip && s.r > o.skip[0] && s.r < o.skip[1]) continue;     // drawn in the clipped pass
    if (o.only && !(s.r > o.only[0] && s.r < o.only[1])) continue;
    const a0 = s.a - th0, a1 = s.a - th1;              // the sky turns anticlockwise on screen: angles fall
    const col = `rgb(${s.c[0]},${s.c[1]},${s.c[2]})`, per = STEP_A * s.r, dash = (1 - FAST) * per;
    ctx.strokeStyle = col;
    if (s.b > 0.55) {                                   // the bright ones bloom a little
      ctx.setLineDash([]); ctx.lineWidth = s.w * 3.2; ctx.globalAlpha = 0.045 * s.b * gain;
      ctx.beginPath(); ctx.arc(POLE.x, POLE.y, s.r, a0, a1, true); ctx.stroke();
    }
    ctx.lineWidth = s.w;
    ctx.setLineDash([]); ctx.globalAlpha = DIM * s.b * gain;
    ctx.beginPath(); ctx.arc(POLE.x, POLE.y, s.r, a0, a1, true); ctx.stroke();
    ctx.setLineDash([dash, per - dash]); ctx.lineDashOffset = ph * per; ctx.globalAlpha = s.b * gain;
    ctx.beginPath(); ctx.arc(POLE.x, POLE.y, s.r, a0, a1, true); ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.restore();
}
// A finished step of the sky never changes, so each era keeps a bitmap of its finished steps, extended a step
// at a time and in order (a partial first step if the era opens mid-step), erasing whoever was in front after
// every step. The same operations run whichever frame a worker starts on, so the bitmap is a pure function of
// (exposure, era, steps done) and the render stays deterministic.
const TCACHE = {};
function trailBitmap(key, th0, thEnd, pose) {
  const tf = MAINCTX.getTransform(), tk = `${PXW}x${PXH}:${tf.a},${tf.d},${tf.e},${tf.f}`;
  let C = TCACHE[key];
  if (!C || C.tk !== tk || thEnd < C.upto - 1e-9) {
    if (!C || C.cv.width !== PXW || C.cv.height !== PXH) C = TCACHE[key] = { cv: mkCanvas(PXW, PXH) };
    const c = C.cv.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, PXW, PXH);
    C.upto = th0; C.tk = tk;
  }
  if (thEnd > C.upto + 1e-9) {
    const c = C.cv.getContext('2d'), paths = pose ? herPose(pose) : null;
    let a = C.upto;
    while (a < thEnd - 1e-9) {
      const b = Math.min(thEnd, (Math.floor(a / STEP_A + 1e-9) + 1) * STEP_A);
      c.setTransform(tf); c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
      withCtx(c, () => drawTrails(a, b));
      if (paths) { c.save(); c.setTransform(tf); c.globalCompositeOperation = 'destination-out'; c.fillStyle = '#000'; for (const p of paths) c.fill(p); c.restore(); }
      a = b;
    }
    C.upto = thEnd;
  }
  return C.cv;
}
// The stars where they are now: the live view's points (only while the shutter is open). They shimmer a
// little on the hi-hats -- the only thing in the frame that does.
function drawHeads(th, t, env, o = {}) {
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  const hat = clamp(1.6 * (env.hflux || 0) - 0.5), gain = o.gain == null ? 1 : o.gain;
  for (const s of STARS) {
    if (s.b < 0.16) continue;
    const a = s.a - th, x = POLE.x + s.r * Math.cos(a), y = POLE.y + s.r * Math.sin(a);
    if (x < -8 || x > W + 8 || y < -8 || y > 1260) continue;
    const tw = 0.75 + 0.25 * Math.sin(t * (5 + 7 * s.tw) + 40 * s.tw) * (0.4 + 0.6 * hat);
    ctx.globalAlpha = clamp(0.75 * s.b * tw * gain);
    ctx.fillStyle = `rgb(${s.c[0]},${s.c[1]},${s.c[2]})`;
    ctx.beginPath(); ctx.arc(x, y, 0.55 * s.w + 0.4, 0, TAU); ctx.fill();
  }
  ctx.restore();
}

// Setareh: the pole star. It never moves, so its light piles up: the only star that keeps getting brighter.
function drawSetareh(X, t, o = {}) {
  const u = o.u != null ? o.u : expoU(X, t), acc = 0.28 + 0.72 * Math.sqrt(u);
  const breath = o.still ? 0 : 0.06 * envAt('vstem', t);  // live, it listens to the voice a little
  const k = acc * (1 + breath);
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  drawSprite(ctx, glowSprite(255, 120, 70, 'hal'), POLE.x, POLE.y, 30 + 70 * k, 0.16 * k);      // film halation: a warm ring
  drawSprite(ctx, glowSprite(205, 222, 255, 'sg'), POLE.x, POLE.y, 22 + 92 * k, 0.55 + 0.45 * k);
  drawSprite(ctx, glowSprite(255, 255, 255, 'sw'), POLE.x, POLE.y, 6 + 16 * k, 1);
  // four diffraction spikes, longer as the light piles up
  const L = 24 + 190 * k * k;
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2 + rad(1.5), dx = Math.cos(a), dy = Math.sin(a);
    const g = ctx.createLinearGradient(POLE.x, POLE.y, POLE.x + dx * L, POLE.y + dy * L);
    g.addColorStop(0, 'rgba(255,255,255,0.95)'); g.addColorStop(0.25, 'rgba(225,235,255,0.45)'); g.addColorStop(1, 'rgba(200,215,255,0)');
    ctx.strokeStyle = g; ctx.lineCap = 'round';
    ctx.globalAlpha = 1; ctx.lineWidth = 1.6 + 1.3 * k;
    ctx.beginPath(); ctx.moveTo(POLE.x, POLE.y); ctx.lineTo(POLE.x + dx * L, POLE.y + dy * L); ctx.stroke();
  }
  ctx.fillStyle = '#ffffff'; ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.arc(POLE.x, POLE.y, 2.4 + 2.6 * k, 0, TAU); ctx.fill();
  ctx.restore();
}

// A shooting star: from near the pole, outwards. The streak stays; the head flares while it flies.
function drawMeteor(m, t, o = {}) {
  const p = clamp((t - m.t) / m.dur);
  if (p <= 0) return;
  const ca = Math.cos(m.ang), sa = Math.sin(m.ang);
  const x0 = POLE.x + ca * m.r0, y0 = POLE.y + sa * m.r0, L = m.len;
  const xe = x0 + ca * L, ye = y0 + sa * L, x1 = x0 + ca * L * p, y1 = y0 + sa * L * p;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round';
  const glowC = m.hue < 0.6 ? [140, 255, 200] : [170, 210, 255];      // oxygen green, or a blue-white one
  const gr = ctx.createLinearGradient(x0, y0, xe, ye);
  gr.addColorStop(0, `rgba(${glowC},0)`); gr.addColorStop(0.2, `rgba(${glowC},0.55)`);
  gr.addColorStop(0.58, 'rgba(255,255,248,1)'); gr.addColorStop(0.86, 'rgba(255,214,168,0.75)'); gr.addColorStop(1, 'rgba(255,170,120,0)');
  ctx.strokeStyle = gr;
  ctx.globalAlpha = 0.20 * (0.6 + 0.4 * m.s); ctx.lineWidth = m.w * 4.2;
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
  ctx.globalAlpha = 0.95; ctx.lineWidth = m.w;
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
  if (p < 1 && !o.still) {                              // the head, and the sky lighting up round it for a moment
    const f = 1 - p * 0.6;
    drawSprite(ctx, glowSprite(glowC[0], glowC[1], glowC[2], 'mg' + glowC), x1, y1, 46 + 70 * m.s, 0.55 * f);
    drawSprite(ctx, glowSprite(255, 255, 255, 'sw'), x1, y1, 8 + 7 * m.s, f);
  }
  ctx.restore();
}

// The moon: rises from behind the cone near the end of the night cut; its trail is a broad bright band.
function drawMoon(X, t, o = {}) {
  if (X.moon == null || t < X.moon) return;
  const th = thetaAt(X, t) - thetaAt(X, X.moon), a0 = MOON.a0, a1 = MOON.a0 - th;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round';
  if (th > 1e-4) {
    ctx.strokeStyle = 'rgb(200,215,255)'; ctx.globalAlpha = 0.10; ctx.lineWidth = 70;
    ctx.beginPath(); ctx.arc(POLE.x, POLE.y, MOON.r, a0, a1, true); ctx.stroke();
    ctx.strokeStyle = 'rgb(255,250,240)'; ctx.globalAlpha = 0.85; ctx.lineWidth = 2 * MOON.R;
    ctx.beginPath(); ctx.arc(POLE.x, POLE.y, MOON.r, a0, a1, true); ctx.stroke();
  }
  const [x, y] = moonPos(X, t), up = moonUp(X, t);
  if (up > 0) {
    drawSprite(ctx, glowSprite(255, 130, 80, 'hal'), x, y, 90, 0.14 * up);
    drawSprite(ctx, glowSprite(190, 210, 255, 'mo'), x, y, 260, 0.30 * up);
  }
  ctx.fillStyle = '#fffaf0'; ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.arc(x, y, MOON.R, 0, TAU); ctx.fill();
  ctx.restore();
}

// A plane: two navigation lights drawing faint parallel lines (red, green), and its white strobe on every beat
// leaving a row of dots.
function drawPlane(X, a, b, o = {}) {
  const P = X.plane;
  a = Math.max(a, P.t0); b = Math.min(b, P.t1);
  if (b <= a) return;
  const at = tt => { const u = (tt - P.t0) / (P.t1 - P.t0); return [lerp(P.a[0], P.b[0], u), lerp(P.a[1], P.b[1], u)]; };
  const p0 = at(a), p1 = at(b), dx = P.b[0] - P.a[0], dy = P.b[1] - P.a[1], n = Math.hypot(dx, dy), nx = -dy / n * 6, ny = dx / n * 6;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round'; ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.45; ctx.strokeStyle = 'rgb(255,70,60)';
  ctx.beginPath(); ctx.moveTo(p0[0] + nx, p0[1] + ny); ctx.lineTo(p1[0] + nx, p1[1] + ny); ctx.stroke();
  ctx.strokeStyle = 'rgb(90,255,140)';
  ctx.beginPath(); ctx.moveTo(p0[0] - nx, p0[1] - ny); ctx.lineTo(p1[0] - nx, p1[1] - ny); ctx.stroke();
  for (let k = Math.ceil((a - G.downbeat) / G.beat); ; k++) {
    const tb = G.downbeat + k * G.beat - 0.018;
    if (tb > b) break;
    if (tb < a) continue;
    const [x, y] = at(tb);
    drawSprite(ctx, glowSprite(255, 255, 255, 'sw'), x, y, 9, 0.9);
    drawSprite(ctx, glowSprite(220, 230, 255, 'pg'), x, y, 26, 0.25);
  }
  if (!o.still && o.live) { const [x, y] = at(b); drawSprite(ctx, glowSprite(255, 255, 255, 'sw'), x, y, 7, 0.8); }
  ctx.restore();
}

// A phone's light as the figure on the right gets up and goes (dawn cut): the way out, written in light.
const WALK_T = 3.0;
function phonePos(X, s) {                               // s: 0..1 over the walk
  const stand = [HER.head[0] + 62, 1012], u = easeIn(clamp(s) * 0.5) * 2 * 0.25 + clamp(s) * 0.75;   // it starts slowly
  return [lerp(stand[0], W + 80, u), stand[1] + 26 * u * u - 18 * Math.sin(u * Math.PI) + 2.5 * Math.sin(u * 6 * TAU)];  // a gentle arc, a small bob on each step
}
function drawPhone(X, t, o = {}) {
  if (X.leave == null || t < X.leave) return;
  const s1 = clamp((t - X.leave) / WALK_T), n = Math.max(2, Math.ceil(90 * s1));
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  const path = () => { ctx.beginPath(); for (let i = 0; i <= n; i++) { const p = phonePos(X, s1 * i / n); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); } };
  ctx.strokeStyle = 'rgb(255,226,190)';
  ctx.globalAlpha = 0.20; ctx.lineWidth = 13; path(); ctx.stroke();
  ctx.globalAlpha = 0.95; ctx.lineWidth = 3.0; path(); ctx.stroke();
  if (s1 < 1 && !o.still) { const p = phonePos(X, s1); drawSprite(ctx, glowSprite(255, 236, 210, 'ph'), p[0], p[1], 34, 0.7); }
  ctx.restore();
}

// ---- the valley: the city's lights and its highways (only the cars' light: the roads look empty) ----
// The city lies on a plane in perspective: a point d units away (1 = the foot of their hill, 37 = the range)
// and L units to the side is on screen at gp(L, d).
const GK = 262, GKX = 240;
const gp = (L, d) => [VALLEY.vp[0] + L * GKX / d, VALLEY.vp[1] + GK / d];
const CITY = (() => {
  const R = mulberry32(4242), out = [];
  const add = (L, d) => {
    const [x, y] = gp(L, d);
    if (x < -10 || x > W + 10 || y < VALLEY.y0) return;
    const near = 1 / Math.sqrt(d), u = R();
    out.push({ x, y, r: 0.55 + 1.9 * near * (0.5 + 0.5 * R()), b: 0.35 + 0.65 * R(), c: u < 0.66 ? [255, 172, 88] : u < 0.92 ? [236, 240, 255] : u < 0.96 ? [255, 90, 70] : [120, 255, 170] });
  };
  for (let i = 0; i < 1500; i++) {
    const d = 1.05 + 36 * Math.pow(R(), 1.6), L = (R() * 2 - 1) * (2.6 * d + 3);
    if (R() < 0.5) add(L, d);                                          // scattered
    else if (R() < 0.5) add(Math.round(L / 0.9) * 0.9 + 0.04 * (R() - 0.5), d);     // along the streets that run away from us
    else add(L, Math.exp(Math.round(Math.log(d) / 0.075) * 0.075) * (1 + 0.004 * (R() - 0.5)));   // along the cross streets
  }
  return out;
})();
function drawCity(X, t, o = {}) {
  const dev = develop(o.u != null ? o.u : expoU(X, t));
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  for (const c of CITY) {
    ctx.globalAlpha = clamp(c.b * dev * 0.8); ctx.fillStyle = `rgb(${c.c})`;
    ctx.beginPath(); ctx.arc(c.x, c.y, c.r, 0, TAU); ctx.fill();
  }
  ctx.restore();
}
// Highways on the plane, as polylines of (L, d). Cars run along them at a steady speed on the ground (so on
// screen they rush near us and crawl at the range): white coming, red going. Only their light is recorded.
const HIGHWAYS = [
  { pts: [[-46, 10], [-16, 5.6], [-5, 4.3], [4, 4.1], [15, 5.2], [44, 8.6]], seed: 11, a: 0.36 },       // the ring road
  { pts: [[-36, 26], [-12, 14], [-1, 10.5], [11, 7.6], [34, 6.2]], seed: 23, a: 0.30 },                 // across, diagonal
  { pts: [[7.5, 37], [6.2, 22], [4.6, 13], [3.2, 7.6], [2.2, 4.9], [1.6, 3.4]], seed: 37, a: 0.30 },    // to the range
];
for (const hw of HIGHWAYS) {                            // arc length on the ground, for steady speeds
  hw.s = [0];
  for (let i = 1; i < hw.pts.length; i++) hw.s.push(hw.s[i - 1] + Math.hypot(hw.pts[i][0] - hw.pts[i - 1][0], hw.pts[i][1] - hw.pts[i - 1][1]));
  hw.len = hw.s[hw.s.length - 1];
}
function hwAt(hw, s) {                                  // the point s along the highway, on screen
  s = clamp(s, 0, hw.len);
  let i = 1; while (i < hw.s.length - 1 && hw.s[i] < s) i++;
  const u = (s - hw.s[i - 1]) / (hw.s[i] - hw.s[i - 1] || 1), L = lerp(hw.pts[i - 1][0], hw.pts[i][0], u), d = lerp(hw.pts[i - 1][1], hw.pts[i][1], u);
  return [gp(L, d), d];
}
function carsOn(hw, X) {
  if (!hw.cache) hw.cache = {};
  const key = X.open.toFixed(2);
  if (hw.cache[key]) return hw.cache[key];
  const out = [], e8 = G.beat / 2;
  for (let k = Math.floor((X.open - 40) / e8); k * e8 < X.close; k++) {
    if (HS(k, hw.seed) > 0.6) continue;
    out.push({ t0: k * e8 + 0.2 * HS(k, hw.seed + 2), v: 2.0 + 1.6 * HS(k, hw.seed + 3), dir: HS(k, hw.seed + 1) < 0.5 ? 1 : -1, b: 0.55 + 0.45 * HS(k, hw.seed + 4) });
  }
  return (hw.cache[key] = out);
}
function drawCars(X, t) {
  const tc = Math.min(t, X.close);
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (const hw of HIGHWAYS) {
    for (const c of carsOn(hw, X)) {
      const T = hw.len / c.v, ta = Math.max(X.open, c.t0), tb = Math.min(tc, c.t0 + T);
      if (tb <= ta) continue;
      ctx.strokeStyle = c.dir > 0 ? 'rgb(255,58,40)' : 'rgb(255,236,206)';
      ctx.globalAlpha = hw.a * c.b;
      const n = Math.max(2, Math.ceil(40 * (tb - ta) / T));
      let prevD = null;
      ctx.beginPath();
      for (let i = 0; i <= n; i++) {
        const tt = lerp(ta, tb, i / n), s = (tt - c.t0) * c.v, [[x, y], d] = hwAt(hw, c.dir > 0 ? s : hw.len - s);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); prevD = d;
      }
      ctx.lineWidth = Math.max(0.8, 3.2 / Math.sqrt(prevD));
      ctx.stroke();
    }
  }
  ctx.restore();
}
