'use strict';
/* ============================================================================
   kaleidophone canvas lib -- rig.js
   RIG v2 from SAME AS YOU: anchor-driven figures with two-bone IK limbs, and
   furniture built FROM the body so the two can never disagree.

   ( - )'s chairs floated because the chair and the body were placed
   independently. Here a seated body is built from the floor up (ankle on the
   floor -> vertical shin -> horizontal thigh -> pill bottom exactly on the seat)
   and the chair is built from that body (seat top = pill bottom, seat front at
   the knee, back post touching the torso, legs to the floor). A lean at a
   window is solved from the sill up; a walk plants its feet on the beat. Every
   contact is logged (ink.js contact()), and ?qa=1 draws them all
   (docs/TECHNIQUES.md #33-#35).

   API
     figure(f)                         draw a figure; returns joints { P, S, H, hands, elbows, knees, ankles }
       f = { view: 'side'|'front', x, y (pelvis), r (head radius), dir: 1|-1, lean,
             head: { dx, dy, tilt, look, eyes: open|closed|down|wide, mouth: dash|o, up },
             hair: him|her|bob|beanie, style: ink|sketch|sil, fill, noBody, noHead,
             legs: { near|far|L|R: { to:[x,y], pole:[x,y] } | { joint, end } },
             arms: { near|far|L|R: { to, pole, hand: fist|open|point|palm, front, item } } }
     seated(x, floorY, r, dir)         seated geometry from the floor up -> g
     seatedLegs(g)                     legs for figure() from g
     chairFor(g, 'cafe'|'plain')       a chair built from the seated body (logs its contacts)
     tableSide(cx, topY, floorY, halfW, r)
     standPelvisY(floorY, r)           pelvis height for a standing figure
     walkLegs(xAt, tau, dir, floorY, r, stride)   planted-feet walk, one step per beat
     ik(ax, ay, tx, ty, l1, l2, px, py)            two-bone IK, joint on the pole's side

   Needs: core.js, live.js, ink.js.
   ============================================================================ */
const RG = { neck: 1.28, torso: 2.0, tr: 0.74, thigh: 1.42, shin: 1.42, foot: 0.46, upper: 1.25, fore: 1.2, hand: 0.26, shW: 0.56, hipW: 0.3 };

function ik(ax, ay, tx, ty, l1, l2, px, py) {
  // two-bone IK; the joint lands on the side of the pole point (px,py)
  let dx = tx - ax, dy = ty - ay, d = Math.hypot(dx, dy) || 1e-6;
  const maxd = (l1 + l2) * 0.9995, mind = Math.abs(l1 - l2) + 1e-3;
  let ex = tx, ey = ty, reach = true;
  if (d > maxd) { ex = ax + dx / d * maxd; ey = ay + dy / d * maxd; d = maxd; reach = false; }
  const dd = Math.max(d, mind);
  const b = Math.atan2(ey - ay, ex - ax);
  const A = Math.acos(clamp((l1 * l1 + dd * dd - l2 * l2) / (2 * l1 * dd), -1, 1));
  const j1 = [ax + Math.cos(b + A) * l1, ay + Math.sin(b + A) * l1];
  const j2 = [ax + Math.cos(b - A) * l1, ay + Math.sin(b - A) * l1];
  const j = Math.hypot(j1[0] - px, j1[1] - py) <= Math.hypot(j2[0] - px, j2[1] - py) ? j1 : j2;
  return { j, e: [ex, ey], reach };
}

