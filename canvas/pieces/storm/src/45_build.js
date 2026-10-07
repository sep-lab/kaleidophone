// ---------------------------------------------------------------- buildings
// Painter's order, far to near from the point under the camera: with a camera straight down
// every box leans away from the middle of the frame, so a nearer box can only ever cover a
// farther one. Walls that face away are never drawn; the street wall gets windows and a shop.
const shadeWall = (c, o) => mul3(c, 0.74 + 0.12 * (o[0] * -0.55 + o[1] * -0.83));
function faceVisible(a, b) { const o = outN(a, b); return (CAM.x - a[0]) * o[0] + (CAM.y - a[1]) * o[1] > 0; }
function quadPath(g, A, B, C, D) { g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.lineTo(C[0], C[1]); g.lineTo(D[0], D[1]); g.closePath(); }

function drawPrism(g, quad, z0, z1, wall, roof, face) {
  const n = quad.length;
  for (let e = 0; e < n; e++) {
    const a = quad[e], b = quad[(e + 1) % n];
    if (!faceVisible(a, b)) continue;
    const A0 = proj(a[0], a[1], z0), B0 = proj(b[0], b[1], z0), B1 = proj(b[0], b[1], z1), A1 = proj(a[0], a[1], z1);
    quadPath(g, A0, B0, B1, A1); g.fillStyle = css(shadeWall(wall, outN(a, b))); g.fill();
    if (face) face(e, a, b);
  }
  tracePoly(g, quad, z1); g.fillStyle = css(roof); g.fill();
}

// window w (floor f, bay b) of a lot: 0 dark, 1 warm, 2 a television
function windowLight(seed, f, b, t) {
  const m = gameMin(t), u = H1(seed, f * 31 + b, 77);
  if (u < 0.05) return m < 420 + 30 * H1(seed, f, b) ? 1 : 0;                  // up all night
  if (u < 0.065) return m < 170 + 90 * H1(b, seed, f) ? 2 : 0;                 // the television, until 03:00-04:30
  if (u < 0.1) return m < 150 + 50 * H1(f, b, seed) ? 1 : 0;                   // late, then bed
  if (u < 0.58) return m > 330 + 128 * H1(seed, b, f + 5) ? 1 : 0;            // waking: 05:30-07:38
  return 0;
}
const LIT = [[255, 206, 138], [150, 182, 255]];

function shopState(lot, t) {           // how far the shutter is up, 0..1, and is it lit
  const m = gameMin(t);
  if (lot.shop === 'cafe' && lot.place && lot.place.name === 'night') return 1;
  let open;
  if (lot.place && lot.place.open) open = lot.place.open[0];
  else if (lot.shop === 'cafe') open = 6 * 60 + 30 + 75 * H1(lot.seed * 1e4 | 0, 3, 3);
  else if (lot.shop === 'shutter' || lot.shop === 'glass') open = H1(lot.seed * 1e4 | 0, 5, 5) < 0.4 ? 7 * 60 + 5 + 40 * H1(lot.seed * 1e4 | 0, 7, 7) : 9999;
  else return 0;
  return clamp((m - open) / 4);       // four game minutes (seconds) to roll up
}

