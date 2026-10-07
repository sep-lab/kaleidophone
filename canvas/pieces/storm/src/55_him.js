// ---------------------------------------------------------------- him
// Hood up, hands in the rain, a step on every beat. Under the dawn café's awning -- the only
// dry metres his storm allows him -- he lights a cigarette on a snare. After the stop he is the
// only thing in the city that moves: the hood falls back and he looks up.
const ME = { coat: [44, 50, 74], hood: [170, 176, 190], skin: [204, 160, 126], hair: [24, 19, 17] };
const LIGHT_T = 293.27;                                  // a snare, under the awning
const lookUp = t => step(t, SONG.stop + 0.4, SONG.stop + 1.45);
function dragOf(t) {                                     // hand at the mouth: one beat in every six, from 296
  if (t < 295.5) return 0;
  const b = (t - 295.52) / BEAT, ph = fract(b / 6);
  return ph < 0.22 ? Math.sin(ph / 0.22 * Math.PI) : 0;
}
function emberPos(t) {                                   // world position of the cigarette's tip
  const w = walker(t), d = w.d, rt = [d[1], -d[0]];       // right of his heading
  const tt = Math.min(t, SONG.stop), b = stepOf(tt), sw = Math.cos(fract(b / 2) * TAU);
  const lift = Math.max(t < LIGHT_T + 1.0 ? step(t, LIGHT_T - 0.7, LIGHT_T - 0.15) : 0, dragOf(tt));
  const hx = lerp(-0.2 * sw + 0.12, 0.2, lift), hy = lerp(0.42, 0.08, lift);
  return [w.p[0] + (d[0] * hx + rt[0] * hy) * EX, w.p[1] + (d[1] * hx + rt[1] * hy) * EX, lift];
}

