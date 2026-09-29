// ============================================================
//  FX — chromatography (the ink bleeds into its colours), kaleidoscope, droste
// ============================================================
let FX = null;
function mkCanvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
function fxBufs() {
  if (FX && FX.w === PXW && FX.h === PXH) return FX;
  const w4 = Math.max(2, Math.round(PXW / 4)), h4 = Math.max(2, Math.round(PXH / 4));
  FX = { w: PXW, h: PXH, w4, h4, q: mkCanvas(w4, h4), lay: mkCanvas(w4, h4), mask: mkCanvas(w4, h4), accB: mkCanvas(w4, h4), accT: mkCanvas(w4, h4), full: mkCanvas(PXW, PXH), full2: mkCanvas(PXW, PXH) };
  return FX;
}
// three rings, like black marker ink climbing wet paper: blue inside, magenta, then yellow
const RINGS = [
  { rot: 170, sat: 5.5, blur: 2.2, stops: [[0, 0.95], [0.42, 0.85], [0.66, 0]], tint: 'rgb(40,110,200)' },
  { rot: 268, sat: 5.0, blur: 4.5, stops: [[0.28, 0], [0.6, 0.9], [0.86, 0]], tint: 'rgb(200,40,150)' },
  { rot: 14, sat: 5.5, blur: 7.0, stops: [[0.6, 0], [0.86, 0.95], [1.0, 0]], tint: 'rgb(235,180,30)' }
];
const RING_SPR = [];
function ringSprite(ri) {
  if (RING_SPR[ri]) return RING_SPR[ri];
  const c = mkCanvas(128, 128), x = c.getContext('2d');
  const gr = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const [o, a] of RINGS[ri].stops) gr.addColorStop(o, `rgba(0,0,0,${(a * 0.75).toFixed(3)})`);
  x.fillStyle = gr; x.fillRect(0, 0, 128, 128);
  return (RING_SPR[ri] = c);
}
function spotsPass(t, st) {
  if (st.noSpots) return;
  let sp = spotsAt(t);
  if (st.spotMinBirth != null) sp = sp.filter(q => q.born >= st.spotMinBirth);
  if (!sp.length) return;
  const F = fxBufs(), k = S / 4, g = st.gap || 0;
  const qx = F.q.getContext('2d');
  qx.setTransform(1, 0, 0, 1, 0, 0); qx.globalCompositeOperation = 'copy'; qx.drawImage(cv, 0, 0, F.w4, F.h4); qx.globalCompositeOperation = 'source-over';
  const gain = st.spotGain == null ? 1 : st.spotGain;
  const ab = F.accB.getContext('2d'), at = F.accT.getContext('2d');
  ab.setTransform(1, 0, 0, 1, 0, 0); ab.clearRect(0, 0, F.w4, F.h4);
  at.setTransform(1, 0, 0, 1, 0, 0); at.clearRect(0, 0, F.w4, F.h4);
  const live = [];
  for (const s of sp) {
    const rho = s.R * (1 - Math.exp(-s.age / (s.grow || 0.32))) * k;
    const A = Math.min(1, s.age / 0.08) * (1 - ease((s.age - 0.35 * s.life) / (0.65 * s.life))) * gain;
    if (A > 0.01 && rho >= 0.5) live.push([s, rho, A]);
  }
  if (!live.length) return;
  const mx = F.mask.getContext('2d'), lx = F.lay.getContext('2d');
  // bounding box of everything wet (quarter-res px) — the full-res blends only touch this
  let bx0 = 1e9, by0 = 1e9, bx1 = -1e9, by1 = -1e9;
  const stamps = [];
  for (const [s, rho, A] of live) {
    const sy = (s.y + s.drip * s.age * 16) * k, ys = 1 + s.drip * s.age * 0.22;
    for (const sx of [(s.x - g / 2) * k, (W - s.x + g / 2) * k]) {
      const mir = sx > F.w4 / 2 ? -1 : 1;
      for (let b = 0; b < 2; b++) {            // two lobes → an organic blot, not a target
        const ox = (s.hue * 7.3 + b * 2.1) % 1 - 0.5, oy = (s.hue * 5.1 + b * 3.7) % 1 - 0.5;
        const rr = rho * (0.78 + 0.22 * ((s.hue * 13 + b) % 1));
        const cx = sx + mir * ox * rho * 0.45, cy = sy + oy * rho * 0.45;
        stamps.push([cx - rr, cy - rr * ys, 2 * rr, 2 * rr * ys, A]);
        bx0 = Math.min(bx0, cx - rr); bx1 = Math.max(bx1, cx + rr); by0 = Math.min(by0, cy - rr * ys); by1 = Math.max(by1, cy + rr * ys);
      }
    }
  }
  bx0 = Math.max(0, Math.floor(bx0)); by0 = Math.max(0, Math.floor(by0)); bx1 = Math.min(F.w4, Math.ceil(bx1)); by1 = Math.min(F.h4, Math.ceil(by1));
  if (bx1 <= bx0 || by1 <= by0) return;
  for (let ri = 0; ri < RINGS.length; ri++) {
    const ring = RINGS[ri], spr = ringSprite(ri);
    mx.setTransform(1, 0, 0, 1, 0, 0); mx.globalAlpha = 1; mx.clearRect(0, 0, F.w4, F.h4);
    for (const [x, y, w, h, A] of stamps) { mx.globalAlpha = A; mx.drawImage(spr, x, y, w, h); }
    mx.globalAlpha = 1;
    // the bleed: colourised, blurred, brightened copy of the frame, cut to this ring
    lx.setTransform(1, 0, 0, 1, 0, 0); lx.globalCompositeOperation = 'copy';
    lx.filter = `blur(${(ring.blur * k * 2).toFixed(2)}px) sepia(1) saturate(${ring.sat}) hue-rotate(${ring.rot}deg) brightness(1.45)`;
    lx.drawImage(F.q, 0, 0); lx.filter = 'none';
    lx.globalCompositeOperation = 'destination-in'; lx.drawImage(F.mask, 0, 0); lx.globalCompositeOperation = 'source-over';
    ab.drawImage(F.lay, 0, 0);
    // the tint for this ring
    lx.globalCompositeOperation = 'copy'; lx.fillStyle = ring.tint; lx.fillRect(0, 0, F.w4, F.h4);
    lx.globalCompositeOperation = 'destination-in'; lx.drawImage(F.mask, 0, 0); lx.globalCompositeOperation = 'source-over';
    at.drawImage(F.lay, 0, 0);
  }
  const sw = bx1 - bx0, sh = by1 - by0, K = PXW / F.w4;
  const blit = src => ctx.drawImage(src, bx0, by0, sw, sh, bx0 * K, by0 * K, sw * K, sh * K);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.imageSmoothingQuality = 'high';
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.85; blit(F.accB);
  ctx.globalCompositeOperation = 'color'; ctx.globalAlpha = 0.8; blit(F.accT);
  ctx.globalCompositeOperation = 'screen'; ctx.globalAlpha = 0.34 * (st.spotGlow == null ? 1 : st.spotGlow); blit(F.accT);
  ctx.restore();
}

