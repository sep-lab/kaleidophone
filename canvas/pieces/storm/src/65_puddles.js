// ---------------------------------------------------------------- puddles: the only sky there is
// Looking straight down, you see the sky only where the street is a mirror. In the storm the
// puddles are dark cloud and every flash; when it clears for everyone else they hold stars, and at
// dawn the pink; under his cloud they hold his cloud, and ring with his rain.
const PUDS = new Map();
function puddlesOf(S) {
  const key = S.dir + S.i + ',' + S.j;
  let L = PUDS.get(key);
  if (L) return L;
  L = [];
  const a = (S.dir === 'v' ? S.j : S.i) * P + 24, b = ((S.dir === 'v' ? S.j : S.i) + 1) * P - 24, c = (S.dir === 'v' ? S.i : S.j) * P;
  const seed = (S.dir === 'v' ? 3 : 4) * 1000 + S.i * 41 + S.j * 97;
  for (let s = a, n = 0; s < b; s += 4.5, n++) {
    const u = H1(seed, n, 81);
    if (u > 0.42) continue;
    // in the gutters mostly, sometimes on the pavement or out in the road
    const lane = u < 0.24 ? (H1(seed, n, 82) < 0.5 ? -4.55 : 4.55) : u < 0.33 ? (H1(seed, n, 83) < 0.5 ? -7.2 : 7.2) : (H1(seed, n, 84) - 0.5) * 6;
    const along = s + 4 * H1(seed, n, 85), len = 0.7 + 1.6 * H1(seed, n, 86), wid = 0.35 + 0.4 * H1(seed, n, 87);
    L.push({ p: S.dir === 'v' ? [c + lane, along] : [along, c + lane], rx: S.dir === 'v' ? wid : len, ry: S.dir === 'v' ? len : wid, seed: seed * 31 + n });
  }
  PUDS.set(key, L);
  return L;
}
function skyColor(t, L) {
  const tt = Math.min(t, SONG.stop), clear = step(tt, SONG.fadeA, SONG.fadeB + 2), dawn = dawnOf(tt);
  let c = mix3([38, 42, 58], [12, 16, 42], clear);
  c = mix3(c, [178, 160, 192], dawn);
  return mix3(c, [236, 236, 255], Math.min(1, L.city * 1.1));
}
// two that the film needs: the one he stops in, and one on the first zebra
const PLACE_PUDDLES = [
  { p: [133.5, 266.4], rx: 1.5, ry: 1.0, seed: 9101, sky: true },
  { p: [18.2, -1.5], rx: 1.4, ry: 0.9, seed: 9102 },
];
function drawPuddles(g, t, W, L) {
  const tt = Math.min(t, SONG.stop), sky = skyColor(t, L), clear = step(tt, SONG.fadeA, SONG.fadeB + 2) * (1 - dawnOf(tt));
  const cg = tt > SONG.beatIn - 1 ? cloudGround(tt) : null, fl = Math.max(flicker(t), L.me);
  const [x0, y0, x1, y1] = viewRect(3);
  const all = [];
  for (const S of W.segs) for (const pd of puddlesOf(S)) all.push(pd);
  for (const pd of PLACE_PUDDLES) all.push(pd);
  for (const pd of all) {
    if (pd.p[0] < x0 || pd.p[0] > x1 || pd.p[1] < y0 || pd.p[1] > y1) continue;
    const c = proj(pd.p[0], pd.p[1]), k = kAt(0), rx = Math.max(1, pd.rx * k), ry = Math.max(1, pd.ry * k);
    // under his cloud: the cloud's underside, lit by his flicker
    const under = cg && !pd.sky ? clamp(1.4 - Math.hypot(pd.p[0] - cg[0], pd.p[1] - cg[1]) / (RAIN_R * 1.1)) : 0;
    const col = mix3(sky, mix3([28, 30, 42], [210, 204, 255], fl), under);
    // an irregular puddle: three overlapping lobes, a darker wet rim, the sky brighter in the middle
    const lobes = [[0, 0, 1, 1], [(H1(pd.seed, 1, 3) - 0.5) * 0.9, (H1(pd.seed, 2, 3) - 0.5) * 0.7, 0.7, 0.75], [(H1(pd.seed, 3, 3) - 0.5) * 0.9, (H1(pd.seed, 4, 3) - 0.5) * 0.7, 0.6, 0.6]];
    const lobe = (grow, f) => { g.beginPath(); for (const [ox, oy, sx, sy] of lobes) { g.moveTo(c[0] + ox * rx + rx * sx + grow, c[1] + oy * ry); g.ellipse(c[0] + ox * rx, c[1] + oy * ry, rx * sx + grow, ry * sy + grow, 0, 0, TAU); } f(); };
    lobe(0.8, () => { g.fillStyle = css(mul3(col, 0.45)); g.fill(); });
    lobe(0, () => { g.fillStyle = css(mul3(col, 0.82)); g.fill(); });
    g.fillStyle = css(mix3(col, [255, 255, 255], 0.12)); g.beginPath(); g.ellipse(c[0] - rx * 0.15, c[1] - ry * 0.1, rx * 0.55, ry * 0.45, 0, 0, TAU); g.fill();
    // stars, where the sky is clear and dark
    if (clear * (1 - under) > 0.2 && rx > 2) {
      for (let q = 0; q < 3; q++) {
        const sx = c[0] + (H1(pd.seed, q, 1) - 0.5) * rx * 1.4, sy = c[1] + (H1(pd.seed, q, 2) - 0.5) * ry * 1.4;
        const tw = 0.5 + 0.5 * Math.sin(tt * 3 + q * 2 + pd.seed);
        g.fillStyle = `rgba(230,236,255,${(clear * tw * 0.9).toFixed(3)})`; g.fillRect(Math.round(sx), Math.round(sy), 1, 1);
      }
    }
    // the rain's rings
    const r = rainAt(pd.p, tt);
    if (r > 0.05 && t < SONG.stop + 1e9) {
      g.strokeStyle = 'rgba(210,222,245,0.5)'; g.lineWidth = 1;
      for (let q = 0; q < 2; q++) {
        const per = 0.55 + 0.3 * H1(pd.seed, q, 5), ph = fract(tt / per + H1(pd.seed, q, 6)), rr = (0.15 + 0.6 * ph) * k;
        if (H1(pd.seed, q + Math.floor(tt / per), 7) > r) continue;
        const ox = (H1(pd.seed, q, 8) - 0.5) * rx, oy = (H1(pd.seed, q, 9) - 0.5) * ry;
        g.globalAlpha = 1 - ph; g.beginPath(); g.ellipse(c[0] + ox, c[1] + oy, Math.max(0.6, rr), Math.max(0.6, rr * 0.8), 0, 0, TAU); g.stroke(); g.globalAlpha = 1;
      }
    }
  }
}
