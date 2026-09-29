// ============================================================================
// 10_her: her silhouettes (bust profile / bust front / full-body FK rig),
// hands, the eye. Everything is drawn as ONE dark shape + a light rim.
// ============================================================================

// ---- rim helper: fill `shape` (a function that builds+fills paths with current fillStyle)
function silhouette(ctx, shape, o) {
  o = o || {};
  const dark = o.dark || '#0b0a0c';
  ctx.save();
  if (o.rim) {
    // light rim peeking out on the light side (shadow offset toward the light)
    ctx.shadowColor = o.rim; ctx.shadowBlur = o.rimBlur == null ? 6 : o.rimBlur;
    ctx.shadowOffsetX = o.rimDx || 0; ctx.shadowOffsetY = o.rimDy || 0;
  }
  ctx.fillStyle = dark; shape(ctx);
  if (o.rim2) { // second, softer rim (e.g. warm lamp from the other side)
    ctx.shadowColor = o.rim2; ctx.shadowBlur = o.rim2Blur || 14; ctx.shadowOffsetX = o.rim2Dx || 0; ctx.shadowOffsetY = o.rim2Dy || 0;
    shape(ctx);
  }
  ctx.restore();
}

// ---- BUST, PROFILE facing right. origin = crown, unit = head height.
const HEAD_PROFILE = [[0, 0], [0.20, 0.03], [0.33, 0.14], [0.385, 0.28], [0.40, 0.385], [0.378, 0.448], [0.405, 0.52], [0.468, 0.612],
  [0.447, 0.648], [0.405, 0.662], [0.424, 0.712], [0.396, 0.744], [0.414, 0.776], [0.372, 0.822], [0.386, 0.884], [0.335, 0.946],
  [0.21, 0.975], [0.14, 1.0], [-0.1, 0.93], [-0.27, 0.79], [-0.355, 0.56], [-0.335, 0.3], [-0.22, 0.09]];
const TORSO_PROFILE = [[0.14, 0.95], [0.155, 1.3], [0.245, 1.41], [0.355, 1.57], [0.44, 1.78], [0.395, 1.99], [0.34, 2.22], [0.31, 2.7],
  [-0.36, 2.7], [-0.385, 2.05], [-0.345, 1.62], [-0.21, 1.39], [-0.12, 1.27], [-0.1, 0.92]];
function hairProfile(flow = 0, lift = 0) {
  // flow: + blows forward, - back (wind); lift: hair lifted (laughing / falling)
  const f = flow * 0.12, L = lift * 0.2;
  return [[0.27, 0.07], [0.13, -0.035], [-0.08, -0.06], [-0.31, 0.03], [-0.455, 0.28 - L * 0.2], [-0.51 + f * 0.3, 0.64 - L * 0.4], [-0.53 + f * 0.6, 1.05 - L * 0.6],
    [-0.57 + f, 1.5 - L * 0.8], [-0.56 + f * 1.3, 1.95 - L], [-0.43 + f * 1.4, 2.2 - L], [-0.3 + f, 2.06 - L], [-0.22 + f * 0.6, 1.6 - L * 0.6], [-0.15, 1.24], [-0.09, 0.98],
    [0.015, 0.63], [0.085, 0.4], [0.185, 0.19]];
}
function bustProfile(ctx, x, y, s, o) {
  o = o || {};
  const tilt = o.tilt || 0;           // head rotation (rad), negative = look up / laugh back
  const S = pts => pts.map(p => [p[0] * s, p[1] * s]);
  silhouette(ctx, c => {
    c.save(); c.translate(x, y); if (o.flip) c.scale(-1, 1);
    // torso (not rotated)
    blobPath(c, S(TORSO_PROFILE)); c.fill();
    // head + hair rotate around the neck pivot
    c.translate(0.02 * s, 0.98 * s); c.rotate(tilt); c.translate(-0.02 * s, -0.98 * s);
    blobPath(c, S(hairProfile(o.flow || 0, o.lift || 0))); c.fill();
    blobPath(c, S(HEAD_PROFILE)); c.fill();
    if (o.phone) { // phone at the ear: hand + phone block
      c.save(); c.translate(0.12 * s, 0.62 * s); c.rotate(-0.25);
      rrect(c, -0.07 * s, -0.26 * s, 0.14 * s, 0.34 * s, 0.03 * s); c.fill();
      c.restore();
      c.beginPath(); c.moveTo(0.05 * s, 0.9 * s); c.quadraticCurveTo(0.34 * s, 1.1 * s, 0.30 * s, 1.55 * s); c.lineTo(0.18 * s, 1.6 * s); c.quadraticCurveTo(0.2 * s, 1.15 * s, -0.02 * s, 0.95 * s); c.fill(); // forearm up
    }
    c.restore();
  }, o);
  if (o.phone && o.phoneGlow) { // screen light on the cheek
    ctx.save(); ctx.translate(x, y); if (o.flip) ctx.scale(-1, 1);
    ctx.translate(0.02 * s, 0.98 * s); ctx.rotate(tilt); ctx.translate(-0.02 * s, -0.98 * s);
    ctx.globalCompositeOperation = 'lighter';
    drawSprite(ctx, glowSprite(150, 185, 255, 'phoneglow'), 0.2 * s, 0.6 * s, 0.42 * s, 0.55 * o.phoneGlow);
    ctx.restore();
  }
  if (o.eye) { // a catchlight where the eye is (profile: tiny highlight)
    ctx.save(); ctx.translate(x, y); if (o.flip) ctx.scale(-1, 1);
    ctx.translate(0.02 * s, 0.98 * s); ctx.rotate(tilt); ctx.translate(-0.02 * s, -0.98 * s);
    ctx.fillStyle = rgba(235, 240, 255, 0.85 * o.eye); ell(ctx, 0.31 * s, 0.445 * s, 0.018 * s, 0.012 * s); ctx.fill();
    ctx.restore();
  }
}

