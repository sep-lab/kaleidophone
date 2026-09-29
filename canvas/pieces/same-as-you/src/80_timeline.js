// ============================================================
//  THE STORYBOARD — 120 BPM; bar b starts at T0 + 2b seconds.
//    0–1   the card: one window, one red heart, SAME | AS YOU (the reel loops back here)
//    1–8   the snap: the page tears; two windows, the same rain, the same gestures
//    8–12  two phones: both typing… both see the other typing… both delete
//   12–16  they get up, the lights go out, the rain builds
//   16–21  THE DROP — one café torn in half: back to back, each with someone new;
//          on the beat the someone new flickers into the one you lost
//   21–27  one street: umbrellas, they pass in the dark between two lamps; the page rips
//   27–31  one bed torn in half: a hand slides to the torn edge
//   31–36  the heart: breath on the glass, half a heart each; the page closes; red.  [reel ends]
//   36–48  the dream: the tear heals, the rain hangs, the heart pulls us in, kaleidoscope
//   48–62  the storm: the page rips again; palms on the glass; lightning shows the other one;
//          memories on every beat
//   62–    after: the rain stops, they sleep at their windows, the halves drift apart
// ============================================================
function sinceCut(t, b0, win = 1.7) { const d = t - bt(b0); return d >= 0 && d < win ? d : null; }
function blink(bq, list, len = 0.085) { for (const x of list) if (bq >= x && bq < x + len) return true; return false; }
function onDrawing(t, tb) { return Math.floor(t * DRAW_FPS + 1e-6) === Math.ceil(tb * DRAW_FPS - 1e-6); }
function flashAt(t, list, k = 16) { let f = 0; for (const tb of list) { const d = t - tb; if (d >= 0 && d < 0.5) f = Math.max(f, Math.exp(-d * k) * (d < 0.05 || (d > 0.11 && d < 0.17) ? 1 : 0.55)); } return f; }

function beatPulse(t, k = 0.011) { const ph = fract((t - T0) / BEAT); return k * Math.exp(-ph * 5.5); }
function cardV(t) {
  return { t, night: 1, light: 1, pose: { pose: 'chin', eyes: 'open' }, fog: 0.3, heartU: 1, heartRed: 1, heartA: 1, rainN: 150, slant: 0.1, drops: 14 };
}

function timeline(t, env, opts = {}) {
  const tq = Math.floor(t * DRAW_FPS + 1e-6) / DRAW_FPS;
  const b = (t - T0) / BAR, bq = (tq - T0) / BAR;
  if (b < 8) return secWindowA(t, tq, b, bq, env);
  if (b < 12) return secPhone(t, tq, b, bq, env);
  if (b < 16) return secLeave(t, tq, b, bq, env);
  if (b < 21) return secCafe(t, tq, b, bq, env);
  if (b < 27) return secStreet(t, tq, b, bq, env);
  if (b < 31) return secBed(t, tq, b, bq, env);
  if (b < 36) return secHeart(t, tq, b, bq, env);
  if (b < 48.5) return secDream(t, tq, b, bq, env);
  if (b < 62) return secStorm(t, tq, b, bq, env);
  return secAfter(t, tq, b, bq, env);
}

