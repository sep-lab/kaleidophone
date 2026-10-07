// ---------------------------------------------------------------- the storm
// Until 0:31.5 it rains on the whole city. Then the rain's edge closes in on him from every side
// and, by 0:36, falls only inside RAIN_R of the small cloud that trails him (1.1 s behind, like
// a dog on a lead). Rain is world-anchored: every drop is hashed from its cell and its cycle.
const RAIN_R = 4.6, CLOUD_Z = 11, CLOUD_LAG = 2.3;          // the cloud keeps 2.3 m behind him, on his path
function cloudGround(t) {
  const tt = Math.min(t, SONG.stop), r = routeAt(arcAt(tt) - CLOUD_LAG);
  return [r.p[0] + 0.45 * Math.sin(tt * 0.37), r.p[1] + 0.45 * Math.cos(tt * 0.29)];
}
function rainRadius(t) {                  // how far from his cloud it is raining
  const u = clamp((t - SONG.fadeA) / (36.0 - SONG.fadeA));
  return u <= 0 ? 1e6 : RAIN_R + 240 * Math.pow(1 - u, 3);
}
const cloudForm = t => step(t, SONG.beatIn - 0.6, SONG.beatIn + 2.6);

// ---------------------------------------------------------------- lightning
// The intro: the storm's own strikes, each seen GAP seconds before it is heard -- the gap is the
// distance, and it shrinks: the storm is walking toward him. [index into storm.thunder, gap s,
// bearing from him (deg, 0 = north, clockwise)].
const GAPS = [1.4, 1.2, 1.0, 0.7, 0.7, 0.7, 0.12, 0.05];
const BEARINGS = [-30, 50, -70, 20, 20, 20, -14, 38];
function cityStrikes() {
  const th = stormEvents().thunder;
  return th.map(([tt, s], i) => {
    const gap = GAPS[Math.min(i, GAPS.length - 1)], tf = tt - gap, dist = gap * 343;
    const w = walker(tf), b = rad(BEARINGS[Math.min(i, BEARINGS.length - 1)]);
    return { tf, s, dist, at: [w.p[0] + Math.sin(b) * dist, w.p[1] + Math.cos(b) * dist], seed: i * 7 + 3, city: true, sheet: i === 4 || i === 5 };
  });
}
// His: one on every change of room, from the cloud's base to the street beside him; the last
// one, on the stop, never finishes.
function myStrikes() {
  return stormEvents().rooms.map(([tf, s], i) => {
    const c = cloudGround(tf);
    if (Math.abs(tf - SONG.stop) < 0.05) {
      const w = walker(tf), rt = [w.d[1], -w.d[0]];
      return { tf, s, at: [w.p[0] + rt[0] * 1.9 + w.d[0] * 0.9, w.p[1] + rt[1] * 1.9 + w.d[1] * 0.9], from: c, seed: 977, city: false };
    }
    // the first of twelve hashed spots round the cloud that is on the street, and not on him
    const me = walker(tf).p;
    let at = null;
    for (let k = 0; k < 12 && !at; k++) {
      const a = (H1(i, 3, 61) + k / 12) * TAU, r = 1.6 + (RAIN_R - 1.9) * H1(i, 4 + k, 62);
      const p = [c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * r];
      if (!onBuilding(p) && Math.hypot(p[0] - me[0], p[1] - me[1]) > 1.6) at = p;
    }
    if (!at) at = [2 * c[0] - me[0], 2 * c[1] - me[1]];
    return { tf, s, at, from: c, seed: i * 11 + 5, city: false };
  });
}
// is this ground point under a block (its buildings or courtyard), not the street?
function onBuilding(p) {             // (with 0.8 m to spare: nothing lands at the foot of a wall)
  const B = block(Math.floor(p[0] / P), Math.floor(p[1] / P)), O = B.Oexp || (B.Oexp = inset(B.O, -0.8));
  for (let k = 0; k < O.length; k++) {
    const a = O[k], b = O[(k + 1) % O.length];
    if ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0) return false;
  }
  return true;
}
// a strike's light, frame by frame: the return stroke, a restrike, a long tail
function flashEnv(x) {
  if (x < 0) return 0;
  const f = x * FPS;
  if (f < 1) return 1;
  if (f < 2) return 0.3;
  if (f < 3) return 0.8;
  if (f < 4) return 0.22;
  return 0.25 * Math.exp(-(x - 4 / FPS) / 0.09);
}
const frozenX = (t, tf) => (t >= SONG.stop && Math.abs(tf - SONG.stop) < 0.05 ? 0 : t - tf);   // the stop's strike: held on its first frame
function stormLight(t) {                   // -> { city: global flash, me: his local flash, strikes: [...] visible bolts }
  let city = 0, me = 0;
  const bolts = [];
  if (t < SONG.beatIn + 1) for (const s of cityStrikes()) {
    const x = t - s.tf, e = flashEnv(x) * s.s * clamp(1.3 - s.dist / 520) * (s.sheet ? 0.4 : 1);
    city = Math.max(city, e);
    if (x >= 0 && x < 0.4 && s.dist < 160) bolts.push({ ...s, x, e });
  }
  if (t > SONG.beatIn - 1) for (const s of myStrikes()) {
    const held = t >= SONG.stop && Math.abs(s.tf - SONG.stop) < 0.05, x = frozenX(t, s.tf), e = held ? 0.42 : flashEnv(x) * s.s;
    me = Math.max(me, e);
    if (x >= 0 && x < 0.35) bolts.push({ ...s, x, e: held ? 1 : e, held });
  }
  return { city, me, bolts };
}
// the cloud's flicker: the snares bright, the kicks dim -- his thunder is the beat
function flicker(t) {
  if (t < SONG.beatIn - 0.05) return 0;
  const st = stormEvents(), tt = Math.min(t, SONG.stop);
  const lvl = 0.55 + 0.6 * clamp(envAt('rms', tt) * 1.2);
  return cloudForm(t) * lvl * Math.max(evPulse(st.snare, tt, 0.004, 0.1), 0.35 * evPulse(st.kick, tt, 0.004, 0.06));
}

