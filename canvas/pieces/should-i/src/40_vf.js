// ============================================================================
// 40_vf: the viewfinder. Split-image circle, microprism ring, ground glass,
// match-needle meter, frame counter, mirror slap. M = output px per virtual px.
// ============================================================================
const LAY = { S: 0 };
function ensureLayers(M) {
  const S = VF.w / SW * M;               // scene px per scene unit (scene 900 wide -> VF.w virtual px)
  if (LAY.S === S) return LAY;
  LAY.S = S; LAY.M = M;
  LAY.scene = mkCanvas(SW * S, SH * S); LAY.sctx = LAY.scene.getContext('2d');
  LAY.small = mkCanvas(SW * S / 4, SH * S / 4); LAY.smctx = LAY.small.getContext('2d');
  LAY.small2 = mkCanvas(SW * S / 4, SH * S / 4); LAY.sm2ctx = LAY.small2.getContext('2d');
  return LAY;
}
// draw a scene through a "lens": camera transform + scene function -> LAY.scene
function shootScene(M, cam, drawFn) {
  const L = ensureLayers(M), c = L.sctx, S = L.S;
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.globalCompositeOperation = 'source-over'; c.filter = 'none';
  c.fillStyle = '#000'; c.fillRect(0, 0, L.scene.width, L.scene.height);
  c.setTransform(S, 0, 0, S, 0, 0);
  c.translate(SW / 2 + (cam.x || 0), SH / 2 + (cam.y || 0)); c.rotate(cam.rot || 0); c.scale(cam.zoom || 1, cam.zoom || 1); c.translate(-SW / 2, -SH / 2);
  drawFn(c, S);
  c.setTransform(1, 0, 0, 1, 0, 0);
  // blurred copy (quarter res)
  const b = cam.blur || 0;
  if (b > 0.02) {
    const sm = L.smctx; sm.setTransform(1, 0, 0, 1, 0, 0); sm.filter = 'none'; sm.globalAlpha = 1;
    sm.drawImage(L.scene, 0, 0, L.small.width, L.small.height);
    const s2 = L.sm2ctx; s2.setTransform(1, 0, 0, 1, 0, 0); s2.filter = `blur(${(2 + b * 10) * S * 0.5}px)`; s2.clearRect(0, 0, L.small2.width, L.small2.height); s2.drawImage(L.small, 0, 0); s2.filter = 'none';
  }
  return L;
}

function vfRectPath(ctx, M) { rrect(ctx, VF.x * M, VF.y * M, VF.w * M, VF.h * M, VF.r * M); }