function drawHim(g, t) {
  const tt = Math.min(t, SONG.stop), w = walker(tt), ang = Math.atan2(w.d[1], w.d[0]);
  const c = proj(w.p[0], w.p[1], 1.4), k = kAt(1.4) * EX;
  LIGHTS.push({ p: w.p, r: 2.6, c: [236, 226, 210], a: 0.32 });          // the game keeps its man lit
  const b = stepOf(tt), plant = step(t, SONG.stop, SONG.stop + 0.3);
  const sw = Math.cos(fract(b / 2) * TAU) * (1 - plant), up = lookUp(t);
  const smoking = t >= LIGHT_T - 0.7, lighting = t > LIGHT_T - 0.7 && t < LIGHT_T + 1.0;
  const lift = smoking ? Math.max(lighting ? step(t, LIGHT_T - 0.7, LIGHT_T - 0.15) : 0, dragOf(tt)) : 0;
  g.save(); g.translate(c[0], c[1]); g.rotate(-ang); g.scale(k, k);
  g.fillStyle = 'rgba(6,6,12,0.4)'; g.beginPath(); g.ellipse(-0.05, 0.04, 0.36, 0.42, 0, 0, TAU); g.fill();
  g.fillStyle = css([22, 20, 22]);
  for (const s of [-1, 1]) { g.beginPath(); g.ellipse(0.3 * sw * s + 0.02, s * 0.12, 0.15, 0.07, 0, 0, TAU); g.fill(); }
  // arms: the right one comes up to his face to light, and to smoke
  g.fillStyle = css(mul3(ME.coat, 0.85));
  g.beginPath(); g.ellipse(-0.2 * sw * -1, -0.3, 0.15, 0.075, 0, 0, TAU); g.fill();                    // left
  const toss = tossArm(t);
  const rx = lerp(lerp(-0.2 * sw, 0.14, lift), 0.22, toss), ry = lerp(lerp(0.3, 0.16, lift), 0.52, toss);
  g.beginPath(); g.ellipse(rx, ry, 0.15, 0.075, lift * -0.9, 0, TAU); g.fill();                         // right
  if (lighting) { g.beginPath(); g.ellipse(lerp(0.2 * sw, 0.16, lift), lerp(-0.3, -0.12, lift), 0.15, 0.075, lift * 0.9, 0, TAU); g.fill(); }
  // body: a dark outline so he reads on any street, the wet sheen of the shoulders
  g.fillStyle = css([12, 12, 18]); g.beginPath(); g.ellipse(0, 0, 0.235, 0.345, 0, 0, TAU); g.fill();
  g.fillStyle = css(ME.coat); g.beginPath(); g.ellipse(0, 0, 0.2, 0.31, 0, 0, TAU); g.fill();
  g.fillStyle = css(mul3(ME.coat, 1.5)); g.beginPath(); g.ellipse(-0.05, -0.08, 0.08, 0.2, 0, 0, TAU); g.fill();
  // head: turned to whatever he is watching; the hood, falling back as he looks up; under it his face
  g.rotate(-headLook(t));
  if (up > 0) {
    g.fillStyle = css(ME.hair); g.beginPath(); g.arc(0.02, 0, 0.13, 0, TAU); g.fill();
    g.fillStyle = css(ME.skin); g.beginPath(); g.ellipse(0.04 + 0.02 * up, 0, 0.1 * up + 0.02, 0.09, 0, 0, TAU); g.fill();
    if (up > 0.6) {                                          // eyes, then the beard's shadow
      g.fillStyle = css([18, 14, 14]);
      for (const s of [-1, 1]) g.fillRect(0.06, s * 0.045 - 0.02, 0.04, 0.035);
      g.fillStyle = 'rgba(60,40,32,0.5)'; g.beginPath(); g.ellipse(0.12, 0, 0.035, 0.07, 0, 0, TAU); g.fill();
    }
    g.fillStyle = css(ME.hood); g.beginPath(); g.ellipse(-0.08 - 0.1 * up, 0, 0.1, 0.15 * (1 - 0.2 * up), 0, 0, TAU); g.fill();
  } else {
    g.fillStyle = css(ME.hood); g.beginPath(); g.arc(0.02, 0, 0.14, 0, TAU); g.fill();
    g.fillStyle = css(mul3(ME.hood, 1.3)); g.beginPath(); g.arc(-0.02, -0.04, 0.06, 0, TAU); g.fill();
    g.fillStyle = css(mul3(ME.hood, 0.6)); g.beginPath(); g.ellipse(0.13, 0, 0.03, 0.08, 0, 0, TAU); g.fill();   // the hood's opening
  }
  g.restore();
  // the cigarette: the lighter's flame, then the ember (both light the rain around them)
  if (smoking) {
    const e = emberPos(t), ep = proj(e[0], e[1], 1.5);
    if (lighting && t >= LIGHT_T && t < LIGHT_T + 0.9) {
      const fl = 0.7 + 0.3 * hsh(Math.floor(t * 24), 9), x0 = Math.round(ep[0]), y0 = Math.round(ep[1]);
      EMIT.push(cx => {
        cx.fillStyle = 'rgba(255,150,40,0.45)'; cx.fillRect(x0 - 3, y0 - 3, 6, 6);
        cx.fillStyle = css([255, 150, 40]); cx.fillRect(x0 - 2, y0 - 3, 4, 5);
        cx.fillStyle = css([255, 226, 120]); cx.fillRect(x0 - 1, y0 - 3, 2, 4);
        cx.fillStyle = css([255, 255, 236]); cx.fillRect(x0, y0 - 2, 1, 2);
      });
      LIGHTS.push({ p: [e[0], e[1]], r: 4.2, c: [255, 186, 96], a: fl });
      LIGHTS.push({ p: [e[0], e[1]], r: 1.6, c: [255, 220, 150], a: fl });
    } else if (t >= LIGHT_T + 0.9) {
      const glow = 0.55 + 0.45 * e[2];
      EMIT.push(cx => { cx.fillStyle = css(mix3([150, 40, 20], [255, 120, 40], glow)); cx.fillRect(Math.round(ep[0]), Math.round(ep[1]), 1, 1); });
      LIGHTS.push({ p: [e[0], e[1]], r: 1.2 + e[2], c: [255, 110, 40], a: 0.5 * glow });
    }
  }
  return c;
}
// the smoke: puffs let go from the ember every quarter second, drifting back and up, thinning;
// frozen with everything else at the stop
function drawSmoke(g, t) {
  if (t < LIGHT_T + 0.3) return;
  const tt = Math.min(t, SONG.stop);
  for (let q = 0; q < 16; q++) {
    const te = Math.floor(tt * 4) / 4 - q * 0.25;
    if (te < LIGHT_T + 0.3) break;
    const age = tt - te, e = emberPos(te), wv = [0.35, 0.25];
    const p = [e[0] + wv[0] * age + 0.25 * Math.sin(te * 7), e[1] + wv[1] * age + 0.25 * Math.cos(te * 5)];
    const pp = proj(p[0], p[1], 1.6 + 0.6 * age), a = 0.42 * (1 - age / 4) * (dragOf(te) > 0.2 ? 1.4 : 0.6);
    if (a <= 0.02) continue;
    const r = Math.max(1, (0.12 + 0.18 * age) * kAt(1.8));
    g.fillStyle = `rgba(196,200,210,${Math.min(0.6, a).toFixed(3)})`;
    g.beginPath(); g.arc(pp[0], pp[1], r, 0, TAU); g.fill();
  }
}
