// ---------------------------------------------------------------- the city: a grid of chamfered blocks, from above
// World units are metres; x east, y north. Street centrelines at x = i*P and y = j*P, 20 m wide
// (a 10 m roadway between two 5 m sidewalks); each block is the square between them with its four
// corners cut at 45 degrees -- the octagons that make the grid recognisable from the air. Blocks
// are perimeter rings of 6-to-8-storey lots around an inner courtyard.
const P = 133.3, HALF = 10, ROAD = 5, CH = 14.14, DEPTH = 21;

const polyArea = p => { let a = 0; for (let i = 0; i < p.length; i++) { const q = p[i], r = p[(i + 1) % p.length]; a += q[0] * r[1] - r[0] * q[1]; } return a / 2; };
const centroid = p => { let x = 0, y = 0; for (const q of p) { x += q[0]; y += q[1]; } return [x / p.length, y / p.length]; };
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]], add = (a, b) => [a[0] + b[0], a[1] + b[1]], scl = (a, k) => [a[0] * k, a[1] * k];
const len = a => Math.hypot(a[0], a[1]), nrm = a => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
const lerp2 = (a, b, u) => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
// outward normal of edge a->b of a CCW polygon (y up)
const outN = (a, b) => nrm([b[1] - a[1], -(b[0] - a[0])]);

function octagon(x0, y0, x1, y1, c) {     // CCW from the south side: S, SE, E, NE, N, NW, W, SW
  return [[x0 + c, y0], [x1 - c, y0], [x1, y0 + c], [x1, y1 - c], [x1 - c, y1], [x0 + c, y1], [x0, y1 - c], [x0, y0 + c]];
}
function inset(poly, d) {                 // a convex CCW polygon moved in by d on every side
  const n = poly.length, lines = [];
  for (let i = 0; i < n; i++) {
    const a = poly[i], b = poly[(i + 1) % n], o = outN(a, b);
    lines.push([sub(a, scl(o, d)), sub(b, a)]);
  }
  const out = [];
  for (let i = 0; i < n; i++) {
    const [p1, d1] = lines[(i - 1 + n) % n], [p2, d2] = lines[i];
    const den = d1[0] * d2[1] - d1[1] * d2[0];
    const u = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / (den || 1e-9);
    out.push([p1[0] + d1[0] * u, p1[1] + d1[1] * u]);
  }
  return out;
}

// ---------------------------------------------------------------- places the film needs (set by the route)
// A lot whose street edge passes within 3 m of one of these points is that place.
const PLACES = [];       // { at: [x, y], kind: 'cafe' | ..., ...props }
function placeAt(q0, q1) {
  for (const pl of PLACES) {
    const ab = sub(q1, q0), L = len(ab), u = clamp(((pl.at[0] - q0[0]) * ab[0] + (pl.at[1] - q0[1]) * ab[1]) / (L * L));
    const c = lerp2(q0, q1, u);
    if (Math.hypot(c[0] - pl.at[0], c[1] - pl.at[1]) < 3) return pl;
  }
  return null;
}