// ---- BUST, FRONT (facing camera). origin = crown, unit = head height.
const HEAD_FRONT = [[0, 0], [0.24, 0.05], [0.345, 0.21], [0.37, 0.42], [0.345, 0.62], [0.27, 0.81], [0.15, 0.94], [0, 0.99], [-0.15, 0.94], [-0.27, 0.81], [-0.345, 0.62], [-0.37, 0.42], [-0.345, 0.21], [-0.24, 0.05]];
const TORSO_FRONT = [[0.12, 0.9], [0.13, 1.17], [0.34, 1.29], [0.6, 1.37], [0.79, 1.47], [0.86, 1.67], [0.87, 2.15], [0.83, 2.8], [-0.83, 2.8], [-0.87, 2.15], [-0.86, 1.67], [-0.79, 1.47], [-0.6, 1.37], [-0.34, 1.29], [-0.13, 1.17], [-0.12, 0.9]];
function hairFront(flow = 0) {
  const f = flow * 0.1;
  return [[0, -0.07], [0.3, -0.02], [0.47 + f, 0.2], [0.52 + f, 0.6], [0.53 + f * 1.4, 1.0], [0.58 + f * 1.8, 1.42], [0.55 + f * 2, 1.86], [0.44 + f * 2, 2.0], [0.37 + f, 1.62], [0.31, 1.18], [0.3, 0.8],
    [0.2, 0.5], [0, 0.18], [-0.2, 0.5], [-0.3, 0.8], [-0.31, 1.18], [-0.37 + f, 1.62], [-0.44 + f * 2, 2.0], [-0.55 + f * 2, 1.86], [-0.58 + f * 1.8, 1.42], [-0.53 + f * 1.4, 1.0], [-0.52 + f, 0.6], [-0.47 + f, 0.2], [-0.3, -0.02]];
}
function bustFront(ctx, x, y, s, o) {
  o = o || {};
  const S = pts => pts.map(p => [p[0] * s, p[1] * s]);
  silhouette(ctx, c => {
    c.save(); c.translate(x, y);
    blobPath(c, S(TORSO_FRONT)); c.fill();
    c.save(); c.translate(0, 0.98 * s); c.rotate(o.tilt || 0); c.translate(0, -0.98 * s);
    blobPath(c, S(hairFront(o.flow || 0))); c.fill();
    blobPath(c, S(HEAD_FRONT)); c.fill();
    c.restore();
    // arms / hands for gestures
    if (o.heart) { // right hand flat on the heart
      c.beginPath(); c.moveTo(0.84 * s, 1.6 * s); c.quadraticCurveTo(0.75 * s, 2.35 * s, 0.1 * s, 1.98 * s); c.lineTo(0.02 * s, 1.74 * s); c.quadraticCurveTo(0.5 * s, 2.0 * s, 0.62 * s, 1.55 * s); c.fill();
      ell(c, 0.02 * s, 1.78 * s, 0.17 * s, 0.11 * s, -0.5); c.fill();
    }
    if (o.handsOnHead) { // both hands up, fingers in the hair
      for (const sg of [-1, 1]) {
        limb(c, sg * 0.78 * s, 1.52 * s, sg * 0.98 * s, 0.8 * s, 0.28 * s, 0.21 * s);
        limb(c, sg * 0.98 * s, 0.8 * s, sg * 0.36 * s, 0.12 * s, 0.21 * s, 0.15 * s);
        ell(c, sg * 0.3 * s, 0.1 * s, 0.13 * s, 0.09 * s, sg * 0.6); c.fill();
      }
    }
    if (o.handOnHead) { // one hand flat on top of the head (measuring)
      limb(c, 0.78 * s, 1.52 * s, 1.05 * s, 0.72 * s, 0.28 * s, 0.21 * s);
      limb(c, 1.05 * s, 0.72 * s, 0.3 * s, -0.05 * s, 0.21 * s, 0.15 * s);
      ell(c, 0.05 * s, -0.06 * s, 0.3 * s, 0.075 * s, 0.03); c.fill();
    }
    c.restore();
  }, o);
  if (o.eyes) { // two catchlights: she is looking into the lens
    ctx.save(); ctx.translate(x, y); ctx.rotate(0);
    ctx.fillStyle = rgba(235, 240, 255, 0.9 * o.eyes);
    for (const sg of [-1, 1]) { ell(ctx, sg * 0.145 * s + 0.012 * s, 0.445 * s, 0.017 * s, 0.013 * s); ctx.fill(); }
    ctx.restore();
  }
}

