// ---------------------------------------------------------------- people, from above
// Seen from straight up a person is a head, a pair of shoulders and the feet that stick out in
// front and behind as they walk. Everyone is drawn half as big again as life, as the old games
// did, so the figure reads at a third of the resolution.
const EX = 1.75;
function person(g, p, ang, o = {}) {
  const c = proj(p[0], p[1], 1.3), k = kAt(1.3) * EX;
  g.save(); g.translate(c[0], c[1]); g.rotate(-ang); g.scale(k, k);
  // shadow
  g.fillStyle = 'rgba(8,8,14,0.35)'; g.beginPath(); g.ellipse(-0.04, 0.03, 0.34, 0.4, 0, 0, TAU); g.fill();
  const u = o.walk == null ? null : fract(o.walk / 2), sw = u == null ? 0 : Math.cos(u * TAU);
  // feet
  if (!o.seated) {
    g.fillStyle = css(o.shoe || [26, 24, 26]);
    for (const s of [-1, 1]) { const fx = u == null ? 0.05 : 0.3 * sw * s; g.beginPath(); g.ellipse(fx, s * 0.12, 0.14, 0.065, 0, 0, TAU); g.fill(); }
  } else {
    g.fillStyle = css(mul3(o.coat, 0.7)); g.fillRect(0.05, -0.2, 0.32, 0.4);      // knees under the table
  }
  // arms (swing against the feet)
  g.fillStyle = css(mul3(o.coat, 0.82));
  for (const s of [-1, 1]) { const ax = o.seated ? 0.16 : -0.2 * sw * s; g.beginPath(); g.ellipse(ax, s * 0.29, 0.14, 0.07, 0, 0, TAU); g.fill(); }
  // body
  g.fillStyle = css(o.coat); g.beginPath(); g.ellipse(0, 0, 0.19, 0.3, 0, 0, TAU); g.fill();
  g.fillStyle = css(mul3(o.coat, 1.25)); g.beginPath(); g.ellipse(-0.03, -0.05, 0.1, 0.2, 0, 0, TAU); g.fill();
  // head
  g.fillStyle = css(o.hair || PAL.hair[0]); g.beginPath(); g.arc(0.03, 0, 0.12, 0, TAU); g.fill();
  g.restore();
}
function umbrella(g, p, ang, col, close, walk) {
  const c = proj(p[0], p[1], 2.0), k = kAt(2.0) * EX;
  if (close >= 1) return false;
  g.save(); g.translate(c[0], c[1]); g.rotate(-ang); g.scale(k, k);
  const ry = 0.62 * (1 - close * 0.85), rx = 0.62 * (1 - close * 0.35);
  g.fillStyle = 'rgba(6,6,12,0.3)'; g.beginPath(); g.ellipse(-0.05, 0.05, rx, ry, 0, 0, TAU); g.fill();
  g.fillStyle = css(col); g.beginPath(); g.ellipse(0, 0, rx, ry, 0, 0, TAU); g.fill();
  g.strokeStyle = css(mul3(col, 0.6)); g.lineWidth = 0.05;
  for (let q = 0; q < 8; q++) { const a = q / 8 * TAU; g.beginPath(); g.moveTo(0, 0); g.lineTo(Math.cos(a) * rx, Math.sin(a) * ry); g.stroke(); }
  g.fillStyle = css(mul3(col, 1.4)); g.beginPath(); g.arc(-0.12, -0.12, 0.12 * (1 - close), 0, TAU); g.fill();
  g.restore();
  return close < 0.5;
}

// ---------------------------------------------------------------- the others (pure functions of t)
const OTHERS = [
  // the intro: umbrellas hurrying the other way; they close when the rain stops for them
  { from: [-7.4, -16], dir: [0, -1], v: 1.35, t0: 0, coat: PAL.coats[2], hair: PAL.hair[1], umb: [176, 40, 52] },
  { from: [30, 7.2], dir: [1, 0], v: 1.25, t0: 24, coat: PAL.coats[3], hair: PAL.hair[4], umb: [30, 32, 40] },
  { from: [-30, -7.6], dir: [1, 0], v: 1.2, t0: 30, coat: PAL.coats[5], hair: PAL.hair[2], umb: [40, 70, 140] },
  // dawn: a woman on the kerb side of his pavement, coming the other way; a dog walker across the street
  { from: [127.7, 262], dir: [0, -1], v: 1.3, t0: 284, coat: PAL.coats[6], hair: PAL.hair[2] },
  { from: [140.9, 226], dir: [0, -1], v: 1.0, t0: 296, coat: PAL.coats[1], hair: PAL.hair[4], dog: true },
  { from: [118, 274.0], dir: [-1, 0], v: 1.4, t0: 300, coat: PAL.coats[0], hair: PAL.hair[3] },
];
function drawOthers(g, t) {
  const [x0, y0, x1, y1] = viewRect(6);
  for (const o of OTHERS) {
    const tt = Math.min(t, SONG.stop), d = o.v * (tt - o.t0), p = [o.from[0] + o.dir[0] * d, o.from[1] + o.dir[1] * d];
    if (p[0] < x0 || p[0] > x1 || p[1] < y0 || p[1] > y1) continue;
    const ang = Math.atan2(o.dir[1], o.dir[0]), walk = (tt - o.t0) * o.v / 0.75;
    person(g, p, ang, { coat: o.coat, hair: o.hair, walk });
    if (o.dog) {
      const dp = [p[0] + o.dir[0] * 1.6 + 0.4, p[1] + o.dir[1] * 1.6], dc = proj(dp[0], dp[1], 0.4), k = kAt(0.4) * EX;
      g.fillStyle = css([150, 110, 70]); g.beginPath(); g.ellipse(dc[0], dc[1], 0.16 * k, 0.32 * k, -ang + Math.PI / 2, 0, TAU); g.fill();
      const pc = proj(p[0] + 0.25, p[1], 0.9); g.strokeStyle = 'rgba(30,30,30,0.6)'; g.lineWidth = 1; g.beginPath(); g.moveTo(pc[0], pc[1]); g.lineTo(dc[0], dc[1]); g.stroke();
    }
    if (o.umb) {
      const close = step(t, SONG.fadeA + 1.5 + 0.7 * hsh(o.t0 | 0, 3), SONG.fadeB + 0.6 + 0.8 * hsh(o.t0 | 0, 4));
      umbrella(g, p, ang, o.umb, close, walk);
    }
  }
}