// ---------------------------------------------------------------- blocks, memoised
const BLOCKS = new Map();
function block(i, j) {
  const key = i + ',' + j;
  let B = BLOCKS.get(key);
  if (B) return B;
  const x0 = i * P + HALF, x1 = (i + 1) * P - HALF, y0 = j * P + HALF, y1 = (j + 1) * P - HALF;
  const O = octagon(x0, y0, x1, y1, CH), I = inset(O, DEPTH);
  const lots = [];
  let id = 0;
  for (let k = 0; k < 8; k++) {
    const oa = O[k], ob = O[(k + 1) % 8], ia = I[k], ib = I[(k + 1) % 8], L = len(sub(ob, oa));
    // split the side into lots: chamfers are one corner lot, long sides 10-19 m frontages
    const us = [0];
    if (k % 2 === 1) us.push(1);
    else {
      let s = 0, n = 0;
      while (true) {
        const w = 10 + 9 * H1(i * 31 + k, j * 17 + n, 5);
        if (s + w > L - 7) { us.push(1); break; }
        s += w; us.push(s / L); n++;
      }
    }
    for (let m = 0; m < us.length - 1; m++) {
      const u0 = us[m], u1 = us[m + 1];
      const q0 = lerp2(oa, ob, u0), q1 = lerp2(oa, ob, u1), r1 = lerp2(ia, ib, u1), r0 = lerp2(ia, ib, u0);
      const hs = H1(i * 7 + k * 3 + m, j * 11 + m, 9);
      const floors = 5 + Math.floor(hs * 4);
      const h = 4.6 + floors * 3.05;
      const place = placeAt(q0, q1);
      const lot = {
        id: key + ':' + id++, k, quad: [q0, q1, r1, r0], street: [q0, q1], h, floors,
        wall: pick(PAL.walls, H1(hs * 1e4 | 0, k, 1)), roof: pick(PAL.roofs, H1(m, k * 5 + i, j + 2)),
        attic: H1(i + 3, j * 5 + k, m + 7) < 0.55, hut: H1(i, j + k, m + 11) < 0.7,
        tank: H1(i + k, j, m + 13) < 0.45, panels: H1(i * 3 + m, j, k + 17) < 0.2, sky: H1(i + m, j * 7, k + 19) < 0.35,
        chimneys: Math.floor(H1(m * 3, i + j, k + 23) * 4),
        shop: place ? place.kind : pick(['shutter', 'shutter', 'shutter', 'door', 'glass', 'shutter', 'door', 'cafe'], H1(i * 13 + m, j * 3 + k, 29)),
        place, seed: hs,
        uLen: len(sub(q1, q0)), out: outN(q0, q1),
      };
      if (k % 2 === 1 && !place && H1(i, j, k + 31) < 0.4) lot.shop = 'cafe';
      lots.push(lot);
    }
  }
  // the courtyard: low workshops, gardens with trees
  const court = [];
  const cx0 = x0 + DEPTH + 3, cx1 = x1 - DEPTH - 3, cy0 = y0 + DEPTH + 3, cy1 = y1 - DEPTH - 3;
  const n = 3, cw = (cx1 - cx0) / n, chh = (cy1 - cy0) / n;
  for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) {
    const u = H1(i * 5 + a, j * 9 + b, 37);
    const bx0 = cx0 + a * cw + 1, by0 = cy0 + b * chh + 1, bx1 = bx0 + cw - 2, by1 = by0 + chh - 2;
    if (u < 0.55) court.push({ kind: 'box', quad: [[bx0, by0], [bx1, by0], [bx1, by1], [bx0, by1]], h: 3.5 + 2 * H1(a, b, i + j), roof: pick(PAL.roofs, H1(a + 5, b, j)), wall: [150, 144, 136], sky: H1(a, b + 3, i) < 0.3 });
    else court.push({ kind: 'garden', quad: [[bx0, by0], [bx1, by0], [bx1, by1], [bx0, by1]], trees: 1 + Math.floor(H1(a, b, 41 + i) * 3) });
  }
  B = { i, j, O, I, lots, court, x0, y0, x1, y1, curb: inset(O, -ROAD) };
  BLOCKS.set(key, B);
  return B;
}

