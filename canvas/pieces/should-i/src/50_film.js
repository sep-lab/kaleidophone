// ============================================================================
// 50_film: what happens to the roll. Rewind as negatives (126-129), the
// darkroom (129-156), the red grease pencil (156-168), into her eye (168-180).
// ============================================================================
const PHOTO = {};
function expoPhoto(k) { // the picture actually taken at shutter k (positive), cached
  if (PHOTO[k]) return PHOTO[k];
  const w = 360, h = 540, c = mkCanvas(w, h), x = c.getContext('2d');
  x.scale(w / SW, h / SH); drawExpo(x, k, expoTime(k) - 0.02, 0.4);
  x.setTransform(1, 0, 0, 1, 0, 0); overlayTile(x, noiseTile(128, 3 + k, 30, 'pg' + (k % 4)), w, h, k * 17, k * 29, 0.18, 'overlay');
  return (PHOTO[k] = c);
}
function negativeOf(k) {
  const key = 'neg' + k; if (PHOTO[key]) return PHOTO[key];
  const src = expoPhoto(k), c = mkCanvas(src.width, src.height), x = c.getContext('2d');
  x.drawImage(src, 0, 0); x.globalCompositeOperation = 'difference'; x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height);
  x.globalCompositeOperation = 'multiply'; x.fillStyle = 'rgb(255,168,110)'; x.fillRect(0, 0, c.width, c.height); // orange mask
  return (PHOTO[key] = c);
}
function grainOver(ctx, W, H, t, a) { overlayTile(ctx, noiseTile(256, 11, 60, 'fg'), W, H, Math.floor(t * 12) * 37, Math.floor(t * 12) * 53, a, 'overlay'); }

// ---- the rewind: 36 negatives through the gate in one bar (12 per second)
function drawRewind(ctx, W, H, t) {
  const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  const u = clamp((t - T_REWIND) * 12, 0, 35.999), j = 36 - Math.floor(u), fr = u - Math.floor(u);
  const far = easeIn(smooth(T_REWIND, T_DARK, t)); // life is going far
  const z = lerp(1, 0.34, far), rot = lerp(0, -0.12, far);
  const fw = VF.w * M * z, fh = VF.h * M * z, gap = 70 * M * z, pitch = fh + gap;
  ctx.save(); ctx.translate(W / 2, VF.cy * M); ctx.rotate(rot);
  // strip base
  const sw = fw + 150 * M * z;
  ctx.fillStyle = 'rgb(58,30,14)'; ctx.fillRect(-sw / 2, -H * 2, sw, H * 4);
  for (let n = -3; n <= 3; n++) {
    const k = j + n; const yy = n * pitch + fr * pitch * 0.9; // strip runs down while rewinding
    if (k < 1 || k > 36) { ctx.fillStyle = 'rgb(40,20,10)'; ctx.fillRect(-fw / 2, yy - fh / 2, fw, fh); continue; }
    ctx.drawImage(negativeOf(k), -fw / 2, yy - fh / 2, fw, fh);
    // sprocket holes + edge print
    ctx.fillStyle = '#000';
    for (let s = 0; s < 8; s++) { const sy = yy - fh / 2 + (s + 0.5) * (pitch / 8) - gap / 2; rrect(ctx, -sw / 2 + 18 * M * z, sy - 14 * M * z, 30 * M * z, 30 * M * z, 6 * M * z); ctx.fill(); rrect(ctx, sw / 2 - 48 * M * z, sy - 14 * M * z, 30 * M * z, 30 * M * z, 6 * M * z); ctx.fill(); }
    ctx.save(); ctx.translate(-sw / 2 + 62 * M * z, yy); ctx.rotate(-Math.PI / 2); ctx.fillStyle = 'rgba(255,200,120,0.85)'; ctx.font = `700 ${26 * M * z}px "Space Mono"`; ctx.textAlign = 'center'; ctx.fillText(`▸${k}   SEP 400   ▸${k}A`, 0, 0); ctx.restore();
  }
  ctx.restore();
  // motion streaks + dim the edges
  ctx.fillStyle = `rgba(0,0,0,${0.15 + 0.5 * far})`; ctx.fillRect(0, 0, W, H);
  grainOver(ctx, W, H, t, 0.25);
  // the flash from the lock (125.25) still burning off at the start
  const fl = 1 - smooth(T_REWIND, T_REWIND + 0.5, t); if (fl > 0) { ctx.fillStyle = `rgba(255,250,240,${0.55 * fl})`; ctx.fillRect(0, 0, W, H); }
  // counter spinning back
  drawInfo(ctx, M, { t, needle: -1, counter: Math.max(0, 36 - Math.floor(u)), speed: 'R', infoAlpha: 1 - far * 0.6 });
}