// ---- 0–8: the card, the snap, the window ---------------------------------------
function secWindowA(t, tq, b, bq, env) {
  const V = cardV(t), P = V.pose;
  let gap = 0, titleA = 1, cam = null;
  if (b >= 0.85) { V.heartRed = 1 - step(b, 0.9, 1.15); V.heartA = 1 - step(b, 1.0, 1.7); V.fog = lerp(0.3, 0.12, step(b, 1, 2.6)); }
  if (b >= 1) {
    const k = b - 1;
    gap = k < 0.03 ? lerp(0, 46, k / 0.03) : 30 + 16 * Math.exp(-(k - 0.03) * 6) * Math.cos((k - 0.03) * 20);
    gap += 3 * Math.sin((b - 1) * Math.PI / 2);
    titleA = 1 - step(b, 1.3, 2.3);
  }
  P.eyes = blink(bq, [0.55, 1.8, 2.6, 5.05, 7.3]) ? 'closed' : 'open';
  P.look = kf(bq, [[2.96, 0], [3.04, 1], [3.7, 1], [3.8, 0]]);
  if (bq >= 3 && bq < 3.75) P.tilt = 0.06;
  V.race = b >= 4.1 && b < 4.95 ? (b - 4.1) / 0.85 : 0;
  P.up = b < 4.1 ? kf(bq, [[4, 0], [4.08, 1]]) : b < 4.95 ? lerp(1, -1.6, ease(V.race)) : kf(bq, [[4.95, -1.6], [5.1, 0]]);
  if (bq >= 5.3 && bq < 6) P.eyes = P.eyes === 'closed' ? 'closed' : 'down';
  V.breath = kf(b, [[5.5, 0], [5.6, 1], [6.3, 0.6], [7.5, 0]]);
  if (b >= 5.5 && b < 5.62) P.mouth = 'o';
  if (bq >= 6) { P.pose = 'phone'; V.phoneLight = kf(b, [[6, 0], [6.06, 1], [7.45, 1], [7.5, 0.25], [7.56, 1]]); V.light = lerp(1, 0.72, step(b, 6, 6.6)); }
  V.rainN = 150 + 40 * step(b, 4, 8);
  if (b < 1) cam = { z: 1.12, cy: 820 };
  else if (b >= 1 && b < 3) cam = { z: lerp(1.12, 1.04, step(b, 1, 3)), cy: lerp(820, 900, step(b, 1, 3)) };
  else if (b >= 3 && b < 4) cam = { z: 1.32, cy: 890 };
  else if (b >= 4 && b < 6) cam = { z: 1.1 + 0.03 * step(b, 4, 6), cy: 880 };
  else if (b >= 6) cam = { z: 1.36, cy: 930 };
  return { scene: sceneWindow, lt: t, V, gap, title: 1, titleA, cam, gapGlow: 0.05, pulse: b >= 1 ? beatPulse(t) : 0 };
}

// ---- 8–12: the phones ---------------------------------------------------------
function secPhone(t, tq, b, bq, env) {
  const lb = b - 8;
  const V = { screen: 1, typing: 0, typed: 0, caret: 0, tap: -1, press: 0, back: false, reflect: 0, lit: 1 };
  if (lb >= 0.5 && lb < 1.75) {
    const u = (t - bt(8.5)) / 0.125; V.tap = Math.floor(u); V.press = fract(u) < 0.45 ? 1 : 0;
    V.typed = clamp((t - bt(8.5)) / (BAR * 1.25), 0, 1) * 0.8;
  } else if (lb >= 1.75 && lb < 2.75) { V.typed = 0.8; V.caret = fract(t * 2) < 0.5 ? 1 : 0; }
  else if (lb >= 2.75 && lb < 3.25) { V.back = true; V.typed = 0.8 * (1 - clamp((t - bt(10.75)) / (BAR * 0.45), 0, 1)); }
  else if (lb >= 3.25) { V.typed = 0; V.thumbAway = true; }
  if (lb >= 1.5 && lb < 2.5) V.typing = 1;
  if (lb >= 3.5) { V.screen = 0; V.reflect = step(lb, 3.5, 3.85); V.lit = 0; }
  const gap = 22 - 6 * step(lb, 0, 3.5) + 5 * (env.bass || 0);
  return { scene: scenePhone, mirror: false, lt: t - bt(8), V, gap, drawOn: sinceCut(t, 8), cam: { z: 1 + 0.07 * step(lb, 0, 4), cy: 930 } };
}

// ---- 12–16: they get up; the lights go out; the rain builds ----------------------
function secLeave(t, tq, b, bq, env) {
  const V = { t, night: 1, light: 1, pose: { pose: 'chin', eyes: 'down' }, fog: 0.1, rainN: 160, slant: 0.1, drops: 14 };
  if (bq >= 12.5) V.pose = { pose: 'rise', rise: step(bq, 12.5, 12.95), x: WG.hx - 270 * step(bq, 12.8, 13.3), eyes: 'down' };
  if (bq >= 13.3) V.fig = false;
  const flick = b >= 13 && b < 13.12 ? (Math.floor(t * 24) % 2) : 1;
  V.light = b < 13 ? 1 : b < 13.12 ? flick : 1 - step(b, 13.12, 13.3);
  V.rainN = lerp(160, 420, step(b, 13, 15.95)); V.slant = lerp(0.1, 0.2, step(b, 14, 16)); V.drops = Math.round(lerp(14, 36, step(b, 13, 16)));
  const cam = { z: lerp(1, 0.86, step(b, 13.4, 16)), cy: 880 };
  const gap = 30 + 20 * step(b, 14, 16) + 6 * (env.bass || 0);
  const shake = 12 * step(b, 15, 16) * (0.35 + (env.rms || 0));
  const flash = b > 15.86 ? step(b, 15.86, 16) * 0.95 : 0;
  return { scene: sceneWindow, lt: t - bt(12), V, gap, shake, cam, drawOn: sinceCut(t, 12), flash, gapGlow: 0.06 };
}

