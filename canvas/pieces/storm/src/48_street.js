// ---------------------------------------------------------------- street furniture
// Low things (containers, parked scooters and cars, café tables) go down before the buildings,
// high things (awnings, lamps, traffic lights, plane trees) after them. Lights are collected
// for the light pass: LIGHTS = [{ p:[x,y], r: metres, c:[r,g,b], a: 0..1 }].
const LIGHTS = [];
const lampsOn = t => t < SONG.stop;                      // the city switches its lamps off at 07:36, on the stop

function rect3(g, c, ang, l, w, z, col) {                 // a rectangle l x w (metres) at height z, rotated ang (rad)
  const ca = Math.cos(ang), sa = Math.sin(ang), hl = l / 2, hw = w / 2;
  const pts = [[-hl, -hw], [hl, -hw], [hl, hw], [-hl, hw]].map(([u, v]) => [c[0] + u * ca - v * sa, c[1] + u * sa + v * ca]);
  tracePoly(g, pts, z); g.fillStyle = css(col); g.fill();
  return pts;
}
// a car from above: body, glass, roof; lights go to EMIT / LIGHTS
function drawCar(g, c, angDeg, col, opts = {}) {
  const a = rad(angDeg), ca = Math.cos(a), sa = Math.sin(a), L = opts.len || 4.3, Wd = 1.85;
  const at = (u, v) => [c[0] + u * ca - v * sa, c[1] + u * sa + v * ca];
  rect3(g, at(-0.2, 0), a, L + 0.3, Wd + 0.3, 0, [20, 20, 24]);                 // the shadow under it
  rect3(g, c, a, L, Wd, 0.9, opts.taxi ? [236, 196, 40] : col);
  rect3(g, at(0.1, 0), a, L * 0.86, Wd * 0.8, 1.1, opts.taxi ? [26, 26, 28] : mul3(col, 0.86));   // the body's top (a taxi: black over yellow)
  rect3(g, at(L * 0.18, 0), a, L * 0.16, Wd * 0.74, 1.35, [34, 40, 54]);       // windscreen
  rect3(g, at(-L * 0.24, 0), a, L * 0.1, Wd * 0.72, 1.35, [34, 40, 54]);       // rear window
  rect3(g, at(-0.03, 0), a, L * 0.3, Wd * 0.72, 1.45, opts.taxi ? [26, 26, 28] : mul3(col, 1.08));
  if (opts.taxi) { const p = proj(...at(-0.05, 0), 1.6); EMIT.push(cx => { cx.fillStyle = css(opts.free ? [80, 255, 120] : [255, 80, 60]); cx.fillRect(Math.round(p[0]) - 1, Math.round(p[1]) - 1, 2, 2); }); }
  if (opts.moving) {
    for (const s of [-1, 1]) {
      const hp = proj(...at(L / 2, s * 0.65), 0.7), tp = proj(...at(-L / 2, s * 0.65), 0.8);
      EMIT.push(cx => { cx.fillStyle = css([255, 250, 228]); cx.fillRect(Math.round(hp[0]) - 1, Math.round(hp[1]) - 1, 2, 2); cx.fillStyle = css([255, 40, 30]); cx.fillRect(Math.round(tp[0]) - 1, Math.round(tp[1]) - 1, 2, 2); });
      LIGHTS.push({ p: at(-L / 2 - 1.2, s * 0.6), r: 2.2, c: [255, 40, 30], a: 0.55 });
    }
    LIGHTS.push({ p: at(L / 2 + 6, 0), r: 7, c: [255, 246, 220], a: 0.55, cone: { from: at(L / 2, 0), dir: [ca, sa], spread: 0.4, len: 15 } });
  }
}
function drawMoto(g, m) {
  const a = m.dir === 'v' ? 0 : Math.PI / 2;
  rect3(g, m.p, a, 1.8, 0.55, 0.7, [36, 38, 42]);
  rect3(g, m.p, a, 0.8, 0.4, 0.9, m.c);
}
function drawBin(g, b) {
  const a = b.dir === 'v' ? Math.PI / 2 : 0;
  rect3(g, b.p, a, 1.15, 1.55, 0, [24, 24, 26]);
  rect3(g, b.p, a, 1.1, 1.5, 1.45, b.c);
  rect3(g, [b.p[0], b.p[1]], a, 0.12, 1.5, 1.5, mul3(b.c, 0.7));
}