// ---- contact sheet ---------------------------------------------------------
// frames laid out 6 x 6 (six strips of six, vertical strips). dev(k) -> 0..1 development
const SHEET = { cols: 6, rows: 6 };
function sheetGeom(x, y, w) { const fw = w / 6.9, fh = fw * 1.5, gx = fw * 0.18, gy = fw * 0.2; return { x, y, w, fw, fh, gx, gy, h: 6 * fh + 7 * gy }; }
function sheetFrameRect(g, k) { const i = (k - 1) % 6, j = Math.floor((k - 1) / 6); return [g.x + g.gx * 0.5 + i * (g.fw + g.gx), g.y + g.gy + j * (g.fh + g.gy), g.fw, g.fh]; }
function drawContactSheet(ctx, g, dev, o) {
  o = o || {};
  // paper
  ctx.fillStyle = o.paper || '#f2ede4'; ctx.fillRect(g.x - g.fw * 0.25, g.y - g.fw * 0.25, g.w + g.fw * 0.5, g.h + g.fw * 1.7);
  for (let j = 0; j < 6; j++) {
    // film strip borders (black on the print) with sprocket holes
    const d = Math.max(...[1, 2, 3, 4, 5, 6].map(i => dev(j * 6 + i)));
    const [sx, sy] = sheetFrameRect(g, j * 6 + 1);
    ctx.fillStyle = `rgba(12,10,10,${0.95 * d})`; ctx.fillRect(g.x, sy - g.gy * 0.5, g.w, g.fh + g.gy);
    ctx.fillStyle = `rgba(40,36,34,${0.9 * d})`;
    for (let s = 0; s < 42; s++) { const hx = g.x + (s + 0.5) * g.w / 42; ctx.fillRect(hx - g.fw * 0.03, sy - g.gy * 0.42, g.fw * 0.06, g.gy * 0.24); ctx.fillRect(hx - g.fw * 0.03, sy + g.fh + g.gy * 0.18, g.fw * 0.06, g.gy * 0.24); }
    ctx.fillStyle = `rgba(245,236,220,${0.8 * d})`; ctx.font = `700 ${g.fw * 0.075}px "Space Mono"`; ctx.textAlign = 'left';
    for (let i = 1; i <= 6; i++) { const k = j * 6 + i; const [fx] = sheetFrameRect(g, k); ctx.fillText(`${k}  ▸${k}A`, fx, sy + g.fh + g.gy * 0.14); }
  }
  for (let k = 1; k <= 36; k++) {
    const d = dev(k); if (d <= 0.001) continue;
    const [fx, fy, fw, fh] = sheetFrameRect(g, k);
    ctx.globalAlpha = clamp(d); ctx.drawImage(expoPhoto(k), fx, fy, fw, fh); ctx.globalAlpha = 1;
  }
}