// ---- FULL BODY FK RIG. origin = feet (ground), unit = figure height, y up is negative.
// view: 'side' (faces +x), 'front', 'back'.  pose: angles in radians.
function figure(ctx, x, y, H, pose, o) {
  pose = pose || {}; o = o || {};
  const view = pose.view || 'side';
  const lean = pose.lean || 0, sit = pose.sit || 0;
  silhouette(ctx, c => {
    c.save(); c.translate(x, y); c.scale(H * (pose.flip ? -1 : 1), H);
    const w = view === 'side' ? 0.62 : 1.0;           // body width factor in side view
    // hip point
    const hipY = -0.52 + (pose.hipDrop || 0);
    const hip = [pose.hipX || 0, hipY];
    // legs
    const legs = pose.legs || [[0.02, 0.02], [-0.02, 0.02]]; // [hipAngle, kneeBend] from straight down; + = forward
    const legPts = [];
    for (let i = 0; i < 2; i++) {
      const [ha, kb] = legs[i]; const off = view === 'side' ? 0 : (i ? -0.045 : 0.045);
      const h0 = [hip[0] + off, hip[1] + 0.02];
      const knee = [h0[0] + Math.sin(ha) * 0.245, h0[1] + Math.cos(ha) * 0.245];
      const a2 = ha - kb; const ank = [knee[0] + Math.sin(a2) * 0.235, knee[1] + Math.cos(a2) * 0.235];
      legPts.push([h0, knee, ank, a2]);
      limb(c, h0[0], h0[1], knee[0], knee[1], 0.078, 0.05);
      limb(c, knee[0], knee[1], ank[0], ank[1], 0.05, 0.03);
      // foot
      c.save(); c.translate(ank[0], ank[1]); c.rotate(-a2 * (view === 'side' ? 1 : 0));
      if (view === 'side') { ell(c, 0.035, 0.012, 0.055, 0.018); c.fill(); } else { ell(c, 0, 0.012, 0.026, 0.02); c.fill(); }
      c.restore();
    }
    // torso (lean around hip)
    c.save(); c.translate(hip[0], hip[1]); c.rotate(lean); c.translate(-hip[0], -hip[1]);
    const T = view === 'side'
      ? [[0.035, -0.84], [0.09, -0.77], [0.095, -0.7], [0.06, -0.62], [0.07, -0.54], [0.05, -0.47], [-0.07, -0.47], [-0.095, -0.55], [-0.065, -0.64], [-0.075, -0.74], [-0.045, -0.82]]
      : [[0.04, -0.85], [0.098, -0.815], [0.105, -0.77], [0.088, -0.7], [0.06, -0.62], [0.085, -0.54], [0.09, -0.47], [-0.09, -0.47], [-0.085, -0.54], [-0.06, -0.62], [-0.088, -0.7], [-0.105, -0.77], [-0.098, -0.815], [-0.04, -0.85]];
    blobPath(c, T.map(p => [p[0] + hip[0], p[1] + hipY + 0.52])); c.fill();
    // dress (A-line) from waist to above the knee
    if (pose.dress !== false) {
      const fl = pose.flare || 0; const hem = -0.3 + (pose.hemUp || 0);
      const D = view === 'side'
        ? [[0.055, -0.62], [0.078, -0.5], [0.1 + fl, hem], [-0.11 - fl * 1.2, hem - fl * 0.2], [-0.085, -0.5], [-0.058, -0.62]]
        : [[0.058, -0.62], [0.094, -0.5], [0.122 + fl, hem], [-0.122 - fl, hem], [-0.094, -0.5], [-0.058, -0.62]];
      blobPath(c, D.map(p => [p[0] + hip[0], p[1] + hipY + 0.52])); c.fill();
    }
    // arms
    const arms = pose.arms || [[0.08, 0.1], [-0.08, 0.1]]; // [shoulderAngle, elbowBend]
    const sh = view === 'side' ? [[0.0, -0.8], [-0.01, -0.8]] : [[0.1, -0.8], [-0.1, -0.8]];
    for (let i = 0; i < 2; i++) {
      const [sa, eb] = arms[i]; const s0 = [sh[i][0] + hip[0], sh[i][1] + hipY + 0.52];
      const sgn = view === 'side' ? 1 : (i ? -1 : 1);
      const el = [s0[0] + Math.sin(sa) * 0.165 * sgn, s0[1] + Math.cos(sa) * 0.165];
      const a2 = sa + eb; const wr = [el[0] + Math.sin(a2) * 0.145 * sgn, el[1] + Math.cos(a2) * 0.145];
      limb(c, s0[0], s0[1], el[0], el[1], 0.046, 0.034);
      limb(c, el[0], el[1], wr[0], wr[1], 0.034, 0.026);
      const hd = [wr[0] + Math.sin(a2) * 0.035 * sgn, wr[1] + Math.cos(a2) * 0.035];
      ell(c, hd[0], hd[1], 0.02, 0.036, -a2 * sgn); c.fill();
    }
    // neck + head + hair
    const nk = [hip[0] + (view === 'side' ? 0.0 : 0), hipY + 0.52 - 0.84];
    limb(c, nk[0], nk[1], nk[0] + (view === 'side' ? 0.012 : 0), nk[1] - 0.05, 0.036, 0.032);
    c.save(); c.translate(nk[0], nk[1] - 0.04); c.rotate(pose.head || 0);
    const hs = 0.132; // head height
    const hf = pose.hairFlow || 0, hl = pose.hairLift || 0;
    if (view === 'side') {
      c.translate(-0.01, -hs - 0.012);
      const S = pts => pts.map(p => [p[0] * hs, p[1] * hs]);
      blobPath(c, S(hairProfile(hf, hl))); c.fill();
      blobPath(c, S(HEAD_PROFILE)); c.fill();
    } else {
      c.translate(0, -hs - 0.012);
      const S = pts => pts.map(p => [p[0] * hs, p[1] * hs]);
      if (view === 'back') { // hair covers the whole back of the head and falls long
        blobPath(c, S([[0, -0.07], [0.33, 0.0], [0.47, 0.25], [0.5 + hf * 0.1, 0.7], [0.52 + hf * 0.2, 1.2], [0.5 + hf * 0.3, 1.75 - hl], [0.3, 1.95 - hl], [0, 2.0 - hl], [-0.3, 1.95 - hl], [-0.5 + hf * 0.3, 1.75 - hl], [-0.52 + hf * 0.2, 1.2], [-0.5 + hf * 0.1, 0.7], [-0.47, 0.25], [-0.33, 0.0]])); c.fill();
      } else {
        blobPath(c, S(hairFront(hf))); c.fill();
        blobPath(c, S(HEAD_FRONT)); c.fill();
      }
    }
    c.restore();
    c.restore(); // lean
    c.restore();
  }, o);
}

