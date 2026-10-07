// ---------------------------------------------------------------- the cast
// A few people the night has in it, each a pure function of time:
//   the sax player in a doorway, playing the intro's own melody (a note on every onset of the
//     keys under the rain); he turns his head to him, and flicks a coin into the case in passing
//   a couple slow-dancing under one umbrella on the corner of the first crossing; when the rain
//     stops for everyone but him the umbrella closes, and they keep dancing
//   a black cat under the night café's awning -- the only other creature that looks up at his cloud
//   at dawn, pigeons on the pavement that burst into the air on the finale's strike
const SAX = { p: [9.2, -30.5], face: Math.PI, coin: { t: 13.35, land: 13.9 } };
const COUPLE = { p: [11.3, -16.3] };
const PIGS = { p: [126.0, 235.0], t: 300.02 };
const NOTE = ['01100', '01010', '01001', '01000', '11000', '11000'];
const SAX_CASE = [SAX.p[0] - 0.85, SAX.p[1] + 0.2];

// where his head points: at the sax player as he passes (relative to his heading, radians)
function headLook(t) {
  const w = walker(Math.min(t, SONG.stop)), ang = Math.atan2(w.d[1], w.d[0]);
  const on = step(t, 10.8, 12.0) * (1 - step(t, 15.2, 16.6));
  if (on <= 0) return 0;
  let rel = Math.atan2(SAX.p[1] - w.p[1], SAX.p[0] - w.p[0]) - ang;
  rel = Math.atan2(Math.sin(rel), Math.cos(rel));
  return clamp(rel, -1.5, 1.5) * on;
}
// the toss: his right hand out over the case, the coin's arc
const tossArm = t => step(t, SAX.coin.t - 0.35, SAX.coin.t - 0.05) * (1 - step(t, SAX.coin.t + 0.15, SAX.coin.t + 0.55));

