// ============================================================================
// 80_timeline: t -> what the lens sees and what the viewfinder shows.
// ============================================================================
const STUT = (typeof __STUTTER__ !== 'undefined') ? __STUTTER__ : { s1: [], s2: [], s3: [], type: [] };
function kickP(t) { const k = lastKick(t); return pulse(t, k, 0.012, 0.11); }
function lastShutter(t) { if (t < T_ROLL0) return -99; const n = Math.min(36, Math.floor((t - T_ROLL0) / 1.5 + 1e-9) + 1); return expoTime(n); }
function mirrorSlap(t) { const d = t - lastShutter(t); if (d < 0 || d > 0.12) return 0; return d < 0.055 ? 1 : 1 - smooth(0.055, 0.115, d); }
function jolts(t) {
  let s = 0;
  for (const [key, g] of [['s1', 1.0], ['s2', 1.15], ['s3', 1.0]]) {
    const L = STUT[key] || [];
    for (let i = 0; i < L.length; i++) {
      const [ti, si] = L[i]; if (t < ti - 0.02 || t > ti + 0.9) continue;
      let amp = 62 * g * Math.min(si, 1.6);
      if (key === 's3') amp *= lerp(1.0, 2.3, i / Math.max(1, L.length - 1));
      amp = Math.min(amp, 230);
      s += (i % 2 === 0 ? 1 : -1) * amp * pulse(t, ti, 0.016, 0.1);
    }
  }
  return s;
}
function blinkAt(t) { let b = 0; for (const c of [109.08, 111.24, 112.9]) b = Math.max(b, 1 - Math.abs(t - c) / 0.09); return clamp(b); }
function typedAt(t) { const L = (STUT.type || []).filter(o => o[0] < 115.4); if (!L.length) return clamp((t - 113.9) / 1.4); let n = 0; for (const o of L) if (t >= o[0]) n++; return n / L.length; }