// ---- hair & faces --------------------------------------------------------
function hairFrontCap(kind, x, hy, r, look, col) {
  const lk = look * 0.12 * r;
  if (kind === 'him') {
    const cap = arcPts(x, hy, 1.04 * r, rad(-195), rad(15), 12);
    cap.push([x + 0.86 * r, hy - 0.05 * r], [x + 0.38 * r + lk, hy - 0.52 * r], [x - 0.1 * r + lk, hy - 0.42 * r], [x - 0.4 * r + lk, hy - 0.55 * r], [x - 0.86 * r, hy - 0.05 * r]);
    poly(cap, col, null, 0);
  } else if (kind === 'her') {
    const cap = arcPts(x, hy, 1.05 * r, rad(-192), rad(12), 12);
    cap.push([x + 0.95 * r, hy - 0.1 * r], [x + 0.62 * r + lk, hy - 0.38 * r], [x + 0.18 * r + lk, hy - 0.6 * r], [x + 0.02 * r + lk, hy - 0.72 * r],
      [x - 0.2 * r + lk, hy - 0.58 * r], [x - 0.62 * r + lk, hy - 0.4 * r], [x - 0.95 * r, hy - 0.1 * r]);
    poly(cap, col, null, 0);
    // strands framing the face
    poly([[x - 1.05 * r, hy - 0.25 * r], [x - 0.78 * r, hy - 0.12 * r], [x - 0.8 * r, hy + 0.85 * r], [x - 1.1 * r, hy + 1.15 * r]], col, null, 0);
    poly([[x + 1.05 * r, hy - 0.25 * r], [x + 0.78 * r, hy - 0.12 * r], [x + 0.8 * r, hy + 0.85 * r], [x + 1.1 * r, hy + 1.15 * r]], col, null, 0);
  } else if (kind === 'bob') {
    const cap = arcPts(x, hy, 1.06 * r, rad(-195), rad(15), 12);
    cap.push([x + 0.98 * r, hy - 0.22 * r], [x - 0.98 * r, hy - 0.22 * r]);
    poly(cap, col, null, 0);
    poly([[x - 1.1 * r, hy - 0.25 * r], [x - 0.8 * r, hy - 0.2 * r], [x - 0.8 * r, hy + 0.72 * r], [x - 1.12 * r, hy + 0.72 * r]], col, null, 0);
    poly([[x + 1.1 * r, hy - 0.25 * r], [x + 0.8 * r, hy - 0.2 * r], [x + 0.8 * r, hy + 0.72 * r], [x + 1.12 * r, hy + 0.72 * r]], col, null, 0);
  } else if (kind === 'beanie') {
    const cap = arcPts(x, hy - 0.05 * r, 1.1 * r, rad(-190), rad(10), 12); cap.push([x + 1.08 * r, hy - 0.3 * r], [x - 1.08 * r, hy - 0.3 * r]);
    poly(cap, col, C.sketch, LW(0.5));
    rect(x - 1.14 * r, hy - 0.44 * r, 2.28 * r, 0.24 * r, col, C.sketch, LW(0.5));
    circ(x, hy - 1.22 * r, 0.24 * r, col, C.sketch, LW(0.5), 10);
  }
}
function hairBack(kind, x, hy, r, col, view, dir) {
  if (view === 'front') {
    if (kind === 'her') {
      const p = arcPts(x, hy, 1.12 * r, rad(-172), rad(-8), 10);
      p.push([x + 1.14 * r, hy + 0.3 * r], [x + 1.24 * r, hy + 1.3 * r], [x + 1.16 * r, hy + 2.05 * r], [x - 1.16 * r, hy + 2.05 * r], [x - 1.24 * r, hy + 1.3 * r], [x - 1.14 * r, hy + 0.3 * r]);
      poly(p, col, null, 0);
    } else if (kind === 'bob') {
      const p = arcPts(x, hy, 1.12 * r, rad(-172), rad(-8), 10); p.push([x + 1.14 * r, hy + 0.78 * r], [x - 1.14 * r, hy + 0.78 * r]);
      poly(p, col, null, 0);
    }
  }
}
function face(x, hy, r, hd, inkC, lw, view, dir) {
  const eyes = hd.eyes || 'open', mouth = hd.mouth || 'dash', look = hd.look || 0, up = hd.up || 0;
  if (view === 'side') {
    const ex = x + dir * 0.42 * r, ey = hy - 0.08 * r - up * 0.08 * r;
    if (eyes === 'closed') stroke([[ex - 0.13 * r, ey], [ex + 0.13 * r, ey]], inkC, lw * 0.8);
    else circ(ex, ey + (eyes === 'down' ? 0.1 * r : 0), (eyes === 'wide' ? 0.14 : 0.1) * r, inkC, null, 0, 8);
    if (mouth === 'o') circ(x + dir * 0.62 * r, hy + 0.45 * r, 0.1 * r, null, inkC, lw * 0.7, 8);
    else stroke([[x + dir * 0.35 * r, hy + 0.45 * r], [x + dir * 0.7 * r, hy + 0.45 * r]], inkC, lw * 0.8);
    return;
  }
  const ox = look * 0.2 * r, ey = hy - 0.05 * r + (eyes === 'down' ? 0.13 * r : 0) - up * 0.08 * r;
  for (const s of [-1, 1]) {
    const ex = x + s * 0.33 * r + ox;
    if (eyes === 'closed') stroke([[ex - 0.13 * r, ey + 0.02 * r], [ex + 0.13 * r, ey + 0.02 * r]], inkC, lw * 0.8);
    else circ(ex, ey, (eyes === 'wide' ? 0.15 : 0.1) * r, inkC, null, 0, 8);
  }
  const my = hy + 0.45 * r;
  if (mouth === 'o') circ(x + ox * 1.1, my, 0.11 * r, null, inkC, lw * 0.7, 8);
  else if (mouth === 'sad') stroke([[x - 0.2 * r + ox, my + 0.05 * r], [x + ox, my - 0.02 * r], [x + 0.2 * r + ox, my + 0.05 * r]], inkC, lw * 0.8);
  else stroke([[x - 0.21 * r + ox * 1.1, my], [x + 0.21 * r + ox * 1.1, my]], inkC, lw * 0.8);
}
function headSide(kind, x, hy, r, dir, shY, col, inkC, lw, sil) {
  if (kind === 'her') {           // long hair down the back (drawn under the head)
    const a0 = dir > 0 ? rad(-80) : rad(-100);
    const p = arcPts(x, hy, 1.08 * r, a0, a0 - Math.PI * dir, 9);
    p.push([x - dir * 1.05 * r, shY + 1.0 * r], [x - dir * 0.05 * r, shY + 1.0 * r], [x + dir * 0.05 * r, shY - 0.1 * r]);
    poly(p, col, null, 0);
  }
  circ(x, hy, r, sil ? C.paper : C.paper, sil ? null : inkC, lw, 18);
  if (sil) return;
  if (kind === 'him' || kind === 'her' || kind === 'bob') {
    const a0 = dir > 0 ? rad(-205) : rad(25), a1 = dir > 0 ? rad(-35) : rad(-145);
    const cap = arcPts(x, hy, 1.04 * r, a0, a1, 10);
    if (kind === 'him') cap.push([x - dir * 0.12 * r, hy - 0.38 * r], [x - dir * 0.78 * r, hy + 0.22 * r]);
    else if (kind === 'her') cap.push([x + dir * 0.5 * r, hy - 0.5 * r], [x - dir * 0.3 * r, hy - 0.25 * r], [x - dir * 0.95 * r, hy + 0.35 * r]);
    else cap.push([x + dir * 0.55 * r, hy - 0.28 * r], [x - dir * 0.2 * r, hy - 0.2 * r], [x - dir * 1.02 * r, hy + 0.7 * r], [x - dir * 0.6 * r, hy + 0.78 * r]);
    poly(cap, col, null, 0);
  } else if (kind === 'beanie') {
    const cap = arcPts(x, hy - 0.05 * r, 1.1 * r, rad(-190), rad(10), 12); cap.push([x + 1.08 * r, hy - 0.3 * r], [x - 1.08 * r, hy - 0.3 * r]);
    poly(cap, col, C.sketch, LW(0.5));
    rect(x - 1.14 * r, hy - 0.44 * r, 2.28 * r, 0.24 * r, col, C.sketch, LW(0.5));
    circ(x - dir * 0.2 * r, hy - 1.22 * r, 0.22 * r, col, C.sketch, LW(0.5), 10);
  }
}