// ---- 16–21: THE DROP — the café -----------------------------------------------
const FLICKS = [17, 18, 18.5, 19.5, 20, 20.25, 20.5, 20.75];
function secCafe(t, tq, b, bq, env) {
  let flick = 0; for (const fb of FLICKS) if (onDrawing(t, bt(fb))) flick = 1;
  const V = { ghost: 0.95, talk: (tq - bt(16)) * 2.2, flicker: flick, turnBack: (bq >= 19 && bq < 19.5) ? 1 : 0, rainN: 270, eyesUp: flick };
  const bs = env.bass || 0;
  const gap = 16 + 26 * bs * bs;
  const flash = b < 16.1 ? 0.55 * (1 - step(b, 16, 16.1)) : 0;
  return { scene: sceneCafe, lt: t - bt(16), V, gap, cam: { z: 1.24, cy: 1010 }, drawOn: sinceCut(t, 16, 3.5), drawK: 0.5, flash, shake: 5 * (env.bflux || 0) };
}

// ---- 21–27: the street --------------------------------------------------------
function walkX(τ) {
  if (τ <= 8) return -360 + 112.5 * τ;
  if (τ <= 11) return 540 + 112.5 * (τ - 8) - 18.75 * (τ - 8) * (τ - 8);
  if (τ <= 20) return 708.75;
  if (τ <= 21) return 708.75 + 56.25 * (τ - 20) * (τ - 20);
  return 765 + 112.5 * (τ - 21);
}
function secStreet(t, tq, b, bq, env) {
  const tau = (tq - bt(21)) / BEAT;
  const walking = tau < 11 ? 1 : tau < 20 ? 0 : 1;
  const back = tau >= 14 && tau < 20;
  const near = { who: 'him', r: 50, dir: 1, floor: STREET.walkY, xAt: walkX, tau, x: walkX(tau), bob: walking * 2.5 * Math.abs(Math.sin(tau * Math.PI)), walking, faceDir: back ? -1 : 1, eyes: back ? 'open' : 'down' };
  const xAt2 = τ => W - walkX(τ) + 0;
  const far = { who: 'her', r: 47, dir: -1, floor: STREET.walkY2, xAt: xAt2, tau, x: xAt2(tau), bob: walking * 2.4 * Math.abs(Math.sin(tau * Math.PI)), walking, faceDir: back ? 1 : -1, eyes: back ? 'open' : 'down' };
  let gap;
  if (b < 23) gap = lerp(28, 0, step(b, 21.5, 23));
  else if (b < 25) gap = 6 * step(b, 23, 24);
  else if (b < 26) gap = lerp(6, 170, easeOut((b - 25) / 0.12));
  else gap = lerp(170, 64, step(b, 26, 27));
  const tilt = 0.012 * (b >= 25 ? 1 - step(b, 25, 26.5) : 0);
  const shake = b >= 25 && b < 25.2 ? 16 : 0;
  return { scene: sceneStreet, mirror: false, lt: t - bt(21), V: { near, far, rainN: 330 }, gap, tilt, shake, cam: { z: 1.1, cy: 1150 }, drawOn: sinceCut(t, 21), gapGlow: 0.07 };
}

// ---- 27–31: the bed -------------------------------------------------------------
function secBed(t, tq, b, bq, env) {
  const V = { reach: step(bq, 28, 29), phone: 1 - step(bq, 27.92, 28.05), eyes: bq >= 30 ? 'closed' : 'open', light: 1 };
  if (blink(bq, [27.6, 29.4])) V.eyes = 'closed';
  const gap = lerp(30, 7, step(b, 28, 29)) + 14 * step(b, 30.5, 31);
  return { scene: sceneBed, lt: t - bt(27), V, gap, cam: { z: 1.12, cy: 760 }, drawOn: sinceCut(t, 27), gapGlow: 0.05 };
}