function vfPlan(t, opts) {
  const P = { cam: { x: 0, y: 0, rot: 0, zoom: 1, blur: 0 }, st: { t, counter: 0, speed: '1/60', needle: 0, split: 0, blur: 0, prism: null, black: 0, flash: 0, bright: 1, alpha: 1, title: 0 } };
  P.cam.x = jit(t * 1.3, 1, 4) + jit(t * 5.1, 2, 1.1); P.cam.y = jit(t * 1.1, 3, 4) + jit(t * 4.7, 4, 1.1); P.cam.rot = jit(t * 0.9, 5, 0.005);
  const rms = envAvg('rms', t, 0.04);
  P.st.needle = (rms - 0.62) * 3.4 + jit(t * 9, 8, 0.04);

  if (t < T_DROP) {
    // ---- the long take: her at the snowy window (the first vocal part)
    P.draw = (c, S) => drawHerTake(c, t, S);
    let f = 0.5 * Math.sin(t * 0.42 + 0.6) + 0.24 * Math.sin(t * 1.13 + 2.0) + 0.07 * Math.sin(t * 3.1);
    f *= 1 - 0.85 * smooth(22.3, 22.9, t) * (1 - smooth(23.7, 24.3, t));  // a breath: almost in focus
    f *= 1 - 0.6 * smooth(38.6, 39.6, t) * (1 - smooth(45.4, 46.2, t));   // her eyes on the lens: nearly there
    f = lerp(1.2, f, smooth(2.5, 7.0, t));                                  // coming up to the eye, far out
    P.st.split = f * 64; P.st.blur = clamp(Math.abs(f) * 0.85 + 0.06);
    const push = easeInOut(clamp((t - 6) / 42));
    P.cam.zoom = 1.0 + 0.2 * push; P.cam.x += -38 * push; P.cam.y += -20 * push;
    P.st.alpha = smooth(2.0, 4.6, t);
    P.st.title = smooth(0.6, 1.6, t) * (1 - smooth(4.8, 5.8, t));
    P.st.infoAlpha = smooth(5.2, 6.2, t);
    P.st.needle = t < 6 ? lerp(-1.0, 0, smooth(4.5, 6, t)) : (vocAt(t) * 1.7 - 0.7) + jit(t * 9, 8, 0.04);
    const fall = easeIn(smooth(48.2, 53.6, t));
    if (fall > 0) {
      P.cam.rot += -0.6 * fall; P.cam.y += 560 * fall * fall; P.cam.x += 140 * fall; P.cam.zoom *= 1 + 0.3 * fall;
      P.st.blur = clamp(P.st.blur + fall); P.st.split += 110 * fall;
      P.st.bright = 1 - 0.88 * smooth(52.0, 53.9, t);
      P.st.needle = lerp(P.st.needle, -1.1, fall);
    }
    P.st.counter = 0;
  } else if (t < T_ROLL_END) {
    // ---- the roll: a shutter on every snare, 36 exposures
    const k = t < T_ROLL0 ? 1 : Math.min(36, Math.floor((t - T_ROLL0) / 1.5 + 1e-9) + 2);
    const lt = t - expoShown(k);
    P.draw = (c, S) => drawExpo(c, k, t, S);
    P.st.counter = t < T_ROLL0 ? 0 : Math.min(36, Math.floor((t - T_ROLL0) / 1.5 + 1e-9) + 1);
    const f0 = (hash(k * 7.7) - 0.5) * 1.4 * (k === 1 ? 0 : 1);
    const f = f0 * Math.exp(-Math.max(0, lt - 0.05) / 0.11) + 0.025 * Math.sin(t * 2.3);
    P.st.split = f * 62; P.st.blur = clamp(Math.abs(f) * 0.9);
    P.cam.zoom = 1 + 0.035 * hash(k * 3.1) + 0.018 * lt + 0.012 * kickP(t);
    P.st.speed = '1/125';
    if (t < 54.6) P.st.flash = 0.95 * (1 - smooth(54.0, 54.5, t));
    P.st.black = mirrorSlap(t);
    const ls = lastShutter(t); if (ls > 0 && t - ls < 0.2) { P.st.roll = (t - ls - 0.03) / 0.12; P.st.counterPrev = P.st.counter - 1; }
  } else if (t < T_REWIND) {
    // ---- out of film. every vocal onset of the hook tears the focusing circle in two
    const paused = t >= 120.12 && t < 121.72; const ts = paused ? 120.12 : t;
    const whip = smooth(113.55, 113.95, t);
    const st = { screen: 'type', typed: typedAt(ts), del: clamp((ts - 115.42) / 0.95), t: ts };
    if (ts >= 121.6) { st.screen = 'call'; st.callPulse = clamp(Math.abs(jolts(ts)) / 60); st.press = smooth(125.2, 125.32, ts); }
    P.draw = (c, S) => {
      if (whip < 1) { c.save(); c.translate(0, -SH * 1.05 * easeInOut(whip)); drawExpo(c, 36, ts, S, { blink: blinkAt(ts), look: [jit(ts * 0.8, 3, 0.35), jit(ts * 0.7, 4, 0.2)] }); c.restore(); }
      if (whip > 0) { c.save(); c.translate(0, SH * 1.05 * (1 - easeInOut(whip))); drawPhoneScene(c, ts, S, st); c.restore(); }
    };
    let sp = jolts(t) + (paused ? 0 : 9 * Math.sin(t * 1.9)) + (t > 121.6 ? 6 * Math.sin(t * 7) : 0);
    const snap = t >= T_CALL;
    if (snap) sp = 0;
    P.st.split = sp; P.st.blur = snap ? 0 : clamp(0.1 + Math.abs(sp) / 95 + 0.9 * Math.sin(Math.PI * whip));
    P.st.prism = snap ? 0 : clamp(0.15 + Math.abs(sp) / 60);
    P.st.counter = snap ? '?' : 36; P.st.counterBlink = !snap;
    P.st.splitR = lerp(SPLIT_R, 250, smooth(107.3, 108.0, t)) * (1 - 0.25 * whip * (1 - whip) * 4);
    P.cam.x += sp * 0.12;
    P.st.speed = '1/15';
    P.st.needle = paused ? -0.95 : clamp(-0.2 + Math.abs(sp) / 45 + (rms - 0.6) * 1.5, -1.1, 1.15);
    if (paused) P.st.bright = 0.8;
    P.cam.zoom = 1 + 0.03 * Math.sin(Math.PI * whip) + (t > 121.6 && !snap ? 0.04 * smooth(121.6, 125.2, t) : 0);
    if (snap) { P.st.flash = 1.0 - 0.8 * smooth(125.34, 126.0, t); P.cam.zoom += 0.06 * (1 - smooth(125.25, 125.8, t)); }
    P.st.black = t < 107.37 ? mirrorSlap(t) : 0;
  }
  return P;
}

// ---- master frame ----------------------------------------------------------
function renderFrame(ctx, W, H, t, opts) {
  opts = opts || {};
  const M = W / VW;
  if (t < T_REWIND) {
    const P = vfPlan(t, opts);
    P.cam.blur = P.st.blur;
    shootScene(M, P.cam, P.draw);
    if (opts.cardT0 != null) P.st.title = Math.max(P.st.title, 1 - smooth(opts.cardT0 + 1.2, opts.cardT0 + 1.8, t));
    composeVF(ctx, W, H, P.st);
  } else if (t < T_DARK) drawRewind(ctx, W, H, t);
  else if (t < T_PENCIL) drawDarkroom(ctx, W, H, t);
  else if (t < T_END) drawPencil(ctx, W, H, t);
  else drawEnd(ctx, W, H, t);
}
