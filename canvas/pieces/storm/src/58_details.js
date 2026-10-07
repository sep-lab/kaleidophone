// ---------------------------------------------------------------- the small things
// Steam: off the chimneys (a few at 2 am, more as the heating comes on towards dawn), out of some
// manholes on the wet street, off the café's cups -- drawn after the light, lit by what is under
// it: a lamp turns a manhole's breath gold, the city's glow tints the chimneys' at night. A green
// pharmacy cross blinking on a corner; the night café's neon cup; washing on the roofs, moving in
// the wind; seagulls over the city at first light; and at the end a sheet of newspaper that the
// wind walks across the empty crossing -- and the pause catches in the air. All pure functions of
// time, all frozen with the world at the stop.
const STEAM = [];                 // emitters collected while the roofs are drawn: { p, z, seed, big }
const PHARMACIES = [{ p: [9.55, -41], side: -1 }, { p: [123.75, 203.5], side: 1 }];

// how much of the city is steaming: some at night, most at dawn
const steamShare = T => 0.35 + 0.35 * dawnOf(T);

// a lot's chimneys: the even ones at the back of the roof, the odd ones near its street edge
function chimneyAt(lot, at, c) {
  const seed = lot.seed * 1e5 | 0;
  return at(lot.uLen * (0.15 + 0.7 * H1(seed, c, 21)), c % 2 ? 3 + 2.5 * H1(seed, c, 22) : 15 + 4 * H1(seed, c, 22));
}
// three flues that always breathe, on the roofs the camera looks along as he nears the dawn café
// (one is the café's own); drawn after the attic, on top of whatever roof is there
const FLUES = [[119.6, 204.0], [119.2, 214.5], [119.8, 227.5]];
function drawFlues(g, lot, T) {
  for (const f of FLUES) {
    if (!inQuad(lot.quad, f)) continue;
    const w = (f[0] - lot.quad[0][0]) * -lot.out[0] + (f[1] - lot.quad[0][1]) * -lot.out[1];
    const z = lot.h + (lot.attic && lot.uLen > 8 && w > 2.6 ? 3 : 0), k = kAt(z + 1.2);
    const pp = proj(f[0], f[1], z + 1.2), s = Math.max(2, 0.7 * k);
    g.fillStyle = css(mul3(lot.roof, 0.55)); g.fillRect(Math.round(pp[0] - s / 2), Math.round(pp[1] - s / 2), Math.ceil(s), Math.ceil(s));
    g.fillStyle = css([28, 26, 26]); g.fillRect(Math.round(pp[0] - s / 4), Math.round(pp[1] - s / 4), Math.max(1, Math.ceil(s / 2)), Math.max(1, Math.ceil(s / 2)));
    STEAM.push({ p: f, z: z + 1.4, seed: Math.round(f[1] * 10), big: false });
  }
}
function roofSteam(lot, at, base, T) {
  const seed = lot.seed * 1e5 | 0;
  for (let c = 0; c < Math.min(2, lot.chimneys); c++) {
    if (H1(seed, 7 + c * 5, 201) > steamShare(T)) continue;
    STEAM.push({ p: chimneyAt(lot, at, c), z: base + 1.3, seed: seed * 3 + c, big: false });
  }
}
// the manholes that breathe (the same ones drawGround draws)
function manholeSteam(S) {
  const a = (S.dir === 'v' ? S.j : S.i) * P + 30, c = (S.dir === 'v' ? S.i : S.j) * P;
  for (let q = 0; q < 4; q++) {
    if (H1(S.i * 7 + q, S.j * 3, 211) > 0.3) continue;
    const s = a + q * 19 + 7 * H1(S.i, S.j, q), off = (H1(S.j, q, S.i) - 0.5) * 6;
    STEAM.push({ p: S.dir === 'v' ? [c + off, s] : [s, c + off], z: 0.1, seed: S.i * 1000 + S.j * 10 + q, big: true });
  }
}
const STEAMSPR = {};
function steamSprite(c) {             // a soft puff in exactly this colour (its own cache: never another colour's sprite)
  const key = c.join(',');
  if (STEAMSPR[key]) return STEAMSPR[key];
  const s = 64, cv = mkCanvas(s, s), x = cv.getContext('2d'), gr = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  gr.addColorStop(0, css(c, 1)); gr.addColorStop(0.3, css(c, 0.78)); gr.addColorStop(0.65, css(c, 0.3)); gr.addColorStop(1, css(c, 0));
  x.fillStyle = gr; x.fillRect(0, 0, s, s);
  return (STEAMSPR[key] = cv);
}
function drawSteam(g, T, lim) {
  const [x0, y0, x1, y1] = viewRect(8), amb = ambient(T), night = 1 - dawnOf(T);
  // what lights a plume over the roofs: the sky, and at night the orange glow of the streets below
  const sky = [Math.min(255, amb[0] * 1.2 + 34 * night), Math.min(255, amb[1] * 1.2 + 22 * night), Math.min(255, amb[2] * 1.12 + 6 * night)];
  for (const e of STEAM) {
    if (e.p[0] < x0 || e.p[0] > x1 || e.p[1] < y0 || e.p[1] > y1) continue;
    let L = sky;
    if (e.big && lim) {                                     // a manhole: the light of the street it is in
      const c = proj(e.p[0], e.p[1]), X = clamp(Math.round(c[0]), 0, BW - 1), Y = clamp(Math.round(c[1]), 0, BH - 1), o = (Y * BW + X) * 4;
      L = [Math.max(sky[0], lim.data[o]), Math.max(sky[1], lim.data[o + 1]), Math.max(sky[2], lim.data[o + 2])];
    }
    // (quantised to the sprite cache's own step, so a frame never depends on which frame drew first)
    const col = [L[0] * 0.9 + 30, L[1] * 0.9 + 30, L[2] * 0.92 + 34].map(v => Math.min(248, Math.round(v / 8) * 8)), spr = steamSprite(col);
    // soft puffs (the light pools' own sprite), born small at the flue, growing and thinning as the wind takes them
    const life = e.big ? 3.6 : 3.2, n = e.big ? 7 : 9, rain = rainAt(e.p, T) > 0.5 ? 0.55 : 1;
    for (let q = 0; q < n; q++) {
      const age = fract(T / life + q / n + H1(e.seed, q, 203) * 0.13) * life, u = age / life;
      const drift = (e.big ? 0.35 : 0.8) * age * rain;
      const p = [e.p[0] + WIND[0] * drift + 0.2 * Math.sin(age * 2.3 + e.seed), e.p[1] + WIND[1] * drift + 0.2 * Math.cos(age * 1.9 + q)];
      const z = e.z + (e.big ? 0.9 : 1.0) * age * rain;
      const c = proj(p[0], p[1], z), r = Math.max(1.5, (e.big ? 0.55 + 0.75 * age : 0.4 + 0.6 * age) * kAt(z));
      const a = (e.big ? 0.42 : 0.55) * Math.sin(Math.PI * Math.min(1, u * 1.25)) * (1 - u * 0.6);
      if (a < 0.02) continue;
      g.globalAlpha = clamp(a); g.drawImage(spr, c[0] - r, c[1] - r, 2 * r, 2 * r);
    }
    g.globalAlpha = 1;
  }
}
// the café's cups, once the regulars are out at their table
function cupSteam(g, C, T) {
  if (T < SONG.fadeB + 4) return;
  for (const s of [-1, 1]) {
    const cp = C.at(C.L * 0.25 + s * 0.22, 3.95);
    for (let q = 0; q < 3; q++) {
      const age = fract(T / 1.6 + q / 3 + (s > 0 ? 0.5 : 0)) * 1.6;
      const pp = proj(cp[0] + 0.12 * Math.sin(age * 4 + q), cp[1] + 0.25 * age, 0.85 + 0.5 * age);
      EMIT.push(cx => { cx.fillStyle = `rgba(236,236,240,${(0.5 * (1 - age / 1.6)).toFixed(3)})`; cx.fillRect(Math.round(pp[0]), Math.round(pp[1]), 1, 1); });
    }
  }
}