// st: {t, blur, split, prism, bright, flash, black, counter, needle, speed, alpha, title, info}
function composeVF(ctx, W, H, st) {
  const M = W / VW, L = LAY;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  const x0 = VF.x * M, y0 = VF.y * M, w = VF.w * M, h = VF.h * M, cx = VF.cx * M, cy = VF.cy * M;
  const a = st.alpha == null ? 1 : st.alpha;
  if (a > 0.003) {
    ctx.save(); vfRectPath(ctx, M); ctx.clip();
    ctx.globalAlpha = a;
    ctx.drawImage(L.scene, x0, y0, w, h);
    const bm = clamp(st.blur || 0);
    if (bm > 0.02) { ctx.globalAlpha = a * clamp(bm * 1.6); ctx.drawImage(L.small2, x0, y0, w, h); ctx.globalAlpha = a; }
    // microprism ring: the out-of-focus image breaks into a shimmering mosaic
    const pr = clamp(st.prism == null ? bm : st.prism);
    const Rsv = st.splitR || SPLIT_R; const R0 = (Rsv + 4) * M, R1 = (Rsv + 58) * M, sx = L.scene.width / w, sy = L.scene.height / h;
    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R1, 0, TAU); ctx.arc(cx, cy, R0, 0, TAU, true); ctx.clip();
    if (pr > 0.03) {
      const ts = 9 * M, amp = pr * 7 * M, tq = Math.floor((st.t || 0) * 24);
      for (let yy = cy - R1; yy < cy + R1; yy += ts) for (let xx = cx - R1; xx < cx + R1; xx += ts) {
        const d = Math.hypot(xx + ts / 2 - cx, yy + ts / 2 - cy); if (d < R0 - ts || d > R1 + ts) continue;
        const hh = hash2(Math.round(xx / ts) + tq * 0.0, Math.round(yy / ts)), ang = hh * TAU;
        const jx = Math.cos(ang) * amp, jy = Math.sin(ang) * amp;
        ctx.drawImage(L.scene, (xx - x0 + jx) * sx, (yy - y0 + jy) * sy, ts * sx, ts * sy, xx, yy, ts + 0.6, ts + 0.6);
      }
      ctx.fillStyle = `rgba(255,255,255,${0.012 + 0.02 * pr})`; ctx.fillRect(cx - R1, cy - R1, R1 * 2, R1 * 2);
      ctx.fillStyle = `rgba(0,0,0,${0.12 + 0.18 * pr})`; const dg = 6 * M;
      for (let yy = cy - R1; yy < cy + R1; yy += dg) for (let xx = cx - R1 + ((Math.round((yy - cy) / dg) & 1) ? dg / 2 : 0); xx < cx + R1; xx += dg) ctx.fillRect(xx, yy, 1.4 * M, 1.4 * M);
    } else ctx.drawImage(L.scene, x0, y0, w, h);
    ctx.restore();
    // split-image circle: top half shifted right, bottom half shifted left
    const sp = (st.split || 0) * M, Rs = Rsv * M;
    for (const half of [-1, 1]) {
      ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, Rs, 0, TAU); ctx.clip();
      ctx.beginPath(); ctx.rect(cx - Rs, half < 0 ? cy - Rs : cy, Rs * 2, Rs); ctx.clip();
      const off = half < 0 ? sp : -sp;
      ctx.drawImage(L.scene, x0 + off, y0, w, h);
      ctx.restore();
    }
    // ground glass texture + a faint fresnel
    overlayTile(ctx, noiseTile(256, 7, 38, 'gg'), W, H, 0, 0, 0.22, 'soft-light');
    ctx.strokeStyle = 'rgba(255,255,255,0.025)'; ctx.lineWidth = 1 * M;
    for (let r = 220; r < 900; r += 26) { ctx.beginPath(); ctx.arc(cx, cy, r * M, 0, TAU); ctx.stroke(); }
    // circle outlines
    ctx.strokeStyle = 'rgba(0,0,0,0.55)'; ctx.lineWidth = 2.2 * M; ctx.beginPath(); ctx.arc(cx, cy, Rs, 0, TAU); ctx.stroke();
    ctx.strokeStyle = `rgba(0,0,0,${0.35 + 0.4 * clamp(Math.abs(st.split || 0) / 80)})`; ctx.lineWidth = (1.4 + 2 * clamp(Math.abs(st.split || 0) / 80)) * M; ctx.beginPath(); ctx.moveTo(cx - Rs, cy); ctx.lineTo(cx + Rs, cy); ctx.stroke();
    ctx.strokeStyle = 'rgba(0,0,0,0.3)'; ctx.lineWidth = 1.6 * M; ctx.beginPath(); ctx.arc(cx, cy, R1, 0, TAU); ctx.stroke();
    // exposure (brightness) + vignette
    if (st.bright != null && st.bright !== 1) { if (st.bright < 1) { ctx.fillStyle = `rgba(0,0,0,${1 - st.bright})`; ctx.fillRect(x0, y0, w, h); } else { ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = `rgba(255,245,230,${(st.bright - 1) * 0.5})`; ctx.fillRect(x0, y0, w, h); ctx.globalCompositeOperation = 'source-over'; } }
    const vg = ctx.createRadialGradient(cx, cy, h * 0.28, cx, cy, h * 0.75); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.62)');
    ctx.fillStyle = vg; ctx.fillRect(x0, y0, w, h);
    if (st.flash > 0) { ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = `rgba(255,250,240,${clamp(st.flash)})`; ctx.fillRect(x0, y0, w, h); ctx.globalCompositeOperation = 'source-over'; }
    ctx.restore();
    // frame edge
    ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = 'rgba(0,0,0,0.9)'; ctx.lineWidth = 3 * M; vfRectPath(ctx, M); ctx.stroke(); ctx.restore();
  }
  // eyepiece: soft dark falloff around the whole view
  const eg = ctx.createRadialGradient(W / 2, H * 0.49, H * 0.38, W / 2, H * 0.49, H * 0.72); eg.addColorStop(0, 'rgba(0,0,0,0)'); eg.addColorStop(1, 'rgba(0,0,0,0.85)');
  ctx.fillStyle = eg; ctx.fillRect(0, 0, W, H);
  if (st.info !== false) drawInfo(ctx, M, st);
  if (st.title > 0) drawTitle(ctx, M, st.title, st.t || 0);
  if (st.black > 0) { ctx.save(); vfRectPath(ctx, M); ctx.fillStyle = `rgba(0,0,0,${clamp(st.black)})`; ctx.fill(); ctx.restore(); }
}