function drawSax(g, t) {
  const tt = Math.min(t, SONG.stop), [x0, y0, x1, y1] = viewRect(4);
  if (SAX.p[0] < x0 || SAX.p[0] > x1 || SAX.p[1] < y0 || SAX.p[1] > y1) return;
  const k = kAt(1.4) * EX, c = proj(SAX.p[0], SAX.p[1], 1.4);
  // the open case on the pavement in front of him, its coins
  const cs = SAX_CASE, coins = 3 + (tt > SAX.coin.land ? 1 : 0);
  rect3(g, cs, Math.PI / 2, 0.9 * 1.3, 0.36 * 1.3, 0.05, [24, 20, 22]);
  rect3(g, cs, Math.PI / 2, 0.8 * 1.3, 0.28 * 1.3, 0.08, [120, 30, 40]);
  for (let q = 0; q < coins; q++) {
    const cp = proj(cs[0] + (H1(q, 1, 91) - 0.5) * 0.25, cs[1] + (H1(q, 2, 92) - 0.5) * 0.8, 0.1);
    EMIT.push(cx => { cx.fillStyle = css([236, 196, 90]); cx.fillRect(Math.round(cp[0]), Math.round(cp[1]), 1, 1); });
  }
  // him: swaying with the music, the horn out in front, a hat
  const b = (tt - DOWNBEAT) / BEAT, sway = Math.sin(b * Math.PI) * 0.12 + Math.sin(tt * 0.7) * 0.05;
  const nod = Math.exp(-Math.pow((tt - 14.4) / 0.35, 2)) * 0.25;
  g.save(); g.translate(c[0], c[1]); g.rotate(-(SAX.face + sway)); g.scale(k, k);
  g.fillStyle = 'rgba(6,6,12,0.4)'; g.beginPath(); g.ellipse(-0.04, 0.04, 0.34, 0.42, 0, 0, TAU); g.fill();
  g.fillStyle = css([24, 22, 24]); for (const s of [-1, 1]) { g.beginPath(); g.ellipse(0.06, s * 0.12, 0.14, 0.065, 0, 0, TAU); g.fill(); }
  g.fillStyle = css([12, 12, 16]); g.beginPath(); g.ellipse(0, 0, 0.235, 0.335, 0, 0, TAU); g.fill();
  g.fillStyle = css([58, 50, 44]); g.beginPath(); g.ellipse(0, 0, 0.2, 0.3, 0, 0, TAU); g.fill();
  // arms forward to the horn
  g.fillStyle = css([48, 42, 38]);
  for (const s of [-1, 1]) { g.beginPath(); g.ellipse(0.16, s * 0.2, 0.15, 0.07, s * -0.6, 0, TAU); g.fill(); }
  // the saxophone: a gold body from his mouth down and out, the bell turned up, catching the light
  g.strokeStyle = css([212, 168, 62]); g.lineWidth = 0.09; g.lineCap = 'round';
  g.beginPath(); g.moveTo(0.14, -0.02); g.quadraticCurveTo(0.42, 0.04, 0.4, 0.22); g.stroke(); g.lineCap = 'butt';
  g.fillStyle = css([236, 196, 84]); g.beginPath(); g.ellipse(0.4, 0.25, 0.09, 0.07, 0, 0, TAU); g.fill();
  g.fillStyle = css([255, 236, 150]); g.fillRect(0.36, 0.2, 0.05, 0.05);
  // the hat: brim, band, crown -- nodding at him as the coin lands
  g.scale(1 + nod, 1 + nod);
  g.fillStyle = css([34, 28, 26]); g.beginPath(); g.arc(0.02, 0, 0.2, 0, TAU); g.fill();
  g.fillStyle = css([120, 40, 36]); g.beginPath(); g.arc(0.02, 0, 0.13, 0, TAU); g.fill();
  g.fillStyle = css([50, 42, 38]); g.beginPath(); g.arc(0.02, 0, 0.11, 0, TAU); g.fill();
  g.restore();
  LIGHTS.push({ p: [SAX.p[0] - 0.4, SAX.p[1]], r: 3.6, c: [255, 190, 120], a: 0.55 });
  // the notes: one for each onset of the intro's keys (or, without them, on the beat), rising
  // from the bell and drifting off with the rain's wind
  const mel = stormEvents().melody || [];
  const bell = [SAX.p[0] - 0.55 * EX, SAX.p[1] - 0.3 * EX];
  const list = mel.length ? mel : null;
  const recent = [];
  if (list) { for (let i = evLast(list, tt); i >= 0 && tt - list[i][0] < 1.8; i--) recent.push(list[i]); }
  else for (let q = 0; q < 3; q++) { const te = Math.floor(tt / BEAT - q) * BEAT; recent.push([te, 0.8, q * 5]); }
  for (const [te, s, bin] of recent) {
    const age = tt - te, u = age / 1.8;
    const p = [bell[0] + 0.15 + 0.65 * age + (H1(Math.round(te * 100), 1, 93) - 0.5) * 0.5, bell[1] - 0.3 + 0.35 * age + Math.sin(age * 5 + te) * 0.25];
    const me = walker(tt).p, near = clamp((Math.hypot(p[0] - me[0], p[1] - me[1]) - 0.5) / 0.6);
    const pp = proj(p[0], p[1], 1.6 + 1.6 * age), a = near * clamp(age / 0.18) * (1 - u * u) * (0.7 + 0.3 * s);
    const col = mix3([255, 222, 130], [176, 226, 255], clamp(bin / 47)), sc = kAt(0) > 9 ? 2 : 1;
    EMIT.push(cx => {
      cx.globalAlpha = clamp(a);
      const x0 = Math.round(pp[0]) - 2 * sc, y0 = Math.round(pp[1]) - 3 * sc;
      for (const [dx, col2] of [[1, 'rgba(10,8,16,0.8)'], [0, css(col)]]) {
        cx.fillStyle = col2;
        NOTE.forEach((row, r) => [...row].forEach((ch, q) => { if (ch === '1') cx.fillRect(x0 + q * sc + dx, y0 + r * sc + dx, sc, sc); }));
      }
      cx.globalAlpha = 1;
    });
  }
  // the coin in the air
  if (tt > SAX.coin.t && tt < SAX.coin.land + 0.12) {
    const u = clamp((tt - SAX.coin.t) / (SAX.coin.land - SAX.coin.t));
    const from = emberlessHand(SAX.coin.t), z = lerp(1.0, 0.1, u) + 1.6 * Math.sin(u * Math.PI);
    const p = [lerp(from[0], cs[0], u), lerp(from[1], cs[1], u)], pp = proj(p[0], p[1], z), sp = proj(p[0], p[1], 0.02);
    if (tt <= SAX.coin.land) EMIT.push(cx => { cx.fillStyle = 'rgba(8,8,14,0.6)'; cx.fillRect(Math.round(sp[0]) - 1, Math.round(sp[1]), 3, 2); });
    const landed = tt > SAX.coin.land, x0 = Math.round(pp[0]), y0 = Math.round(pp[1]);
    EMIT.push(cx => {
      cx.fillStyle = 'rgba(16,12,8,0.85)'; cx.fillRect(x0 - 1, y0 - 1, 5, 5);
      cx.fillStyle = css([255, 214, 96]); cx.fillRect(x0, y0, 3, 3);
      cx.fillStyle = css([255, 250, 214]); cx.fillRect(x0, y0, 1, 1);
      // a glint at the top of its arc, and where it lands
      if (landed || Math.abs(u - 0.5) < 0.08) { cx.fillStyle = 'rgba(255,250,220,0.9)'; cx.fillRect(x0 - 2, y0 + 1, 1, 1); cx.fillRect(x0 + 4, y0 + 1, 1, 1); cx.fillRect(x0 + 1, y0 - 2, 1, 1); cx.fillRect(x0 + 1, y0 + 4, 1, 1); }
    });
  }
}
// his right hand, in the world (for the coin)
function emberlessHand(t) {
  const w = walker(t), rt = [w.d[1], -w.d[0]];
  return [w.p[0] + (w.d[0] * 0.3 + rt[0] * 0.45) * EX, w.p[1] + (w.d[1] * 0.3 + rt[1] * 0.45) * EX];
}