// ---- the white-sheet ghost (a person under a bedsheet). origin = floor centre, unit = height
function sheetGhost(ctx, x, y, H, o) {
  o = o || {}; const t = o.t || 0; const lift = o.lift || 0; // lift: sheet raised off the face like a veil
  ctx.save(); ctx.translate(x, y); ctx.scale(H, H);
  const sw = 0.012 * Math.sin(t * 2.1);
  const pts = [[0, -1.02], [0.1, -1.0], [0.155, -0.9], [0.17, -0.78], [0.2, -0.55], [0.26 + sw, -0.25], [0.3 + sw, -0.02], [0.2, 0.0], [0.12, -0.03], [0.02, 0.0], [-0.08, -0.03], [-0.18, 0.0], [-0.29 - sw, -0.02], [-0.25 - sw, -0.27], [-0.2, -0.55], [-0.17, -0.78], [-0.155, -0.9], [-0.1, -1.0]];
  const g = ctx.createLinearGradient(-0.3, 0, 0.3, 0);
  const L = o.light || [236, 230, 218];
  g.addColorStop(0, col(mix3(L, [60, 60, 70], 0.55))); g.addColorStop(0.45, col(L)); g.addColorStop(1, col(mix3(L, [40, 40, 55], 0.7)));
  ctx.fillStyle = g; blobPath(ctx, pts); ctx.fill();
  // fold shadows
  ctx.strokeStyle = 'rgba(40,38,50,0.25)'; ctx.lineWidth = 0.012; ctx.lineCap = 'round';
  for (const f of [[-0.08, -0.6, -0.14, -0.05], [0.06, -0.55, 0.11, -0.04], [0.0, -0.7, -0.01, -0.1]]) { ctx.beginPath(); ctx.moveTo(f[0], f[1]); ctx.quadraticCurveTo((f[0] + f[2]) / 2 + 0.02, (f[1] + f[3]) / 2, f[2], f[3]); ctx.stroke(); }
  if (lift > 0) { // her face under the raised sheet (veil)
    ctx.save(); ctx.beginPath(); ctx.rect(-0.16, -1.05, 0.32, 0.05 + lift * 0.22); ctx.clip();
    ctx.fillStyle = '#0d0b0d'; ell(ctx, 0, -0.9, 0.085, 0.1); ctx.fill();
    ctx.restore();
    ctx.fillStyle = col(L); ctx.beginPath(); ctx.moveTo(-0.17, -0.97 + lift * 0.2); ctx.quadraticCurveTo(0, -0.93 + lift * 0.23, 0.17, -0.97 + lift * 0.2); ctx.lineTo(0.18, -0.9 + lift * 0.2); ctx.quadraticCurveTo(0, -0.86 + lift * 0.23, -0.18, -0.9 + lift * 0.2); ctx.fill();
  } else {
    ctx.fillStyle = '#0c0b10';
    ell(ctx, -0.052, -0.83, 0.024, 0.032); ctx.fill(); ell(ctx, 0.052, -0.83, 0.024, 0.032); ctx.fill();
  }
  ctx.restore();
}
function sheetOnFloor(ctx, x, y, s, o) { // an empty sheet in a heap
  o = o || {}; ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  const L = o.light || [236, 230, 218];
  const g = ctx.createRadialGradient(0.05, -0.12, 0.05, 0, 0, 0.9); g.addColorStop(0, col(L)); g.addColorStop(1, col(mix3(L, [30, 30, 45], 0.75)));
  ctx.fillStyle = g;
  blobPath(ctx, [[-0.9, 0.05], [-0.7, -0.12], [-0.4, -0.2], [-0.15, -0.34], [0.12, -0.28], [0.4, -0.22], [0.75, -0.1], [0.95, 0.04], [0.6, 0.12], [0.2, 0.1], [-0.3, 0.14]]); ctx.fill();
  ctx.fillStyle = '#0c0b10'; ell(ctx, -0.08, -0.12, 0.05, 0.03, 0.3); ctx.fill(); ell(ctx, 0.1, -0.1, 0.05, 0.028, -0.2); ctx.fill();
  ctx.strokeStyle = 'rgba(30,30,40,0.3)'; ctx.lineWidth = 0.02;
  for (const f of [[-0.6, -0.02, -0.2, -0.16], [0.25, -0.15, 0.6, -0.02], [-0.3, 0.06, 0.2, 0.02]]) { ctx.beginPath(); ctx.moveTo(f[0], f[1]); ctx.quadraticCurveTo((f[0] + f[2]) / 2, (f[1] + f[3]) / 2 - 0.05, f[2], f[3]); ctx.stroke(); }
  ctx.restore();
}