// ---------------------------------------------------------------- street furniture, memoised per street segment
// A segment is the straight stretch of one street between two intersections, beyond the chamfers.
const SEGS = new Map();
function segment(dir, i, j) {     // dir 'v': the N-S street x = i*P from y = j*P to (j+1)*P; 'h': the E-W street y = j*P
  const key = dir + i + ',' + j;
  let S = SEGS.get(key);
  if (S) return S;
  const items = { trees: [], lamps: [], parked: [], bins: [], motos: [] };
  const a = (dir === 'v' ? j : i) * P + 24, b = ((dir === 'v' ? j : i) + 1) * P - 24, c = (dir === 'v' ? i : j) * P;
  const at = (along, across) => dir === 'v' ? [c + across, along] : [along, c + across];
  const seed = (dir === 'v' ? 1 : 2) * 1000 + i * 37 + j * 101;
  for (const side of [-1, 1]) {
    for (let s = a + 3, n = 0; s < b - 2; s += 7.4, n++) {
      if (H1(seed, n, side + 3) < 0.78) items.trees.push({ p: at(s + (H1(seed, n, 7) - 0.5) * 1.2, side * 6.3), r: 1.6 + 0.7 * H1(seed, n, 8), h: 7 + 1.6 * H1(seed, n, 9), c: pick(PAL.tree, H1(seed, n, side + 10)), seed: H1(seed, n, 12) });
    }
    for (let s = a + 6 + (side > 0 ? 0 : 12), n = 0; s < b; s += 24, n++) items.lamps.push({ p: at(s, side * 5.35), head: at(s, side * 4.2), h: 8.6, side });
    for (let s = a + 2, n = 0; s < b - 4; s += 5.3, n++) {
      const u = H1(seed + side * 7, n, 15);
      if (u < 0.5) items.parked.push({ p: at(s + 2.2, side * 3.9), ang: dir === 'v' ? (side > 0 ? 90 : -90) : (side > 0 ? 0 : 180), c: pick(PAL.cars, H1(seed, n, side + 16)), taxi: u < 0.07, seed: u });
      else if (u > 0.93 && n > 1) {
        for (let q = 0; q < 5; q++) items.bins.push({ p: at(s + q * 1.25 - 1.5, side * 3.9), c: PAL.bins[q], dir });
        s += 3;
      }
    }
    for (let s = a + 10, n = 0; s < b - 6; s += 31, n++) if (H1(seed, n, side + 21) < 0.5) {
      const k = 3 + Math.floor(H1(seed, n, 22) * 4);
      for (let q = 0; q < k; q++) items.motos.push({ p: at(s + q * 0.9, side * 5.9), dir, c: pick(PAL.cars, H1(seed + q, n, 23)) });
    }
  }
  S = { dir, i, j, items };
  SEGS.set(key, S);
  return S;
}

// The crossings of intersection (i, j): four zebras where the streets meet the octagon, and
// traffic lights at their ends.
function crossing(i, j) {
  const cx = i * P, cy = j * P, zebras = [], poles = [];
  const mouth = 27.07 - 17;      // the roadway's half-width at the zebra (x + y = 27.07 is the chamfer's curb)
  for (const s of [-1, 1]) {
    zebras.push({ c: [cx, cy + s * 17], w: 2 * mouth, d: 3.4, dir: 'h' });     // across the N-S street (bars run N-S)
    zebras.push({ c: [cx + s * 17, cy], w: 2 * mouth, d: 3.4, dir: 'v' });     // across the E-W street
    for (const t of [-1, 1]) { poles.push([cx + t * (mouth + 0.6), cy + s * 15.2]); poles.push([cx + s * 15.2, cy + t * (mouth + 0.6)]); }
  }
  return { i, j, cx, cy, zebras, poles };
}

// What is on screen: the blocks, segments and crossings whose footprint meets the ground rect
function visibleWorld(x0, y0, x1, y1) {
  const out = { blocks: [], segs: [], crossings: [] };
  const i0 = Math.floor(x0 / P) - 1, i1 = Math.floor(x1 / P) + 1, j0 = Math.floor(y0 / P) - 1, j1 = Math.floor(y1 / P) + 1;
  for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
    const bx0 = i * P + HALF, bx1 = (i + 1) * P - HALF, by0 = j * P + HALF, by1 = (j + 1) * P - HALF;
    if (bx1 > x0 - 30 && bx0 < x1 + 30 && by1 > y0 - 30 && by0 < y1 + 30) out.blocks.push(block(i, j));
    if (Math.abs(i * P - (x0 + x1) / 2) < (x1 - x0) / 2 + 15 && (j + 1) * P > y0 - 15 && j * P < y1 + 15) out.segs.push(segment('v', i, j));
    if (Math.abs(j * P - (y0 + y1) / 2) < (y1 - y0) / 2 + 15 && (i + 1) * P > x0 - 15 && i * P < x1 + 15) out.segs.push(segment('h', i, j));
    if (i * P > x0 - 40 && i * P < x1 + 40 && j * P > y0 - 40 && j * P < y1 + 40) out.crossings.push(crossing(i, j));
  }
  return out;
}
