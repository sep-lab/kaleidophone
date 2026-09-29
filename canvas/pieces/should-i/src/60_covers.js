// ============================================================================
// 60_covers: variants of the contact-sheet cover (red grease pencil + SHOULD I ?)
//   __draw('cv', { v: 'circle' | 'three' | 'xout' | 'print37', k, ks, keep, y })
// ============================================================================
function gLine(x1, y1, x2, y2, n, bow, seed) {
  const P = [], nx = -(y2 - y1), ny = x2 - x1, L = Math.hypot(nx, ny) || 1;
  for (let i = 0; i <= n; i++) { const u = i / n, b = Math.sin(u * Math.PI) * bow; P.push([lerp(x1, x2, u) + nx / L * b, lerp(y1, y2, u) + ny / L * b]); }
  return P;
}
function circleK(ctx, g, k, M, seed, s) {
  const r = sheetFrameRect(g, k), cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2; s = s || 1;
  greaseStroke(ctx, circlePts(cx, cy, r[2] * 0.78 * s, r[3] * 0.66 * s, 1, 60), 9 * M, 0.95, seed);
  return [cx, cy, r];
}
function crossK(ctx, g, k, M, seed) {
  const [x, y, w, h] = sheetFrameRect(g, k), p = 0.12, q = 0.1;
  greaseStroke(ctx, gLine(x + w * p, y + h * q, x + w * (1 - p), y + h * (1 - q), 12, w * 0.05, seed), 7.5 * M, 0.92, seed);
  greaseStroke(ctx, gLine(x + w * (1 - p * 0.8), y + h * q * 1.4, x + w * p * 1.3, y + h * (1 - q * 0.8), 12, -w * 0.06, seed + 3), 7.5 * M, 0.92, seed + 3);
}
function smallQ(ctx, x, y, s, M, seed) {
  greaseStroke(ctx, qPts(x, y, s, 1), 7 * M, 0.95, seed);
  ctx.save(); ctx.fillStyle = 'rgba(196,20,26,0.95)'; ell(ctx, x, y + s * 0.02, 6.5 * M, 6 * M); ctx.fill(); ctx.restore();
}
function frame37Print(w, h) {
  const c = mkCanvas(w, h), x = c.getContext('2d');
  x.save(); x.scale(w / SW, h / SH); drawDoorway(x, 180.4, {}); x.restore();
  overlayTile(x, noiseTile(256, 37, 60, 'p37'), w, h, 11, 23, 0.14, 'overlay');
  const vg = x.createRadialGradient(w / 2, h * 0.45, h * 0.25, w / 2, h / 2, h * 0.75); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.35)');
  x.fillStyle = vg; x.fillRect(0, 0, w, h);
  return c;
}
function drawCoverVariant(ctx, W, H, o) {
  o = o || {}; const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0);
  const g = sheetGeom(95 * M, (o.y == null ? -460 : o.y) * M, 890 * M); drawDesk(ctx, W, H, 0, g);
  const tp = titleMargin(g), v = o.v || 'circle';
  if (v === 'circle') circleK(ctx, g, o.k || 29, M, o.k || 29);
  else if (v === 'three') { for (const k of (o.ks || [27, 29, 33])) { const [cx, cy, r] = circleK(ctx, g, k, M, k); greaseText(ctx, '?', cx + r[2] * 1.0, cy - r[3] * 0.64, r[2] * 0.82, 1); } }
  else if (v === 'xout') { const keep = o.keep || 33; for (let k = 13; k <= 36; k++) if (k !== keep && hash(k * 3.3 + 1) < 0.7) crossK(ctx, g, k, M, k * 5); circleK(ctx, g, keep, M, keep, 1.06); }
  if (v === 'print37') {
    // frame 37 was never on the roll: a print of it lies on the sheet, the title on its border
    const pw = W * 0.5, ph = pw * 1.5, bw = pw * 0.055, bb = pw * 0.26;
    ctx.save(); ctx.translate(W * 0.53, H * 0.47); ctx.rotate(o.rot == null ? -0.055 : o.rot);
    ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 70 * M; ctx.shadowOffsetX = 16 * M; ctx.shadowOffsetY = 26 * M;
    ctx.fillStyle = '#f4efe6'; ctx.fillRect(-pw / 2 - bw, -ph / 2 - bw, pw + 2 * bw, ph + bw + bb);
    ctx.shadowColor = 'rgba(0,0,0,0)';
    ctx.drawImage(frame37Print(Math.round(pw), Math.round(ph)), -pw / 2, -ph / 2, pw, ph);
    ctx.fillStyle = 'rgba(0,0,0,0.25)'; ctx.fillRect(-pw / 2, -ph / 2, pw, 2 * M);
    greaseText(ctx, 'SHOULD I ?', 0, ph / 2 + bb * 0.5, bb * 0.5, 1);
    ctx.fillStyle = 'rgba(40,34,30,0.75)'; ctx.font = `700 ${bb * 0.13}px "Space Mono"`; ctx.textAlign = 'right'; ctx.fillText('37', pw / 2, -ph / 2 - bw * 0.25);
    ctx.restore();
  } else greaseText(ctx, 'SHOULD I ?', tp[0], tp[1], tp[2], 1);
  grainOver(ctx, W, H, 0, 0.12);
}