// ---- hands ----------------------------------------------------------------
function hand(p, kind, dirv, r, inkC, lw, sil, fill) {
  const hr = RG.hand * r;
  if (sil) { circ(p[0], p[1], hr * 1.4, C.paper, null, 0, 10); return; }
  if (kind === 'palm') {             // open palm pressed flat on the glass, fingers spread
    const w = 0.66 * r, h = 0.56 * r, cx = p[0], cy = p[1];
    const fl = [[-0.23, 0.44, -0.2], [-0.08, 0.52, -0.06], [0.07, 0.5, 0.06], [0.21, 0.4, 0.2]];
    for (const [ox, L, a] of fl) { const bx = cx + ox * r, by = cy - h * 0.32; poly(capsulePts(bx, by, bx + Math.sin(a) * L * r, by - Math.cos(a) * L * r, 0.085 * r, 4), C.paper, inkC, lw * 0.7); }
    poly(capsulePts(cx - w * 0.42, cy + h * 0.1, cx - w * 0.78, cy - h * 0.28, 0.1 * r, 4), C.paper, inkC, lw * 0.7);
    poly(rrPts(cx - w / 2, cy - h / 2, w, h, 0.24 * r), C.paper, inkC, lw * 0.85);
    stroke([[cx - w * 0.2, cy + h * 0.05], [cx + w * 0.18, cy - h * 0.08]], 'rgba(23,20,15,0.35)', lw * 0.45);
    return;
  }
  circ(p[0], p[1], hr, fill || C.paper, inkC, lw * 0.9, 10);
  if (kind === 'open' && dirv) {
    const a = Math.atan2(dirv[1], dirv[0]);
    for (let k = -1; k <= 1; k++) { const b = a + k * 0.5; stroke([[p[0] + Math.cos(b) * hr * 0.9, p[1] + Math.sin(b) * hr * 0.9], [p[0] + Math.cos(b) * hr * 1.9, p[1] + Math.sin(b) * hr * 1.9]], inkC, lw * 0.7); }
  }
}