// ---- 31–36: the heart (the reel's ending = its first frame) ------------------------
function secHeart(t, tq, b, bq, env) {
  const V = cardV(t), P = V.pose;
  V.heartU = bq < 32 ? 0 : bq < 33.5 ? (bq - 32) / 1.5 : 1;
  V.heartRed = step(b, 34.5, 34.75);
  V.fog = lerp(0.12, 0.3, step(b, 31.5, 32.2));
  V.breath = kf(b, [[31.5, 0], [31.6, 1], [32.4, 0.55], [33.6, 0]]);
  if (bq >= 32 && bq < 33.5) { P.pose = 'draw'; P.heartU = Math.max(0.001, V.heartU); P.look = 0.7; }
  if (b >= 31.5 && b < 31.64) P.mouth = 'o';
  P.eyes = blink(bq, [31.3, 34.1, 35.2]) ? 'closed' : 'open';
  if (bq >= 34.6 && bq < 35.1) P.look = 0.25;
  const gap = b < 34 ? 30 + 3 * Math.sin((b - 31) * Math.PI / 2) : lerp(30, 0, easeOut((b - 34) / 0.5));
  const title = step(b, 34.6, 35.5);
  let cam = null;
  if (b >= 32 && b < 34) cam = { z: 1.22, cy: 880 };
  else if (b >= 34) cam = { z: lerp(1.22, 1.12, step(b, 34, 35.5)), cy: lerp(880, 820, step(b, 34, 35.5)) };
  return { scene: sceneWindow, lt: t - bt(31), V, gap, title, cam, drawOn: sinceCut(t, 31), gapGlow: 0.05, pulse: b < 34 ? beatPulse(t, 0.008) : 0 };
}

// ---- 36–48.5: the dream, then THE INHALE -----------------------------------------
// The final master holds its breath at bars 47.5–48.5 (bass out, highs rising): everything
// fades — un-drawn stroke by stroke, last stroke first — until only the bare page is left.
function secDream(t, tq, b, bq, env) {
  const V = cardV(t), P = V.pose;
  const heal = step(b, 36, 37);
  V.healed = heal;
  P.x = lerp(WG.hx, 452, step(bq, 36.5, 38));
  P.tilt = 0.16 * step(bq, 36.5, 38);
  P.eyes = bq >= 37.3 ? 'closed' : 'open';
  V.hang = step(b, 36.5, 38);
  V.fog = 0.3;
  V.heartCy = lerp(HEART.cy, 700, step(b, 36.5, 38.5));
  V.heartK = lerp(HEART.k, 4.4, step(b, 36.5, 38.5));
  V.light = 1 + 0.12 * Math.sin((t - bt(36)) * Math.PI);
  const inhale = b >= 47.5 ? ease((b - 47.5) / 0.85) : 0;
  V.rainN = Math.round(300 * (1 - inhale));
  const st = { scene: sceneWindow, lt: t - bt(36), V, gap: 0, healed: heal, spotGain: 1.15 * (1 - inhale), spotGlow: 1.4,
    cam: { z: lerp(1.12, 1, step(b, 36, 37.5)) * (1 + 0.07 * inhale), cy: lerp(820, 880, step(b, 36, 37.5)) } };
  if (inhale > 0) st.erase = inhale;
  if (b >= 40 && b < 44) st.droste = { u: fract((b - 40) / 2), hcy: V.heartCy, hk: V.heartK };
  const kk = step(b, 43.6, 44) * (1 - step(b, 46.6, 47.4));
  if (kk > 0) st.kaleido = { n: b < 45.5 ? 6 : 8, rot: (t - bt(43)) * 0.32, cx: SEAM, cy: 820, k: kk, zoom: 1.9 + 0.35 * Math.sin((t - bt(43)) * Math.PI / 2) + 0.12 * (env.bass || 0) };
  return st;
}