function drawCouple(g, t) {
  const tt = Math.min(t, SONG.stop), [x0, y0, x1, y1] = viewRect(4);
  if (COUPLE.p[0] < x0 || COUPLE.p[0] > x1 || COUPLE.p[1] < y0 || COUPLE.p[1] > y1) return;
  // a slow turn, one round every two bars; on the full beat (0:45) she spins out under his arm
  const th = 0.6 + TAU * (tt - DOWNBEAT) / (2 * BAR), b = (tt - DOWNBEAT) / BEAT;
  const out = Math.sin(clamp((tt - 45.02) / (2 * BEAT)) * Math.PI) * 0.55;
  const sway = Math.sin(b * Math.PI) * 0.05;
  const dir = [Math.cos(th), Math.sin(th)];
  const pa = [COUPLE.p[0] - dir[0] * 0.3, COUPLE.p[1] - dir[1] * 0.3];
  const pb = [COUPLE.p[0] + dir[0] * (0.3 + out), COUPLE.p[1] + dir[1] * (0.3 + out)];
  person(g, pa, th + sway, { coat: [40, 44, 56], hair: PAL.hair[0], walk: b * 0.5 });
  person(g, pb, th + Math.PI + sway + out * 6, { coat: [168, 40, 48], hair: PAL.hair[1], walk: b * 0.5 + 1 });
  const close = step(tt, SONG.fadeA + 2.4, SONG.fadeB + 1.4);
  umbrella(g, COUPLE.p, th, [176, 36, 50], close, 0);
  LIGHTS.push({ p: COUPLE.p, r: 6, c: [255, 176, 96], a: 0.75 });
}

// the cat under the night café's awning: curled up; it lifts its head to watch his cloud, and its
// eyes catch his lightning
function drawCat(g, t, C) {
  const tt = Math.min(t, SONG.stop), p = C.at(C.L * 0.45, 2.6);
  const cg = tt > SONG.beatIn ? cloudGround(tt) : null;
  const near = cg ? clamp(1.6 - Math.hypot(cg[0] - p[0], cg[1] - p[1]) / 9) : 0;
  const k = kAt(0.3) * EX, c = proj(p[0], p[1], 0.3);
  const look = cg ? Math.atan2(cg[1] - p[1], cg[0] - p[0]) : C.ang;
  g.save(); g.translate(c[0], c[1]); g.rotate(-look); g.scale(k, k);
  g.fillStyle = css([14, 14, 18]);
  g.beginPath(); g.ellipse(-0.1, 0, 0.2, 0.13, 0, 0, TAU); g.fill();                        // body
  g.lineWidth = 0.05; g.strokeStyle = css([14, 14, 18]); g.beginPath(); g.moveTo(-0.28, 0.02); g.quadraticCurveTo(-0.38, 0.18, -0.2, 0.2); g.stroke();   // tail
  g.beginPath(); g.arc(0.08, 0, 0.085, 0, TAU); g.fill();                                     // head
  g.beginPath(); g.moveTo(0.1, -0.08); g.lineTo(0.16, -0.06); g.lineTo(0.12, -0.02); g.fill();   // ears
  g.beginPath(); g.moveTo(0.1, 0.08); g.lineTo(0.16, 0.06); g.lineTo(0.12, 0.02); g.fill();
  g.restore();
  if (near > 0.15) {                                         // looking up: two green eyes, lit by his thunder
    const fl = Math.max(0.35, flicker(t));
    const e1 = proj(p[0] + Math.cos(look) * 0.12 * EX - Math.sin(look) * 0.04 * EX, p[1] + Math.sin(look) * 0.12 * EX + Math.cos(look) * 0.04 * EX, 0.35);
    const e2 = proj(p[0] + Math.cos(look) * 0.12 * EX + Math.sin(look) * 0.04 * EX, p[1] + Math.sin(look) * 0.12 * EX - Math.cos(look) * 0.04 * EX, 0.35);
    EMIT.push(cx => { cx.fillStyle = css([140, 255, 160], clamp(near * fl * 1.4)); cx.fillRect(Math.round(e1[0]), Math.round(e1[1]), 2, 2); cx.fillRect(Math.round(e2[0]), Math.round(e2[1]), 2, 2); });
  }
}

