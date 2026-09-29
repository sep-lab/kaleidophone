// ============================================================
//  THE OTHER SCENES: phones · café · street · bed
// ============================================================

// ---------------------------------------------------------------
//  PHONES — two phones, both typing to each other, both deleting.
//  Drawn un-mirrored in screen space (a chat UI has a correct side).
// ---------------------------------------------------------------
const KEYS = (() => { const k = []; const rows = [10, 9, 7]; rows.forEach((n, ri) => { for (let i = 0; i < n; i++) k.push([ri, i, n]); }); return k; })();
function scenePhone(who, lt, env, V, side, t) {
  const L = side === 'L';
  const pw = 356, ph = 740, cx = L ? 292 : W - 292, cy = 920;
  const x0 = cx - pw / 2, y0 = cy - ph / 2;
  // the dark room around the phone, the phone's own cold light
  flat(L ? -50 : SEAM - 40, -50, 640, H + 100, '#17181a');
  glow(cx, cy + 40, 560, `rgba(150,180,210,${0.16 + 0.1 * (V.lit == null ? 1 : V.lit)})`);
  // blanket folds under the hand
  for (let i = 0; i < 5; i++) { const y = 1380 + i * 90 + 12 * Math.sin(i * 1.7); stroke([[L ? 20 : SEAM + 30, y], [L ? 520 : W - 20, y - 30 + 20 * HS(i, 5)]], 'rgba(90,92,96,0.5)', LW(0.8)); }
  const s = L ? 1 : -1;                      // his left hand (thumb from the left) / her right hand
  const skin = C.paper, sleeve = who === 'her' ? '#d9d2c2' : '#9fa2a3';
  // palm & wrist behind the phone
  poly(capsulePts(cx - s * 90, cy + 260, cx - s * 220, H + 80, 78, 6), sleeve, C.ink, LW(1));
  poly(ellPts(cx - s * 70, cy + 230, 150, 120, 20, -0.3 * s), skin, C.ink, LW(1));
  // fingers wrapping the far edge
  for (let i = 0; i < 4; i++) {
    const fy = cy + 40 + i * 62, fx = cx + s * (pw / 2 - 4);
    poly(capsulePts(fx - s * 18, fy, fx + s * 26, fy + 8, 21, 5), skin, C.ink, LW(0.9));
  }
  // the phone
  rrect(x0 - 12, y0 - 12, pw + 24, ph + 24, 48, C.ink, C.ink, LW(1));
  const on = V.screen == null ? 1 : V.screen;
  const scr = on > 0.5 ? '#ece7da' : '#060606';
  rrect(x0, y0, pw, ph, 38, scr, null, 0);
  if (on > 0.5) {
    // status + header
    stroke([[x0 + 30, y0 + 26], [x0 + 64, y0 + 26]], C.grey, LW(0.6));
    rect(x0 + pw - 58, y0 + 19, 30, 14, null, C.grey, LW(0.5));
    rect(x0 + 4, y0 + 50, pw - 8, 76, '#dcd5c5', null, 0); stroke([[x0 + 4, y0 + 126], [x0 + pw - 4, y0 + 126]], C.grey, LW(0.5));
    stroke([[x0 + 34, y0 + 72], [x0 + 22, y0 + 88], [x0 + 34, y0 + 104]], C.ink, LW(0.8));
    // the other one's face, tiny, as the avatar
    const ax = x0 + 80, ay = y0 + 88;
    circ(ax, ay, 26, '#cbc3b2', C.ink, LW(0.6), 16);
    ctx.save(); ctx.beginPath(); ctx.arc(ax, ay, 25, 0, TAU); ctx.clip();
    const other = who === 'him' ? 'her' : 'him';
    if (other === 'her') poly([[ax - 20, ay - 4], [ax - 24, ay + 30], [ax + 24, ay + 30], [ax + 20, ay - 4], [ax, ay - 22]], C.ink, null, 0);
    circ(ax, ay + 2, 14, C.paper, C.ink, LW(0.45), 12);
    hairFrontCap(other, ax, ay + 2, 14, 0, C.ink);
    circ(ax - 5, ay + 1, 1.6, C.ink, null, 0, 6); circ(ax + 5, ay + 1, 1.6, C.ink, null, 0, 6);
    ctx.restore();
    stroke([[x0 + 118, y0 + 80], [x0 + 200, y0 + 80]], C.ink, LW(0.9));
    stroke([[x0 + 118, y0 + 100], [x0 + 176, y0 + 100]], C.grey, LW(0.55));
    // an old conversation (scribbles), a "months ago" divider
    const bub = (bx, by, bw, bh, mine, n) => {
      rrect(bx, by, bw, bh, 20, mine ? '#3b3833' : '#fbf8f1', mine ? null : C.ink, LW(0.5));
      for (let j = 0; j < n; j++) { const yy = by + 18 + j * 16; const pts = []; for (let q = 0; q <= 8; q++) pts.push([bx + 16 + q * (bw - 34) / 8, yy + 2.5 * Math.sin(q * 1.9 + j + by)]); stroke(pts, mine ? '#e9e3d6' : '#6d675e', LW(0.45)); }
    };
    bub(x0 + 18, y0 + 150, 190, 54, false, 2);
    bub(x0 + 18, y0 + 214, 128, 38, false, 1);
    bub(x0 + pw - 214, y0 + 268, 196, 54, true, 2);
    bub(x0 + pw - 150, y0 + 332, 132, 38, true, 1);
    stroke([[x0 + pw - 66, y0 + 382], [x0 + pw - 60, y0 + 388], [x0 + pw - 50, y0 + 376]], '#7a8fa0', LW(0.5));
    stroke([[x0 + pw - 56, y0 + 382], [x0 + pw - 50, y0 + 388], [x0 + pw - 40, y0 + 376]], '#7a8fa0', LW(0.5));
    stroke([[x0 + 60, y0 + 424], [x0 + 130, y0 + 424]], C.grey2, LW(0.4)); stroke([[x0 + pw - 130, y0 + 424], [x0 + pw - 60, y0 + 424]], C.grey2, LW(0.4));
    rrect(x0 + pw / 2 - 40, y0 + 414, 80, 20, 10, '#dcd5c5', null, 0);
    // the other one is typing…  (the dots bounce)
    if (V.typing > 0) {
      ctx.save(); ctx.globalAlpha = V.typing;
      const by = y0 + 450; rrect(x0 + 18, by, 96, 50, 24, '#fbf8f1', C.ink, LW(0.55));
      for (let d = 0; d < 3; d++) { const bounce = Math.max(0, Math.sin(t * 9 - d * 0.9)) * 7; circ(x0 + 44 + d * 22, by + 26 - bounce, 6, '#6d675e', null, 0, 8); }
      ctx.restore();
    }
    // input field with what I'm typing (a scribble that grows / shrinks)
    const iy = y0 + ph - 250;
    rrect(x0 + 16, iy, pw - 86, 48, 24, '#fbf8f1', C.ink, LW(0.55));
    circ(x0 + pw - 38, iy + 24, 22, V.typed > 0.01 ? '#3b3833' : '#cbc3b2', null, 0, 14);
    const tl = V.typed || 0;
    if (tl > 0.01) { const pts = []; const n = Math.max(2, Math.round(28 * tl)); for (let q = 0; q <= n; q++) pts.push([x0 + 34 + q * (pw - 140) / 28, iy + 25 + 4 * Math.sin(q * 2.3) + 2 * Math.sin(q * 5.1)]); stroke(pts, C.ink, LW(0.6), 1); }
    if (V.caret) stroke([[x0 + 36 + (pw - 140) * tl, iy + 12], [x0 + 36 + (pw - 140) * tl, iy + 38]], '#4a7aa0', LW(0.5));
    // keyboard
    const ky = y0 + ph - 188, kh = 38;
    rect(x0 + 4, ky - 12, pw - 8, 188, '#d8d1c2', null, 0);
    for (const [ri, i, n] of KEYS) {
      const kw = (pw - 30) / 10, off = (10 - n) * kw / 2;
      const kx = x0 + 15 + off + i * kw, kyy = ky + ri * (kh + 10);
      const kk = V.tap >= 0 && V.tap != null && V.press > 0 ? KEYS[Math.floor(HS(V.tap, 707) * KEYS.length)] : null;
      const pressed = kk && kk[0] === ri && kk[1] === i;
      rrect(kx + 2, kyy, kw - 4, kh, 7, pressed ? '#9a938a' : '#fbf8f1', null, 0);
    }
    rrect(x0 + 80, ky + 3 * (kh + 10), pw - 160, kh, 8, '#fbf8f1', null, 0);
    rrect(x0 + pw - 62, ky + 2 * (kh + 10), 46, kh, 7, V.back ? '#9a938a' : '#cbc3b2', null, 0);
    stroke([[x0 + pw - 50, ky + 2 * (kh + 10) + 19], [x0 + pw - 30, ky + 2 * (kh + 10) + 19]], C.ink, LW(0.5));
  } else {
    // locked: the black glass shows a faint reflection of the face
    if (V.reflect > 0) {
      ctx.save(); ctx.globalAlpha = 0.34 * V.reflect;
      const fx = cx, fy = cy - 60, rr = 120;
      if (who === 'her') poly([[fx - 1.12 * rr, fy - 0.2 * rr], [fx - 1.2 * rr, fy + 1.9 * rr], [fx + 1.2 * rr, fy + 1.9 * rr], [fx + 1.12 * rr, fy - 0.2 * rr], [fx, fy - 1.12 * rr]], '#8a8a8a', null, 0);
      circ(fx, fy, rr, '#9a9a9a', null, 0, 20);
      hairFrontCap(who, fx, fy, rr, 0, '#555');
      face(fx, fy, rr, { eyes: 'down' }, '#333', LW(1.4), 'front', 1);
      ctx.restore();
    }
    ctx.save(); ctx.globalCompositeOperation = 'screen'; ctx.fillStyle = 'rgba(255,255,255,0.05)';
    ctx.beginPath(); ctx.moveTo(x0 + 40, y0); ctx.lineTo(x0 + 140, y0); ctx.lineTo(x0 + 20, y0 + ph); ctx.lineTo(x0 - 80, y0 + ph); ctx.fill(); ctx.restore();
  }
  // the thumb, over the glass
  let tip;
  if (V.tap >= 0 && V.tap != null) { const kk = KEYS[Math.floor(HS(V.tap, 707) * KEYS.length)]; tip = keyPos(side, kk[0], kk[1]); tip = [tip[0], tip[1] + (V.press || 0) * 4]; }
  else if (V.back) tip = backPos(side);
  else tip = V.thumbAway ? [cx - s * 150, y0 + ph + 60] : [cx - s * 20, y0 + ph - 150];
  const tb = [cx - s * 190, cy + 330];
  poly(capsulePts(tb[0], tb[1], tip[0], tip[1], 30, 6), skin, C.ink, LW(1));
  stroke([[tip[0] - s * 10, tip[1] - 14], [tip[0] + s * 8, tip[1] - 20]], 'rgba(23,20,15,0.45)', LW(0.5));
}
function keyPos(side, ri, i) {
  const L = side === 'L', pw = 356, ph = 740, cx = L ? 292 : W - 292, cy = 920, x0 = cx - pw / 2, y0 = cy - ph / 2;
  const n = [10, 9, 7][ri], kw = (pw - 30) / 10, off = (10 - n) * kw / 2;
  return [x0 + 15 + off + i * kw + kw / 2, y0 + ph - 188 + ri * 48 + 19];
}
function backPos(side) { const L = side === 'L', pw = 356, ph = 740, cx = L ? 292 : W - 292, cy = 920, x0 = cx - pw / 2, y0 = cy - ph / 2; return [x0 + pw - 39, y0 + ph - 188 + 2 * 48 + 19]; }

