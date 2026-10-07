// ---------------------------------------------------------------- the walk
// One step on every beat, never a stop until the music stops. The route is fixed by two
// landmarks: at 0:34 he steps off the kerb onto the zebra at the first crossing (the storm has
// just become his), and at the stop (5:36.02) he is standing at the exact centre of an empty
// crossing. Between the two windows the stride is stretched a little to make the distance.
const ROUTE = [
  [7.5, -47],                     // 0:00, the east pavement of a N-S street, walking north into the storm
  [7.5, -23.1],                   // the chamfer of the block on his right
  [17, -13.6],
  [17, 13.6],                     // across the zebra (kerb to kerb, 0:34 -> 0:51)
  [23.1, 7.5],                    // the café on the chamfer, then east along the block
  [110.2, 7.5],
  [125.8, 23.1],                  // round the far chamfer, north
  [125.8, 156.4],                 // straight over the next crossing
  [125.8, 243.5],                 // past the café that opens at dawn, to the chamfer of the last block
  [133.3, 266.6],                 // into the middle of the crossing: the stop
];
// the places the city builds for him (10_city.js reads PLACES)
PLACES.push({ at: [17.07, 17.07], kind: 'cafe', name: 'night', open: [0, 24 * 60], terrace: true });
PLACES.push({ at: [123.3, 216.8], kind: 'cafe', name: 'dawn', open: [6 * 60 + 47, 24 * 60], awning: true, terrace: false });

// every interior corner replaced by a circular arc (radius up to 1.5 m, less where the legs are short)
function roundCorners(pts, R = 1.5, n = 8) {
  const out = [pts[0]];
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i], a = pts[i - 1], b = pts[i + 1];
    const da = nrm(sub(a, p)), db = nrm(sub(b, p)), cosT = clamp(da[0] * db[0] + da[1] * db[1], -1, 1), theta = Math.acos(cosT);
    if (theta > Math.PI - 0.01) { out.push(p); continue; }
    const tanLen = Math.min(R / Math.tan(theta / 2), 0.45 * len(sub(a, p)), 0.45 * len(sub(b, p)));
    const r = tanLen * Math.tan(theta / 2), p0 = add(p, scl(da, tanLen)), p1 = add(p, scl(db, tanLen));
    const bis = nrm(add(da, db)), c = add(p, scl(bis, r / Math.sin(theta / 2)));
    let a0 = Math.atan2(p0[1] - c[1], p0[0] - c[0]), a1 = Math.atan2(p1[1] - c[1], p1[0] - c[0]), da1 = a1 - a0;
    while (da1 > Math.PI) da1 -= TAU; while (da1 < -Math.PI) da1 += TAU;
    for (let k = 0; k <= n; k++) { const u = a0 + da1 * k / n; out.push([c[0] + Math.cos(u) * r, c[1] + Math.sin(u) * r]); }
  }
  out.push(pts[pts.length - 1]);
  return out;
}
const RT = (() => {
  const seg = [], R2 = roundCorners(ROUTE);
  let s = 0;
  for (let i = 0; i < R2.length - 1; i++) {
    const a = R2[i], b = R2[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 1e-6) continue;
    seg.push({ a, b, s0: s, L, d: [(b[0] - a[0]) / L, (b[1] - a[1]) / L] });
    s += L;
  }
  return { seg, total: s };
})();
function routeAt(s) {                // position and direction at arc length s
  const S = RT.seg;
  if (s <= 0) { const g = S[0]; return { p: [g.a[0] + g.d[0] * s, g.a[1] + g.d[1] * s], d: g.d }; }
  for (const g of S) if (s <= g.s0 + g.L) { const u = s - g.s0; return { p: [g.a[0] + g.d[0] * u, g.a[1] + g.d[1] * u], d: g.d }; }
  const g = S[S.length - 1]; return { p: g.b.slice(), d: g.d };
}
// Arc length at time t: 1.2 m/s in both windows (0-63 s and 279.02 s to the stop); in between the
// speed eases (over RAMP s) to whatever lands him on the centre of the last crossing at the stop.
// s(34) = 40.9 m: the kerb of the first zebra.
const W1 = 63.0, W2 = 279.02, RAMP = 6;
const rampF = x => { if (x <= 0) return 0; if (x >= RAMP) return RAMP / 2; const u = x / RAMP; return x - RAMP * (u * u * u - u * u * u * u / 2); };
function vMid() { return (RT.total - SPEED * (W1 + RAMP + SONG.stop - W2)) / (W2 - W1 - RAMP); }
function arcAt(t) {
  t = Math.min(t, SONG.stop);
  if (t <= W1) return SPEED * t;
  const v = vMid();
  if (t >= W2) return RT.total - SPEED * (SONG.stop - t);
  return SPEED * W1 + v * (t - W1) + (SPEED - v) * (rampF(t - W1) + RAMP / 2 - rampF(W2 - t));
}
function walker(t) {
  const s = arcAt(t), r = routeAt(s);
  // his heading: the chord over 1.8 m of the path, so a corner is a turn, not a snap
  const a = routeAt(s - 0.9).p, b = routeAt(s + 0.9).p;
  const d = nrm([b[0] - a[0], b[1] - a[1]]);
  return { p: r.p, d, s };
}
// steps: beat number (fractional) from the first downbeat; foot down on every beat
const stepOf = t => (Math.min(t, SONG.stop) - DOWNBEAT) / BEAT;