// pigeons: pecking on the pavement until the strike, then up and away from it
function drawPigeons(g, t, high) {
  const tt = Math.min(t, SONG.stop), [x0, y0, x1, y1] = viewRect(30);
  if (PIGS.p[0] < x0 || PIGS.p[0] > x1 || PIGS.p[1] < y0 || PIGS.p[1] > y1) return;
  const fly = tt - PIGS.t;
  for (let q = 0; q < 14; q++) {
    const a0 = H1(q, 1, 101) * TAU, r0 = 1.7 * Math.sqrt(H1(q, 2, 102));
    let p = [PIGS.p[0] + Math.cos(a0) * r0, PIGS.p[1] + Math.sin(a0) * r0 * 0.7], z = 0.15, head = H1(q, 3, 103) * TAU;
    if (fly < 0) {                                           // a little shuffling about
      p = [p[0] + Math.sin(tt * 0.6 + q) * 0.25, p[1] + Math.cos(tt * 0.5 + q * 2) * 0.2];
      head += Math.sin(tt * 0.9 + q) * 0.8;
      if (high) continue;
    } else {
      if (!high) continue;
      let dir = a0 + (H1(q, 4, 104) - 0.5) * 0.9; if (Math.cos(dir) < 0.15) dir = Math.PI - dir + 0.3;   // the facade is west of them
      const v = 4.5 + 2.5 * H1(q, 5, 105), d = v * fly;
      p = [p[0] + Math.cos(dir) * d, p[1] + Math.sin(dir) * d]; z = 0.15 + Math.min(9, 3.2 * fly + 1.2 * fly * fly); head = dir;
    }
    const k = kAt(z) * 1.6, c = proj(p[0], p[1], z);
    if (c[0] < -6 || c[0] > BW + 6 || c[1] < -6 || c[1] > BH + 6) continue;
    g.save(); g.translate(c[0], c[1]); g.rotate(-head); g.scale(k, k);
    if (fly >= 0) {                                         // wings, beating
      const flap = Math.sin((fly * 14 + q) * Math.PI) * 0.5 + 0.5;
      g.fillStyle = css([132, 136, 150]);
      for (const s of [-1, 1]) { g.beginPath(); g.ellipse(-0.02, s * (0.12 + 0.1 * flap), 0.08, 0.16 * (0.4 + 0.6 * flap), 0, 0, TAU); g.fill(); }
    } else { g.fillStyle = 'rgba(6,6,12,0.3)'; g.beginPath(); g.ellipse(-0.02, 0.02, 0.15, 0.1, 0, 0, TAU); g.fill(); }
    g.fillStyle = css([118, 124, 140]); g.beginPath(); g.ellipse(0, 0, 0.13, 0.075, 0, 0, TAU); g.fill();
    g.fillStyle = css([88, 120, 104]); g.fillRect(0.06, -0.035, 0.04, 0.07);                    // the green of the neck
    g.fillStyle = css([70, 72, 84]); g.beginPath(); g.arc(0.12 + (fly < 0 ? 0.03 * Math.max(0, Math.sin(tt * 7 + q * 3)) : 0), 0, 0.045, 0, TAU); g.fill();
    g.restore();
  }
}