// ---- the darkroom: the sheet develops in the tray, one frame per beat ------
function drawDarkroom(ctx, W, H, t) {
  const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#070202'; ctx.fillRect(0, 0, W, H);
  const lt = t - T_DARK, push = easeInOut(clamp(lt / 27)), bar = Math.floor(lt / BAR);
  const rock = Math.sin(lt * TAU / BAR) * 0.008 + (hash(bar) - 0.5) * 0.004;
  ctx.save(); ctx.translate(W / 2, H * 0.5); ctx.rotate(rock); ctx.scale(1 + 0.12 * push, 1 + 0.12 * push); ctx.translate(-W / 2, -H * 0.5);
  // tray
  const tx = 60 * M, ty = 150 * M, tw = 960 * M, th = 1620 * M;
  ctx.fillStyle = '#6f6a64'; rrect(ctx, tx - 22 * M, ty - 22 * M, tw + 44 * M, th + 44 * M, 50 * M); ctx.fill();
  ctx.fillStyle = '#4a4540'; rrect(ctx, tx, ty, tw, th, 36 * M); ctx.fill();
  // paper in the developer
  const g = sheetGeom(tx + 70 * M, ty + 130 * M, tw - 140 * M);
  const dev = k => { const t0 = T_DARK + BEAT * (k - 1); return easeIn(clamp((t - t0) / 1.1)); };
  drawContactSheet(ctx, g, dev, { paper: '#f4efe6' });
  // liquid: moving caustic lines, ripples on the voice
  ctx.save(); rrect(ctx, tx, ty, tw, th, 36 * M); ctx.clip();
  const v = vocAt(t);
  ctx.globalCompositeOperation = 'screen';
  for (let i = 0; i < 18; i++) {
    const yy = ty + ((i / 18 + lt * 0.03) % 1) * th; ctx.strokeStyle = `rgba(255,255,255,${0.05 + 0.08 * v})`; ctx.lineWidth = (3 + 5 * hash(i)) * M;
    ctx.beginPath(); for (let xx = 0; xx <= tw; xx += 40 * M) { const w2 = Math.sin(xx / (120 * M) + lt * 1.3 + i) * (8 + 18 * v) * M; if (xx === 0) ctx.moveTo(tx + xx, yy + w2); else ctx.lineTo(tx + xx, yy + w2); } ctx.stroke();
  }
  // the rocking wave crossing on each bar
  const wp = (lt % BAR) / BAR; const wy = ty + wp * th;
  const wg = ctx.createLinearGradient(0, wy - 90 * M, 0, wy + 90 * M); wg.addColorStop(0, 'rgba(255,255,255,0)'); wg.addColorStop(0.5, 'rgba(255,255,255,0.12)'); wg.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = wg; ctx.fillRect(tx, wy - 90 * M, tw, 180 * M);
  ctx.restore();
  ctx.restore();
  // SAFELIGHT: everything goes red
  ctx.save(); ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = 'rgb(225,34,20)'; ctx.fillRect(0, 0, W, H); ctx.restore();
  // the spoken voice message breathes through the safelight: fast attack, slow release on the voice
  let vs = 0; for (let d = 0; d < 1.2; d += 0.04) vs = Math.max(vs, vocAt(t - d) * Math.exp(-d / 0.35));
  vs = smooth(0.12, 0.85, vs);
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  drawSprite(ctx, glowSprite(255, 40, 20, 'safe'), W * 0.82, H * 0.04, (500 + 170 * vs) * M, 0.5 + 0.1 * envAt('bass', t) + 0.38 * vs);
  drawSprite(ctx, glowSprite(255, 40, 20, 'safe'), W * 0.82, H * 0.04, 1500 * M, 0.1 * vs);
  ctx.restore();
  const vg = ctx.createRadialGradient(W / 2, H * 0.42, H * 0.18, W / 2, H * 0.45, H * 0.7); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.9)'); ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(0,0,0,0.18)'; ctx.fillRect(0, 0, W, H);
  grainOver(ctx, W, H, t, 0.22);
  // fade in from the rewind
  const fi = 1 - smooth(T_DARK, T_DARK + 0.7, t); if (fi > 0) { ctx.fillStyle = `rgba(0,0,0,${fi})`; ctx.fillRect(0, 0, W, H); }
}