// ---- the figure -----------------------------------------------------------
// f = { view:'side'|'front', x,y = pelvis P, r, dir, lean, head:{dx,dy,tilt,look,eyes,mouth,up},
//       hair, style:'ink'|'sketch'|'sil', fill, noBody, legs:{near|far|L|R: {to,pole}|{joint,end}},
//       arms:{near|far|L|R: {to,pole,hand,front,finger}}, feet:true }
function figure(f) {
  const r = f.r, view = f.view || 'side', dir = f.dir || 1, lean = f.lean || 0;
  const style = f.style || 'ink', sil = style === 'sil', sk = style === 'sketch';
  const inkC = sil ? C.paper : sk ? C.sketch : C.ink;
  const lw = LW(f.lwK || 1) * (sil ? 2.5 : 1);
  const body = sil ? C.paper : (f.fill || C.grey2);
  const hairC = sil ? C.paper : (f.hair === 'bob' ? C.bob : f.hair === 'beanie' ? C.beanie : C.ink);
  const P = [f.x, f.y];
  const ax = view === 'side' ? Math.sin(lean) * dir : Math.sin(lean), ay = -Math.cos(lean);
  const Sh = [P[0] + ax * RG.torso * r, P[1] + ay * RG.torso * r];
  const hd = f.head || {};
  const Hc = [Sh[0] + ax * RG.neck * r + (hd.dx || 0) * r, Sh[1] + ay * RG.neck * r + (hd.dy || 0) * r];
  const bottom = [P[0] - ax * RG.tr * r, P[1] - ay * RG.tr * r];            // bottom of the pill
  const J_ = { P, S: Sh, H: Hc, r, bottom, hands: {}, elbows: {}, knees: {}, ankles: {} };
  const prevSk = SKETCH; if (sk) SKETCH = 1;

  function leg(key, rootX, defPole) {
    const L = f.legs && f.legs[key]; if (!L) return;
    const root = [rootX, bottom[1] - lw / 2 * (sil ? 0.4 : 1)];
    let j, e;
    if (L.joint) { j = L.joint; e = L.end; }
    else { const s = ik(root[0], root[1], L.to[0], L.to[1], RG.thigh * r, RG.shin * r, ...(L.pole || defPole)); j = s.j; e = s.e; }
    stroke([root, j, e], inkC, lw);
    if (f.feet !== false && !sil) {
      const fd = L.footDir != null ? L.footDir : (view === 'side' ? dir : (key === 'L' ? -0.35 : 0.35));
      stroke([e, [e[0] + fd * RG.foot * r, e[1]]], inkC, lw);
    }
    J_.knees[key] = j; J_.ankles[key] = e;
  }
  function arm(key, root, defPole) {
    const A = f.arms && f.arms[key]; if (!A) return;
    let target = A.to, fingerEnd = null;
    if (A.hand === 'point') {                 // the fingertip is the target; the hand sits behind it
      const v = [target[0] - root[0], target[1] - root[1]], L = Math.hypot(v[0], v[1]) || 1;
      const fl = 0.42 * r; fingerEnd = target; target = [target[0] - v[0] / L * fl, target[1] - v[1] / L * fl];
    }
    let j, e;
    if (A.joint) { j = A.joint; e = A.end; }
    else { const s = ik(root[0], root[1], target[0], target[1], RG.upper * r, RG.fore * r, ...(A.pole || defPole)); j = s.j; e = s.e; }
    stroke([root, j, e], inkC, lw);
    if (fingerEnd) { stroke([e, [lerp(e[0], fingerEnd[0], 1.0), lerp(e[1], fingerEnd[1], 1.0)]], inkC, lw * 0.85); }
    hand(e, A.hand === 'point' ? 'fist' : (A.hand || 'fist'), [e[0] - j[0], e[1] - j[1]], r, inkC, lw, sil, f.handFill);
    J_.hands[key] = fingerEnd || e; J_.elbows[key] = j;
    if (A.item) item(A.item, e, j, r, inkC, lw, sil);
  }

  if (view === 'side') {
    const shN = [Sh[0] + dir * 0.06 * r, Sh[1] + 0.14 * r], shF = [Sh[0] - dir * 0.06 * r, Sh[1] + 0.12 * r];
    arm('far', shF, [shF[0] - dir * 2 * r, shF[1] + 2 * r]);
    leg('far', P[0] - dir * 0.08 * r, [P[0] + dir * 4 * r, P[1]]);
    if (!f.noBody) poly(capsulePts(Sh[0], Sh[1] + 0.1 * r, P[0], P[1], RG.tr * r), body, sil ? null : inkC, lw);
    leg('near', P[0] + dir * 0.04 * r, [P[0] + dir * 4 * r, P[1]]);
    if (!f.noHead) {
      if (!sil) headSide(f.hair, Hc[0], Hc[1], r, dir, Sh[1], hairC, inkC, lw, false);
      else { headSide(f.hair === 'her' ? 'her' : null, Hc[0], Hc[1], r * 1.06, dir, Sh[1], C.paper, inkC, lw, true); }
      if (!sil) face(Hc[0], Hc[1], r, hd, inkC, lw, 'side', dir);
    }
    arm('near', shN, [shN[0] - dir * 2 * r, shN[1] + 2 * r]);
  } else {
    // front view
    if (f.hair && !f.noHead) hairBack(f.hair, Hc[0], Hc[1], r * (sil ? 1.06 : 1), hairC, 'front');
    const ca = Math.cos(lean), sa = Math.sin(lean);
    const rot = (dx, dy) => [dx * ca - dy * sa, dx * sa + dy * ca];
    const hl = rot(-RG.hipW * r, 0), hr_ = rot(RG.hipW * r, 0);
    leg('L', bottom[0] + hl[0], [bottom[0] - 4 * r, bottom[1] + 1 * r]);
    leg('R', bottom[0] + hr_[0], [bottom[0] + 4 * r, bottom[1] + 1 * r]);
    if (!f.noBody) poly(capsulePts(Sh[0], Sh[1] + 0.05 * r, P[0], P[1], RG.tr * r * 1.12), body, sil ? null : inkC, lw);
    const oL = rot(-RG.shW * r, 0.12 * r), oR = rot(RG.shW * r, 0.12 * r);
    const shL = [Sh[0] + oL[0], Sh[1] + oL[1]], shR = [Sh[0] + oR[0], Sh[1] + oR[1]];
    const aL = f.arms && f.arms.L, aR = f.arms && f.arms.R;
    if (aL && !aL.front) arm('L', shL, [shL[0] - 2 * r, shL[1] + 2 * r]);
    if (aR && !aR.front) arm('R', shR, [shR[0] + 2 * r, shR[1] + 2 * r]);
    if (!f.noHead) {
      ctx.save();
      if (hd.tilt) { ctx.translate(Hc[0], Hc[1]); ctx.rotate(hd.tilt); ctx.translate(-Hc[0], -Hc[1]); }
      circ(Hc[0], Hc[1], r * (sil ? 1.06 : 1), sil ? C.paper : C.paper, sil ? null : inkC, lw, 18);
      if (!sil) {
        if (f.hair) hairFrontCap(f.hair, Hc[0], Hc[1], r, hd.look || 0, hairC);
        face(Hc[0], Hc[1], r, hd, inkC, lw, 'front', 1);
        if (f.hair === 'beanie') for (let i = 0; i < 6; i++) { const a = rad(35 + i * 22); circ(Hc[0] + Math.cos(a) * 0.72 * r, Hc[1] + Math.sin(a) * 0.72 * r, 0.035 * r, C.sketch, null, 0, 5); }
      }
      ctx.restore();
    }
    if (aL && aL.front) arm('L', shL, aL.pole || [shL[0] - 2 * r, shL[1] + 2 * r]);
    if (aR && aR.front) arm('R', shR, aR.pole || [shR[0] + 2 * r, shR[1] + 2 * r]);
  }
  SKETCH = prevSk;
  return J_;
}