// ---------------------------------------------------------------- traffic (few cars, as asked)
// Everyone keeps to the right. On a wet street the rear wheels throw a little spray, lit by
// whatever is behind them -- their own tail lights, mostly.
const CARS = [
  { from: [1.6, -38.6], dir: [0, 1], v: 8, t0: 7.0, c: [26, 26, 28], taxi: true, free: true },      // passes him in the storm, on his side
  { from: [0, 1.6], dir: [-1, 0], v: 9.5, t0: 26.0, c: PAL.cars[1] },                              // across the crossing
  { from: [17, -1.6], dir: [1, 0], v: 8.5, t0: 57, c: PAL.cars[0] },                               // after he is over
  { from: [134.9, 196], dir: [0, 1], v: 7.5, t0: 283.5, c: [232, 232, 226], len: 5.4 },           // the bakery van
  { from: [131.7, 236], dir: [0, -1], v: 4.2, t0: 302, c: [226, 230, 222], len: 6.2, washer: true }, // the street washer
  { from: [96, 265.0], dir: [1, 0], v: 10, t0: 311, c: [26, 26, 28], taxi: true, free: false },     // the last car before he walks into the crossing
];
function drawCars(g, t) {
  const [x0, y0, x1, y1] = viewRect(25);
  for (const c of CARS) {
    const tt = Math.min(t, SONG.stop), d = c.v * (tt - c.t0), p = [c.from[0] + c.dir[0] * d, c.from[1] + c.dir[1] * d];
    if (p[0] < x0 || p[0] > x1 || p[1] < y0 || p[1] > y1) continue;
    const ang = Math.atan2(c.dir[1], c.dir[0]) * 180 / Math.PI;
    drawCar(g, p, ang, c.c, { taxi: c.taxi, free: c.free, moving: true, len: c.len });
    const spray = clamp((groundWet(tt) - 0.3) / 0.5);
    if (spray > 0.02) {
      const L = c.len || 4.3, d = c.dir, rt = [d[1], -d[0]];
      for (let q = 0; q < 16; q++) {
        const u = fract(hsh(q, 11) + tt * 3.1), s = q % 2 ? 1 : -1, back = L / 2 - 0.75 + 2.6 * u, side = s * (0.8 + 0.45 * u * hsh(q, 12));
        const sp = [p[0] - d[0] * back + rt[0] * side, p[1] - d[1] * back + rt[1] * side], z = 0.12 + 0.55 * Math.sin(u * Math.PI) * (0.6 + 0.4 * hsh(q, 13));
        const pp = proj(sp[0], sp[1], z);
        g.fillStyle = `rgba(206,214,228,${(0.6 * spray * (1 - u)).toFixed(3)})`; g.fillRect(Math.round(pp[0]), Math.round(pp[1]), 1, 1);
      }
    }
    if (c.washer) {                                      // sideways jets: more rain, for the street
      g.fillStyle = 'rgba(190,220,255,0.75)';
      for (let q = 0; q < 26; q++) {
        const u = fract(hsh(q, 7) + tt * 2.2), s = q % 2 ? 1 : -1, back = -1.5 - 1.2 * hsh(q, 8);
        const wp = [p[0] + c.dir[0] * back + s * (1.0 + 2.6 * u) * -c.dir[1], p[1] + c.dir[1] * back + s * (1.0 + 2.6 * u) * c.dir[0]];
        const pp = proj(wp[0], wp[1], 0.6 * (1 - u));
        g.fillRect(Math.round(pp[0]), Math.round(pp[1]), 1, 1);
      }
    }
  }
}