// ---- snapshot helpers for post effects ----
function snap(dst) { const x = dst.getContext('2d'); x.setTransform(1, 0, 0, 1, 0, 0); x.globalCompositeOperation = 'copy'; x.drawImage(cv, 0, 0); x.globalCompositeOperation = 'source-over'; return dst; }

// ---- kaleidoscope: n mirrored wedges around a centre, mixed in by k ----
function kaleido(n, rot, cx, cy, k, zoom = 1) {
  if (k <= 0) return;
  const F = fxBufs(); snap(F.full);
  const R = Math.hypot(PXW, PXH), a = TAU / n, pcx = cx * S, pcy = cy * S;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = k;
  for (let i = 0; i < n; i++) {
    ctx.save(); ctx.translate(pcx, pcy); ctx.rotate(rot + i * a);
    if (i % 2) ctx.scale(1, -1);
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, R, -a / 2 - 0.004, a / 2 + 0.004); ctx.closePath(); ctx.clip();
    ctx.rotate(-rot); ctx.scale(zoom, zoom);
    ctx.drawImage(F.full, -pcx, -pcy);
    ctx.restore();
  }
  ctx.restore();
}

// ---- droste: the frame inside the heart inside the frame... ----
function heartPath2D(cx, cy, k) { const p = new Path2D(); for (let i = 0; i <= 64; i++) { const q = heartPt(i / 64 * TAU, cx, cy, k); i ? p.lineTo(q[0], q[1]) : p.moveTo(q[0], q[1]); } p.closePath(); return p; }
function droste(u, levels = 3, hcy = HEART.cy, hk = HEART.k) {
  // u ∈ [0,1): zoom progress into the heart; at u = 1 the view equals the next level down
  const F = fxBufs();
  if (!F.full3) F.full3 = mkCanvas(PXW, PXH);
  const cxp = SEAM * S, cyp = (hcy + 2.5 * hk) * S;
  const s = (32 * hk * 1.25) / W;
  const heart = heartPath2D(SEAM, hcy, hk);
  const B = snap(F.full);
  let A = F.full2, T = F.full3;
  const ax = A.getContext('2d'); ax.setTransform(1, 0, 0, 1, 0, 0); ax.globalCompositeOperation = 'copy'; ax.drawImage(B, 0, 0); ax.globalCompositeOperation = 'source-over';
  for (let l = 0; l < levels; l++) {
    const tx = T.getContext('2d');
    tx.setTransform(1, 0, 0, 1, 0, 0); tx.globalCompositeOperation = 'copy'; tx.drawImage(B, 0, 0); tx.globalCompositeOperation = 'source-over';
    tx.save(); tx.setTransform(S, 0, 0, S, 0, 0); tx.clip(heart);
    tx.setTransform(1, 0, 0, 1, 0, 0); tx.translate(cxp, cyp); tx.scale(s, s); tx.translate(-cxp, -cyp);
    tx.drawImage(A, 0, 0); tx.restore();
    const sw = A; A = T; T = sw;
  }
  const z = Math.pow(1 / s, u);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.translate(cxp, cyp); ctx.scale(z, z); ctx.translate(-cxp, -cyp);
  ctx.globalCompositeOperation = 'copy'; ctx.drawImage(A, 0, 0); ctx.restore();
  base();
}