// ---- hands (close-ups). origin = wrist centre, unit = hand length, fingers point up (-y)
const HAND_OPEN = [[-0.22, 0.0], [-0.25, -0.28], [-0.31, -0.37], [-0.43, -0.5], [-0.465, -0.6], [-0.43, -0.645], [-0.35, -0.6], [-0.255, -0.53],
  [-0.215, -0.62], [-0.225, -0.9], [-0.205, -0.985], [-0.15, -0.975], [-0.12, -0.63], [-0.105, -0.66], [-0.085, -1.03], [-0.04, -1.07], [0.005, -1.04],
  [0.012, -0.66], [0.028, -0.66], [0.05, -0.99], [0.1, -1.01], [0.13, -0.97], [0.125, -0.63], [0.142, -0.6], [0.175, -0.84], [0.215, -0.86], [0.24, -0.8],
  [0.222, -0.52], [0.225, -0.28], [0.19, 0.0]];
function handOpen(ctx, x, y, s, rot, o) {
  silhouette(ctx, c => { c.save(); c.translate(x, y); c.rotate(rot || 0); if (o && o.flip) c.scale(-1, 1); blobPath(c, HAND_OPEN.map(p => [p[0] * s, p[1] * s])); c.fill(); limb(c, 0, 0, 0, 0.9 * s, 0.4 * s, 0.36 * s); c.restore(); }, o);
}
const HANDS_PRAY = [[-0.2, 0.45], [-0.19, 0.1], [-0.22, -0.1], [-0.2, -0.35], [-0.16, -0.62], [-0.12, -0.86], [-0.07, -0.99], [-0.02, -1.04], [0.02, -1.04], [0.07, -0.99], [0.12, -0.86],
  [0.16, -0.62], [0.2, -0.35], [0.22, -0.1], [0.19, 0.1], [0.2, 0.45]];
