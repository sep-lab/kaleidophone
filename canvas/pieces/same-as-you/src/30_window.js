// ============================================================
//  THE WINDOW — one double window, torn down its mullion.
//  Seen from outside in the rain.  Half-world coords: x ∈ [0, 560],
//  the seam (the mullion's centre) at x = 540.  Mirrored for her.
// ============================================================
const WG = { fx0: 118, fy0: 574, fr: 26, mull: 13, sill: 1058, r: 70, hx: 372 };
const GLS = { x0: WG.fx0 + WG.fr, y0: WG.fy0 + WG.fr, x1: SEAM - WG.mull, y1: WG.sill };
const HEART = { cx: SEAM, cy: 868, k: 3.7 };

function bodyPts(f) {
  const r = f.r, lean = f.lean || 0, dir = f.view === 'side' ? (f.dir || 1) : 1;
  const ax = Math.sin(lean) * dir, ay = -Math.cos(lean);
  const S = [f.x + ax * RG.torso * r, f.y + ay * RG.torso * r];
  const hd = f.head || {};
  return { S, Hc: [S[0] + ax * RG.neck * r + (hd.dx || 0) * r, S[1] + ay * RG.neck * r + (hd.dy || 0) * r] };
}

// ---- poses at the window (front view, lower body hidden by the sill) ----
// The resting poses are built FROM THE SILL UP: elbows on the sill at exact
// upper-arm length from the shoulders, forearms at exact length toward the jaw,
// and the head is then set down onto the hands (the chibi neck sinks).
function windowFigure(who, P, lw) {
  const r = WG.r, pose = P.pose || 'chin';
  const up = RG.upper * r, fo = RG.fore * r, sillTop = WG.sill - lw / 2;
  const x = P.x != null ? P.x : WG.hx, lean = P.lean || 0;
  const f = {
    view: 'front', x, y: 1110, r, hair: who, fill: who === 'her' ? C.paper : C.grey2, lean,
    head: { dy: 0, look: P.look || 0, eyes: P.eyes || 'open', mouth: P.mouth || 'dash', tilt: P.tilt || 0, up: P.up || 0 }
  };
  const setShoulders = (Sy) => { f.y = Sy + RG.torso * r * Math.cos(lean); };
  const armFromSill = (s, th, target) => {
    // s = -1 (L) / +1 (R); th = upper-arm angle outward from vertical
    const shx = x + s * RG.shW * r, shy = sillTop - up * Math.cos(th);
    const el = [shx + s * up * Math.sin(th), sillTop];
    const v = [target[0] - el[0], target[1] - el[1]], L = Math.hypot(v[0], v[1]) || 1;
    const hd = [el[0] + v[0] / L * fo, el[1] + v[1] / L * fo];
    return { sh: [shx, shy], el, hd };
  };
  if (pose === 'chin' || pose === 'draw' || pose === 'rest' || pose === 'sleep') {
    const th = pose === 'chin' || pose === 'draw' ? 0.46 : 0.82;
    const Sy = sillTop - up * Math.cos(th) - 0.12 * r;          // arm root sits 0.12r below the shoulder line
    setShoulders(Sy);
    const { S } = bodyPts(f);
    if (pose === 'chin' || pose === 'draw') {
      const aL = armFromSill(-1, th, [x - 0.52 * r, Sy - 1.1 * r]);
      const aR = armFromSill(1, th, [x + 0.52 * r, Sy - 1.1 * r]);
      const handY = (aL.hd[1] + aR.hd[1]) / 2;
      const HcY = handY - 0.84 * r;                               // jaw rests on the hands
      f.head.dy = (HcY - (S[1] - RG.neck * r)) / r;
      if (pose === 'draw') f.head.dy -= 0.16;                     // lifts a little to look
      f.arms = { L: { joint: aL.el, end: aL.hd } };
      if (pose === 'chin') f.arms.R = { joint: aR.el, end: aR.hd };
      else {
        const pts = heartHalf(Math.max(0.001, P.heartU || 0), HEART.cx, HEART.cy, HEART.k);
        const tip = pts[pts.length - 1];
        f.arms.R = { to: tip, hand: 'point', front: true, pole: [x + 2.2 * r, Sy + 2.2 * r] };
      }
    } else {
      // forearms folded on the sill, head laid on them
      const aL = armFromSill(-1, th, [x + 0.9 * r, sillTop - 0.06 * r]);
      const aR = armFromSill(1, th, [x - 0.9 * r, sillTop - 0.14 * r]);
      const HcY = sillTop - 0.16 * r - 0.9 * r;
      f.head.dy = (HcY - (S[1] - RG.neck * r)) / r;
      f.head.tilt = (P.tilt || 0) + (pose === 'sleep' ? 0.3 : 0.08);
      f.head.dx = pose === 'sleep' ? 0.12 : 0;
      f.arms = { L: { joint: aL.el, end: aL.hd, front: true }, R: { joint: aR.el, end: aR.hd, front: true } };
    }
    return f;
  }
  // standing poses: palm on the glass / leaving / looking down at a phone
  if (pose === 'phone') {
    setShoulders(sillTop - up * Math.cos(0.3) - 0.12 * r);
    const { S, Hc } = bodyPts(f);
    f.head.dy = 0.55; f.head.eyes = P.eyes || 'down';
    f.arms = {
      L: { to: [x - 0.35 * r, WG.sill + 0.6 * r], pole: [x - 2.2 * r, S[1] + 1 * r] },
      R: { to: [x + 0.35 * r, WG.sill + 0.6 * r], pole: [x + 2.2 * r, S[1] + 1 * r] }
    };
    return f;
  }
  f.y = WG.sill + 0.3 * r - (P.rise || 0) * 3.4 * r;
  const { S, Hc } = bodyPts(f);
  if (pose === 'palm') {
    f.arms = {
      L: { to: [Hc[0] - 1.3 * r, Hc[1] + 0.45 * r], hand: 'palm', front: true, pole: [x - 2.4 * r, S[1] + 1.6 * r] },
      R: { to: [SEAM - WG.mull - 0.4 * r, Hc[1] + 0.05 * r], hand: 'palm', front: true, pole: [x + 1.4 * r, S[1] + 2.4 * r] }
    };
  } else {
    f.arms = {
      L: { to: [x - 0.8 * r, S[1] + 2.25 * r], pole: [x - 2 * r, S[1] + 1 * r] },
      R: { to: [x + 0.8 * r, S[1] + 2.25 * r], pole: [x + 2 * r, S[1] + 1 * r] }
    };
  }
  return f;
}

