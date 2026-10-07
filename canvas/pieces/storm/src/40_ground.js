// ---------------------------------------------------------------- the ground
// Roadway, pavements, kerbs, lane paint, zebras, the courtyards' floors; the wet: everything is
// soaked until 0:34, then dries slowly towards dawn -- except where his storm has passed.
function groundWet(t) { return t < SONG.fadeB ? 1 : 0.28 + 0.72 * Math.exp(-(t - SONG.fadeB) / 120); }
const EMIT = [];          // emissive draws queued for after the light pass: fn(ctx)

function drawGround(g, t, W) {
  const wet = groundWet(t);
  const base = mix3(PAL.asphalt, PAL.asphaltWet, wet);
  g.fillStyle = css(base); g.fillRect(0, 0, BW, BH);
  const k0 = kAt(0);
  drawWear(g, W, base, wet, k0);
  // the pavements: each block's kerb octagon, the kerb itself a lighter ring
  const sw = mix3(PAL.sidewalk, PAL.sidewalkWet, wet);
  for (const B of W.blocks) {
    tracePoly(g, B.curb); g.fillStyle = css(PAL.curb); g.fill();
    tracePoly(g, inset(B.curb, 0.35)); g.fillStyle = css(sw); g.fill();
    // panot tiles: a faint grid on close views
    if (k0 > 12) {
      g.save(); tracePoly(g, inset(B.curb, 0.35)); g.clip();
      g.fillStyle = css(mul3(sw, 0.9));
      const [vx0, vy0, vx1, vy1] = viewRect(2);
      for (let x = Math.floor(vx0 / 0.6) * 0.6; x < vx1; x += 1.2) { const a = proj(x, 0, 0)[0]; g.fillRect(Math.round(a), 0, 1, BH); }
      for (let y = Math.floor(vy0 / 0.6) * 0.6; y < vy1; y += 1.2) { const a = proj(0, y, 0)[1]; g.fillRect(0, Math.round(a), BW, 1); }
      g.restore();
    }
    // the courtyard's floor (the lots cover the rest of the block)
    tracePoly(g, B.I); g.fillStyle = css([92, 86, 80]); g.fill();
    for (const c of B.court) if (c.kind === 'garden') { tracePoly(g, c.quad); g.fillStyle = css(PAL.garden); g.fill(); }
  }
  drawLeaves(g, W, wet, k0);
  // lane paint (traffic keeps right): the parking lanes' edges; the centre line, solid for the
  // last ten metres before a crossing and dashed between; on each approach a stop line and an arrow
  const paint = css(mix3(PAL.marking, [120, 120, 118], wet * 0.4));
  g.fillStyle = paint;
  for (const S of W.segs) {
    const ax = (S.dir === 'v' ? S.j : S.i) * P, bx = ax + P, c = (S.dir === 'v' ? S.i : S.j) * P;
    const at = (s, o) => S.dir === 'v' ? [c + o, s] : [s, c + o];
    for (const off of [-2.9, 2.9]) lineW(g, at(ax + 22, off), at(bx - 22, off), 0.1);
    lineW(g, at(ax + 20.1, 0), at(ax + 30, 0), 0.14); lineW(g, at(bx - 30, 0), at(bx - 20.1, 0), 0.14);
    for (let s = ax + 33; s < bx - 33; s += 8) lineW(g, at(s, 0), at(Math.min(s + 3.5, bx - 33), 0), 0.14);
    for (const sg of [1, -1]) {                      // sg +1: the traffic heading for the crossing at bx
      const os = S.dir === 'v' ? sg : -sg, end = sg > 0 ? bx : ax;
      lineW(g, at(end - sg * 19.9, os * 0.12), at(end - sg * 19.9, os * 2.9), 0.4);
      if (k0 > 4) laneArrow(g, at(end - sg * 23.4, os * 1.45), S.dir === 'v' ? [0, sg] : [sg, 0], H1(S.i * 7 + S.j * 3, sg + 2, 311) < 0.4);
    }
  }
  // zebras: bars 0.5 m wide, 0.55 m apart, across the roadway
  for (const X of W.crossings) for (const z of X.zebras) {
    const n = Math.floor(z.w / 1.05);
    for (let q = 0; q < n; q++) {
      const o = -z.w / 2 + q * 1.05 + 0.3;
      const c = z.dir === 'h' ? [z.c[0] + o, z.c[1]] : [z.c[0], z.c[1] + o];
      const hw = z.dir === 'h' ? [0.25, z.d / 2] : [z.d / 2, 0.25];
      tracePoly(g, [[c[0] - hw[0], c[1] - hw[1]], [c[0] + hw[0], c[1] - hw[1]], [c[0] + hw[0], c[1] + hw[1]], [c[0] - hw[0], c[1] + hw[1]]]);
      g.fill();
    }
  }
  // no stopping on the chamfers: a yellow line along each corner's kerb, between its zebras
  g.fillStyle = css(mix3([224, 176, 40], [150, 124, 56], wet * 0.45));
  for (const X of W.crossings) for (const [sx, sy] of [[1, 1], [1, -1], [-1, -1], [-1, 1]]) lineW(g, [X.cx + sx * 11.7, X.cy + sy * 15.0], [X.cx + sx * 15.0, X.cy + sy * 11.7], 0.15);
  // manholes and gratings
  g.fillStyle = css([44, 44, 48]);
  for (const S of W.segs) {
    const a = (S.dir === 'v' ? S.j : S.i) * P + 30, c = (S.dir === 'v' ? S.i : S.j) * P;
    for (let q = 0; q < 4; q++) {
      const s = a + q * 19 + 7 * H1(S.i, S.j, q), off = (H1(S.j, q, S.i) - 0.5) * 6;
      const p = S.dir === 'v' ? [c + off, s] : [s, c + off], pp = proj(p[0], p[1]);
      const r = 0.35 * k0; g.beginPath(); g.arc(pp[0], pp[1], Math.max(0.6, r), 0, TAU); g.fill();
    }
  }
}
// a lane arrow on the ground: its tip at `tip`, pointing along `f`; `right` adds the branch that
// turns off to the kerb side
function laneArrow(g, tip, f, right) {
  const r = [f[1], -f[0]], P2 = (b, d) => [tip[0] - f[0] * b + r[0] * d, tip[1] - f[1] * b + r[1] * d];
  tracePoly(g, [P2(4.6, -0.09), P2(1.5, -0.09), P2(1.5, 0.09), P2(4.6, 0.09)]); g.fill();
  tracePoly(g, [P2(1.6, -0.42), P2(0, 0), P2(1.6, 0.42)]); g.fill();
  if (right) {
    const u = nrm([f[0] + r[0], f[1] + r[1]]), n = [u[1], -u[0]], B0 = P2(3.3, 0.02), B1 = add(B0, scl(u, 0.85)), T = add(B1, scl(u, 0.75));
    tracePoly(g, [add(B0, scl(n, 0.09)), add(B1, scl(n, 0.09)), sub(B1, scl(n, 0.09)), sub(B0, scl(n, 0.09))]); g.fill();
    tracePoly(g, [add(B1, scl(n, 0.32)), T, sub(B1, scl(n, 0.32))]); g.fill();
  }
}