function handsPray(ctx, x, y, s, o) {
  silhouette(ctx, c => { c.save(); c.translate(x, y); blobPath(c, HANDS_PRAY.map(p => [p[0] * s, p[1] * s])); c.fill(); limb(c, -0.12 * s, 0.4 * s, -0.5 * s, 1.3 * s, 0.26 * s, 0.34 * s); limb(c, 0.12 * s, 0.4 * s, 0.5 * s, 1.3 * s, 0.26 * s, 0.34 * s); c.restore(); }, o);
  // thumbs line (slightly lighter)
  ctx.save(); ctx.strokeStyle = 'rgba(80,70,70,0.35)'; ctx.lineWidth = 0.012 * s; ctx.beginPath(); ctx.moveTo(x, y - 0.95 * s); ctx.lineTo(x, y + 0.3 * s); ctx.stroke(); ctx.restore();
}

// ---- THE EYE (close-up, looking into the lens). centre (x,y), s = eye width
function drawEye(ctx, x, y, s, o) {
  o = o || {}; const t = o.t || 0; const blink = o.blink || 0; const look = o.look || [0, 0];
  const iris = o.iris || [[12, 40, 70], [40, 120, 175], [140, 205, 230]];
  ctx.save(); ctx.translate(x, y);
  // skin
  const sk = ctx.createRadialGradient(0, 0.05 * s, 0.1 * s, 0, 0, 1.3 * s);
  sk.addColorStop(0, rgba(205, 160, 135)); sk.addColorStop(0.5, rgba(150, 105, 90)); sk.addColorStop(1, rgba(38, 26, 26));
  ctx.fillStyle = sk; ctx.fillRect(-1.6 * s, -1.4 * s, 3.2 * s, 2.8 * s);
  // brow shadow + crease
  { const bg = ctx.createRadialGradient(0, -0.6 * s, 0.05 * s, 0, -0.6 * s, 0.8 * s); bg.addColorStop(0, 'rgba(40,24,22,0.32)'); bg.addColorStop(1, 'rgba(40,24,22,0)'); ctx.fillStyle = bg; ctx.fillRect(-1.6 * s, -1.4 * s, 3.2 * s, 1.4 * s); }
  ctx.save(); ctx.beginPath(); ctx.rect(-1.6 * s, -1.4 * s, 3.2 * s, 2.8 * s); ctx.clip(); overlayTile(ctx, noiseTile(128, 21, 50, 'skin'), 3.2 * s, 2.8 * s, 0, 0, 0.1, 'overlay'); ctx.restore();
  ctx.strokeStyle = 'rgba(70,40,35,0.55)'; ctx.lineWidth = 0.02 * s; ctx.beginPath(); ctx.moveTo(-0.52 * s, -0.2 * s); ctx.quadraticCurveTo(0, -0.52 * s, 0.55 * s, -0.16 * s); ctx.stroke();
  // eye opening (almond); blink closes it
  const op = 1 - clamp(blink);
  const almond = c => { c.beginPath(); c.moveTo(-0.5 * s, 0.02 * s); c.bezierCurveTo(-0.28 * s, (-0.34 * op + 0.02) * s, 0.26 * s, (-0.36 * op + 0.02) * s, 0.5 * s, -0.02 * s); c.bezierCurveTo(0.28 * s, (0.2 * op + 0.02) * s, -0.26 * s, (0.22 * op + 0.02) * s, -0.5 * s, 0.02 * s); c.closePath(); };
  ctx.save(); almond(ctx); ctx.clip();
  const sc = ctx.createRadialGradient(0, 0, 0.05 * s, 0, 0, 0.55 * s); sc.addColorStop(0, '#e9e1dc'); sc.addColorStop(0.7, '#c9b8b0'); sc.addColorStop(1, '#6d5550');
  ctx.fillStyle = sc; ctx.fillRect(-0.6 * s, -0.5 * s, 1.2 * s, 1 * s);
  // iris
  const ix = look[0] * 0.12 * s, iy = look[1] * 0.08 * s - 0.03 * s, R = 0.235 * s;
  const ig = ctx.createRadialGradient(ix, iy, 0.02 * s, ix, iy, R);
  ig.addColorStop(0, col(iris[2])); ig.addColorStop(0.45, col(iris[1])); ig.addColorStop(0.86, col(iris[0])); ig.addColorStop(1, '#05080c');
  ctx.fillStyle = ig; ctx.beginPath(); ctx.arc(ix, iy, R, 0, TAU); ctx.fill();
  // striations
  ctx.save(); ctx.beginPath(); ctx.arc(ix, iy, R * 0.96, 0, TAU); ctx.clip(); ctx.lineCap = 'round';
  for (let i = 0; i < 90; i++) { const a = i / 90 * TAU + hash(i) * 0.05, r0 = R * (0.3 + hash(i + 5) * 0.12), r1 = R * (0.75 + hash(i + 9) * 0.22);
    ctx.strokeStyle = hash(i + 2) > 0.5 ? rgba(170, 225, 240, 0.22) : rgba(10, 30, 50, 0.3); ctx.lineWidth = (0.004 + hash(i + 3) * 0.006) * s;
    ctx.beginPath(); ctx.moveTo(ix + Math.cos(a) * r0, iy + Math.sin(a) * r0); ctx.lineTo(ix + Math.cos(a + 0.03) * r1, iy + Math.sin(a + 0.03) * r1); ctx.stroke(); }
  // ocean reflected in the lower iris (waves, moving)
  if (o.ocean) { ctx.globalAlpha = 0.35 * o.ocean; ctx.strokeStyle = 'rgba(220,245,255,1)'; ctx.lineWidth = 0.006 * s;
    for (let k = 0; k < 6; k++) { const yy = iy + R * (0.2 + k * 0.12); ctx.beginPath();
      for (let xx = -R; xx <= R; xx += R / 12) { const w = Math.sin(xx / R * 6 + t * 1.6 + k * 1.3) * R * 0.035; if (xx === -R) ctx.moveTo(ix + xx, yy + w); else ctx.lineTo(ix + xx, yy + w); } ctx.stroke(); }
    ctx.globalAlpha = 1; }
  ctx.restore();
  // pupil
  const pr = R * (o.pupil || 0.36);
  ctx.fillStyle = '#030305'; ctx.beginPath(); ctx.arc(ix, iy, pr, 0, TAU); ctx.fill();
  // catchlight: a window
  ctx.fillStyle = 'rgba(255,255,255,0.9)'; rrect(ctx, ix + R * 0.28, iy - R * 0.55, R * 0.26, R * 0.3, R * 0.05); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.35)'; ell(ctx, ix - R * 0.35, iy + R * 0.35, R * 0.07, R * 0.05); ctx.fill();
  // upper lid shadow on the eyeball
  const ls = ctx.createLinearGradient(0, -0.3 * s, 0, 0.05 * s); ls.addColorStop(0, 'rgba(40,20,20,0.6)'); ls.addColorStop(1, 'rgba(40,20,20,0)');
  ctx.fillStyle = ls; ctx.fillRect(-0.6 * s, -0.4 * s, 1.2 * s, 0.45 * s);
  ctx.restore();
  // lid lines + lashes
  ctx.strokeStyle = '#1a0f0e'; ctx.lineCap = 'round';
  ctx.lineWidth = 0.028 * s; ctx.beginPath(); ctx.moveTo(-0.5 * s, 0.02 * s); ctx.bezierCurveTo(-0.28 * s, (-0.34 * op + 0.02) * s, 0.26 * s, (-0.36 * op + 0.02) * s, 0.5 * s, -0.02 * s); ctx.stroke();
  for (let i = 0; i <= 64; i++) { const k = clamp(i / 64 + (hash(i * 3.1) - 0.5) * 0.012), bx = lerp(-0.47, 0.48, k) * s; const by = (-0.34 * op * 4 * k * (1 - k) * 0.72 + 0.02) * s - 0.02 * s;
    const ang = -Math.PI / 2 + (k - 0.5) * 1.6 + 0.3 + (hash(i * 7.7) - 0.5) * 0.25; const L = (0.07 + 0.09 * Math.sin(k * Math.PI)) * s * (0.6 + hash(i) * 0.6);
    ctx.lineWidth = (0.0035 + 0.003 * hash(i * 2.2)) * s; ctx.beginPath(); ctx.moveTo(bx, by); ctx.quadraticCurveTo(bx + Math.cos(ang) * L * 0.6, by + Math.sin(ang) * L * 0.6 - 0.02 * s, bx + Math.cos(ang + 0.35) * L, by + Math.sin(ang + 0.35) * L); ctx.stroke(); }
  ctx.lineWidth = 0.012 * s; ctx.strokeStyle = 'rgba(40,20,20,0.6)'; ctx.beginPath(); ctx.moveTo(-0.46 * s, 0.05 * s); ctx.bezierCurveTo(-0.26 * s, (0.2 * op + 0.03) * s, 0.26 * s, (0.2 * op + 0.02) * s, 0.48 * s, 0.0); ctx.stroke();
  for (let i = 0; i <= 14; i++) { const k = i / 14, bx = lerp(-0.4, 0.42, k) * s, by = (0.2 * op * 4 * k * (1 - k) * 0.72 + 0.04) * s; ctx.lineWidth = 0.005 * s; ctx.strokeStyle = 'rgba(30,15,15,0.7)';
    ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + (k - 0.5) * 0.04 * s, by + 0.05 * s); ctx.stroke(); }
  ctx.restore();
}