// ---- the room behind the glass ----
function roomInterior(who, V, lt) {
  const on = V.light == null ? 1 : V.light;
  const wall = on > 0.5 ? C.room : C.roomOff;
  flat(GLS.x0 - 4, GLS.y0 - 4, GLS.x1 - GLS.x0 + 30, GLS.y1 - GLS.y0 + 8, wall);
  if (on > 0 && on < 1) { ctx.save(); ctx.globalAlpha = 1 - on; flat(GLS.x0, GLS.y0, 460, 480, C.roomOff); ctx.restore(); }
  // a picture rail
  stroke([[GLS.x0, 668], [GLS.x1 + 20, 668]], on > 0.5 ? C.roomDk : '#1b1a18', LW(0.7));
  // the photo of two — one of them is paper (the ( - ) rule, kept on the wall)
  const px = 196, py = 694;
  rect(px, py, 78, 62, on > 0.5 ? C.paper : '#34322e', C.ink, LW(0.7));
  if (on > 0.5) {
    const me = who === 'him' ? 0 : 1;
    for (let k = 0; k < 2; k++) {
      const cx = px + 26 + k * 26, isMe = k === me;
      circ(cx, py + 24, 8, isMe ? C.paper : C.paper, isMe ? C.ink : null, LW(0.4), 10);
      poly(capsulePts(cx, py + 34, cx, py + 52, 7, 4), isMe ? C.grey2 : C.paper, isMe ? C.ink : null, LW(0.4));
      if (!isMe) { /* she / he is cut out: paper, no outline */ }
    }
  }
  if (who === 'him') {
    // the setar on the wall
    ctx.save(); ctx.translate(176, 842); ctx.rotate(-0.22);
    const c = on > 0.5 ? '#8a6a44' : '#2a2520';
    poly(capsulePts(0, -150, 0, -20, 6, 3), c, C.ink, LW(0.6));
    ell(0, 10, 26, 34, c, C.ink, LW(0.7), 16);
    circ(0, 14, 5, C.ink, null, 0, 8);
    rect(-7, -172, 14, 24, c, C.ink, LW(0.6));
    ctx.restore();
  } else {
    // her plant on a shelf
    stroke([[GLS.x0, 930], [GLS.x0 + 130, 930]], C.ink, LW(0.8));
    const c = on > 0.5 ? '#6f7a5a' : '#262821';
    poly([[190, 930], [212, 930], [208, 900], [194, 900]], on > 0.5 ? '#9c6b4c' : '#2a2320', C.ink, LW(0.6));
    for (let i = 0; i < 5; i++) { const a = rad(-160 + i * 34); ell(201 + Math.cos(a) * 34, 880 + Math.sin(a) * 30, 22, 12, c, C.ink, LW(0.55), 12, a); }
  }
  // the pendant lamp
  const lx = WG.hx - 68, ly = 716;
  stroke([[lx, GLS.y0 - 4], [lx, ly - 22]], C.ink, LW(0.6));
  poly([[lx - 16, ly - 24], [lx + 16, ly - 24], [lx + 40, ly + 8], [lx - 40, ly + 8]], on > 0.5 ? C.dark : '#141312', C.ink, LW(0.7));
  if (on > 0.02 && !DRY) {
    glow(lx, ly + 30, 330, `rgba(255,232,178,${0.34 * on})`, 'rgba(255,232,178,0)');
    ell(lx, ly + 10, 32, 7, `rgba(255,240,205,${0.9 * on})`, null, 0, 14);
  }
}