// ---------------------------------------------------------------- the wear of the asphalt
// So that an empty crossing at dawn is a surface and not a colour: the patches where the street
// was opened and closed again, a trench across a crossing, cracks and their black tar seals, the
// arcs that turning tyres polish into the corners, oil where cars wait at the line, iron lids, and
// the stone in the asphalt itself. Memoised per crossing and per street segment, world-anchored.
const WEAR = new Map();
function wearOf(kind, i, j) {
  const key = kind + i + ',' + j;
  let w = WEAR.get(key);
  if (w) return w;
  const sd = (kind === 'x' ? 5000 : kind === 'v' ? 6000 : 7000) + i * 41 + j * 113;
  let nr = 0;
  const R = () => H1(sd, nr++, 307);
  const crack = (p, h, m, stepL, turn) => {
    const pts = [p];
    for (let s = 0; s < m; s++) { h += (R() - 0.5) * turn; const q = pts[pts.length - 1], l = stepL * (0.6 + 0.8 * R()); pts.push([q[0] + Math.cos(h) * l, q[1] + Math.sin(h) * l]); }
    return pts;
  };
  w = { patches: [], cracks: [], seals: [], arcs: [], oil: [], lids: [], box: null };
  if (kind === 'x') {
    const cx = i * P, cy = j * P;
    const open = (u, v) => Math.abs(u) <= 20.5 && Math.abs(v) <= 20.5 && (Math.abs(u) <= 4.6 || Math.abs(v) <= 4.6 || Math.abs(u) + Math.abs(v) <= 26.2);
    const spot = (lim, avoid = 1.8) => {
      for (let k = 0; k < 10; k++) {
        const u = (R() - 0.5) * 2 * lim, v = (R() - 0.5) * 2 * lim;
        if (open(u, v) && Math.max(Math.abs(u), Math.abs(v)) > avoid) return [cx + u, cy + v];
      }
      return null;
    };
    for (let q = 2 + Math.floor(R() * 3); q > 0; q--) {
      const c = spot(18); if (!c) continue;
      const a = 0.7 + 1.6 * R(), b = 0.5 + 1.2 * R();
      w.patches.push({ r: [c[0] - a, c[1] - b, c[0] + a, c[1] + b], tone: R() < 0.6 ? 0.92 : 1.07 });
    }
    if (R() < 0.65) {                                  // a trench across the crossing, kerb to kerb
      const o = (R() - 0.5) * 22, hw = 0.36 + 0.12 * R();
      w.patches.push({ r: R() < 0.5 ? [cx - 23, cy + o - hw, cx + 23, cy + o + hw] : [cx + o - hw, cy - 23, cx + o + hw, cy + 23], tone: 0.93 });
    }
    // tyre polish: the right turns, faint, hugging each corner
    for (const [sx, sy] of [[1, 1], [1, -1], [-1, -1], [-1, 1]]) {
      const phi = Math.atan2(-sy, -sx), r = 11 + 2.5 * R(), c = 1.45 + r, a = 0.035 + 0.02 * R();
      for (const d of [-0.8, 0.8]) w.arcs.push({ c: [cx + sx * c, cy + sy * c], r: r + d, a0: phi - Math.PI / 4, a1: phi + Math.PI / 4, a });
    }
    // oil where the cars wait at the stop lines, and a few drips in the crossing
    for (const [ux, uy, ou, ov] of [[0, -1, 1.45, 0], [0, 1, -1.45, 0], [-1, 0, 0, -1.45], [1, 0, 0, 1.45]]) {
      for (let q = 3 + Math.floor(R() * 4); q > 0; q--) {
        const d = 20.8 + 13 * R(), j2 = (R() - 0.5) * 0.7;
        w.oil.push({ p: [cx + ux * d + ou + (uy ? j2 : 0), cy + uy * d + ov + (ux ? j2 : 0)], rx: 0.3 + 0.32 * R(), ry: 0.22 + 0.22 * R(), rot: R() * Math.PI, a: 0.14 + 0.12 * R() });
      }
    }
    w.oil[Math.floor(R() * w.oil.length)].sheen = true;
    for (let q = 2; q > 0; q--) { const c = spot(14, 3); if (c) w.oil.push({ p: c, rx: 0.2 + 0.2 * R(), ry: 0.16 + 0.14 * R(), rot: R() * Math.PI, a: 0.12 + 0.1 * R() }); }
    for (let q = 5 + Math.floor(R() * 4); q > 0; q--) {
      const c = spot(19); if (!c) continue;
      const h = R() * TAU, pts = crack(c, h, 4 + Math.floor(R() * 5), 0.9, 1.3);
      w.cracks.push(pts);
      if (R() < 0.4) w.cracks.push(crack(pts[pts.length >> 1], h + (R() < 0.5 ? 1 : -1), 3, 0.7, 1.2));
    }
    for (let q = 1 + Math.floor(R() * 2); q > 0; q--) { const c = spot(16); if (c) w.seals.push(crack(c, R() * TAU, 9 + Math.floor(R() * 7), 1.1, 0.5)); }
    const m0 = spot(12, 3.5); if (m0) w.lids.push({ p: m0, round: true });
    for (let q = 1 + Math.floor(R() * 2); q > 0; q--) { const c = spot(19, 6); if (c) w.lids.push({ p: c, round: false, rot: R() < 0.5 ? 0 : Math.PI / 2 }); }
    w.box = [cx - 36, cy - 36, cx + 36, cy + 36];
  } else {
    const a0 = (kind === 'v' ? j : i) * P + 21, b0 = a0 + P - 42, c = (kind === 'v' ? i : j) * P;
    const at = (s, o) => kind === 'v' ? [c + o, s] : [s, c + o];
    const rect = (s0, s1, o0, o1) => { const p = at(s0, o0), q = at(s1, o1); return [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[0], q[0]), Math.max(p[1], q[1])]; };
    for (let q = 2 + Math.floor(R() * 3); q > 0; q--) {
      const s = lerp(a0 + 3, b0 - 3, R()), o = (R() - 0.5) * 7, L = 1.2 + 3 * R(), Wd = 0.9 + 1.8 * R();
      w.patches.push({ r: rect(s - L / 2, s + L / 2, o - Wd / 2, o + Wd / 2), tone: R() < 0.6 ? 0.92 : 1.07 });
    }
    for (let q = Math.floor(R() * 2.4); q > 0; q--) {   // a service trench out from the kerb
      const s = lerp(a0 + 6, b0 - 6, R()), hw = 0.3 + 0.1 * R(), side = R() < 0.5 ? -1 : 1;
      w.patches.push({ r: rect(s - hw, s + hw, side * 5.2, side * (-0.4 - 2 * R())), tone: 0.92 });
    }
    for (let q = 4 + Math.floor(R() * 4); q > 0; q--) {
      const s = lerp(a0 + 2, b0 - 2, R()), o = (R() - 0.5) * 8.5;
      w.cracks.push(crack(at(s, o), R() * TAU, 3 + Math.floor(R() * 5), 0.9, 1.3));
    }
    if (R() < 0.7) {                                   // the paving joint beside the centre line, sealed
      const o = (R() < 0.5 ? -1 : 1) * (0.25 + 0.2 * R()), s0 = lerp(a0, b0, R() * 0.4), L = 15 + 30 * R(), pts = [];
      for (let s = s0; s < Math.min(b0, s0 + L); s += 1.2) pts.push(at(s, o + (R() - 0.5) * 0.12));
      w.seals.push(pts);
    }
    for (let q = 3 + Math.floor(R() * 4); q > 0; q--) {
      const s = lerp(a0 + 2, b0 - 2, R()), o = (R() < 0.5 ? -1 : 1) * (1.45 + (R() - 0.5) * 0.7);
      w.oil.push({ p: at(s, o), rx: 0.3 + 0.3 * R(), ry: 0.22 + 0.2 * R(), rot: R() * Math.PI, a: 0.12 + 0.12 * R() });
    }
    if (R() < 0.6) w.lids.push({ p: at(lerp(a0 + 8, b0 - 8, R()), (R() - 0.5) * 4), round: false, rot: kind === 'v' ? 0 : Math.PI / 2 });
    w.box = rect(a0 - 1, b0 + 1, -5.5, 5.5);
  }
  WEAR.set(key, w);
  return w;
}
function drawWear(g, W, base, wet, k0) {
  const [vx0, vy0, vx1, vy1] = viewRect(1);
  const vis = [];
  for (const X of W.crossings) vis.push(wearOf('x', X.i, X.j));
  for (const S of W.segs) vis.push(wearOf(S.dir, S.i, S.j));
  const seen = vis.filter(w => w.box[2] > vx0 && w.box[0] < vx1 && w.box[3] > vy0 && w.box[1] < vy1);
  const onScreen = (c, m) => c[0] > -m && c[0] < BW + m && c[1] > -m && c[1] < BH + m;
  // the patches, their sealed edges
  for (const w of seen) for (const pa of w.patches) {
    const [x0, y0, x1, y1] = pa.r;
    if (x1 < vx0 || x0 > vx1 || y1 < vy0 || y0 > vy1) continue;
    const a = proj(x0, y1), b = proj(x1, y0), X = Math.round(a[0]), Y = Math.round(a[1]), Wd = Math.max(1, Math.round(b[0]) - X), Ht = Math.max(1, Math.round(b[1]) - Y);
    g.fillStyle = css(mul3(base, pa.tone)); g.fillRect(X, Y, Wd, Ht);
    if (k0 > 5 && Wd > 2 && Ht > 2) { g.strokeStyle = css(mul3(base, 0.62), 0.55); g.lineWidth = 1; g.strokeRect(X + 0.5, Y + 0.5, Wd - 1, Ht - 1); }
  }
  // the tyres' polish
  if (k0 > 3) {
    g.lineCap = 'butt'; g.lineWidth = Math.max(1, 0.3 * k0);
    for (const w of seen) for (const ar of w.arcs) {
      const c = proj(ar.c[0], ar.c[1]);
      g.strokeStyle = css(mul3(base, 0.5), ar.a.toFixed(3));
      g.beginPath(); g.arc(c[0], c[1], ar.r * k0, -ar.a1, -ar.a0); g.stroke();
    }
  }
  // oil; on a wet street the odd one shows its rainbow
  if (k0 > 4) for (const w of seen) for (const o of w.oil) {
    const c = proj(o.p[0], o.p[1]);
    if (!onScreen(c, 20)) continue;
    g.fillStyle = `rgba(10,10,16,${o.a.toFixed(3)})`;
    g.beginPath(); g.ellipse(c[0], c[1], o.rx * k0, o.ry * k0, -o.rot, 0, TAU); g.fill();
    g.beginPath(); g.ellipse(c[0] + o.rx * 0.45 * k0, c[1] - o.ry * 0.3 * k0, o.rx * 0.5 * k0, o.ry * 0.55 * k0, -o.rot, 0, TAU); g.fill();
    if (o.sheen && wet > 0.25 && k0 > 9) {
      g.lineWidth = 1;
      [[200, 90, 210], [70, 200, 210], [230, 200, 80]].forEach((col, q) => {
        g.strokeStyle = css(col, (0.45 * Math.min(1, wet * 1.6)).toFixed(3));
        g.beginPath(); g.ellipse(c[0], c[1], o.rx * k0 * (0.75 - 0.2 * q), o.ry * k0 * (0.75 - 0.2 * q), -o.rot, 0.3 + q, 2.6 + q * 1.3); g.stroke();
      });
    }
  }
  // cracks, and the black tar that seals the longer ones
  if (k0 > 5) {
    g.lineCap = 'round'; g.lineJoin = 'round';
    const trace = pts => { g.beginPath(); pts.forEach((p, n) => { const q = proj(p[0], p[1]); if (n) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); }); g.stroke(); };
    g.strokeStyle = css(mul3(base, 0.52)); g.lineWidth = 1;
    for (const w of seen) for (const c of w.cracks) trace(c);
    g.strokeStyle = css(mul3(base, 0.56)); g.lineWidth = Math.max(1, 0.08 * k0);
    for (const w of seen) for (const c of w.seals) trace(c);
    g.lineCap = 'butt'; g.lineJoin = 'miter';
  }
  // the iron lids: a round one with its ribs, the telephone company's rectangles
  if (k0 > 6) for (const w of seen) for (const l of w.lids) {
    const c = proj(l.p[0], l.p[1]);
    if (!onScreen(c, 20)) continue;
    if (l.round) {
      const r = 0.42 * k0;
      g.fillStyle = css([58, 58, 62]); g.beginPath(); g.arc(c[0], c[1], r, 0, TAU); g.fill();
      g.strokeStyle = css([96, 96, 98]); g.lineWidth = 1; g.beginPath(); g.arc(c[0], c[1], Math.max(1, r - 0.5), 0, TAU); g.stroke();
      if (r > 4) { g.fillStyle = css([82, 82, 86]); g.fillRect(Math.round(c[0] - r * 0.6), Math.round(c[1]), Math.round(r * 1.2), 1); g.fillRect(Math.round(c[0]), Math.round(c[1] - r * 0.6), 1, Math.round(r * 1.2)); }
    } else {
      const hw = (l.rot ? 0.55 : 0.35) * k0, hh = (l.rot ? 0.35 : 0.55) * k0;
      g.fillStyle = css([88, 90, 94]); g.fillRect(Math.round(c[0] - hw), Math.round(c[1] - hh), Math.max(1, Math.round(2 * hw)), Math.max(1, Math.round(2 * hh)));
      g.fillStyle = css([60, 62, 66]); g.fillRect(Math.round(c[0] - hw) + 1, Math.round(c[1] - hh) + 1, Math.max(1, Math.round(2 * hw) - 2), Math.max(1, Math.round(2 * hh) - 2));
    }
  }
  // the stone in the asphalt: a sparse speckle, world-anchored, thinning out as the camera climbs
  const dens = clamp((k0 - 6) / 14) * 0.45;
  if (dens > 0.01) {
    const cell = 0.3, i0 = Math.floor(vx0 / cell), i1 = Math.ceil(vx1 / cell), j0 = Math.floor(vy0 / cell), j1 = Math.ceil(vy1 / cell);
    const lite = css(mul3(base, 1.24)), dark = css(mul3(base, 0.78));
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const h = H1(i, j, 301);
      if (h > dens) continue;
      const p = proj((i + H1(j, i, 302)) * cell, (j + H1(i + 7, j, 303)) * cell);
      g.fillStyle = h < dens * 0.5 ? lite : dark; g.fillRect(Math.round(p[0]), Math.round(p[1]), 1, 1);
    }
  }
}
// autumn: the plane trees' leaves, round each trunk and blown into the gutter
function drawLeaves(g, W, wet, k0) {
  if (k0 < 6) return;
  const cols = [[176, 120, 48], [150, 96, 40], [196, 152, 62], [120, 84, 40], [164, 74, 38]].map(c => css(mul3(c, 1 - 0.25 * wet)));
  const sz = k0 > 15 ? 2 : 1;
  for (const S of W.segs) S.items.trees.forEach((tr, n) => {
    const seed = (tr.seed * 1e4) | 0, c = S.dir === 'v' ? S.i * P : S.j * P, side = Math.sign((S.dir === 'v' ? tr.p[0] : tr.p[1]) - c);
    const m = 6 + Math.floor(H1(seed, n, 401) * 8);
    for (let q = 0; q < m; q++) {
      let p;
      if (q < m * 0.6) { const a = H1(seed, q, 402) * TAU, r = 1.4 + 2.2 * Math.sqrt(H1(seed, q, 403)); p = [tr.p[0] + Math.cos(a) * r, tr.p[1] + Math.sin(a) * r]; }
      else { const along = (H1(seed, q, 404) - 0.5) * 8, o = side * (4.65 + 0.28 * H1(seed, q, 405)); p = S.dir === 'v' ? [c + o, tr.p[1] + along] : [tr.p[0] + along, c + o]; }
      const pp = proj(p[0], p[1]);
      if (pp[0] < -2 || pp[0] > BW + 2 || pp[1] < -2 || pp[1] > BH + 2) continue;
      g.fillStyle = pick(cols, H1(seed, q, 406));
      const flip = sz > 1 && H1(seed, q, 407) < 0.5;
      g.fillRect(Math.round(pp[0]), Math.round(pp[1]), flip ? 1 : sz, flip ? sz : 1);
    }
  });
}
// a line of width w metres on the ground
function lineW(g, p0, p1, w) {
  const d = nrm(sub(p1, p0)), n = [-d[1] * w / 2, d[0] * w / 2];
  tracePoly(g, [add(p0, n), add(p1, n), sub(p1, n), sub(p0, n)]); g.fill();
}