// the street face: windows, balconies, the shop
function streetFace(g, lot, a, b, t) {
  const h = lot.h, L = lot.uLen;
  const mid = lerp2(a, b, 0.5), pz0 = proj(mid[0], mid[1], 0), pz1 = proj(mid[0], mid[1], h);
  const depthPx = Math.hypot(pz1[0] - pz0[0], pz1[1] - pz0[1]);
  if (depthPx < 2.2) return;
  const W = (u, z) => { const p = lerp2(a, b, u); return proj(p[0], p[1], z); };
  const glass = [40, 46, 62], rail = mul3(lot.wall, 0.55);
  const bays = Math.max(1, Math.floor(L / 3.4)), hw = Math.min(0.42, 0.65 / L * bays) / bays;
  const seed = lot.seed * 1e5 | 0;
  for (let f = 0; f < lot.floors; f++) {
    const z0 = 4.6 + f * 3.05 + 0.45, z1 = z0 + 2.15;
    if (depthPx > 7) {                                  // the balcony slab
      const s0 = W(0.02, z0 - 0.35), s1 = W(0.98, z0 - 0.35), s2 = W(0.98, z0 - 0.15), s3 = W(0.02, z0 - 0.15);
      quadPath(g, s0, s1, s2, s3); g.fillStyle = css(rail); g.fill();
    }
    for (let q = 0; q < bays; q++) {
      const uc = (q + 0.5) / bays, A = W(uc - hw, z0), B = W(uc + hw, z0), C = W(uc + hw, z1), D = W(uc - hw, z1);
      const lit = windowLight(seed, f, q, t);
      if (lit) {
        const col = LIT[lit - 1], fl = lit === 2 ? 0.6 + 0.4 * hsh(Math.floor(t * 9) + q, f + seed) : 1;
        EMIT.push(c => { quadPath(c, A, B, C, D); c.fillStyle = css(mul3(col, fl)); c.fill(); });
      } else if (depthPx > 3.5) { quadPath(g, A, B, C, D); g.fillStyle = css(glass); g.fill(); }
    }
  }
  // the ground floor
  const up = shopState(lot, t), z1 = 3.7;
  if (lot.shop === 'door') {
    quadPath(g, W(0.4, 0), W(0.6, 0), W(0.6, 3.0), W(0.4, 3.0)); g.fillStyle = css([74, 52, 40]); g.fill();
  } else {
    const A = W(0.07, 0), B = W(0.93, 0), C = W(0.93, z1), D = W(0.07, z1);
    const lit = lot.shop === 'cafe' ? up > 0 : lot.shop === 'glass' ? (up > 0 || H1(seed, 1, 9) < 0.2) : up > 0;
    if (lit || up > 0) {
      const warm = lot.shop === 'cafe' ? [255, 196, 120] : [236, 236, 220];
      EMIT.push(c => { quadPath(c, A, B, C, D); c.fillStyle = css(warm); c.fill(); });
    } else { quadPath(g, A, B, C, D); g.fillStyle = css(lot.shop === 'glass' ? glass : [44, 48, 56]); g.fill(); }
    // the shutter (persiana): ribbed steel with graffiti, rolling up from the street
    if (lot.shop !== 'glass' && up < 1) {
      const zb = up * z1, E = W(0.07, zb), Fp = W(0.93, zb);
      const steel = [128, 130, 136];
      if (lit || up > 0) EMIT.push(c => { quadPath(c, E, Fp, C, D); c.fillStyle = css(mul3(steel, 0.42)); c.fill(); });
      quadPath(g, E, Fp, C, D); g.fillStyle = css(steel); g.fill();
      if (depthPx > 5) {
        g.fillStyle = css(mul3(steel, 0.7));
        for (let z = zb + 0.4; z < z1; z += 0.55) { const p = W(0.07, z), q = W(0.93, z); g.fillRect(Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.abs(q[0] - p[0]) + 1, 1); }
        // graffiti: a few saturated blobs
        for (let k = 0; k < 3; k++) {
          const u = 0.15 + 0.7 * H1(seed, k, 13), z = zb + (z1 - zb) * (0.2 + 0.6 * H1(seed, k, 14));
          if (z > z1 - 0.3) continue;
          const p = W(u, z), col = pick([[220, 60, 120], [60, 200, 220], [250, 210, 60], [120, 220, 90], [240, 120, 40]], H1(seed, k, 15));
          g.fillStyle = css(col); g.fillRect(Math.round(p[0] - 1.5), Math.round(p[1] - 1), 3 + (k & 1), 2);
        }
      }
    }
  }
}