// ---- the red grease pencil: hesitate over the frames, circle 36, write ? ---
const PENCIL_PATH = [[156.0, 1], [157.5, 6], [159.0, 13], [160.5, 23], [162.0, 29], [163.2, 36]];
function pencilTarget(t, g) {
  let a = PENCIL_PATH[0], b = PENCIL_PATH[0];
  for (let i = 0; i < PENCIL_PATH.length; i++) { if (t >= PENCIL_PATH[i][0]) { a = PENCIL_PATH[i]; b = PENCIL_PATH[Math.min(i + 1, PENCIL_PATH.length - 1)]; } }
  const r1 = sheetFrameRect(g, a[1]), r2 = sheetFrameRect(g, b[1]);
  const p1 = [r1[0] + r1[2] * 0.5, r1[1] + r1[3] * 0.5], p2 = [r2[0] + r2[2] * 0.5, r2[1] + r2[3] * 0.5];
  const k = b[0] > a[0] ? easeInOut(clamp((t - a[0] - 0.9) / 0.55)) : 0;
  return [lerp(p1[0], p2[0], k), lerp(p1[1], p2[1], k)];
}
function greaseStroke(ctx, pts, w, a, seed) {
  if (pts.length < 2) return;
  ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (let pass = 0; pass < 3; pass++) {
    ctx.strokeStyle = `rgba(${200 + pass * 10},${20 + pass * 8},${24},${a * (pass === 0 ? 0.9 : 0.35)})`; ctx.lineWidth = w * (pass === 0 ? 1 : 0.55);
    ctx.beginPath(); for (let i = 0; i < pts.length; i++) { const jx = (hash(seed + i * 1.3 + pass) - 0.5) * w * 0.35, jy = (hash(seed + i * 2.1 + pass * 3) - 0.5) * w * 0.35; if (i === 0) ctx.moveTo(pts[i][0] + jx, pts[i][1] + jy); else ctx.lineTo(pts[i][0] + jx, pts[i][1] + jy); } ctx.stroke();
  }
  ctx.restore();
}
function circlePts(cx, cy, rx, ry, k, n) { const out = []; const N = Math.max(2, Math.floor(n * k)); for (let i = 0; i <= N; i++) { const a = -2.1 + (i / n) * TAU * 1.12; const wob = 1 + 0.05 * Math.sin(i * 0.7); out.push([cx + Math.cos(a) * rx * wob, cy + Math.sin(a) * ry * wob]); } return out; }
function qPts(x, y, s, k) { // a hand-written question mark as one stroke + dot
  const P = []; const N = 40; const K = Math.floor(N * clamp(k / 0.85));
  for (let i = 0; i <= K; i++) { const u = i / N; let px, py; if (u < 0.7) { const a = lerp(-2.6, 1.6, u / 0.7); px = x + Math.cos(a) * s * 0.42; py = y - s * 0.55 + Math.sin(a) * s * 0.38; } else { const v = (u - 0.7) / 0.3; px = x + lerp(Math.cos(1.6) * s * 0.42, 0, v); py = y - s * 0.55 + lerp(Math.sin(1.6) * s * 0.38, s * 0.1, v); } P.push([px, py]); }
  return P;
}
function titleMargin(g) { return [g.x + g.w / 2, g.y + g.h + g.fw * 0.78, g.fw * 0.78]; }
const GT = {};
function greaseTextCanvas(txt, size) {
  const key = txt + '@' + Math.round(size); if (GT[key]) return GT[key];
  const f = `${Math.round(size)}px "Permanent Marker"`; const m = mkCanvas(10, 10).getContext('2d'); m.font = f;
  const w = Math.ceil(m.measureText(txt).width + size * 0.6), h = Math.ceil(size * 1.6);
  const c = mkCanvas(w, h), x = c.getContext('2d'); x.font = f; x.textBaseline = 'middle'; x.textAlign = 'center';
  for (let p = 0; p < 3; p++) { x.fillStyle = p ? 'rgba(214,30,34,0.5)' : 'rgb(196,20,26)'; x.fillText(txt, w / 2 + (p - 1) * size * 0.012, h / 2 + (p === 2 ? size * 0.01 : 0)); }
  // wax texture: knock out specks so it reads as grease pencil on paper
  x.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < w * h / 90; i++) { x.fillStyle = `rgba(0,0,0,${0.3 + hash(i * 1.7) * 0.6})`; x.fillRect(hash(i * 3.1) * w, hash(i * 5.3) * h, 1 + hash(i) * size * 0.03, 1 + hash(i + 2) * size * 0.02); }
  return (GT[key] = c);
}
function greaseTextWidth(size) { return greaseTextCanvas('SHOULD I ?', size).width - size * 0.6; }
function greaseText(ctx, txt, cx, cy, size, reveal) {
  const c = greaseTextCanvas(txt, size); const w = c.width, h = c.height;
  const rw = (size * 0.3 + (w - size * 0.6) * clamp(reveal));
  ctx.save(); ctx.beginPath(); ctx.rect(cx - w / 2, cy - h / 2, rw, h); ctx.clip(); ctx.drawImage(c, cx - w / 2, cy - h / 2); ctx.restore();
}
function drawDesk(ctx, W, H, t, g) {
  const M = W / VW;
  vgrad(ctx, 0, 0, W, H, [[0, '#2a2420'], [1, '#141110']]);
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; drawSprite(ctx, glowSprite(255, 220, 170, 'desk'), W * 0.3, H * 0.1, 1100 * M, 0.35); ctx.restore();
  drawContactSheet(ctx, g, () => 1, {});
}
function drawPencil(ctx, W, H, t) {
  const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0);
  const g = sheetGeom(95 * M, 250 * M, 890 * M);
  drawDesk(ctx, W, H, t, g);
  // the circle around 36 and the question mark
  const r36 = sheetFrameRect(g, 36), c36 = [r36[0] + r36[2] / 2, r36[1] + r36[3] / 2]; const tp = titleMargin(g);
  const ck = clamp((t - 163.9) / 1.2), qk = clamp((t - 165.15) / 2.1);
  if (ck > 0) greaseStroke(ctx, circlePts(c36[0], c36[1], r36[2] * 0.78, r36[3] * 0.66, ck, 60), 9 * M, 0.95, 36);
  if (qk > 0) greaseText(ctx, 'SHOULD I ?', tp[0], tp[1], tp[2], qk);
  // the hand with the pencil hovering ("should I?")
  let [px, py] = pencilTarget(t, g);
  if (t >= 163.9 && t < 165.1) { const p = circlePts(c36[0], c36[1], r36[2] * 0.78, r36[3] * 0.66, ck, 60); [px, py] = p[p.length - 1]; }
  else if (t >= 165.1 && t < 167.3) { const tw = greaseTextWidth(tp[2]); px = tp[0] - tw / 2 + tw * qk; py = tp[1] + tp[2] * 0.05 + Math.sin(t * 31) * tp[2] * 0.18; }
  else if (t >= 167.3) { const tw = greaseTextWidth(tp[2]); px = tp[0] + tw / 2 + 80 * M * easeOut((t - 167.3) / 0.7); py = tp[1] + 300 * M * easeOut((t - 167.3) / 0.7); }
  const hover = t < 163.9 ? 1 : 0;
  px += hover * Math.cos(t * 5.3) * 14 * M; py += hover * Math.sin(t * 4.1) * 10 * M - hover * 18 * M;
  const enter = easeOut(clamp((t - T_PENCIL) / 0.9));
  px += (1 - enter) * 500 * M; py += (1 - enter) * 700 * M;
  drawPencilHand(ctx, px, py, M, hover);
  grainOver(ctx, W, H, t, 0.14);
  const fi = 1 - smooth(T_PENCIL, T_PENCIL + 0.25, t); if (fi > 0) { ctx.fillStyle = `rgba(255,70,40,${0.6 * fi})`; ctx.fillRect(0, 0, W, H); }
}
function drawPencilHand(ctx, px, py, M, lift) {
  ctx.save(); ctx.translate(px, py); ctx.rotate(-0.38);
  ctx.fillStyle = 'rgba(0,0,0,0.16)'; ctx.save(); ctx.translate(22 * M + lift * 26 * M, 30 * M); rrect(ctx, -7 * M, 0, 14 * M, 250 * M, 6 * M); ctx.fill(); ell(ctx, 4 * M, 250 * M, 56 * M, 44 * M, 0.2); ctx.fill(); ctx.restore();
  ctx.fillStyle = '#b3151b'; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-7 * M, 20 * M); ctx.lineTo(7 * M, 20 * M); ctx.fill();
  ctx.fillStyle = '#c21d22'; ctx.fillRect(-7 * M, 20 * M, 14 * M, 30 * M);
  ctx.fillStyle = '#e9e1d0'; ctx.fillRect(-7 * M, 50 * M, 14 * M, 230 * M);
  ctx.strokeStyle = 'rgba(120,100,80,0.6)'; ctx.lineWidth = 1.2 * M; for (let i = 0; i < 12; i++) { ctx.beginPath(); ctx.moveTo(-7 * M, (60 + i * 18) * M); ctx.lineTo(7 * M, (52 + i * 18) * M); ctx.stroke(); }
  // fingers pinching the pencil + the back of the hand, exiting the frame
  ctx.fillStyle = 'rgba(27,21,19,0.92)'; ctx.filter = `blur(${1.5 * M}px)`;
  ell(ctx, 12 * M, 118 * M, 20 * M, 40 * M, 0.25); ctx.fill(); ell(ctx, -15 * M, 132 * M, 16 * M, 34 * M, -0.3); ctx.fill();
  ell(ctx, 22 * M, 190 * M, 46 * M, 62 * M, 0.15); ctx.fill();
  limb(ctx, 22 * M, 200 * M, 70 * M, 700 * M, 96 * M, 120 * M);
  ctx.filter = 'none'; ctx.strokeStyle = 'rgba(255,220,190,0.18)'; ctx.lineWidth = 2 * M; ctx.beginPath(); ctx.moveTo(-28 * M, 120 * M); ctx.quadraticCurveTo(-26 * M, 200 * M, -24 * M, 700 * M); ctx.stroke();
  ctx.restore();
}