// ---------------------------------------------------------------
//  CAFÉ — one café, torn in half.  They sit back to back at the seam,
//  each across from someone new.  The someone new doesn't fit the seat:
//  the other one's paper silhouette is still in it.
// ---------------------------------------------------------------
const CAFE = { gx0: 26, gy0: 596, gy1: 1296, floor: 1262 };
function sceneCafe(who, lt, env, V, side, t) {
  const lw = LW(1);
  flat(-200, -200, 800, H + 400, '#2e2f31');
  // awning
  const aw = [[-40, 496], [SEAM + 40, 496], [SEAM + 40, 572]];
  for (let i = 0; i <= 10; i++) { const x = SEAM + 40 - i * 58; aw.push([x - 29, 590], [x - 58, 572]); }
  poly(aw, '#3c3a38', C.ink, LW(0.9));
  for (let i = 0; i < 10; i++) stroke([[SEAM + 40 - i * 58 - 29, 500], [SEAM + 40 - i * 58 - 29, 580]], 'rgba(20,18,15,0.5)', LW(0.5));
  // the little cup sign (no words)
  circ(286, 440, 34, '#3c3a38', C.ink, LW(0.8), 16);
  poly([[270, 430], [302, 430], [298, 456], [274, 456]], C.paper, C.ink, LW(0.6));
  stroke([[302, 436], [310, 440], [300, 448]], C.paper, LW(0.6));
  // ---- inside ----
  ctx.save(); ctx.beginPath(); ctx.rect(CAFE.gx0, CAFE.gy0, SEAM + 40 - CAFE.gx0, CAFE.gy1 - CAFE.gy0); ctx.clip();
  flat(CAFE.gx0, CAFE.gy0, 600, 800, C.room);
  flat(CAFE.gx0, CAFE.floor, 600, 100, C.roomDk);
  stroke([[CAFE.gx0, CAFE.floor], [SEAM + 40, CAFE.floor]], C.ink, LW(0.8));
  // wainscot + shelf of cups + a chalkboard of scribbles
  stroke([[CAFE.gx0, 1060], [SEAM + 40, 1060]], C.roomDk, LW(0.8));
  stroke([[70, 790], [250, 790]], C.ink, LW(0.8));
  for (let i = 0; i < 5; i++) { const x = 84 + i * 34; poly([[x, 790], [x + 22, 790], [x + 19, 768], [x + 3, 768]], C.paper, C.ink, LW(0.5)); }
  rect(300, 700, 150, 110, '#2b2d2b', C.ink, LW(0.7));
  for (let j = 0; j < 4; j++) { const pts = []; for (let q = 0; q <= 6; q++) pts.push([316 + q * 18, 724 + j * 22 + 3 * Math.sin(q * 2 + j)]); stroke(pts, '#d8d4c8', LW(0.4)); }
  // pendant lamps
  for (const lx of [150, 420]) {
    stroke([[lx, CAFE.gy0], [lx, 660]], C.ink, LW(0.6));
    poly([[lx - 14, 660], [lx + 14, 660], [lx + 30, 690], [lx - 30, 690]], C.dark, C.ink, LW(0.6));
    glow(lx, 720, 240, 'rgba(255,232,178,0.28)');
  }
  // bodies: him near the seam facing out, the new one at the outer seat facing in
  const r = 50;
  const gm = seated(452, CAFE.floor, r, -1);
  const gd = seated(152, CAFE.floor, 48, 1);
  const Sy = gm.P[1] - RG.torso * r;
  const tableTop = Sy + 0.95 * RG.upper * r;
  chairFor(gd, 'cafe');
  chairFor(gm, 'cafe');
  tableSide(302, tableTop, CAFE.floor, 64, r);
  // cups + steam
  const cupD = [272, tableTop], cupM = [334, tableTop];
  for (const [ux, uy] of [cupD, cupM]) { poly([[ux - 13, uy - 26], [ux + 13, uy - 26], [ux + 10, uy - 2], [ux - 10, uy - 2]], C.paper, C.ink, LW(0.6)); stroke([[ux + 13, uy - 20], [ux + 20, uy - 16], [ux + 12, uy - 8]], C.ink, LW(0.5)); }
  for (let i = 0; i < 2; i++) { const sx = cupM[0] - 5 + i * 10; const pts = []; for (let q = 0; q < 5; q++) pts.push([sx + 5 * Math.sin(t * 3 + q + i), cupM[1] - 34 - q * 12]); stroke(pts, 'rgba(240,236,226,0.8)', LW(0.5)); }
  const flick = V.flicker > 0;
  const ex = who === 'him' ? 'her' : 'him';
  // the ghost: the other one's paper silhouette, still in the seat
  if (!flick && V.ghost > 0) {
    ctx.save(); ctx.globalAlpha = V.ghost;
    const gg = seated(166, CAFE.floor, 48 * 1.1, 1);
    figure({ view: 'side', x: gg.P[0], y: gg.P[1], r: 48 * 1.1, dir: 1, hair: ex, style: 'sil', legs: seatedLegs(gg), head: { dx: 0.05 },
      arms: { near: { to: [gd.P[0] + 118, tableTop - 12] }, far: { to: [gd.P[0] + 104, tableTop - 12] } } });
    ctx.restore();
  }
  // the new one (drawn by a less certain hand) — or, for one drawing on the beat, the one you lost
  const talk = V.talk || 0;
  const dHand = [gd.P[0] + 74 + 18 * Math.sin(talk * 2.1), tableTop - 36 - 30 * Math.abs(Math.sin(talk * 1.3))];
  if (flick) {
    figure({ view: 'side', x: gd.P[0], y: gd.P[1], r: 48, dir: 1, hair: ex, fill: ex === 'her' ? C.paper : C.grey2, legs: seatedLegs(gd),
      head: { eyes: 'open' }, arms: { near: { to: [gd.P[0] + 104, tableTop - 12], pole: [gd.P[0], tableTop + 60] }, far: { to: [gd.P[0] + 96, tableTop - 12], pole: [gd.P[0], tableTop + 60] } } });
  } else {
    figure({ view: 'side', x: gd.P[0], y: gd.P[1], r: 48, dir: 1, hair: who === 'him' ? 'bob' : 'beanie', style: 'sketch', fill: '#b9b2a4', legs: seatedLegs(gd),
      head: { eyes: 'open', mouth: fract(talk * 0.9) < 0.5 ? 'o' : 'dash', dy: 0.03 * Math.sin(talk * 3) },
      arms: { near: { to: dHand, pole: [gd.P[0], tableTop + 80], hand: 'open' }, far: { to: [gd.P[0] + 96, tableTop - 12], pole: [gd.P[0], tableTop + 60] } } });
  }
  // him / her, stirring the cup, eyes down — wide on the flicker
  const turn = V.turnBack || 0;
  const Jm = figure({ view: 'side', x: gm.P[0], y: gm.P[1], r, dir: -1, hair: who, fill: who === 'her' ? C.paper : C.grey2, legs: seatedLegs(gm),
    head: { eyes: flick ? 'wide' : (V.eyesUp ? 'open' : 'down'), up: flick ? 1 : 0 },
    arms: { near: { to: [cupM[0] + 16, cupM[1] - 14], pole: [gm.P[0], tableTop + 70] }, far: { to: [cupM[0] + 34, tableTop - 12], pole: [gm.P[0], tableTop + 60] } } });
  if (turn > 0.5) {   // a glance back over the shoulder, toward the seam
    circ(Jm.H[0], Jm.H[1], r, C.paper, C.ink, lw, 18);
    headSide(who, Jm.H[0], Jm.H[1], r, 1, Jm.S[1], C.ink, C.ink, lw, false);
    face(Jm.H[0], Jm.H[1], r, { eyes: 'open' }, C.ink, lw, 'side', 1);
  }
  contact('hand↔cup', Jm.hands.near, [cupM[0] + 16, cupM[1] - 14], 2);
  // glass: tint, reflections, drops
  ctx.fillStyle = 'rgba(22,26,30,0.1)'; ctx.fillRect(CAFE.gx0, CAFE.gy0, 600, 800);
  ctx.globalCompositeOperation = 'screen'; ctx.fillStyle = 'rgba(255,255,255,0.05)';
  ctx.beginPath(); ctx.moveTo(80, CAFE.gy0); ctx.lineTo(180, CAFE.gy0); ctx.lineTo(40, CAFE.gy1); ctx.lineTo(-60, CAFE.gy1); ctx.fill();
  ctx.globalCompositeOperation = 'source-over';
  glassDrops(CAFE.gx0, CAFE.gy0, SEAM, CAFE.gy1, rainClock(t), 12, who === 'her' ? 21 : 3);
  ctx.restore();
  // storefront frame
  const fc = '#262422';
  rect(CAFE.gx0 - 16, CAFE.gy0 - 12, SEAM + 60 - CAFE.gx0, 14, fc, C.ink, LW(0.8));
  rect(CAFE.gx0 - 16, CAFE.gy0, 16, CAFE.gy1 - CAFE.gy0, fc, C.ink, LW(0.8));
  rect(CAFE.gx0 - 20, CAFE.gy1, SEAM + 60 - CAFE.gx0, 34, fc, C.ink, LW(0.8));
  // pavement: wet, the café light spilling on it
  flat(-200, 1330, 800, 700, C.street);
  stroke([[-200, 1330], [600, 1330]], C.ink, LW(0.8)); stroke([[-200, 1460], [600, 1460]], C.ink, LW(0.9));
  glow(300, 1360, 300, 'rgba(230,200,140,0.18)');
  for (let i = 0; i < 4; i++) { const px = 80 + i * 130 + 30 * HS(i, 81), py = 1395 + 30 * HS(i, 82); ell(px, py, 50 + 20 * HS(i, 83), 9, 'rgba(120,110,90,0.35)', null, 0, 14); }
  noDraw(() => rain(rainClock(t), V.rainN == null ? 260 : V.rainN, 0.12, 0.42));
  return Jm;
}