function drawStreetLow(g, t, W, me) {
  for (const S of W.segs) {
    for (const m of S.items.motos) drawMoto(g, m);
    for (const b of S.items.bins) drawBin(g, b);
    for (const c of S.items.parked) drawCar(g, c.p, c.ang, c.c, { taxi: c.taxi, free: c.seed < 0.035 });
  }
  for (const B of W.blocks) for (const lot of B.lots) if (lot.place && lot.place.terrace) drawTerrace(g, lot, t, 'low', me);
}
function drawStreetHigh(g, t, W, me) {
  for (const B of W.blocks) for (const lot of B.lots) if (lot.place && (lot.place.terrace || lot.place.awning)) drawTerrace(g, lot, t, 'high', me);
  const on = lampsOn(t);
  for (const S of W.segs) {
    for (const L of S.items.lamps) {
      const b = proj(L.p[0], L.p[1], 0), h = proj(L.head[0], L.head[1], L.h), reach = 12.5 * kAt(0) + 4;
      if (h[0] < -reach || h[0] > BW + reach || h[1] < -reach || h[1] > BH + reach) continue;
      if (h[0] < -20 || h[0] > BW + 20 || h[1] < -20 || h[1] > BH + 20) { if (on) { LIGHTS.push({ p: L.head, r: 12, c: [255, 160, 80], a: 1 }); LIGHTS.push({ p: L.head, r: 5, c: [255, 196, 130], a: 0.6 }); } continue; }
      // the pole, its arm out over the road, the lamp at the end of it
      const top = proj(L.p[0], L.p[1], L.h);
      g.strokeStyle = css([66, 68, 76]); g.lineWidth = 1; g.beginPath(); g.moveTo(b[0], b[1]); g.lineTo(top[0], top[1]); g.lineTo(h[0], h[1]); g.stroke();
      const k = kAt(L.h), s = Math.max(1, 0.32 * k), s2 = Math.max(1, 0.55 * k);
      const horiz = Math.abs(L.head[0] - L.p[0]) > 0.1;
      const lw = horiz ? s2 : s, lh = horiz ? s : s2;
      if (on) {
        EMIT.push(c => { c.fillStyle = css([255, 214, 150]); c.fillRect(Math.round(h[0] - lw / 2), Math.round(h[1] - lh / 2), Math.ceil(lw), Math.ceil(lh)); });
        LIGHTS.push({ p: L.head, r: 12, c: [255, 160, 80], a: 1 });
        LIGHTS.push({ p: L.head, r: 5, c: [255, 196, 130], a: 0.6 });
      } else { g.fillStyle = css([110, 112, 118]); g.fillRect(Math.round(h[0] - lw / 2), Math.round(h[1] - lh / 2), Math.ceil(lw), Math.ceil(lh)); }
    }
  }
  for (const X of W.crossings) for (const p of X.poles) {
    const b = proj(p[0], p[1], 0), h = proj(p[0], p[1], 3.4);
    g.strokeStyle = css([40, 42, 46]); g.lineWidth = 1; g.beginPath(); g.moveTo(b[0], b[1]); g.lineTo(h[0], h[1]); g.stroke();
    // at night the lights blink amber; from 07:00 they run their cycle
    const m = gameMin(t), blink = Math.floor(t * 1.6) % 2 === 0;
    const col = m < 420 ? (blink ? [255, 170, 30] : null) : (Math.floor((t + p[0] * 0.1) / 9) % 2 ? [60, 255, 120] : [255, 50, 40]);
    if (col && t <= SONG.stop + 1e9) EMIT.push(c => { c.fillStyle = css(col); c.fillRect(Math.round(h[0]) - 1, Math.round(h[1]) - 1, 2, 2); });
  }
  for (const S of W.segs) for (const tr of S.items.trees) {
    if (Math.hypot(tr.p[0] - SAX.p[0], tr.p[1] - SAX.p[1]) < 7 || Math.hypot(tr.p[0] - PIGS.p[0], tr.p[1] - PIGS.p[1]) < 4.5) continue;   // keep these clear
    const c = proj(tr.p[0], tr.p[1], tr.h), dx = c[0] - me.p[0], dy = c[1] - me.p[1], R = tr.r * kAt(tr.h);
    const a = clamp((Math.hypot(dx, dy) - R * 0.3) / (R * 0.9), 0.28, 1);     // see-through over him
    canopy(g, tr.p, tr.h, tr.r, tr.c, (tr.seed * 1e4) | 0, t, a);
  }
}