// ---- 48.5–62: THE SPLASH, then the storm ------------------------------------------
const MEMORIES = [17, 23, 29.6, 9.7, 32.8, 19.2, 24.8, 3.3];
const LIGHTNING = [50, 51.5, 52, 53, 57, 59, 61];
function secStorm(t, tq, b, bq, env) {
  if (b >= 56 && b < 60) {     // memories, one drawing on every beat
    const k = Math.floor((t - bt(56)) / BEAT), inBeat = (t - bt(56)) - k * BEAT;
    if (inBeat < 1 / DRAW_FPS) {
      let mt = bt(MEMORIES[k % MEMORIES.length]);
      if (k % MEMORIES.length === 0) mt = Math.ceil(bt(17) * DRAW_FPS) / DRAW_FPS + 0.01;
      const s = timeline(mt, env);
      s.drawOn = null; s.flash = 0; s.memory = true; s.spotGlow = 1.6;
      return s;
    }
  }
  const V = { t, night: 1, light: 1, fog: 0.16, heartU: 0, rainN: 440, slant: 0.3, rainA: 0.5, drops: 32 };
  const fl = flashAt(t, LIGHTNING.map(bt));
  V.light = 0.82 + 0.18 * Math.sin(t * 37) * Math.sin(t * 11) + 0.4 * fl;
  let pose = 'palm', eyes = 'closed', look = 0;
  if (bq < 49) eyes = 'wide';
  else if (bq >= 52 && bq < 54) { eyes = 'open'; look = 0.8; }
  if (bq >= 54) { pose = 'rest'; eyes = bq >= 60 && bq < 61.5 ? 'closed' : 'open'; }
  if (bq >= 61.5) { pose = 'chin'; eyes = 'open'; }
  V.pose = { pose, eyes, look };
  V.presence = fl > 0.3 && pose === 'palm' ? 1 : 0;
  let gap;
  const bs = env.bass || 0;
  if (b < 48.9) gap = lerp(0, 72, easeOut((b - 48.5) / 0.05));
  else if (b < 49) gap = lerp(72, 0, easeIn((b - 48.9) / 0.1));
  else if (b < 52) gap = 6 * bs;
  else if (b < 54) gap = lerp(0, 40, step(b, 52, 54));
  else gap = 40 + 20 * bs;
  let cam = null;
  if (b < 49) cam = { z: lerp(1.2, 1.0, easeOut((b - 48.5) / 0.3)), cy: 880 };      // the splash punches in
  else if (b >= 49 && b < 50) cam = { z: 1.3, cy: 880 };
  else if (b >= 50 && b < 52) cam = { z: 1.08, cy: 880 };
  else if (b >= 60) cam = { z: 1.12, cy: 900 };
  const flash = fl * 0.85;
  const tilt = 0.012 * (1 - step(b, 48.5, 49.3));
  const kick = b < 48.7 ? 16 * (1 - step(b, 48.5, 48.7)) : 0;
  const st = { scene: sceneWindow, lt: t - bt(48.5), V, gap, cam, flash, tilt, shake: 7 * (env.bflux || 0) + kick, drawOn: null, gapGlow: 0.08, spotGlow: 1.1, spotGain: 0.85 };
  if (b < 48.64) st.splash = easeOut((b - 48.5) / 0.14);          // THE SPLASH: the storm is thrown onto the bare page
  if (b < 51) st.spotMinBirth = bt(48.5) - 0.01;                     // only ink born at the splash (the dream's blooms stay gone)
  return st;
}

// ---- 62–: after --------------------------------------------------------------------
// The final master lets the highs fade slowly (124 → 134 s), then one last flourish
// (135.25–137.0) before the music stops dead.  The halves drift apart… and on the flourish
// they rush back together for one more heartbeat of red.  Then nothing.
function secAfter(t, tq, b, bq, env) {
  const V = { t, night: 1, light: 0.85, pose: { pose: 'sleep', eyes: 'closed' }, fog: 0.16, heartU: 0, drops: 24, slant: 0.3, rainA: 0.5 };
  V.rainN = Math.round(440 * (1 - step(b, 62, 66.4)));
  if (bq >= 64 && bq < 64.6) V.pose.eyes = 'open';
  let gap = 40 + 440 * easeIn(clamp((b - 62.4) / 5.1, 0, 1));
  const title = step(b, 63.5, 64.6);
  let spotGlow = 1, shake = 0, flash = 0;
  if (b >= 67.5) {
    gap = lerp(480, 0, easeOut((b - 67.5) / 0.12));
    V.heartU = 1; V.heartRed = step(b, 67.56, 67.72); V.fog = 0.3;
    V.rainN = 230; V.hang = 0.55;
    if (bq >= 67.62) V.pose = { pose: 'sleep', eyes: 'open', look: 0.7 };
    spotGlow = 1.15;
    if (b < 67.62) { shake = 12; flash = 0.35 * (1 - step(b, 67.56, 67.62)); }
  }
  const fade = b >= 68.375 ? 1 : 0;          // the music stops dead at 137.0 — so does the picture
  return { scene: sceneWindow, lt: t - bt(62), V, gap, title, fade, flash, shake, gapGlow: 0.06 * (1 - step(b, 64, 67)), spotGlow };
}

// ---- Spotify Canvas: the card breathing, no words (crossfaded into a loop by ffmpeg) ----
function canvasState(t, env) {
  const V = cardV(t), P = V.pose;
  P.eyes = blink((t - T0) / BAR, [0.9, 2.6]) ? 'closed' : 'open';
  if (t > 4.2 && t < 5.6) P.look = kf(t, [[4.2, 0], [4.35, 0.8], [5.4, 0.8], [5.55, 0]]);
  return { scene: sceneWindow, lt: t, V, gap: 0, title: 0, cam: { z: 1.12, cy: 840 }, noSpots: true, pulse: beatPulse(t, 0.006) };
}