// ---------------------------------------------------------------
//  STREET — one street.  They walk toward each other under umbrellas,
//  pass in the dark between two lamps, and don't see.  Continuous scene
//  (no mirror): drawn in screen space across both pieces.
// ---------------------------------------------------------------
const STREET = { walkY: 1394, walkY2: 1352 };
function sceneStreet(who, lt, env, V, side, t) {
  flat(-200, -200, W + 400, H + 400, '#1c1d20');
  // far buildings with warm windows
  const bl = [[-40, 520, 250], [200, 610, 190], [380, 470, 160], [530, 560, 180], [700, 500, 210], [900, 590, 240]];
  for (const [bx, by, bw] of bl) {
    rect(bx, by, bw, 1300 - by, '#141517', C.ink, LW(0.6));
    for (let wy = by + 40; wy < 1180; wy += 92) for (let wx = bx + 24; wx < bx + bw - 40; wx += 58) {
      const lit = HS(wx | 0, wy | 0) > 0.62;
      rect(wx, wy, 30, 44, lit ? '#b7a57c' : '#232426', null, 0);
    }
  }
  // the pavement, the curb, the road
  flat(-200, 1300, W + 400, 800, '#2a2b2c');
  stroke([[-200, 1300], [W + 200, 1300]], C.ink, LW(0.8));
  flat(-200, 1450, W + 400, 700, '#1f2021'); stroke([[-200, 1450], [W + 200, 1450]], C.ink, LW(1));
  // two lamps, the middle left dark
  for (const lx of [230, W - 230]) {
    glow(lx, 1000, 520, 'rgba(255,226,160,0.16)');
    const cone = ctx.createLinearGradient(0, 700, 0, 1400); cone.addColorStop(0, 'rgba(255,230,170,0.24)'); cone.addColorStop(1, 'rgba(255,230,170,0.02)');
    ctx.fillStyle = cone; ctx.beginPath(); ctx.moveTo(lx - 22, 712); ctx.lineTo(lx + 22, 712); ctx.lineTo(lx + 210, 1300); ctx.lineTo(lx - 210, 1300); ctx.fill();
    stroke([[lx, 1300], [lx, 700]], C.ink, LW(1.3));
    poly([[lx - 26, 712], [lx + 26, 712], [lx + 16, 680], [lx - 16, 680]], '#2a2825', C.ink, LW(0.8));
    ell(lx, 712, 22, 5, '#fff1cc', null, 0, 12);
    // its reflection in the road
    const rg = ctx.createLinearGradient(0, 1450, 0, 1900); rg.addColorStop(0, 'rgba(255,220,150,0.28)'); rg.addColorStop(1, 'rgba(255,220,150,0)');
    ctx.fillStyle = rg; ctx.fillRect(lx - 24, 1452, 48, 450);
  }
  // puddles
  for (let i = 0; i < 5; i++) { const px = 90 + i * 220 + 40 * HS(i, 91), py = 1380 + 40 * HS(i, 92); ell(px, py, 60 + 30 * HS(i, 93), 10, 'rgba(90,86,74,0.45)', null, 0, 14); }
  // the walkers
  const draw = (P) => {
    if (!P) return;
    const r = P.r, dir = P.dir;
    const Py = standPelvisY(P.floor, r, 0.975) - P.bob;
    const lg = walkLegs(P.xAt, P.tau, dir, P.floor, r, 112);
    const sw = Math.sin(P.tau * Math.PI) * P.walking;
    const fd = P.faceDir || dir;
    const f = {
      view: 'side', x: P.x, y: Py, r, dir: P.faceDir || dir, hair: P.who, fill: P.who === 'her' ? C.paper : C.grey2, lean: 0.06 * P.walking,
      legs: { near: { to: lg.A, pole: [P.x + (P.faceDir || dir) * 4 * r, Py] }, far: { to: lg.B, pole: [P.x + (P.faceDir || dir) * 4 * r, Py] } },
      head: { eyes: P.eyes || 'down' },
      arms: {
        far: { to: [P.x - fd * 0.5 * r * sw, Py + 0.2 * r], pole: [P.x - fd * 2 * r, Py] },
        near: { to: [P.x + fd * 1.22 * r, Py - 2.2 * r], pole: [P.x - fd * 0.6 * r, Py - 0.2 * r], item: { kind: 'umbrella', tilt: P.umbTilt == null ? -fd * 0.1 : P.umbTilt, len: 2.75, R: 2.3 } }
      }
    };
    const Jw = figure(f);
    contact('foot↔pavement', Jw.ankles.near, [Jw.ankles.near[0], P.floor - LW(1) / 2], lg.A[2] ? 1.5 : 999);
  };
  // far one first
  draw(V.far); draw(V.near);
  noDraw(() => rain(rainClock(t), V.rainN == null ? 320 : V.rainN, 0.08, 0.45, { x0: -200, x1: W + 200 }));
}