// ---------------------------------------------------------------- the cafés
// The night café: a chamfer bar open all night; under its awning in the storm, out at the
// tables when the rain stops for everyone else. The dawn café: its shutter rolls up as he
// reaches it, and he lights a cigarette under its awning -- the only dry metres he gets.
function cafeFrame(lot) {
  const q0 = lot.quad[0], q1 = lot.quad[1], e = nrm(sub(q1, q0)), o = lot.out, L = lot.uLen;
  return { at: (u, w) => [q0[0] + e[0] * u + o[0] * w, q0[1] + e[1] * u + o[1] * w], L, ang: Math.atan2(e[1], e[0]) };
}
function drawTerrace(g, lot, t, layer, me) {
  const C = cafeFrame(lot), night = lot.place.name === 'night';
  const awnD = night ? 2.0 : 2.7, awnZ = 3.1;
  if (layer === 'low') {
    if (!night) return;
    // tables on the kerb side, two people at one of them once the rain has stopped for them
    const tables = [[0.25, 3.9], [0.55, 4.0], [0.82, 3.8]];
    tables.forEach(([u, w], n) => {
      const p = C.at(C.L * u, w), pp = proj(p[0], p[1], 0.75), r = Math.max(1.2, 0.4 * kAt(0.75));
      for (const s of [-1, 1]) rect3(g, C.at(C.L * u + s * 0.75, w), C.ang, 0.45, 0.45, 0.45, [70, 72, 78]);
      g.beginPath(); g.arc(pp[0], pp[1], r, 0, TAU); g.fillStyle = css([150, 152, 158]); g.fill();
    });
    drawCat(g, t, C);
    cupSteam(g, C, t);
    const out = step(t, SONG.fadeB - 0.5, SONG.fadeB + 4);
    // two regulars: under the awning in the storm, at the middle table after it
    const seats = [[0.14, 0.55], [0.36, 0.55]], dest = [[0.12, 3.9], [0.38, 3.9]];
    seats.forEach((s0, n) => {
      const u = lerp(s0[0], dest[n][0], out), w = lerp(s0[1] + 0.4, dest[n][1], out);
      const p = C.at(C.L * u, w);
      // the one facing the street turns to watch his cloud go by
      const look = me && me.cloud ? Math.atan2(me.cloud[1] - p[1], me.cloud[0] - p[0]) : C.ang;
      const face = n === 0 ? lerp(C.ang, look, step(t, 52, 54) * (1 - step(t, 61, 63))) : C.ang + Math.PI;
      person(g, p, face, { coat: n ? [120, 60, 58] : [60, 72, 96], hair: n ? PAL.hair[2] : PAL.hair[0], seated: true });
      if (out > 0.9) { const cp = proj(...C.at(C.L * 0.25 + (n ? 0.22 : -0.22), 3.95), 0.8); g.fillStyle = css([236, 232, 222]); g.fillRect(Math.round(cp[0]), Math.round(cp[1]), 1, 1); }
    });
    return;
  }
  // high: the awning, striped, and the light the open door throws on the pavement
  const up = shopState(lot, t);
  if (night) drawCafeNeon(g, C, t);
  const a0 = C.at(C.L * 0.06, 0), a1 = C.at(C.L * 0.94, 0), b1 = C.at(C.L * 0.94, awnD), b0 = C.at(C.L * 0.06, awnD);
  if (!night && up <= 0 && gameMin(t) < lot.place.open[0] - 1) {
    // rolled-up awning: a thin bar on the wall
    const s = C.at(C.L * 0.06, 0.25), e2 = C.at(C.L * 0.94, 0.25);
    g.strokeStyle = css([150, 40, 40]); g.lineWidth = Math.max(1, 0.25 * kAt(awnZ)); const p0 = proj(s[0], s[1], awnZ), p1 = proj(e2[0], e2[1], awnZ);
    g.beginPath(); g.moveTo(p0[0], p0[1]); g.lineTo(p1[0], p1[1]); g.stroke();
  } else {
    const ext = night ? 1 : clamp((gameMin(t) - lot.place.open[0] - 0.5) / 3);
    const n = 10, see = me ? me.p : [-1e9, -1e9];
    // how far he is from the awning's middle, in its own frame: under it, it all goes see-through at once
    const mid = proj(...C.at(C.L * 0.5, awnD * 0.5), awnZ), R = (C.L * 0.5 + 1.6) * kAt(awnZ), Rd = (awnD * 0.5 + 1.6) * kAt(awnZ);
    const ux = [Math.cos(-C.ang), Math.sin(-C.ang)], dx = see[0] - mid[0], dy = see[1] - mid[1];
    const along = Math.abs(dx * ux[0] + dy * ux[1]) / R, across = Math.abs(-dx * ux[1] + dy * ux[0]) / Rd;
    const under = clamp(1.6 - Math.max(along, across) * 1.6);
    g.save();
    if (under > 0.05) {          // a hole round him, so he is never seen through red and white stripes
      const R = 1.05 * kAt(awnZ);
      g.beginPath(); g.rect(-10, -10, BW + 20, BH + 20); g.moveTo(see[0] + R, see[1]); g.arc(see[0], see[1], R, 0, TAU); g.clip('evenodd');
    }
    for (let q = 0; q < n; q++) {
      const u0 = lerp(0.06, 0.94, q / n), u1 = lerp(0.06, 0.94, (q + 1) / n);
      const pts = [C.at(C.L * u0, 0), C.at(C.L * u1, 0), C.at(C.L * u1, awnD * ext), C.at(C.L * u0, awnD * ext)];
      const col = q % 2 ? [236, 228, 210] : (night ? [40, 98, 74] : [176, 44, 44]);
      tracePoly(g, pts, awnZ);
      g.globalAlpha = lerp(1, 0.8, under); g.fillStyle = css(col); g.fill(); g.globalAlpha = 1;
    }
    g.restore();
    tracePoly(g, [a0, a1, b1, b0].map((p, i) => i < 2 ? p : C.at(C.L * (i === 2 ? 0.94 : 0.06), awnD * ext)), awnZ);
    g.strokeStyle = css([60, 30, 30]); g.lineWidth = 1; g.stroke();
  }
  if (night || up > 0) {
    const spill = night ? 1 : up;
    LIGHTS.push({ p: C.at(C.L * 0.5, 2.6), r: 7.5, c: [255, 178, 104], a: 0.95 * spill });
    LIGHTS.push({ p: C.at(C.L * 0.2, 1.5), r: 4.5, c: [255, 190, 120], a: 0.6 * spill });
    LIGHTS.push({ p: C.at(C.L * 0.8, 1.5), r: 4.5, c: [255, 190, 120], a: 0.6 * spill });
  }
}