// ---- the whole window scene ----
function sceneWindow(who, lt, env, V) {
  const lw = LW(1);
  const night = V.night == null ? 1 : V.night;
  // sky above the roofline, facade, cornice
  const skyC = night > 0.5 ? '#2b2d2f' : C.sky;
  flat(-200, -200, 800, 700, skyC);
  if (!DRY) { const g = ctx.createLinearGradient(0, 0, 0, 470); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, night > 0.5 ? 'rgba(70,74,78,0.55)' : 'rgba(255,255,255,0.18)'); ctx.fillStyle = g; ctx.fillRect(-200, 0, 800, 470); }
  flat(-200, 470, 800, H + 200, night > 0.5 ? C.facadeDk : C.facade);
  rect(-40, 462, 620, 30, night > 0.5 ? '#46474a' : C.facadeLt, C.ink, LW(0.8));
  stroke([[-40, 500], [600, 500]], C.ink, LW(0.5));
  if (who === 'him') { stroke([[250, 462], [250, 360]], C.ink, LW(0.7)); stroke([[212, 392], [288, 392]], C.ink, LW(0.6)); stroke([[222, 372], [278, 372]], C.ink, LW(0.6)); stroke([[250, 360], [264, 344]], C.ink, LW(0.5)); }
  else { rect(210, 402, 54, 62, night > 0.5 ? '#3d3e40' : C.facadeLt, C.ink, LW(0.7)); rect(204, 394, 66, 12, night > 0.5 ? '#3d3e40' : C.facadeLt, C.ink, LW(0.6)); }
  // bricks: a few courses, sketched
  for (let i = 0; i < 26; i++) {
    const bx = 20 + HS(i, 201) * 500, by = 520 + HS(i, 202) * 1150;
    if (by > WG.fy0 - 20 && by < WG.sill + 40 && bx > WG.fx0 - 30) continue;
    stroke([[bx, by], [bx + 34 + 20 * HS(i, 203), by]], 'rgba(20,18,15,0.55)', LW(0.45));
    if (HS(i, 204) > 0.5) stroke([[bx + 18, by + 18], [bx + 52, by + 18]], 'rgba(20,18,15,0.45)', LW(0.4));
  }
  // drainpipe on the outer edge
  rect(36, 470, 18, 1500, night > 0.5 ? '#2f3032' : '#5f605d', C.ink, LW(0.6));
  // ---- through the glass ----
  ctx.save(); ctx.beginPath(); ctx.rect(GLS.x0, GLS.y0, GLS.x1 - GLS.x0 + 40, GLS.y1 - GLS.y0); ctx.clip();
  roomInterior(who, V, lt);
  const figs = [];
  if (V.presence > 0) {      // the lightning shows the other one beside you — paper, for a flash
    const g = windowFigure(who === 'him' ? 'her' : 'him', { pose: 'palm', x: WG.hx - 150 }, lw);
    g.style = 'sil'; ctx.save(); ctx.globalAlpha = V.presence; figure(g); ctx.restore();
  }
  if (V.fig !== false) {
    const P = V.pose || { pose: 'chin' };
    const f = windowFigure(who, P, lw);
    if (V.phoneLight > 0) f.handFill = C.paper;
    const Jf = figure(f); figs.push(Jf);
    if (P.pose !== 'palm' && P.pose !== 'rise' && P.pose !== 'phone') contact('elbow↔sill', [Jf.elbows.L[0], Jf.elbows.L[1] + lw / 2], [Jf.elbows.L[0], WG.sill], 1.5);
    if (V.phoneLight > 0 && !DRY) glow(Jf.H[0], WG.sill + 30, 260, `rgba(190,215,235,${0.5 * V.phoneLight})`, 'rgba(190,215,235,0)', 'screen');
  }
  // glass: tint + two faint reflections
  if (!DRY) {
    ctx.fillStyle = `rgba(22,26,30,${V.light === 0 ? 0.28 : 0.12})`; ctx.fillRect(GLS.x0, GLS.y0, 460, 480);
    ctx.globalCompositeOperation = 'screen';
    ctx.fillStyle = 'rgba(255,255,255,0.045)';
    ctx.beginPath(); ctx.moveTo(GLS.x0 + 30, GLS.y0); ctx.lineTo(GLS.x0 + 120, GLS.y0); ctx.lineTo(GLS.x0 + 10, GLS.y1); ctx.lineTo(GLS.x0 - 80, GLS.y1); ctx.fill();
    ctx.beginPath(); ctx.moveTo(GLS.x0 + 170, GLS.y0); ctx.lineTo(GLS.x0 + 200, GLS.y0); ctx.lineTo(GLS.x0 + 90, GLS.y1); ctx.lineTo(GLS.x0 + 60, GLS.y1); ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
  }
  // fog + the heart
  const fogA = V.fog || 0;
  if (fogA > 0) fogPatch(HEART.cx - 40, (V.heartCy == null ? HEART.cy : V.heartCy) + 20, 190, 150, fogA);
  if (V.breath > 0 && figs[0]) fogPatch(figs[0].H[0] + 58, figs[0].H[1] + 40, 60 + 70 * V.breath, 44 + 40 * V.breath, 0.42 * V.breath);
  const hcy = V.heartCy == null ? HEART.cy : V.heartCy, hk = V.heartK == null ? HEART.k : V.heartK;
  if (V.heartU > 0) heartLine(heartHalf(V.heartU, HEART.cx, hcy, hk), V.heartRed || 0, V.heartA == null ? 1 : V.heartA);
  if (V.race > 0 && V.race < 1 && !DRY) {        // one big drop races down past their faces
    const ry = lerp(630, 1034, easeIn(V.race) * 0.35 + ease(V.race) * 0.65), rx = 474 + 6 * Math.sin(V.race * 9);
    ctx.save(); ctx.strokeStyle = 'rgba(232,238,242,0.3)'; ctx.lineWidth = 7; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(474, 620); ctx.lineTo(rx, ry); ctx.stroke();
    ctx.fillStyle = 'rgba(236,242,246,0.45)'; ctx.beginPath(); ctx.ellipse(rx, ry, 9, 11, 0, 0, TAU); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.beginPath(); ctx.arc(rx - 3, ry - 4, 3, 0, TAU); ctx.fill(); ctx.restore();
  }
  glassDrops(GLS.x0, GLS.y0, GLS.x1, GLS.y1, rainClock(V.t), V.drops == null ? 14 : V.drops, who === 'her' ? 7 : 0);
  ctx.restore();
  // ---- the window frame (outside) ----
  const fc = night > 0.5 ? '#cfc9ba' : C.frame, fl = LW(0.9);
  const heal = V.healed || 0;
  poly([[WG.fx0, WG.fy0], [SEAM + 30, WG.fy0], [SEAM + 30, GLS.y0], [GLS.x0, GLS.y0], [GLS.x0, GLS.y1], [WG.fx0, GLS.y1]], fc, C.ink, fl);
  if (heal < 1) { ctx.save(); ctx.globalAlpha = 1 - heal; rect(SEAM - WG.mull, GLS.y0 - 2, WG.mull + 30, GLS.y1 - GLS.y0 + 4, fc, C.ink, fl); ctx.restore(); }
  rect(WG.fx0 - 16, WG.sill, SEAM + 50 - WG.fx0, 26, fc, C.ink, fl);
  stroke([[WG.fx0 - 10, WG.sill + 26], [SEAM + 40, WG.sill + 26]], 'rgba(20,18,15,0.6)', LW(1.6));
  // once it turns red the heart is no longer on the glass — it glows over the mullion too
  if (V.heartU > 0 && (V.heartRed || 0) > 0.02) heartLine(heartHalf(V.heartU, HEART.cx, hcy, hk).concat(V.heartU >= 1 ? [[HEART.cx + 2, hcy + 17 * hk]] : []), V.heartRed, (V.heartA == null ? 1 : V.heartA) * V.heartRed);
  // lintel
  rect(WG.fx0 - 12, WG.fy0 - 30, SEAM + 50 - WG.fx0, 30, night > 0.5 ? '#55565a' : C.facadeLt, C.ink, fl);
  // the window below (a neighbour, dark)
  rect(WG.fx0 + 40, 1330, SEAM - WG.fx0, 360, '#1c1d1e', C.ink, fl);
  rect(SEAM - WG.mull, 1330, WG.mull + 30, 360, fc, C.ink, fl);
  noDraw(() => glassDrops(WG.fx0 + 40, 1330, SEAM - WG.mull, 1690, rainClock(V.t) * 0.8, 6, 13, 0.7));
  // pavement + the warm window reflected in it
  flat(-200, 1720, 800, 400, C.street);
  stroke([[-200, 1720], [600, 1720]], C.ink, LW(0.8));
  if (!DRY && (V.light == null || V.light > 0)) {
    const on = V.light == null ? 1 : V.light;
    const g = ctx.createLinearGradient(0, 1720, 0, 1920); g.addColorStop(0, `rgba(230,200,140,${0.28 * on})`); g.addColorStop(1, 'rgba(230,200,140,0)');
    ctx.fillStyle = g; ctx.fillRect(GLS.x0, 1722, GLS.x1 - GLS.x0 + 40, 200);
    ctx.strokeStyle = 'rgba(20,20,20,0.5)'; ctx.lineWidth = 2;
    for (let i = 0; i < 6; i++) { const y = 1745 + i * 28 + 6 * Math.sin(V.t * 2 + i); ctx.beginPath(); ctx.moveTo(GLS.x0 + 10, y); ctx.lineTo(GLS.x1 + 30, y); ctx.stroke(); }
  }
  // rain in front of everything
  noDraw(() => rain(rainClock(V.t), V.rainN == null ? 150 : V.rainN, V.slant == null ? 0.1 : V.slant, V.rainA == null ? 0.42 : V.rainA, { hang: V.hang || 0 }));
  return figs[0];
}