// a green pharmacy cross, sticking out from the wall over the pavement, blinking
function drawPharmacies(g, T) {
  const [x0, y0, x1, y1] = viewRect(4);
  for (const ph of PHARMACIES) {
    if (ph.p[0] < x0 || ph.p[0] > x1 || ph.p[1] < y0 || ph.p[1] > y1) continue;
    const c = proj(ph.p[0], ph.p[1], 3.6), k = kAt(3.6), s = Math.max(1, Math.round(0.28 * k));
    const on = Math.floor(T * 2.5) % 5 !== 4;                 // the cross's own little animation
    LIGHTS.push({ p: [ph.p[0] - ph.side * 0.8, ph.p[1]], r: 3.4, c: [80, 255, 140], a: on ? 0.55 : 0.2 });
    EMIT.push(cx => {
      const x = Math.round(c[0]), y = Math.round(c[1]);
      cx.fillStyle = 'rgba(8,20,12,0.9)'; cx.fillRect(x - s * 1.5 - 1, y - s * 1.5 - 1, s * 3 + 2, s * 3 + 2);
      cx.fillStyle = on ? css([90, 255, 150]) : css([30, 110, 60]);
      cx.fillRect(x - s / 2, y - s * 1.5, s, s * 3); cx.fillRect(x - s * 1.5, y - s / 2, s * 3, s);
    });
  }
}
// the night café's neon cup, over its door on the chamfer
const NEON_CUP = ['.ooooo.', '.o...oo', '.o...o.o', '.o...oo', '..ooo..', 'ooooooo'];
function drawCafeNeon(g, C, T) {
  const p = C.at(C.L * 0.18, 0.5), c = proj(p[0], p[1], 3.9);
  const flick = hsh(Math.floor(T * 12), 41) < 0.04 ? 0.35 : 1;          // a tube that sometimes stutters
  LIGHTS.push({ p: C.at(C.L * 0.18, 1.4), r: 3.2, c: [255, 90, 160], a: 0.55 * flick });
  EMIT.push(cx => {
    const x = Math.round(c[0]) - 4, y = Math.round(c[1]) - 3;
    cx.fillStyle = css([255, 110, 180], flick);
    NEON_CUP.forEach((row, r) => [...row].forEach((ch, q) => { if (ch === 'o') cx.fillRect(x + q, y + r, 1, 1); }));
  });
}
// washing on a line across a roof: each piece hangs from the line and the wind lifts it, so from
// above it shows as much of itself as the gust gives it
// (and always on the two roofs the camera looks along as he nears the dawn café)
const LAUNDRY_AT = [[121, 204.5], [121.5, 233]];
function inQuad(q, p) { for (let i = 0; i < q.length; i++) { const a = q[i], b = q[(i + 1) % q.length]; if ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0) return false; } return true; }
function laundry(g, lot, at, base, T) {
  const seed = lot.seed * 1e5 | 0;
  if (lot.uLen < 8 || kAt(base) < 4) return;
  if (H1(seed, 9, 221) > 0.2 && !LAUNDRY_AT.some(p => inQuad(lot.quad, p))) return;
  // on the terrace in front of a set-back attic, or across the open roof near its street edge
  const w1 = lot.attic ? 1.2 + 0.3 * H1(seed, 1, 222) : 2.5 + 3 * H1(seed, 1, 222), w2 = lot.attic ? 1.2 + 0.3 * H1(seed, 2, 222) : 2.5 + 3 * H1(seed, 2, 222);
  const zt = base + 1.7, a = at(1.2, w1), b = at(lot.uLen - 1.2, w2);
  const pa = proj(a[0], a[1], zt), pb = proj(b[0], b[1], zt);
  g.strokeStyle = css([176, 176, 172]); g.lineWidth = 1; g.beginPath(); g.moveTo(pa[0], pa[1]); g.lineTo(pb[0], pb[1]); g.stroke();
  const dir = nrm(sub(b, a)), nw = [-dir[1], dir[0]], Ll = len(sub(b, a));
  const wside = Math.sign(WIND[0] * nw[0] + WIND[1] * nw[1]) || 1;           // the side of the line the wind blows it to
  const cols = [[234, 234, 228], [204, 64, 64], [72, 114, 188], [234, 206, 86], [122, 176, 122], [44, 44, 50], [238, 172, 192]];
  let u = 0.3;
  for (let q = 0; q < 9 && u < Ll - 0.4; q++) {
    const wq = 0.45 + 0.65 * H1(seed, q, 225), hq = 0.5 + 0.5 * H1(seed, q, 226);       // a shirt, a towel, a sheet
    const swing = 0.5 + 0.28 * Math.sin(T * 1.9 + q * 1.3 + seed) + 0.14 * Math.sin(T * 4.3 + q);
    const off = scl(nw, wside * hq * Math.sin(swing)), zb = zt - hq * Math.cos(swing);
    const p0 = add(a, scl(dir, u)), p1 = add(a, scl(dir, Math.min(Ll - 0.2, u + wq)));
    quadPath(g, proj(p0[0], p0[1], zt), proj(p1[0], p1[1], zt), proj(p1[0] + off[0], p1[1] + off[1], zb), proj(p0[0] + off[0], p0[1] + off[1], zb));
    g.fillStyle = css(pick(cols, H1(seed, q, 224))); g.fill();
    u += wq + 0.15 + 0.3 * H1(seed, q, 227);
  }
}
// a sheet of newspaper: lying by the north-west corner of the last crossing until a gust takes it
// at 5:14; it skates and hops across the crossing on the wind, and the pause catches it mid-hop
const PAPER = { from: [122.5, 278.3], to: [136.6, 272.1], t0: 314, size: [0.62, 0.44] };
function paperAt(T) {
  const t1 = SONG.stop, u = clamp((T - PAPER.t0) / (t1 - PAPER.t0)), v = u + 0.035 * Math.sin(u * TAU * 3);
  const p = lerp2(PAPER.from, PAPER.to, clamp(v));
  if (T <= PAPER.t0) return { p, z: 0.01, rot: 0.6, tilt: 0 };
  const hop = Math.max(0, Math.sin(Math.PI * (T - t1) / 1.1 + Math.PI / 2));             // its last hop peaks on the stop
  const z = 0.01 + 0.42 * Math.pow(hop, 1.5) * step(T, PAPER.t0, PAPER.t0 + 1.5);
  return { p, z, rot: 0.6 + 2.2 * (T - PAPER.t0) * 0.35 + 0.5 * Math.sin(T * 1.7), tilt: 0.9 * Math.sin(T * 3.1) * hop };
}
function drawPaper(g, T) {
  const [x0, y0, x1, y1] = viewRect(2), s = paperAt(T);
  if (s.p[0] < x0 || s.p[0] > x1 || s.p[1] < y0 || s.p[1] > y1 || kAt(0) < 6) return;
  const k = kAt(s.z), c = proj(s.p[0], s.p[1], s.z), sh = proj(s.p[0] + 0.12 * s.z * 4, s.p[1] - 0.06 * s.z * 4, 0);
  const sx = PAPER.size[0] * k / 2, sy = PAPER.size[1] * k / 2 * Math.max(0.25, Math.abs(Math.cos(s.tilt)));
  if (s.z > 0.05) { g.save(); g.translate(sh[0], sh[1]); g.rotate(-s.rot); g.fillStyle = 'rgba(8,8,14,0.28)'; g.fillRect(-sx, -sy, 2 * sx, 2 * sy); g.restore(); }
  g.save(); g.translate(c[0], c[1]); g.rotate(-s.rot);
  g.fillStyle = css([212, 208, 194]); g.fillRect(-sx, -sy, 2 * sx, 2 * sy);
  g.fillStyle = css([148, 146, 140]);                                                   // the columns of print
  if (sx > 2.5) for (let r = -sy + 1.2; r < sy - 0.8; r += Math.max(1.4, sy * 0.45)) { g.fillRect(-sx + 1, r, sx - 1.5, 0.8); g.fillRect(0.5, r, sx - 1.5, 0.8); }
  g.restore();
}
// two seagulls over the city at first light: gliding, now and then a beat of the wings
const GULLS = [{ from: [96, 196], dir: [0.82, 0.57], v: 7.5, t0: 281, z: 28 }, { from: [92, 190], dir: [0.86, 0.5], v: 7.2, t0: 281.6, z: 31 }];
function drawGulls(g, T) {
  const sky = mix3([120, 126, 150], [255, 250, 246], dawnOf(T));         // lit by the sky, not the lamps
  for (const b of GULLS) {
    const d = b.v * (T - b.t0);
    if (d < -5 || d > 140) continue;
    const p = [b.from[0] + b.dir[0] * d, b.from[1] + b.dir[1] * d];
    if (b.z > CAM.h - 8) continue;
    const c = proj(p[0], p[1], b.z), k = kAt(b.z) * 1.4, ang = Math.atan2(b.dir[1], b.dir[0]);
    if (c[0] < -10 || c[0] > BW + 10 || c[1] < -10 || c[1] > BH + 10) continue;
    const beat = Math.max(0, Math.sin((T - b.t0) * 9)) * (fract((T - b.t0) / 4) < 0.35 ? 1 : 0);
    g.save(); g.translate(c[0], c[1]); g.rotate(-ang); g.scale(k, k);
    g.fillStyle = 'rgba(10,10,20,0.18)'; g.beginPath(); g.ellipse(-0.3, 0.4, 0.3, 0.6, 0, 0, TAU); g.fill();
    g.fillStyle = css(mul3(sky, 0.94));
    g.beginPath(); g.ellipse(0, 0, 0.3, 0.09, 0, 0, TAU); g.fill();                     // body
    for (const s of [-1, 1]) {                                                             // wings
      g.beginPath(); g.moveTo(0.05, 0); g.lineTo(-0.1, s * (0.75 - 0.35 * beat)); g.lineTo(-0.22, s * (0.7 - 0.35 * beat)); g.lineTo(-0.12, 0); g.closePath(); g.fill();
    }
    g.fillStyle = css([40, 40, 46]); for (const s of [-1, 1]) g.fillRect(-0.24, s * (0.66 - 0.35 * beat) - 0.04, 0.1, 0.08);   // the dark tips
    g.fillStyle = css([240, 190, 60]); g.fillRect(0.28, -0.02, 0.06, 0.04);                // beak
    g.restore();
  }
}
