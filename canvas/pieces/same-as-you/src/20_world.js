// ============================================================
//  THE WORLD: the torn page, rain, wet glass, fog, the heart
// ============================================================
const SEAM = 540;

// ---- the tear: one jagged line down the middle of the page, fixed for the film ----
const TEAR = (() => {
  const pts = [];
  for (let y = -80, i = 0; y <= H + 80; y += 12, i++) {
    let x = SEAM + 4.2 * Math.sin(y / 43 + 0.7) + 2.6 * Math.sin(y / 16.7 + 2.1) + (HS(i, 91) - 0.5) * 6.5;
    if (HS(i, 17) > 0.945) x += (HS(i, 18) - 0.5) * 18;
    pts.push([x, y]);
  }
  return pts;
})();
function tearX(y) { const i = clamp(Math.floor((y + 80) / 12), 0, TEAR.length - 2); const f = clamp((y + 80 - i * 12) / 12, 0, 1); return lerp(TEAR[i][0], TEAR[i + 1][0], f); }
const PIECE = { L: new Path2D(), R: new Path2D() };
(() => {
  const E = 600;
  PIECE.L.moveTo(-E, -E); for (const p of TEAR) PIECE.L.lineTo(p[0], p[1]); PIECE.L.lineTo(-E, H + E); PIECE.L.closePath();
  PIECE.R.moveTo(W + E, -E); for (const p of TEAR) PIECE.R.lineTo(p[0], p[1]); PIECE.R.lineTo(W + E, H + E); PIECE.R.closePath();
})();
function tearEdge(side, alpha, fibers = true) {
  if (alpha <= 0) return;
  const s = side === 'L' ? -1 : 1;
  ctx.save(); ctx.globalAlpha = alpha; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  // the torn white core of the paper
  ctx.beginPath();
  for (let i = 0; i < TEAR.length; i++) { const p = TEAR[i]; const x = p[0] + s * (1.6 + 1.2 * HS(i, 71)), y = p[1]; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.strokeStyle = '#faf6ec'; ctx.lineWidth = 4.2; ctx.stroke();
  ctx.strokeStyle = 'rgba(23,20,15,0.35)'; ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (let i = 0; i < TEAR.length; i++) { const p = TEAR[i]; const x = p[0] + s * (4.6 + 1.5 * HS(i, 72)), y = p[1]; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.stroke();
  if (fibers) {
    ctx.strokeStyle = '#fbf8f0'; ctx.lineWidth = 1.1; ctx.beginPath();
    for (let i = 0; i < TEAR.length; i++) {
      if (HS(i, 33 + (side === 'L' ? 0 : 5)) < 0.55) continue;
      const p = TEAR[i], a = (HS(i, 34) - 0.5) * 1.6, L = 2 + 6 * HS(i, 35);
      ctx.moveTo(p[0], p[1] + 3); ctx.lineTo(p[0] - s * Math.cos(a) * L, p[1] + 3 + Math.sin(a) * L);
    }
    ctx.stroke();
  }
  ctx.restore();
}

// ---- rain clock: rain slows to a hang in the dream, speeds up in the storm ----
const RAIN_CLOCK = (() => {
  const n = Math.ceil(DUR * 100) + 400, a = new Float32Array(n); let acc = 0;
  for (let i = 0; i < n; i++) {
    const t = i / 100, b = (t - T0) / BAR;
    const sp = b < 36.5 ? 1 : b < 38 ? lerp(1, 0.035, ease((b - 36.5) / 1.5)) : b < 47.2 ? 0.035 : b < 48 ? lerp(0.035, 1.35, ease((b - 47.2) / 0.8)) : b < 62 ? 1.35 : 1.0;
    a[i] = acc; acc += sp / 100;
  }
  return a;
})();
function rainClock(t) {
  if (t < bt(1)) t += REEL_END; const i = clamp(Math.floor(t * 100), 0, RAIN_CLOCK.length - 2), f = t * 100 - i; return lerp(RAIN_CLOCK[i], RAIN_CLOCK[i + 1], f); }

// ---- rain streaks (drawn in half-world coords; the mirror makes the other half) ----
const RAIN = Array.from({ length: 520 }, (_, i) => ({ x: HS(i, 1), p: HS(i, 2), v: 0.8 + 0.45 * HS(i, 3), l: HS(i, 4), d: HS(i, 5) }));
function rain(tr, n, slant, alpha, opt = {}) {
  if (DRY || n <= 0) return;
  const x0 = opt.x0 == null ? -160 : opt.x0, x1 = opt.x1 == null ? 600 : opt.x1, y0 = opt.y0 == null ? -60 : opt.y0, y1 = opt.y1 == null ? H + 60 : opt.y1;
  const col = opt.col || '222,218,206', lenK = opt.lenK || 1, span = y1 - y0 + 160;
  const hang = opt.hang || 0;             // 0..1: streaks shorten into beads (the dream)
  ctx.save(); ctx.lineCap = 'round';
  for (let layer = 0; layer < 3; layer++) {
    const dep = 0.5 + layer * 0.25;
    ctx.strokeStyle = `rgba(${col},${(alpha * (0.45 + 0.55 * dep)).toFixed(3)})`;
    ctx.lineWidth = (1.4 + 1.5 * dep) * (1 + hang * 1.6);
    ctx.beginPath();
    for (let i = layer; i < n; i += 3) {
      const r = RAIN[i]; const v = 2000 * r.v * dep;
      const L = Math.max(1.5, (20 + 34 * r.l) * dep * lenK * (1 - hang * 0.93));
      const yy = ((r.p * span + v * tr) % span) + y0 - 80;
      const x = x0 + r.x * (x1 - x0) + (yy - y0) * Math.tan(slant);
      ctx.moveTo(x, yy); ctx.lineTo(x - Math.sin(slant) * L, yy - Math.cos(slant) * L);
    }
    ctx.stroke();
  }
  ctx.restore();
}

// ---- drops on the glass: stick, slip, stick ----
function glassDrops(gx0, gy0, gx1, gy1, t, n, sk = 0, alpha = 1) {
  if (DRY || n <= 0) return;
  ctx.save(); ctx.lineCap = 'round';
  const span = gy1 - gy0 + 80;
  for (let i = 0; i < n; i++) {
    const x = gx0 + 12 + HS(i, 50 + sk) * (gx1 - gx0 - 24);
    const rd = 3 + 6 * Math.pow(HS(i, 51 + sk), 2);
    const rate = 0.3 + 1.1 * HS(i, 52 + sk);
    const k = t * rate + HS(i, 53 + sk) * 10;
    const jumps = Math.floor(k) + Math.pow(fract(k), 7);
    const y = gy0 - 40 + ((HS(i, 54 + sk) * span + jumps * (14 + 46 * HS(i, 55 + sk))) % span);
    const tl = 18 + 70 * HS(i, 56 + sk);
    ctx.strokeStyle = `rgba(232,236,238,${0.13 * alpha})`; ctx.lineWidth = rd * 0.5;
    ctx.beginPath(); ctx.moveTo(x + Math.sin(i) * 2, y - tl); ctx.lineTo(x, y); ctx.stroke();
    ctx.fillStyle = `rgba(232,238,242,${0.3 * alpha})`; ctx.beginPath(); ctx.ellipse(x, y, rd * 0.86, rd, 0, 0, TAU); ctx.fill();
    ctx.strokeStyle = `rgba(20,18,15,${0.35 * alpha})`; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.ellipse(x, y, rd * 0.86, rd, 0, 0.2, Math.PI - 0.2); ctx.stroke();
    ctx.fillStyle = `rgba(255,255,255,${0.75 * alpha})`; ctx.beginPath(); ctx.arc(x - rd * 0.3, y - rd * 0.35, rd * 0.28, 0, TAU); ctx.fill();
  }
  ctx.restore();
}

// ---- fog on the inside of the glass ----
function fogPatch(cx, cy, rx, ry, a) {
  if (DRY || a <= 0) return;
  ctx.save(); ctx.translate(cx, cy); ctx.scale(1, ry / rx);
  const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
  g.addColorStop(0, `rgba(236,236,232,${a})`); g.addColorStop(0.62, `rgba(236,236,232,${a * 0.82})`); g.addColorStop(1, 'rgba(236,236,232,0)');
  ctx.fillStyle = g; ctx.fillRect(-rx, -rx, 2 * rx, 2 * rx); ctx.restore();
}

// ---- the heart: each draws a half on their own glass; the seam is its axis ----
function heartPt(s, cx, cy, k) {
  const x = 16 * Math.pow(Math.sin(s), 3);
  const y = 13 * Math.cos(s) - 5 * Math.cos(2 * s) - 2 * Math.cos(3 * s) - Math.cos(4 * s);
  return [cx + k * x, cy - k * y];
}
function heartHalf(u, cx, cy, k, n = 44) {
  // his half (x ≤ seam): from the dip, round the lobe, down to the point
  const pts = []; if (u <= 0) return pts;
  const m = Math.ceil(n * u);
  for (let i = 0; i <= m; i++) { const f = Math.min(i / n, u); pts.push(heartPt(2 * Math.PI - Math.PI * f, cx, cy, k)); if (f >= u) break; }
  return pts;
}
function heartLine(pts, red, alpha = 1) {
  if (DRY || pts.length < 2) return;
  ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  const q = pts.map(p => [p[0] + J() * 0.5, p[1] + J() * 0.5]);
  const path = () => { ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); for (let i = 1; i < q.length; i++) ctx.lineTo(q[i][0], q[i][1]); };
  if (red > 0) {
    ctx.globalAlpha = alpha;
    ctx.shadowColor = `rgba(201,48,28,${0.9 * red})`; ctx.shadowBlur = 26;
    path(); ctx.strokeStyle = `rgba(201,48,28,${red})`; ctx.lineWidth = 11; ctx.stroke();
    ctx.shadowBlur = 0;
    path(); ctx.strokeStyle = `rgba(255,190,160,${0.45 * red})`; ctx.lineWidth = 3; ctx.stroke();
  }
  if (red < 1) {
    ctx.globalAlpha = alpha * (1 - red);
    path(); ctx.strokeStyle = 'rgba(52,44,34,0.7)'; ctx.lineWidth = 10; ctx.stroke();
    // condensation drips hanging from the cleared line
    ctx.strokeStyle = 'rgba(52,44,34,0.55)'; ctx.lineWidth = 3;
    for (let i = 4; i < q.length; i += 9) { const L = 8 + 16 * HS(i, 404); ctx.beginPath(); ctx.moveTo(q[i][0], q[i][1] + 4); ctx.lineTo(q[i][0] + 0.5, q[i][1] + 4 + L); ctx.stroke(); }
  }
  ctx.restore();
}

// ---- chromatography: rain hits the page, the black ink separates into colour ----
// candidates on every 8th note; a pure function of time (no state)
const SPOT_MAXLIFE = 6.0;
function spotProfile(b) {
  // [probability per 8th, size] by bar
  if (b < 1) return [0, 0];
  if (b < 12) return [0.03, 0.6];
  if (b < 14) return [0.07, 0.75];
  if (b < 16) return [lerp(0.15, 0.55, (b - 14) / 2), 0.95];
  if (b < 21) return [0.42, 1.05];
  if (b < 27) return [0.33, 1.0];
  if (b < 31) return [0.07, 0.75];
  if (b < 34) return [0.1, 0.8];
  if (b < 36) return [0.3, 1.1];
  if (b < 47.5) return [0.34, 1.6];
  if (b < 48.5) return [0, 0];          // the inhale: the page holds its breath
  if (b < 62) return [0.42, 1.2];
  return [0, 0];
}
function spotsAt(t) {
  if (t < bt(1)) return spotsRaw(t + REEL_END, REEL_END).concat(spotsRaw(t, 1e9));
  return spotsRaw(t, 1e9);
}
function spotsRaw(t, maxBirth) {
  const out = [];
  const k1 = Math.floor((t - T0) / 0.25), k0 = Math.max(0, k1 - Math.ceil(SPOT_MAXLIFE / 0.25));
  for (let k = k0; k <= k1; k++) {
    const tk = T0 + k * 0.25, b = (tk - T0) / BAR; if (tk > t || tk >= maxBirth) continue;
    let [p, sz] = spotProfile(b);
    const onBeat = k % 2 === 0, downbeat = k % 8 === 0;
    if (b >= 16 && b < 27 && onBeat) p += 0.25;
    if (b >= 48 && b < 62 && downbeat) p = 1;
    let burst = 0;
    if (Math.abs(b - 16) < 0.01 || Math.abs(b - 34.5) < 0.01 || Math.abs(b - 49) < 0.01) burst = 4;
    if (Math.abs(b - 48.5) < 0.01) { burst = 11; sz = 1.55; }        // THE SPLASH
    if (Math.abs(b - 67.5) < 0.01) { burst = 6; sz = 0.8; }          // the last flourish
    for (let j = 0; j <= burst; j++) {
      if (j === 0 && HS(k, 11) >= p) continue;
      const life = 2.6 + 3.2 * HS(k + j * 997, 15);
      const age = t - tk; if (age > life) continue;
      const big = downbeat && b >= 16 ? 1.35 : 1;
      const kk = k + j * 997, seamSpot = HS(kk, 19) < 0.58;
      const x = seamSpot ? 452 + HS(kk, 12) * 84 : 40 + HS(kk, 12) * 400;
      let y = 280 + HS(kk, 13) * 1380;
      if (!seamSpot && x > 230 && y > 740 && y < 1060) y += (y < 900 ? -260 : 260);     // keep off the faces
      if (seamSpot && y > 770 && y < 1040) y += (y < 905 ? -250 : 250);
      out.push({
        x, y, seam: seamSpot,
        R: (30 + 95 * Math.pow(HS(kk, 14), 1.6)) * sz * big * (j ? 1.25 : 1) * (seamSpot ? 1.2 : 0.75),
        age, life, born: tk, hue: HS(k + j * 997, 16), drip: b >= 44 ? 0.9 : 0.25, grow: Math.abs(b - 48.5) < 0.01 ? 0.1 : 0.32
      });
    }
  }
  return out;
}

// ---- paper grain (pixel space) ----
const GRAINS = [];
function grain(alpha) {
  if (!GRAINS.length) for (let g = 0; g < 3; g++) {
    const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d');
    const im = x.createImageData(256, 256); const d = im.data;
    for (let i = 0; i < d.length; i += 4) { const v = 128 + (hsh(g * 7 + 1, i) * 2 - 1) * 62; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
    x.putImageData(im, 0, 0); GRAINS.push(c);
  }
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  const pat = ctx.createPattern(GRAINS[0], 'repeat');
  ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = alpha;
  ctx.fillStyle = pat; ctx.fillRect(0, 0, PXW, PXH);
  ctx.restore();
}