// ---- items held in a hand ------------------------------------------------------
function item(it, hp, elbow, r, inkC, lw, sil) {
  if (it.kind === 'umbrella') {
    // shaft goes up from the hand, tilted by it.tilt (radians, + = toward +x); dome on top
    const L = (it.len || 3.1) * r, a = it.tilt || 0;
    const top = [hp[0] + Math.sin(a) * L, hp[1] - Math.cos(a) * L];
    stroke([[hp[0] - Math.sin(a) * 0.35 * r + 0.18 * r, hp[1] + Math.cos(a) * 0.35 * r], [hp[0] - Math.sin(a) * 0.45 * r, hp[1] + Math.cos(a) * 0.3 * r], hp, top], sil ? C.paper : C.ink, lw);
    const R = (it.R || 2.3) * r, n = 7, pts = [];
    const ca = Math.cos(a), sa = Math.sin(a);
    const T = (dx, dy) => [top[0] + dx * ca - dy * sa, top[1] + dx * sa + dy * ca];
    for (let i = 0; i <= 16; i++) { const th = Math.PI + i / 16 * Math.PI; pts.push(T(Math.cos(th) * R, Math.sin(th) * R * 0.62 + 0.28 * R)); }
    for (let i = n; i >= 0; i--) { const x0 = -R + 2 * R * i / n; const xm = x0 - R / n; pts.push(T(x0, 0.28 * R)); if (i > 0) pts.push(T(xm, 0.28 * R - 0.12 * R)); }
    poly(pts, sil ? C.paper : (it.fill || C.ink), sil ? null : C.ink, lw * 0.9);
    stroke([T(0, -0.34 * R), T(0, -0.46 * R)], sil ? C.paper : C.ink, lw);
    return { top, R };
  }
  if (it.kind === 'cup') {
    const w = 0.5 * r, h = 0.45 * r;
    poly([[hp[0] - w / 2, hp[1] - h], [hp[0] + w / 2, hp[1] - h], [hp[0] + w * 0.4, hp[1] + h * 0.1], [hp[0] - w * 0.4, hp[1] + h * 0.1]], C.paper, inkC, lw * 0.8);
  }
}