// ---- THE SPLASH: the storm lands on the bare page as a thrown splat of ink ----
// Paper covers the frame except inside a mirrored ink splat (a blob + flung drops + streaks)
// that bursts from the heart outward until the whole storm is revealed.
function splashMask(p, cx = SEAM, cy = 880) {
  if (p >= 1) return;
  const F = fxBufs(), mx = F.full2.getContext('2d');
  mx.setTransform(1, 0, 0, 1, 0, 0); mx.globalCompositeOperation = 'source-over'; mx.globalAlpha = 1; mx.filter = 'none';
  mx.fillStyle = C.paper; mx.fillRect(0, 0, PXW, PXH);
  mx.setTransform(S, 0, 0, S, 0, 0); mx.globalCompositeOperation = 'destination-out'; mx.fillStyle = '#000';
  const blob = (x, y, r, k) => {
    mx.beginPath();
    for (let i = 0; i <= 40; i++) {
      const a = i / 40 * TAU;
      const rr = r * (1 + 0.22 * Math.sin(5 * a + k) + 0.12 * Math.sin(9 * a + 2 * k) + 0.07 * Math.sin(17 * a + 3 * k));
      const px = x + Math.cos(a) * rr, py = y + Math.sin(a) * rr;
      i ? mx.lineTo(px, py) : mx.moveTo(px, py);
    }
    mx.closePath(); mx.fill();
  };
  const R = 30 + 1650 * p * p;
  blob(cx, cy, R, 1.3);
  const q = Math.min(1, p * 2.4);
  for (let i = 0; i < 22; i++) {
    const a = -Math.PI / 2 + (HS(i, 901) - 0.5) * Math.PI * 1.9;          // flung sideways and up/down, mirrored below
    const d = (0.28 + 0.95 * HS(i, 902)) * 1050 * q, r = (10 + 64 * Math.pow(HS(i, 903), 1.4)) * Math.min(1, p * 3.2);
    for (const m of [1, -1]) {
      const dx = Math.cos(a) * d * m, dy = Math.sin(a) * d * 1.25;
      const x = cx + dx, y = cy + dy;
      blob(x, y, r, i + (m > 0 ? 0 : 0.7));
      // the streak the drop left on its way out
      const L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
      mx.beginPath(); mx.moveTo(x - ux * r * 0.2, y - uy * r * 0.2);
      mx.lineTo(x - ux * r * 3.2 - uy * r * 0.35, y - uy * r * 3.2 + ux * r * 0.35);
      mx.lineTo(x - ux * r * 3.2 + uy * r * 0.35, y - uy * r * 3.2 - ux * r * 0.35); mx.closePath(); mx.fill();
    }
  }
  mx.globalCompositeOperation = 'source-over';
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(F.full2, 0, 0); ctx.restore();
  base();
}