// ---- the end: into her eye, the aperture closes on the last bass hits -----
let END_HITS = null;
function endHits() {
  if (END_HITS) return END_HITS;
  const hits = []; let last = -9;
  for (let t = 168.0; t < 174.2; t += 0.01) { const v = envAt('bflux', t); if (v > 0.55 && envAt('bflux', t) >= envAt('bflux', t - 0.01) && envAt('bflux', t) >= envAt('bflux', t + 0.01) && t - last > 0.3) { hits.push(t); last = t; } }
  if (hits.length < 4) { hits.length = 0; for (let b = 0; b < 8; b++) hits.push(168 + b * BEAT); }
  return (END_HITS = hits);
}
function apertureOpen(t) {
  if (t < 168.0) return 1;
  const hits = endHits(); let n = 0; for (const h of hits) if (t >= h) n++;
  const step = 1 / (hits.length + 2);
  let o = 1 - n * step; // stepwise, with a quick ease at each hit
  const lh = hits.filter(h => h <= t).pop(); if (lh != null) o += step * (1 - easeOut((t - lh) / 0.08));
  if (t > 174.0) o = Math.min(o, lerp(o, 0, easeIn(clamp((t - 174.0) / 2.4))));
  return clamp(o);
}
function drawAperture(ctx, cx, cy, R, open, rot) {
  // six blades: opening is a hexagon of radius r, blades fill the ring outside it
  const r = R * open, n = 6;
  ctx.save(); ctx.fillStyle = '#060607';
  ctx.beginPath(); ctx.rect(cx - R * 3, cy - R * 3, R * 6, R * 6);
  for (let i = n; i >= 0; i--) { const a = rot + i / n * TAU; const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r; if (i === n) ctx.moveTo(px, py); else ctx.lineTo(px, py); }
  ctx.fill('evenodd');
  // blade edges: each blade's leading edge sweeps out from a hole vertex, catching a little light
  for (let i = 0; i < n; i++) { const a = rot + i / n * TAU; const vx = cx + Math.cos(a) * r, vy = cy + Math.sin(a) * r;
    const g = ctx.createLinearGradient(vx, vy, cx + Math.cos(a + 0.6) * R * 2, cy + Math.sin(a + 0.6) * R * 2); g.addColorStop(0, 'rgba(150,150,165,0.55)'); g.addColorStop(1, 'rgba(60,60,70,0)');
    ctx.strokeStyle = g; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(vx, vy); ctx.quadraticCurveTo(cx + Math.cos(a + 0.35) * (r + R) * 0.9, cy + Math.sin(a + 0.35) * (r + R) * 0.9, cx + Math.cos(a + 0.9) * R * 2.6, cy + Math.sin(a + 0.9) * R * 2.6); ctx.stroke(); }
  const sh = ctx.createRadialGradient(cx - R * 0.4, cy - R * 0.5, R * 0.1, cx, cy, R * 1.6); sh.addColorStop(0, 'rgba(70,70,80,0.18)'); sh.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = sh; ctx.beginPath(); ctx.rect(cx - R * 3, cy - R * 3, R * 6, R * 6);
  for (let i = n; i >= 0; i--) { const a = rot + i / n * TAU; const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r; if (i === n) ctx.moveTo(px, py); else ctx.lineTo(px, py); }
  ctx.fill('evenodd');
  ctx.restore();
}
function drawEnd(ctx, W, H, t) {
  const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0);
  const g = sheetGeom(95 * M, 250 * M, 890 * M);
  const r36 = sheetFrameRect(g, 36), c36 = [r36[0] + r36[2] / 2, r36[1] + r36[3] / 2];
  const zk = easeInOut(clamp((t - T_END) / 2.25));
  // zoom the desk view toward frame 36 until it fills the frame
  const Z = lerp(1, H / r36[3] * 1.02, zk);
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.scale(Z, Z); ctx.translate(-lerp(W / 2, c36[0], zk), -lerp(H / 2, c36[1], zk));
  drawDesk(ctx, W, H, t, g);
  greaseStroke(ctx, circlePts(c36[0], c36[1], r36[2] * 0.78, r36[3] * 0.66, 1, 60), 9 * M, 0.95, 36);
  { const tp = titleMargin(g); greaseText(ctx, 'SHOULD I ?', tp[0], tp[1], tp[2], 1); }
  ctx.restore();
  // crossfade to the living eye (full resolution) once it fills the frame
  const live = smooth(169.6, 170.4, t);
  if (live > 0) {
    ctx.save(); ctx.globalAlpha = live; ctx.fillStyle = '#1b1210'; ctx.fillRect(0, 0, W, H);
    ctx.translate(0, 0); ctx.scale(W / SW, W / SW * 1); ctx.translate(0, (H / (W / SW) - SH) / 2);
    drawEye(ctx, SW / 2, SH * 0.5, 820, { t, ocean: 1, pupil: 0.36 + 0.1 * envAt('bass', t) });
    ctx.restore();
  }
  // aperture blades close on the bass hits, centred on the pupil
  const op = apertureOpen(t);
  if (t >= T_END) drawAperture(ctx, W / 2, H / 2 - 0.03 * 820 * (W / SW), H * 0.62, op, 0.3 + (1 - op) * 0.9);
  grainOver(ctx, W, H, t, 0.12);
  // after: black, the counter reads "?"
  const bk = smooth(176.2, 176.6, t); if (bk > 0) { ctx.fillStyle = `rgba(0,0,0,${bk})`; ctx.fillRect(0, 0, W, H); }
  if (t > 176.6 && t < 179.6) drawInfo(ctx, M, { t, needle: -1.1, counter: '?', speed: ' ', infoAlpha: smooth(176.8, 177.6, t) });
  if (t >= 179.56) drawFinalFrame(ctx, W, H, t);
}