// a jagged bolt from top to ground, its kinks hashed from the strike
function boltPath(s, ztop) {
  const n = 14, pts = [];
  const top = s.city ? [s.at[0] + (H1(s.seed, 1, 1) - 0.5) * 30, s.at[1] + (H1(s.seed, 2, 2) - 0.5) * 30] : s.from;
  for (let i = 0; i <= n; i++) {
    const u = i / n, z = lerp(ztop, 0, u);
    const j = i === 0 || i === n ? 0 : 1;
    const amp = (s.city ? 3.2 : 0.7) * j;
    pts.push([lerp(top[0], s.at[0], u) + (H1(s.seed, i, 3) - 0.5) * amp * 2, lerp(top[1], s.at[1], u) + (H1(s.seed, i, 4) - 0.5) * amp * 2, z]);
  }
  return pts;
}
function drawBolts(g, L) {
  for (const s of L.bolts) {
    const ztop = s.city ? CAM.h - 3 : CLOUD_Z - 1;
    const pts = boltPath(s, ztop), a = s.x < 2.5 / FPS ? 1 : 0.45 * Math.exp(-(s.x - 2.5 / FPS) / 0.08);
    if (a < 0.03) continue;
    const pp = pts.map(p => proj(p[0], p[1], p[2]));
    g.save(); g.lineJoin = 'round'; g.lineCap = 'round';
    const trace = () => { g.beginPath(); pp.forEach((q, i) => i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1])); g.stroke(); };
    g.strokeStyle = `rgba(140,120,255,${(0.35 * a).toFixed(3)})`; g.lineWidth = 7; trace();
    g.strokeStyle = `rgba(190,180,255,${(0.7 * a).toFixed(3)})`; g.lineWidth = 3.5; trace();
    g.strokeStyle = `rgba(255,255,255,${a.toFixed(3)})`; g.lineWidth = 1.6; trace();
    // a branch or two
    for (let b = 0; b < 2; b++) {
      const i0 = 3 + Math.floor(H1(s.seed, b, 5) * 7), q0 = pts[i0], dir = H1(s.seed, b, 6) * TAU, len = (s.city ? 9 : 1.6);
      const q1 = [q0[0] + Math.cos(dir) * len, q0[1] + Math.sin(dir) * len, Math.max(0, q0[2] - len * 0.8)];
      const p0 = proj(...q0), p1 = proj(...q1);
      g.strokeStyle = `rgba(230,230,255,${(0.7 * a).toFixed(3)})`; g.beginPath(); g.moveTo(p0[0], p0[1]); g.lineTo(p1[0], p1[1]); g.stroke();
    }
    // where it lands: a white burst
    const gp = pp[pp.length - 1];
    g.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`; g.beginPath(); g.arc(gp[0], gp[1], 2.5, 0, TAU); g.fill();
    g.restore();
  }
}

// ---------------------------------------------------------------- rain
function rainAt(p, t) {
  const R = rainRadius(t);
  if (R > 1e5) return 1;
  const c = cloudGround(t), d = Math.hypot(p[0] - c[0], p[1] - c[1]);
  return d < R - 0.8 ? 1 : d < R + 0.8 ? (R + 0.8 - d) / 1.6 : 0;
}
const WIND = [1.3, -0.7];
function drawRain(g, t, lightImg) {
  const frozen = t >= SONG.stop, tt = Math.min(t, SONG.stop);
  const R = rainRadius(tt), cg = cloudGround(tt), mine = R < 1e5;
  const cell = 2.5, Z0 = Math.min(17, CAM.h - 5), V = 8.5, T = Z0 / V;
  let [x0, y0, x1, y1] = viewRect(4);
  if (mine) { x0 = Math.max(x0, cg[0] - R - 2); x1 = Math.min(x1, cg[0] + R + 2); y0 = Math.max(y0, cg[1] - R - 2); y1 = Math.min(y1, cg[1] + R + 2); }
  if (x1 <= x0 || y1 <= y0) return;
  const dens = lerp(3.2, 0.62, smooth(8, 45, R));   // drops per m^2: his own storm is denser, and gets so smoothly
  const per = Math.max(1, Math.round(dens * cell * cell));
  const LW = BW, LH = BH, ld = lightImg ? lightImg.data : null;
  const i0 = Math.floor(x0 / cell), i1 = Math.floor(x1 / cell), j0 = Math.floor(y0 / cell), j1 = Math.floor(y1 / cell);
  for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) for (let q = 0; q < per; q++) {
    const ph = H1(i, j, q * 7 + 1), u = tt / T + ph, n = Math.floor(u), f = u - n;
    const base = [(i + H1(i, j, n * 13 + q)) * cell, (j + H1(j, i, n * 17 + q + 3)) * cell];
    const r = rainAt(base, tt);
    if (r <= 0 || H1(i + n, j, q) > r) continue;
    const z = Z0 * (1 - f), fall = Z0 - z;
    const px = base[0] + WIND[0] * (fall / V - T), py = base[1] + WIND[1] * (fall / V - T);
    const a = proj(px, py, z), dz = frozen ? 0.1 : 1.3, b = proj(px - WIND[0] * dz / V * 2.6, py - WIND[1] * dz / V * 2.6, z + dz);
    if (a[0] < -2 || a[0] > BW + 2 || a[1] < -2 || a[1] > BH + 2) continue;
    let lit = 0.35;
    if (ld) { const xi = clamp(Math.round(a[0]), 0, LW - 1), yi = clamp(Math.round(a[1]), 0, LH - 1); const o = (yi * LW + xi) * 4; lit = (ld[o] + ld[o + 1] + ld[o + 2]) / 765; }
    const v = 0.3 + 0.9 * lit;
    g.strokeStyle = `rgba(${(150 * v + 40) | 0},${(168 * v + 40) | 0},${(205 * v + 40) | 0},${(0.42 + 0.3 * lit).toFixed(3)})`;
    g.beginPath(); g.moveTo(b[0], b[1]); g.lineTo(a[0], a[1]); g.stroke();
    // the splash of this drop's previous fall, for the tenth of a second after it hit
    const age = f * T;
    if (age < 0.12 && !frozen) {
      const pb = [(i + H1(i, j, (n - 1) * 13 + q)) * cell + WIND[0] * 0, (j + H1(j, i, (n - 1) * 17 + q + 3)) * cell];
      const sp = proj(pb[0], pb[1], 0), sa = 0.7 * (1 - age / 0.12);
      g.fillStyle = `rgba(200,215,240,${(sa * (0.4 + 0.6 * lit)).toFixed(3)})`;
      g.fillRect(Math.round(sp[0]) - 1, Math.round(sp[1]), 1, 1); g.fillRect(Math.round(sp[0]) + 1, Math.round(sp[1]), 1, 1);
      g.fillRect(Math.round(sp[0]), Math.round(sp[1]) - 1, 1, 1);
    }
  }
}

// ---------------------------------------------------------------- the cloud (⛈️)
// Sixteen puffs swirling slowly round a centre 11 m over the street, drawn the way a sprite
// artist draws a cloud: a dark outline, a flat base, a flat mid-tone and the lit tops (silver at
// night, pink at dawn); lit from inside on his thunder. Close to the camera it turns
// see-through, and there is always a hole over him -- the game lets you see your man.
let CLOUD_LAYER = null;
function cloudPuffs(t) {
  const form = cloudForm(t), tt = Math.min(t, SONG.stop), c = cloudGround(tt), out = [];
  for (let q = 0; q < 16; q++) {
    const a = H1(q, 1, 71) * TAU + tt * (0.05 + 0.05 * H1(q, 2, 72)), r = 2.0 * Math.sqrt(H1(q, 3, 73));
    const z = CLOUD_Z - 1 + 2.4 * H1(q, 4, 74) * (1 - 0.45 * r / 2.0);
    const size = (0.72 + 0.8 * H1(q, 5, 75)) * (0.2 + 0.8 * form) * (1 + 0.07 * Math.sin(tt * 0.8 + q));
    const spread = 0.35 + 0.65 * form;
    out.push({ p: [c[0] + Math.cos(a) * r * spread, c[1] + Math.sin(a) * r * spread], z, size, q });
  }
  return out.sort((a, b) => a.z - b.z);
}
function drawCloud(g, t, me, L) {
  const form = cloudForm(t);
  if (form <= 0) return;
  const tt = Math.min(t, SONG.stop), c = cloudGround(tt), dawn = dawnOf(tt);
  if (!CLOUD_LAYER || CLOUD_LAYER.width !== BW || CLOUD_LAYER.height !== BH) { CLOUD_LAYER = mkCanvas(BW, BH); CLOUD_LAYER.getContext('2d', { willReadFrequently: true }); }
  const x = CLOUD_LAYER.getContext('2d');
  x.setTransform(1, 0, 0, 1, 0, 0); x.globalCompositeOperation = 'source-over'; x.globalAlpha = 1; x.clearRect(0, 0, BW, BH);
  const fl = Math.max(flicker(t), L.me * 0.9);
  const line = mix3([22, 24, 40], [92, 70, 92], dawn), base = mix3([50, 56, 86], [128, 108, 140], dawn);
  const midc = mix3([82, 90, 126], [186, 146, 166], dawn), top = mix3([140, 150, 188], [255, 202, 188], dawn), glow = [222, 210, 255];
  const puffs = cloudPuffs(t).map(pf => ({ ...pf, pp: proj(pf.p[0], pf.p[1], pf.z), R: pf.size * kAt(pf.z) }));
  const hit = Math.floor(tt / (BEAT / 2));
  const fc = [c[0] + (H1(hit, 1, 77) - 0.5) * 3.2, c[1] + (H1(hit, 2, 78) - 0.5) * 3.2];
  const lit = pf => fl * clamp(1.2 - Math.hypot(pf.p[0] - fc[0], pf.p[1] - fc[1]) / 3.8);
  x.fillStyle = css(line);
  for (const pf of puffs) { x.beginPath(); x.arc(pf.pp[0], pf.pp[1], pf.R + 1.2, 0, TAU); x.fill(); }
  for (const pf of puffs) { x.fillStyle = css(mix3(base, glow, lit(pf) * 0.6)); x.beginPath(); x.arc(pf.pp[0], pf.pp[1], pf.R, 0, TAU); x.fill(); }
  for (const pf of puffs) {
    const hi = clamp((pf.z - (CLOUD_Z - 1)) / 2.4);
    x.fillStyle = css(mix3(midc, glow, lit(pf) * 0.8)); x.beginPath(); x.arc(pf.pp[0] - pf.R * 0.14, pf.pp[1] - pf.R * 0.16, pf.R * 0.78, 0, TAU); x.fill();
    if (hi > 0.35) { x.fillStyle = css(mix3(top, glow, lit(pf))); x.beginPath(); x.arc(pf.pp[0] - pf.R * 0.32, pf.pp[1] - pf.R * 0.36, pf.R * 0.42, 0, TAU); x.fill(); }
  }
  if (fl > 0.05) {                              // the bolt inside, glowing through
    const fp = proj(fc[0], fc[1], CLOUD_Z + 0.5), R = 3.0 * kAt(CLOUD_Z);
    x.globalCompositeOperation = 'source-atop'; x.globalAlpha = Math.min(1, fl * 0.9);
    x.drawImage(poolSprite([240, 232, 255]), fp[0] - R, fp[1] - R, R * 2, R * 2);
    x.globalAlpha = 1; x.globalCompositeOperation = 'source-over';
  }
  // see-through as the old consoles did it: hard edges, and pixels left out in an ordered pattern
  // -- more of them the closer the camera, and all of them in a soft disc over him
  const see = remap(CAM.h, 50, 130, 0.66, 1);
  const im = x.getImageData(0, 0, BW, BH), d = im.data;
  const hr = me ? 1.45 * kAt(CLOUD_Z) * (1 + 0.35 * lookUp(t)) : 0;
  for (let y = 0; y < BH; y++) {
    const row = (y & 3) * 4;
    for (let xx = 0; xx < BW; xx++) {
      const o = (y * BW + xx) * 4, al = d[o + 3];
      if (!al) continue;
      let keep = see;
      if (me) { const r = Math.hypot(xx - me[0], y - me[1]) / hr; if (r < 1) keep *= clamp((r - 0.45) / 0.55); }
      d[o + 3] = al > 110 && BAYER[row + (xx & 3)] + 0.5 < keep ? 255 : 0;
    }
  }
  x.putImageData(im, 0, 0);
  g.globalAlpha = Math.min(1, form * 1.4); g.drawImage(CLOUD_LAYER, 0, 0); g.globalAlpha = 1;
}