function drawRoofThings(g, lot, base, t) {
  const q0 = lot.quad[0], e = nrm(sub(lot.quad[1], q0)), v = scl(lot.out, -1), L = lot.uLen;
  const at = (u, w) => [q0[0] + e[0] * u + v[0] * w, q0[1] + e[1] * u + v[1] * w];
  const seed = lot.seed * 1e5 | 0, k = kAt(base);
  const box = (u, w, du, dw) => [at(u, w), at(u + du, w), at(u + du, w + dw), at(u, w + dw)];
  // the parapet, catching the light
  tracePoly(g, lot.quad, base); g.strokeStyle = css(mul3(lot.roof, 1.18)); g.lineWidth = 1; g.stroke();
  if (lot.panels && L > 8) { tracePoly(g, box(L * 0.2, 9, Math.min(5, L * 0.5), 2.2), base + 0.5); g.fillStyle = css([40, 52, 92]); g.fill(); }
  if (lot.sky) {
    const s = box(L * 0.55, 13, 1.3, 1.9), lit = H1(seed, 2, 2) < 0.4 && gameMin(t) < 300 + 160 * H1(seed, 3, 3);
    if (lit) EMIT.push(c => { tracePoly(c, s, base + 0.2); c.fillStyle = css([255, 214, 150]); c.fill(); });
    else { tracePoly(g, s, base + 0.2); g.fillStyle = css([60, 70, 86]); g.fill(); }
  }
  g.fillStyle = css(mul3(lot.roof, 0.62));
  for (let c = 0; c < lot.chimneys; c++) {
    const p = chimneyAt(lot, at, c), pp = proj(p[0], p[1], base + 1.2), s = Math.max(1, 0.6 * k);
    g.fillRect(Math.round(pp[0] - s / 2), Math.round(pp[1] - s / 2), Math.ceil(s), Math.ceil(s));
  }
  if (lot.tank && L > 6) {
    const p = at(L * 0.3, 17), pp = proj(p[0], p[1], base + 1.6);
    g.beginPath(); g.arc(pp[0], pp[1], Math.max(1, 0.75 * k), 0, TAU); g.fillStyle = css([150, 154, 160]); g.fill();
  }
  if (lot.hut && L > 7) drawPrism(g, box(L * 0.42, 12, 3, 3.6), base, base + 2.6, lot.wall, mul3(lot.roof, 0.9));
  laundry(g, lot, at, base, t);
  roofSteam(lot, at, base, t);
}