// ---- the last vocal line: the counter goes past the roll (37), the door is open, focus locks, one last click
function drawFinalFrame(ctx, W, H, t) {
  const M = W / VW;
  const open = smooth(179.56, 179.72, t), out = smooth(181.1, 182.0, t);
  const lock = smooth(179.62, 179.92, t);                       // the words bring it into focus
  let echo = 0; for (const e of [180.25, 180.55, 180.9]) echo = Math.max(echo, pulse(t, e, 0.02, 0.2) * 0.5);
  const cam = { x: jit(t * 1.1, 31, 2), y: jit(t * 0.9, 32, 2), rot: 0, zoom: 1 + 0.04 * smooth(179.6, 181.8, t) + 0.01 * echo, blur: 0.4 * (1 - lock) };
  shootScene(M, cam, (c, S) => drawDoorway(c, t, {}));
  const d = t - T_CLICK; const black = d >= 0 && d < 0.12 ? (d < 0.055 ? 1 : 1 - smooth(0.055, 0.115, d)) : 0;
  composeVF(ctx, W, H, { t, split: 34 * (1 - lock), blur: cam.blur, prism: 0.3 * (1 - lock), alpha: open * (1 - out), bright: 1 + 0.1 * echo,
    black, counter: 37, counterPrev: '?', roll: (t - T_LAST) / 0.14, speed: '1/60', needle: lerp(-1.1, 0, lock) + 0.12 * echo, infoAlpha: 1 - out });
}