// the trail again, on the lit ground: wet street mirrors the sky, and as the sky lightens the
// route he has walked starts to shine
function drawTrailSheen(g, t) {
  const dawn = dawnOf(Math.min(t, SONG.stop));
  if (t < SONG.fadeB || dawn < 0.05) return;
  const now = Math.min(t, SONG.stop), from = Math.max(SONG.fadeB, now - 330), k0 = kAt(0);
  const sky = mix3([150, 150, 200], [236, 196, 214], dawn);
  g.save(); g.lineCap = 'round'; g.lineJoin = 'round'; g.lineWidth = RAIN_R * 0.9 * k0;
  for (let a = now; a > from + 1e-6; a -= 15) {
    const b = Math.max(from, a - 15), age = now - (a + b) / 2, alpha = 0.32 * dawn * Math.exp(-age / 200);
    if (alpha < 0.015) break;
    g.strokeStyle = css(sky, alpha.toFixed(3));
    g.beginPath();
    for (let u = a, n = 0; u >= b - 1e-6; u -= 0.75, n++) { const p = cloudGround(u), q = proj(p[0], p[1]); if (n) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); }
    g.stroke();
  }
  g.restore();
}
// ---------------------------------------------------------------- his wet trail
// Where his rain has fallen the street stays darker, drying over a few minutes: by dawn, seen
// from high up, it is the night's route.
function drawTrail(g, t) {
  if (t < SONG.fadeB - 1) return;
  const now = Math.min(t, SONG.stop), from = Math.max(SONG.fadeB - 1, now - 330), band = 15;
  const k0 = kAt(0);
  g.save(); g.lineCap = 'round'; g.lineJoin = 'round'; g.lineWidth = RAIN_R * 1.5 * k0;
  const contrast = 1 - 0.8 * groundWet(t);            // a wet trail only shows once the rest has dried
  // bands of 15 s, each one stroke at its own age (no double-darkening inside a band)
  for (let a = now; a > from + 1e-6; a -= band) {
    const b = Math.max(from, a - band), age = now - (a + b) / 2;
    const alpha = 0.55 * contrast * Math.exp(-age / 160);
    if (alpha < 0.02) break;
    g.strokeStyle = `rgba(8,10,20,${alpha.toFixed(3)})`;
    g.beginPath();
    for (let u = a, n = 0; u >= b - 1e-6; u -= 0.75, n++) { const p = cloudGround(u), q = proj(p[0], p[1]); if (n) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); }
    g.stroke();
  }
  g.restore();
}