// the roof's surface: tile courses on the clay roofs, a terrace grid on the others
function roofTexture(g, lot) {
  const k = kAt(lot.h);
  if (k < 3.2) return;
  const q0 = lot.quad[0], e = nrm(sub(lot.quad[1], q0)), v = scl(lot.out, -1), L = lot.uLen;
  const at = (u, w) => proj(q0[0] + e[0] * u + v[0] * w, q0[1] + e[1] * u + v[1] * w, lot.h);
  const clay = lot.roof[0] > lot.roof[2] + 30, gap = clay ? 0.9 : 1.6;
  g.save(); tracePoly(g, lot.quad, lot.h); g.clip();
  g.strokeStyle = css(mul3(lot.roof, clay ? 0.8 : 0.9)); g.lineWidth = 1;
  g.beginPath();
  for (let w = gap; w < DEPTH; w += gap) { const a = at(-2, w), b = at(L + 2, w); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
  if (!clay) for (let u = gap; u < L; u += gap) { const a = at(u, 0), b = at(u, DEPTH); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
  g.stroke(); g.restore();
}
function drawLot(g, lot, t) {
  drawPrism(g, lot.quad, 0, lot.h, lot.wall, lot.roof, (e, a, b) => { if (e === 0) streetFace(g, lot, a, b, t); });
  roofTexture(g, lot);
  if (lot.attic && lot.uLen > 8) {
    // the set-back top floor: a terrace along the street, plants in pots on it
    const v = scl(lot.out, -1), q0 = add(lot.quad[0], scl(v, 2.6)), q1 = add(lot.quad[1], scl(v, 2.6));
    const r1 = add(lot.quad[2], scl(v, -1.2)), r0 = add(lot.quad[3], scl(v, -1.2));
    // keep the attic inside the lot along the street: pull the ends in a little
    const e = nrm(sub(q1, q0)), aq = [add(q0, scl(e, 0.8)), sub(q1, scl(e, 0.8)), sub(r1, scl(e, 0.8)), add(r0, scl(e, 0.8))];
    drawRoofThings(g, lot, lot.h, t);
    drawPrism(g, aq, lot.h, lot.h + 3, mul3(lot.wall, 0.95), mul3(lot.roof, 0.95));
    drawFlues(g, lot, t);
    const seed = lot.seed * 1e5 | 0, k = kAt(lot.h);
    if (k > 10) for (let c = 0; c < 4; c++) {
      const p = lerp2(lot.quad[0], lot.quad[1], 0.1 + 0.8 * H1(seed, c, 31)), pp = proj(p[0] + v[0] * 1.2, p[1] + v[1] * 1.2, lot.h + 0.6);
      g.fillStyle = css([70, 112, 60]); g.fillRect(Math.round(pp[0]), Math.round(pp[1]), 2, 2);
    }
  } else { drawRoofThings(g, lot, lot.h, t); drawFlues(g, lot, t); }
}

function drawBuildings(g, t, W) {
  const items = [];
  const [vx0, vy0, vx1, vy1] = viewRect(40);
  for (const B of W.blocks) {
    for (const lot of B.lots) {
      const c = centroid(lot.quad);
      if (c[0] < vx0 || c[0] > vx1 || c[1] < vy0 || c[1] > vy1) continue;
      items.push({ d: Math.hypot(c[0] - CAM.x, c[1] - CAM.y), lot });
    }
    for (const cb of B.court) {
      const c = centroid(cb.quad);
      if (c[0] < vx0 || c[0] > vx1 || c[1] < vy0 || c[1] > vy1) continue;
      items.push({ d: Math.hypot(c[0] - CAM.x, c[1] - CAM.y), court: cb, B });
    }
  }
  items.sort((p, q) => q.d - p.d);
  for (const it of items) {
    if (it.lot) drawLot(g, it.lot, t);
    else if (it.court.kind === 'box') {
      const cb = it.court;
      drawPrism(g, cb.quad, 0, cb.h, cb.wall, cb.roof);
      tracePoly(g, cb.quad, cb.h); g.strokeStyle = css(mul3(cb.roof, 1.15)); g.lineWidth = 1; g.stroke();
    } else drawCourtTrees(g, it.court, it.B, t);
  }
}
function drawCourtTrees(g, c, B, t) {
  for (let n = 0; n < c.trees; n++) {
    const u = H1(B.i * 3 + n, B.j, 51), w = H1(B.j + n, B.i, 52);
    const p = [lerp(c.quad[0][0] + 2, c.quad[1][0] - 2, u), lerp(c.quad[0][1] + 2, c.quad[2][1] - 2, w)];
    canopy(g, p, 6 + 2 * u, 2.2 + 1.2 * w, pick(PAL.tree, w), (B.i * 7 + B.j * 3 + n) | 0, t, 1);
  }
}
// a plane tree from above: a ring of leaf clumps round a darker heart, three tones, autumn colours
function canopy(g, p, h, r, col, seed, t, alpha) {
  const k = kAt(h), c = proj(p[0], p[1], h), R = r * k;
  if (c[0] < -R || c[0] > BW + R || c[1] < -R || c[1] > BH + R) return;
  g.globalAlpha = alpha;
  const sway = Math.sin(t * 0.9 + seed) * 0.05;
  g.fillStyle = css(mul3(col, 0.42));
  g.beginPath(); g.arc(c[0] + R * 0.1, c[1] + R * 0.12, R * 0.92, 0, TAU); g.fill();
  for (let q = 0; q < 7; q++) {
    const a = q / 7 * TAU + seed * 0.37 + sway, d = R * (0.48 + 0.12 * hsh(seed, q)), rr = R * (0.32 + 0.12 * hsh(seed, q + 9));
    g.fillStyle = css(mul3(col, 0.72)); g.beginPath(); g.arc(c[0] + Math.cos(a) * d, c[1] + Math.sin(a) * d, rr, 0, TAU); g.fill();
    g.fillStyle = css(mul3(col, 1.0)); g.beginPath(); g.arc(c[0] + Math.cos(a) * d - rr * 0.25, c[1] + Math.sin(a) * d - rr * 0.3, rr * 0.6, 0, TAU); g.fill();
  }
  g.fillStyle = css(mul3(col, 1.22)); g.beginPath(); g.arc(c[0] - R * 0.18, c[1] - R * 0.2, R * 0.22, 0, TAU); g.fill();
  g.globalAlpha = 1;
}