// ---------------------------------------------------------------
//  BED — one bed, torn in half.  From above.  Each on their side,
//  facing the seam.  A hand slides across the sheet to the torn edge.
// ---------------------------------------------------------------
function sceneBed(who, lt, env, V, side, t) {
  // floor
  flat(-200, -200, 800, H + 400, '#221e1b');
  for (let i = 0; i < 9; i++) stroke([[i * 68 - 10, -20], [i * 68 - 10, H + 20]], 'rgba(0,0,0,0.35)', LW(0.5));
  // bed: headboard, sheet, pillow
  rect(118, 372, SEAM + 60 - 118, 80, '#3a302a', C.ink, LW(1));
  rect(132, 452, SEAM + 60 - 132, 1130, '#e3dccb', C.ink, LW(1));
  rrect(176, 488, 300, 150, 40, C.paper, C.ink, LW(0.9));
  stroke([[230, 560], [300, 548], [380, 566]], 'rgba(23,20,15,0.35)', LW(0.6));
  // her hair spills over the pillow
  const hx = 330, hy = 570, r = 60;
  if (who === 'her') poly([[hx - 40, hy - 70], [hx - 150, hy - 40], [hx - 170, hy + 40], [hx - 120, hy + 110], [hx - 20, hy + 70], [hx + 10, hy - 40]], C.ink, null, 0);
  // the blanket, pulled up to the shoulder; one soft line is the body under it
  const reach = V.reach || 0;
  poly(capsulePts(hx - 20, hy + 70, hx - 6, hy + 200, 66), who === 'her' ? C.paper : C.grey2, C.ink, LW(1));
  poly([[132, 690], [SEAM + 60, 660], [SEAM + 60, 1582], [132, 1582]], '#8f8a80', C.ink, LW(1));
  poly([[132, 690], [SEAM + 60, 660], [SEAM + 60, 712], [132, 742]], '#aaa498', C.ink, LW(0.8));
  // the body under the blanket: a soft raised shape (shoulder → hip → knees bent toward the seam → feet)
  poly([[196, 742], [300, 742], [330, 880], [352, 1010], [400, 1090], [470, 1150], [512, 1226], [496, 1300], [430, 1318], [378, 1352], [372, 1440], [334, 1490], [262, 1470], [248, 1380], [236, 1250], [214, 1080], [196, 920]], '#9b968b', null, 0);
  stroke([[300, 742], [330, 880], [352, 1010], [400, 1090], [470, 1150], [512, 1226], [496, 1300]], 'rgba(255,250,240,0.35)', LW(0.7));
  stroke([[430, 1318], [378, 1352], [372, 1440], [334, 1490]], 'rgba(23,20,15,0.35)', LW(0.6));
  stroke([[290, 1120], [330, 1170]], 'rgba(23,20,15,0.25)', LW(0.5));
  // the head, from above: a side view lying down, facing the seam
  headSide(who, hx, hy, r, 1, hy + 90, C.ink, C.ink, LW(1), false);
  face(hx, hy, r, { eyes: V.eyes || 'open' }, C.ink, LW(1), 'side', 1);
  // the top arm over the blanket, reaching for the torn edge
  const sh = [hx + 10, hy + 120];
  const tgt = [lerp(400, SEAM - 16, reach), lerp(760, 730, reach)];
  const Ja = ik(sh[0], sh[1], tgt[0], tgt[1], RG.upper * r, RG.fore * r, sh[0] + 20, sh[1] + 160);
  stroke([sh, Ja.j, Ja.e], C.ink, LW(1));
  hand(Ja.e, 'open', [1, -0.1], r, C.ink, LW(1), false);
  // the phone in the other hand, lighting the face
  if (V.phone > 0) {
    ctx.save(); ctx.globalAlpha = V.phone;
    rrect(hx + 80, hy + 20, 44, 80, 10, '#dfe8ef', C.ink, LW(0.7));
    ctx.restore();
    glow(hx + 70, hy + 40, 280, `rgba(190,215,235,${0.4 * V.phone})`, 'rgba(190,215,235,0)', 'screen');
  }
  // window light across the bed, with the rain running down it
  const la = V.light == null ? 1 : V.light;
  if (la > 0) {
    ctx.save();
    ctx.beginPath(); ctx.moveTo(120, 980); ctx.lineTo(SEAM + 60, 860); ctx.lineTo(SEAM + 60, 1300); ctx.lineTo(120, 1440); ctx.closePath(); ctx.clip();
    ctx.fillStyle = `rgba(210,220,230,${0.14 * la})`; ctx.fillRect(100, 800, 600, 700);
    ctx.strokeStyle = `rgba(20,24,30,${0.22 * la})`; ctx.lineWidth = 5; ctx.lineCap = 'round';
    for (let i = 0; i < 16; i++) { const x = 140 + i * 29, sp = 30 + 50 * HS(i, 301), y = ((HS(i, 302) * 700 + t * sp) % 700) + 820; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 3 * Math.sin(y * 0.03), y + 40 + 60 * HS(i, 303)); ctx.stroke(); }
    ctx.restore();
  }
  contact('hand→edge', Ja.e, [SEAM - 16, 730], reach > 0.99 ? 2 : 9999);
}