// ---- seated side view: built from the floor up -------------------------------
function seated(x, floorY, r, dir, lwk = 1) {
  const lw = LW(lwk);
  const ankleY = floorY - lw / 2, kneeY = ankleY - RG.shin * r;
  const rootY = kneeY;                                        // horizontal thigh
  const Py = rootY + lw / 2 - RG.tr * r;                      // pill bottom = seat top
  const seatY = rootY + lw / 2;
  const knee = [x + dir * RG.thigh * r, kneeY];
  const ankle = [knee[0], ankleY];
  const kneeF = [x - dir * 0.08 * r + dir * RG.thigh * r * 0.97, kneeY - 0.02 * r];
  const ankleF = [kneeF[0] - dir * 0.14 * r, ankleY];
  return { P: [x, Py], seatY, floorY, knee, ankle, kneeF, ankleF, r, dir };
}
function seatedLegs(g) { return { near: { joint: g.knee, end: g.ankle }, far: { joint: g.kneeF, end: g.ankleF } }; }
function chairFor(g, style = 'cafe') {
  // side-view chair built from a seated() body: seat top = pill bottom, front edge at the knee,
  // back post touching the torso's back, legs to the floor.  Wood-toned so the ink legs read on top.
  const { P, seatY, floorY, r, dir } = g, lw = LW(0.72), wood = C.wood, woodLt = C.woodLt;
  const backX = P[0] - dir * (RG.tr * r + LW(1) * 0.5 + lw * 0.5);
  const frontX = g.knee[0] - dir * 0.18 * r;
  const th = 0.16 * r, topY = P[1] - RG.torso * r * 0.72;
  const x0 = Math.min(backX, frontX), x1 = Math.max(backX, frontX);
  stroke([[backX - dir * 0.16 * r, floorY], [backX, seatY + th], [backX, seatY], [backX - dir * 0.14 * r, topY]], wood, lw * 1.25);
  stroke([[frontX, seatY + th], [frontX + dir * 0.08 * r, floorY]], wood, lw * 1.25);
  if (style === 'cafe') {             // bentwood loop on the back + a stretcher
    stroke([[backX - dir * 0.02 * r, seatY - 0.25 * r], [backX - dir * 0.34 * r, seatY - 0.9 * r], [backX - dir * 0.26 * r, topY + 0.2 * r], [backX - dir * 0.12 * r, topY]], wood, lw);
    stroke([[lerp(backX, frontX, 0.15), seatY + th + 0.45 * r], [lerp(backX, frontX, 0.85), seatY + th + 0.45 * r]], wood, lw * 0.8);
  }
  poly(rectPts(x0 - 0.04 * r, seatY, x1 - x0 + 0.08 * r, th), woodLt, wood, lw);
  contact('seat↔pill', [P[0], P[1] + RG.tr * r], [P[0], seatY], 1.5);
  contact('ankle↔floor', [g.ankle[0], g.ankle[1] + LW(1) / 2], [g.ankle[0], floorY], 1.5);
  return { backX, frontX, seatY, topY };
}
function tableSide(cx, topY, floorY, halfW, r, fill = C.frame) {
  const lw = LW(0.9), th = 0.16 * r;
  stroke([[cx, topY + th], [cx, floorY - 0.1 * r]], C.ink, lw * 1.3);
  stroke([[cx - 0.7 * r, floorY], [cx, floorY - 0.18 * r], [cx + 0.7 * r, floorY]], C.ink, lw * 1.2);
  poly(rectPts(cx - halfW, topY, halfW * 2, th), fill, C.ink, lw);
}

// ---- standing & walking (side view) -----------------------------------------
function standPelvisY(floorY, r, bend = 0.985) { return floorY - LW(1) / 2 - RG.tr * r + LW(1) / 2 - (RG.thigh + RG.shin) * r * bend; }
function walkLegs(xAt, tau, dir, floorY, r, stride) {
  // xAt(τ) = pelvis x at beat τ; one step per beat; stance feet are planted (no sliding)
  const ank = floorY - LW(1) / 2;
  function foot(ph) {
    // foot with stance centred on beats ≡ ph (mod 2)
    const u = tau - ph, m = Math.floor((u + 0.5) / 2), c = ph + 2 * m;      // nearest stance centre ≤
    const local = tau - c;                                                  // -0.5..1.5
    if (local <= 0.5) return [xAt(c) + dir * 0.02 * r, ank, true];
    const s = (local - 0.5) / 1.0;                                          // swing 0..1
    const x0 = xAt(c), x1 = xAt(c + 2);
    return [lerp(x0, x1, ease(s)), ank - Math.sin(Math.PI * s) * 0.32 * r * clamp(Math.abs(x1 - x0) / (stride || 1), 0, 1), false];
  }
  return { A: foot(0), B: foot(1) };
}