// ---- covers ------------------------------------------------------------------
function drawSheetFinal(ctx, W, H, yTop) { // the finished contact sheet: circle on 36 + the title in the margin, no hand
  const M = W / VW; ctx.setTransform(1, 0, 0, 1, 0, 0);
  const g = sheetGeom(95 * M, (yTop == null ? 250 : yTop) * M, 890 * M); drawDesk(ctx, W, H, 0, g);
  const r36 = sheetFrameRect(g, 36), c36 = [r36[0] + r36[2] / 2, r36[1] + r36[3] / 2];
  greaseStroke(ctx, circlePts(c36[0], c36[1], r36[2] * 0.78, r36[3] * 0.66, 1, 60), 9 * M, 0.95, 36);
  const tp = titleMargin(g); greaseText(ctx, 'SHOULD I ?', tp[0], tp[1], tp[2], 1);
  grainOver(ctx, W, H, 0, 0.12);
}

function drawExpoStill(ctx, W, H, k) { // one exposure as a print: full frame, film grain
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  const sc = Math.max(W / SW, H / SH); ctx.save(); ctx.translate(W / 2, H / 2); ctx.scale(sc, sc); ctx.translate(-SW / 2, -SH / 2);
  drawExpo(ctx, k, expoTime(k) - 0.02, sc); ctx.restore();
  const vg = ctx.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.75); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.45)'); ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
  overlayTile(ctx, noiseTile(256, 11, 60, 'fg'), W, H, k * 31, k * 17, 0.16, 'overlay');
}