// ---- readouts: shutter speed · needle meter · frame counter --------------
function drawInfo(ctx, M, st) {
  const ia = st.infoAlpha == null ? 1 : st.infoAlpha; if (ia <= 0.01) return;
  const y = 188 * M, ink = `rgba(236,228,210,${0.85 * ia})`, dim = `rgba(236,228,210,${0.35 * ia})`;
  ctx.save(); ctx.textBaseline = 'middle';
  // shutter speed (left)
  ctx.font = `${40 * M}px "Space Mono"`; ctx.fillStyle = ink; ctx.textAlign = 'left'; ctx.fillText(st.speed || '1/125', 96 * M, y);
  ctx.font = `${28 * M}px "Space Mono"`; ctx.fillStyle = dim; ctx.fillText('f2', 282 * M, y + 3 * M);
  // needle meter (centre): arc scale from -2 to +2
  const mx = 540 * M, my = 246 * M, R = 118 * M;
  ctx.strokeStyle = dim; ctx.lineWidth = 2 * M; ctx.beginPath(); ctx.arc(mx, my, R, -Math.PI / 2 - 0.62, -Math.PI / 2 + 0.62); ctx.stroke();
  for (let i = -4; i <= 4; i++) { const an = -Math.PI / 2 + i * 0.155, L = i % 2 === 0 ? 14 : 8; ctx.strokeStyle = i === 0 ? ink : dim; ctx.lineWidth = (i === 0 ? 3 : 2) * M;
    ctx.beginPath(); ctx.moveTo(mx + Math.cos(an) * R, my + Math.sin(an) * R); ctx.lineTo(mx + Math.cos(an) * (R - L * M), my + Math.sin(an) * (R - L * M)); ctx.stroke(); }
  ctx.font = `600 ${34 * M}px "Barlow Condensed"`; ctx.fillStyle = ink; ctx.textAlign = 'center';
  ctx.fillText('−', mx + Math.cos(-Math.PI / 2 - 0.75) * (R + 4 * M), my + Math.sin(-Math.PI / 2 - 0.75) * (R + 4 * M));
  ctx.fillText('+', mx + Math.cos(-Math.PI / 2 + 0.75) * (R + 4 * M), my + Math.sin(-Math.PI / 2 + 0.75) * (R + 4 * M));
  const nd = clamp(st.needle || 0, -1.15, 1.15), an = -Math.PI / 2 + nd * 0.62;
  ctx.save(); ctx.shadowColor = `rgba(255,120,50,${0.8 * ia})`; ctx.shadowBlur = 10 * M; ctx.strokeStyle = `rgba(255,140,70,${ia})`; ctx.lineWidth = 3.2 * M; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(mx + Math.cos(an) * R * 0.25, my + Math.sin(an) * R * 0.25); ctx.lineTo(mx + Math.cos(an) * (R + 6 * M), my + Math.sin(an) * (R + 6 * M)); ctx.stroke(); ctx.restore();
  // frame counter (right)
  const cxn = 912 * M, bw = 118 * M, bh = 70 * M; const blink = st.counterBlink ? (Math.floor((st.t || 0) * 4) % 2 === 0 ? 1 : 0.25) : 1;
  ctx.strokeStyle = dim; ctx.lineWidth = 2 * M; rrect(ctx, cxn - bw / 2, y - bh / 2, bw, bh, 10 * M); ctx.stroke();
  ctx.font = `700 ${46 * M}px "Space Mono"`; ctx.fillStyle = `rgba(236,228,210,${0.9 * ia * blink})`; ctx.textAlign = 'center';
  ctx.save(); rrect(ctx, cxn - bw / 2, y - bh / 2, bw, bh, 10 * M); ctx.clip();
  const roll = st.roll == null ? 1 : easeOut(st.roll);
  if (roll < 1 && st.counterPrev != null) ctx.fillText(String(st.counterPrev), cxn, y + 2 * M - roll * bh);
  ctx.fillText(st.counter == null ? '0' : String(st.counter), cxn, y + 2 * M + (1 - roll) * bh);
  ctx.restore();
  ctx.restore();
}
function drawTitle(ctx, M, a, t) {
  ctx.save(); ctx.globalAlpha = clamp(a); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#000'; ctx.fillRect(0, 118 * M, VW * M, 150 * M);
  ctx.fillStyle = '#efe8d8'; ctx.font = `600 ${104 * M}px "Barlow Condensed"`;
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${10 * M}px`;
  ctx.fillText('SHOULD I ?', 540 * M, 190 * M);
  ctx.restore();
}
