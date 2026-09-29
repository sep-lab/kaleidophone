// ============================================================================
// 20_props: the world he points the camera at. Scene space = 900 x 1350.
// ============================================================================
const SW = 900, SH = 1350;
const WARM = [255, 176, 96], TUNG = [255, 196, 130], COLD = [120, 160, 230], NIGHT = [14, 18, 32];

function vgrad(ctx, x, y, w, h, stops) { const g = ctx.createLinearGradient(0, y, 0, y + h); for (const [k, c] of stops) g.addColorStop(k, c); ctx.fillStyle = g; ctx.fillRect(x, y, w, h); }
function radial(ctx, x, y, r0, r1, stops) { const g = ctx.createRadialGradient(x, y, r0, x, y, r1); for (const [k, c] of stops) g.addColorStop(k, c); return g; }
function glowAt(ctx, x, y, r, c, a) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; drawSprite(ctx, glowSprite(c[0], c[1], c[2]), x, y, r, a); ctx.restore(); }
function bokeh(ctx, x, y, r, c, a) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; drawSprite(ctx, bokehSprite(c[0], c[1], c[2]), x, y, r, a); ctx.restore(); }
function bokehField(ctx, x0, y0, w, h, n, seed, t, pal, rmin, rmax, amp) {
  for (let i = 0; i < n; i++) {
    const hx = hash(seed + i * 3.1), hy = hash(seed + i * 7.7), hr = hash(seed + i * 1.9), hc = hash(seed + i * 5.3);
    const c = pal[Math.floor(hc * pal.length) % pal.length];
    const tw = 0.75 + 0.25 * Math.sin(t * (1.3 + hr * 2) + i);
    bokeh(ctx, x0 + hx * w, y0 + hy * h, lerp(rmin, rmax, hr), c, (amp || 0.5) * tw);
  }
}
function wallTexture(ctx, x, y, w, h, base, seed) {
  ctx.fillStyle = col(base); ctx.fillRect(x, y, w, h);
  ctx.save(); ctx.globalAlpha = 0.05;
  for (let i = 0; i < 60; i++) { ctx.fillStyle = hash(seed + i) > 0.5 ? '#fff' : '#000'; ell(ctx, x + hash(seed + i * 2.2) * w, y + hash(seed + i * 3.3) * h, 20 + hash(i) * 90, 14 + hash(i + 1) * 60); ctx.fill(); }
  ctx.restore();
}

// ---- a panel door with casing. (x,y) top-left of the slab. o: open 0..1, under (light under the door 0..1), marks, peephole
function door(ctx, x, y, w, h, o) {
  o = o || {}; const lamp = o.lamp || [0.25, -0.2]; // key light position (relative)
  // casing
  const cw = w * 0.11;
  ctx.fillStyle = '#2b241f'; ctx.fillRect(x - cw, y - cw, w + cw * 2, h + cw);
  ctx.fillStyle = '#3a312a'; ctx.fillRect(x - cw * 0.82, y - cw * 0.82, w + cw * 1.64, h + cw * 0.82);
  ctx.fillStyle = '#16120f'; ctx.fillRect(x - 3, y - 3, w + 6, h + 3);
  // opening (if ajar): hallway light spills through a vertical slit on the latch side
  const op = o.open || 0;
  if (op > 0) {
    const gw = w * 0.1 * op;
    vgrad(ctx, x + w - gw, y, gw, h, [[0, col(TUNG, 0.85)], [0.5, col(WARM, 0.95)], [1, col(TUNG, 0.7)]]);
  }
  // slab
  const sw = w * (1 - 0.1 * op);
  const g = ctx.createLinearGradient(x, y, x + sw, y + h);
  g.addColorStop(0, '#5a4c40'); g.addColorStop(0.55, '#3d332b'); g.addColorStop(1, '#231d18');
  ctx.fillStyle = g; ctx.fillRect(x, y, sw, h);
  // panels (2 x 3)
  const px = sw * 0.12, py = h * 0.06, pw = (sw - px * 3) / 2, ph = [h * 0.2, h * 0.36, h * 0.24];
  let yy = y + py;
  for (let r = 0; r < 3; r++) {
    for (let c2 = 0; c2 < 2; c2++) {
      const xx = x + px + c2 * (pw + px);
      ctx.fillStyle = 'rgba(0,0,0,0.28)'; ctx.fillRect(xx, yy, pw, ph[r]);
      ctx.fillStyle = 'rgba(255,230,200,0.07)'; ctx.fillRect(xx + 6, yy + 6, pw - 12, ph[r] - 12);
      ctx.strokeStyle = 'rgba(255,225,190,0.12)'; ctx.lineWidth = 3; ctx.strokeRect(xx + 3, yy + 3, pw - 6, ph[r] - 6);
    }
    yy += ph[r] + py * 0.9;
  }
  // knob + plate
  const kx = x + sw * 0.86, ky = y + h * 0.54;
  ctx.fillStyle = '#1c1612'; rrect(ctx, kx - w * 0.025, ky - h * 0.05, w * 0.05, h * 0.1, 4); ctx.fill();
  ctx.fillStyle = radial(ctx, kx - w * 0.01, ky - w * 0.012, 1, w * 0.045, [[0, '#f6d9a0'], [0.35, '#b88a4a'], [1, '#3a2a18']]);
  ctx.beginPath(); ctx.arc(kx, ky, w * 0.04, 0, TAU); ctx.fill();
  // peephole
  if (o.peephole !== false) { const px2 = x + sw / 2, py2 = y + h * 0.3; ctx.fillStyle = radial(ctx, px2, py2, 1, 12, [[0, o.peepLight ? '#ffe7b0' : '#0a0806'], [0.5, '#8b6a3c'], [1, '#2a2018']]); ctx.beginPath(); ctx.arc(px2, py2, 11, 0, TAU); ctx.fill(); }
  // light under the door
  const u = o.under == null ? 0.6 : o.under;
  if (u > 0) {
    ctx.fillStyle = col(TUNG, 0.95 * u); ctx.fillRect(x + 4, y + h - 5, sw - 8, 5);
    glowAt(ctx, x + sw / 2, y + h + 6, w * 0.55, WARM, 0.35 * u);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    const fl = ctx.createLinearGradient(0, y + h, 0, y + h + h * 0.18); fl.addColorStop(0, col(WARM, 0.35 * u)); fl.addColorStop(1, col(WARM, 0));
    ctx.fillStyle = fl; ctx.beginPath(); ctx.moveTo(x, y + h); ctx.lineTo(x + sw, y + h); ctx.lineTo(x + sw + w * 0.25, y + h + h * 0.18); ctx.lineTo(x - w * 0.25, y + h + h * 0.18); ctx.fill();
    ctx.restore();
  }
  // growth marks on the casing (latch side)
  if (o.marks) pencilMarks(ctx, x + w + cw * 0.15, y, h, o.marks);
  return { kx, ky };
}
function pencilMarks(ctx, x, y, h, m) {
  // m: {n: number of marks, fresh: index of the newest (drawn in over m.draw 0..1)}
  const n = m.n || 7;
  ctx.save(); ctx.lineCap = 'round';
  for (let i = 0; i < n; i++) {
    const my = y + h * (0.62 - i * 0.055 - hash(i * 3.3) * 0.012);
    const fresh = i === n - 1 && m.draw != null;
    const L = 46 * (fresh ? clamp(m.draw) : 1);
    ctx.strokeStyle = fresh ? 'rgba(30,26,24,0.95)' : 'rgba(40,34,30,0.75)'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(x, my); ctx.lineTo(x + L, my + 1); ctx.stroke();
    // tiny scribbled "date" marks
    if (!fresh || m.draw > 0.9) { ctx.lineWidth = 1.6; ctx.beginPath(); for (let k = 0; k < 5; k++) { const sx = x + 52 + k * 7; ctx.moveTo(sx, my - 6); ctx.lineTo(sx + 3 + hash(i + k) * 3, my + 4 - hash(k * 2 + i) * 6); } ctx.stroke(); }
  }
  ctx.restore();
}

// ---- floor from above: boards, a worn strip, his shoes
function floorTop(ctx, o) {
  o = o || {};
  vgrad(ctx, 0, 0, SW, SH, [[0, '#4a3a2c'], [1, '#2a2019']]);
  const bw = 118;
  for (let i = -1; i < SW / bw + 1; i++) {
    const x = i * bw + 20;
    ctx.fillStyle = `rgba(${90 + hash(i) * 30},${66 + hash(i + 1) * 20},${44 + hash(i + 2) * 14},0.55)`; ctx.fillRect(x, 0, bw - 4, SH);
    ctx.fillStyle = 'rgba(10,6,4,0.8)'; ctx.fillRect(x + bw - 4, 0, 4, SH);
    // grain
    ctx.strokeStyle = 'rgba(20,12,8,0.18)'; ctx.lineWidth = 1.5;
    for (let k = 0; k < 7; k++) { const gx = x + 10 + hash(i * 7 + k) * (bw - 24); ctx.beginPath(); ctx.moveTo(gx, 0); for (let yy = 0; yy <= SH; yy += 90) ctx.lineTo(gx + Math.sin(yy * 0.01 + k + i) * 6, yy); ctx.stroke(); }
    // board ends
    for (let k = 0; k < 3; k++) { const ey = (hash(i * 11 + k) * SH); ctx.fillStyle = 'rgba(10,6,4,0.7)'; ctx.fillRect(x, ey, bw - 4, 3); }
  }
  // the worn path: a paler strip from the shoes toward the door (top)
  ctx.save(); ctx.globalCompositeOperation = 'screen';
  const wg = ctx.createLinearGradient(SW * 0.5 - 170, 0, SW * 0.5 + 170, 0); wg.addColorStop(0, 'rgba(180,150,110,0)'); wg.addColorStop(0.5, 'rgba(180,150,110,0.22)'); wg.addColorStop(1, 'rgba(180,150,110,0)');
  ctx.fillStyle = wg; ctx.fillRect(SW * 0.5 - 170, 0, 340, SH);
  ctx.restore();
  // door threshold light at the top edge
  if (o.doorLight) { glowAt(ctx, SW / 2, -20, 520, WARM, 0.5 * o.doorLight); ctx.fillStyle = col(TUNG, 0.8 * o.doorLight); ctx.fillRect(SW * 0.18, 0, SW * 0.64, 7); }
  // shoes
  shoesTop(ctx, SW * 0.5, SH * 0.78, 1, o.t || 0);
  if (o.phone) phone(ctx, SW * 0.78, SH * 0.84, 92, 180, 0.35, { down: true });
}
function shoesTop(ctx, x, y, s, t) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  for (const sg of [-1, 1]) {
    ctx.save(); ctx.translate(sg * 78, sg * 18); ctx.rotate(sg * 0.08);
    ctx.fillStyle = '#0d0c0e'; blobPath(ctx, [[0, -150], [44, -120], [52, -30], [46, 90], [30, 150], [-30, 150], [-46, 90], [-52, -30], [-44, -120]]); ctx.fill();
    ctx.fillStyle = '#e8e2d6'; blobPath(ctx, [[0, -140], [36, -115], [42, -40], [-42, -40], [-36, -115]]); ctx.fill(); // toe cap
    ctx.strokeStyle = '#e8e2d6'; ctx.lineWidth = 5; for (let k = 0; k < 4; k++) { ctx.beginPath(); ctx.moveTo(-20, -20 + k * 22); ctx.lineTo(20, -14 + k * 22); ctx.stroke(); }
    ctx.restore();
  }
  ctx.restore();
}

// ---- smartphone. (x,y) centre. o: down (face-down), screen: 'off'|'glow'|'type'|'call', typed 0..1, del 0..1, callPulse, press
function phone(ctx, x, y, w, h, rot, o) {
  o = o || {};
  ctx.save(); ctx.translate(x, y); ctx.rotate(rot || 0);
  ctx.fillStyle = '#0b0b0e'; rrect(ctx, -w / 2, -h / 2, w, h, w * 0.16); ctx.fill();
  ctx.strokeStyle = 'rgba(160,160,175,0.35)'; ctx.lineWidth = 2; rrect(ctx, -w / 2 + 1, -h / 2 + 1, w - 2, h - 2, w * 0.16); ctx.stroke();
  if (o.down) { // camera bump
    ctx.fillStyle = '#18181d'; rrect(ctx, -w * 0.38, -h * 0.44, w * 0.42, w * 0.42, w * 0.1); ctx.fill();
    ctx.fillStyle = '#050507'; for (const [a, b] of [[-0.25, -0.34], [-0.07, -0.34], [-0.25, -0.2]]) { ctx.beginPath(); ctx.arc(w * a, h * b, w * 0.06, 0, TAU); ctx.fill(); }
    if (o.edgeGlow) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.shadowColor = 'rgba(140,190,255,1)'; ctx.shadowBlur = 30 * o.edgeGlow; ctx.strokeStyle = `rgba(140,190,255,${0.5 * o.edgeGlow})`; ctx.lineWidth = 3; rrect(ctx, -w / 2, -h / 2, w, h, w * 0.16); ctx.stroke(); ctx.restore(); }
    ctx.restore(); return;
  }
  const sx = -w / 2 + w * 0.05, sy = -h / 2 + w * 0.05, swd = w * 0.9, sh = h - w * 0.1;
  const scr = o.screen || 'off';
  if (scr === 'off') { ctx.fillStyle = '#060608'; rrect(ctx, sx, sy, swd, sh, w * 0.12); ctx.fill(); ctx.fillStyle = 'rgba(255,255,255,0.05)'; ctx.beginPath(); ctx.moveTo(sx, sy + sh * 0.1); ctx.lineTo(sx + swd * 0.6, sy); ctx.lineTo(sx + swd, sy); ctx.lineTo(sx, sy + sh * 0.5); ctx.fill(); }
  else {
    const g = ctx.createLinearGradient(0, sy, 0, sy + sh); g.addColorStop(0, '#1d2536'); g.addColorStop(1, '#0c111c');
    ctx.fillStyle = g; rrect(ctx, sx, sy, swd, sh, w * 0.12); ctx.fill();
    ctx.save(); rrect(ctx, sx, sy, swd, sh, w * 0.12); ctx.clip();
    if (scr === 'type' || scr === 'call') {
      // an avatar circle and one "name" bar (no words, just shapes)
      ctx.fillStyle = 'rgba(220,225,240,0.9)'; ctx.beginPath(); ctx.arc(0, sy + sh * 0.12, w * 0.09, 0, TAU); ctx.fill();
      ctx.fillStyle = 'rgba(220,225,240,0.5)'; rrect(ctx, -w * 0.18, sy + sh * 0.19, w * 0.36, w * 0.035, 4); ctx.fill();
    }
    if (scr === 'type') {
      // message draft: blocks appear (typed 0..1) then vanish from the end (del 0..1)
      const words = 11; const shown = Math.floor(clamp(o.typed || 0) * words + 1e-6); const dele = Math.floor(clamp(o.del || 0) * words + 1e-6);
      const vis = Math.max(0, shown - dele);
      let wx = sx + swd * 0.1, wy = sy + sh * 0.74; const lh = w * 0.075;
      ctx.fillStyle = 'rgba(40,120,255,0.95)'; rrect(ctx, sx + swd * 0.06, wy - lh * 0.7, swd * 0.88, lh * 3.3, w * 0.05); ctx.globalAlpha = vis > 0 ? 0.28 : 0.12; ctx.fill(); ctx.globalAlpha = 1;
      for (let i = 0; i < vis; i++) { const ww = w * (0.08 + hash(i * 1.7) * 0.14); if (wx + ww > sx + swd * 0.9) { wx = sx + swd * 0.1; wy += lh * 1.1; } ctx.fillStyle = 'rgba(235,240,255,0.92)'; rrect(ctx, wx, wy, ww, lh * 0.55, 3); ctx.fill(); wx += ww + w * 0.025; }
      // caret
      if ((o.t || 0) % 0.6 < 0.33) { ctx.fillStyle = 'rgba(120,180,255,1)'; ctx.fillRect(wx, wy - 2, 3, lh * 0.7); }
      // keyboard glow
      ctx.fillStyle = 'rgba(255,255,255,0.06)'; ctx.fillRect(sx, sy + sh * 0.84, swd, sh * 0.16);
    }
    if (scr === 'call') {
      const cp = o.callPulse || 0, pr = o.press || 0;
      const cy2 = sy + sh * 0.78, cr = w * 0.12;
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (let k = 0; k < 3; k++) { const ph = ((o.t || 0) * 0.9 + k / 3) % 1; ctx.strokeStyle = `rgba(90,230,140,${0.5 * (1 - ph) * (0.4 + cp)})`; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(0, cy2, cr * (1 + ph * 1.6 + pr * 3), 0, TAU); ctx.stroke(); }
      ctx.restore();
      ctx.fillStyle = `rgba(${lerp(40, 120, pr)},${lerp(200, 255, pr)},${lerp(100, 170, pr)},1)`; ctx.beginPath(); ctx.arc(0, cy2, cr * (1 + 0.12 * cp), 0, TAU); ctx.fill();
      ctx.save(); ctx.translate(0, cy2); ctx.rotate(-0.7); ctx.fillStyle = '#fff'; rrect(ctx, -cr * 0.45, -cr * 0.13, cr * 0.9, cr * 0.26, cr * 0.12); ctx.fill(); ctx.fillRect(-cr * 0.45, -cr * 0.2, cr * 0.18, cr * 0.35); ctx.fillRect(cr * 0.27, -cr * 0.2, cr * 0.18, cr * 0.35); ctx.restore();
    }
    ctx.restore();
  }
  ctx.restore();
}

// ---- windows ------------------------------------------------------------
function nightStreet(ctx, x, y, w, h, t, o) {
  o = o || {};
  vgrad(ctx, x, y, w, h, [[0, '#0a1020'], [0.6, '#16213a'], [1, '#233152']]);
  // far buildings with lit windows (out of focus)
  ctx.fillStyle = '#0b1120';
  for (let i = 0; i < 6; i++) { const bx = x + i * w / 5 - 30 + hash(i) * 40, bw = w / 5 + 30, bh = h * (0.35 + hash(i + 3) * 0.3); ctx.fillRect(bx, y + h - bh, bw, bh); }
  bokehField(ctx, x, y + h * 0.35, w, h * 0.55, 18, 3.3, t, [[255, 190, 110], [255, 160, 90], [200, 220, 255]], 10, 26, 0.35);
  // street lamp (the key light outside)
  if (o.lamp !== false) { const lx = x + w * (o.lampX || 0.72), ly = y + h * 0.22; bokeh(ctx, lx, ly, 70, [255, 196, 120], 0.8); glowAt(ctx, lx, ly, 260, [255, 170, 90], 0.45); }
}
function snowfall(ctx, x, y, w, h, t, n, seed, big) {
  for (let i = 0; i < n; i++) {
    const hs = hash(seed + i), sp = 30 + hs * 60, sz = big ? 3 + hs * 9 : 1.2 + hs * 3;
    const fx = x + ((hash(seed + i * 2.1) * w + Math.sin(t * 0.7 + i) * 18 + t * 8) % w + w) % w;
    const fy = y + ((hash(seed + i * 3.7) * h + t * sp) % h);
    ctx.fillStyle = `rgba(235,240,255,${big ? 0.35 : 0.75})`; ctx.beginPath(); ctx.arc(fx, fy, sz, 0, TAU); ctx.fill();
  }
}
function rainOnGlass(ctx, x, y, w, h, t, o) {
  o = o || {}; const n = o.n || 90;
  ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  // streaks running down
  for (let i = 0; i < 26; i++) {
    const hx = hash(i * 4.4 + 1), sp = 40 + hash(i * 2.3) * 140; const cyc = (t * sp / h + hash(i * 9.1)) % 1;
    const sx = x + hx * w, sy = y + cyc * (h + 200) - 100, L = 60 + hash(i) * 160;
    const g = ctx.createLinearGradient(0, sy - L, 0, sy); g.addColorStop(0, 'rgba(200,220,255,0)'); g.addColorStop(1, 'rgba(200,220,255,0.35)');
    ctx.strokeStyle = g; ctx.lineWidth = 2.5 + hash(i) * 3; ctx.beginPath(); ctx.moveTo(sx + Math.sin(i) * 4, sy - L); ctx.quadraticCurveTo(sx - 5, sy - L / 2, sx, sy); ctx.stroke();
    ctx.fillStyle = 'rgba(225,235,255,0.55)'; ell(ctx, sx, sy, 4 + hash(i) * 3, 5 + hash(i) * 3); ctx.fill();
  }
  // static droplets
  for (let i = 0; i < n; i++) {
    const dx = x + hash(i * 1.37 + 7) * w, dy = y + hash(i * 2.71 + 3) * h, r = 2 + hash(i * 5.1) * 6;
    ctx.fillStyle = 'rgba(10,14,24,0.45)'; ell(ctx, dx, dy + r * 0.3, r, r); ctx.fill();
    ctx.fillStyle = 'rgba(210,225,255,0.5)'; ell(ctx, dx - r * 0.3, dy - r * 0.3, r * 0.35, r * 0.35); ctx.fill();
  }
  ctx.restore();
}
function windowFrame(ctx, x, y, w, h, o) {
  o = o || {};
  const fw = o.frame || 26;
  ctx.fillStyle = o.frameCol || '#15110f';
  ctx.fillRect(x - fw, y - fw, w + fw * 2, fw); ctx.fillRect(x - fw, y + h, w + fw * 2, fw * 1.6);
  ctx.fillRect(x - fw, y, fw, h); ctx.fillRect(x + w, y, fw, h);
  if (o.cross !== false) { ctx.fillRect(x + w / 2 - fw * 0.35, y, fw * 0.7, h); ctx.fillRect(x, y + h * 0.45 - fw * 0.35, w, fw * 0.7); }
}
function breathFog(ctx, x, y, r, a) {
  if (a <= 0.01) return;
  ctx.save(); ctx.globalCompositeOperation = 'screen';
  ctx.fillStyle = radial(ctx, x, y, 0, r, [[0, `rgba(210,220,235,${0.55 * a})`], [0.6, `rgba(200,210,230,${0.3 * a})`], [1, 'rgba(200,210,230,0)']]);
  ell(ctx, x, y, r, r * 0.8); ctx.fill(); ctx.restore();
}

// ---- funfair / sunset / moon ---------------------------------------------
function ferrisWheel(ctx, cx, cy, R, t, o) {
  o = o || {}; const rot = t * 0.08 + (o.rot || 0);
  ctx.save(); ctx.translate(cx, cy);
  ctx.strokeStyle = 'rgba(30,24,40,0.9)'; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(0, 0, R, 0, TAU); ctx.stroke(); ctx.beginPath(); ctx.arc(0, 0, R * 0.93, 0, TAU); ctx.stroke();
  ctx.lineWidth = 3; for (let i = 0; i < 16; i++) { const a = rot + i / 16 * TAU; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a) * R, Math.sin(a) * R); ctx.stroke(); }
  // legs
  ctx.lineWidth = 12; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-R * 0.45, R * 1.6); ctx.moveTo(0, 0); ctx.lineTo(R * 0.45, R * 1.6); ctx.stroke();
  // gondolas
  ctx.fillStyle = 'rgba(20,16,28,0.95)';
  for (let i = 0; i < 12; i++) { const a = rot + i / 12 * TAU; const gx = Math.cos(a) * R, gy = Math.sin(a) * R; rrect(ctx, gx - R * 0.05, gy + 4, R * 0.1, R * 0.08, 5); ctx.fill(); }
  // bulbs (bokeh-ish)
  const pal = [[255, 205, 120], [255, 120, 150], [140, 210, 255]];
  for (let i = 0; i < 48; i++) { const a = rot + i / 48 * TAU; const on = 0.6 + 0.4 * Math.sin(t * 5 + i * 0.9); bokeh(ctx, Math.cos(a) * R, Math.sin(a) * R, o.bulb || 16, pal[i % 3], 0.55 * on * (o.bright || 1)); }
  for (let i = 0; i < 16; i++) { const a = rot + i / 16 * TAU; for (let k = 1; k < 4; k++) bokeh(ctx, Math.cos(a) * R * k / 4, Math.sin(a) * R * k / 4, (o.bulb || 16) * 0.7, pal[(i + k) % 3], 0.3 * (o.bright || 1)); }
  glowAt(ctx, 0, 0, R * 1.5, [255, 150, 120], 0.25 * (o.bright || 1));
  ctx.restore();
}
function sunsetSky(ctx, o) {
  o = o || {}; const sunY = o.sunY || 0.62, sink = o.sink || 0;
  vgrad(ctx, 0, 0, SW, SH, [[0, '#2a2a4a'], [0.35, '#7a4a5a'], [0.55, '#e0785a'], [0.62, '#ffb070'], [0.66, '#ffcf8a'], [1, '#3a2430']]);
  const sy = SH * (sunY + sink * 0.05);
  glowAt(ctx, SW * 0.5, sy, 520, [255, 150, 80], 0.8);
  ctx.fillStyle = 'rgba(255,236,190,1)'; ctx.beginPath(); ctx.arc(SW * 0.5, sy, 70, 0, TAU); ctx.fill();
  // ground: road to the horizon
  const hz = SH * 0.66;
  ctx.fillStyle = '#1c1219'; ctx.fillRect(0, hz, SW, SH - hz);
  ctx.fillStyle = '#2d1c22'; ctx.beginPath(); ctx.moveTo(SW * 0.47, hz); ctx.lineTo(SW * 0.53, hz); ctx.lineTo(SW * 0.95, SH); ctx.lineTo(SW * 0.05, SH); ctx.fill();
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; const rg = ctx.createLinearGradient(0, hz, 0, SH); rg.addColorStop(0, 'rgba(255,170,90,0.55)'); rg.addColorStop(1, 'rgba(255,170,90,0)'); ctx.fillStyle = rg; ctx.beginPath(); ctx.moveTo(SW * 0.47, hz); ctx.lineTo(SW * 0.53, hz); ctx.lineTo(SW * 0.8, SH); ctx.lineTo(SW * 0.2, SH); ctx.fill(); ctx.restore();
  // poles
  ctx.strokeStyle = '#140c12'; ctx.lineWidth = 5;
  for (let i = 0; i < 5; i++) { const k = Math.pow(i / 5, 1.6); const px = lerp(SW * 0.56, SW * 0.98, k), ph = lerp(40, 420, k); ctx.beginPath(); ctx.moveTo(px, hz + ph * 0.25); ctx.lineTo(px, hz - ph * 0.9); ctx.stroke(); }
  // clipped cloud strips
  ctx.fillStyle = 'rgba(120,60,80,0.45)'; for (let i = 0; i < 5; i++) { ell(ctx, SW * hash(i * 3), SH * (0.42 + hash(i) * 0.14), 160 + hash(i + 2) * 200, 10 + hash(i + 4) * 8); ctx.fill(); }
}
function moonSky(ctx, phase, t, o) {
  o = o || {};
  vgrad(ctx, 0, 0, SW, SH, [[0, '#04060d'], [0.6, '#0b1224'], [1, '#18223a']]);
  for (let i = 0; i < 140; i++) { const a = 0.3 + hash(i * 7.3) * 0.7 * (0.7 + 0.3 * Math.sin(t * 3 + i)); ctx.fillStyle = `rgba(230,235,255,${a * 0.7})`; ctx.fillRect(hash(i * 1.3) * SW, hash(i * 2.9) * SH * 0.7, 1.6, 1.6); }
  const mx = SW * (o.mx || 0.66), my = SH * (o.my || 0.2), mr = o.mr || 78;
  glowAt(ctx, mx, my, mr * 5, [180, 200, 255], 0.35);
  // moon disc with phase: lit fraction via two ellipses
  ctx.save(); ctx.beginPath(); ctx.arc(mx, my, mr, 0, TAU); ctx.clip();
  ctx.fillStyle = '#0d1222'; ctx.fillRect(mx - mr, my - mr, mr * 2, mr * 2);
  ctx.fillStyle = radial(ctx, mx - mr * 0.3, my - mr * 0.3, 2, mr * 1.3, [[0, '#fbf6e6'], [1, '#c9c3b2']]);
  // phase: 0 new .. 0.5 full; waxing lit on the right
  const p = clamp(phase, 0, 1); const lit = p <= 0.5 ? p * 2 : (1 - p) * 2; // 0..1
  ctx.beginPath(); ctx.arc(mx, my, mr, -Math.PI / 2, Math.PI / 2); // right half
  const k = 1 - 2 * lit; ctx.ellipse(mx, my, Math.abs(k) * mr, mr, 0, Math.PI / 2, -Math.PI / 2, k > 0);
  ctx.fill();
  ctx.fillStyle = 'rgba(120,115,100,0.25)'; for (let i = 0; i < 7; i++) { ell(ctx, mx + (hash(i) - 0.5) * mr * 1.2, my + (hash(i + 3) - 0.5) * mr * 1.2, 6 + hash(i + 5) * 14, 5 + hash(i + 6) * 10); ctx.fill(); }
  ctx.restore();
  // rooftops
  ctx.fillStyle = '#05070c';
  const base = SH * 0.72;
  ctx.beginPath(); ctx.moveTo(0, SH);
  let x = 0; let i = 0; while (x < SW + 40) { const w = 80 + hash(i * 2.2) * 140, hgt = 40 + hash(i * 1.1) * 180; ctx.lineTo(x, base - hgt); if (hash(i + 9) > 0.5) ctx.lineTo(x + w * 0.5, base - hgt - 50); ctx.lineTo(x + w, base - hgt); x += w; i++; }
  ctx.lineTo(SW, SH); ctx.fill();
  // antennas + chimneys
  ctx.strokeStyle = '#05070c'; ctx.lineWidth = 3; for (let k = 0; k < 5; k++) { const ax = hash(k * 4.4) * SW, ay = base - 120 - hash(k) * 80; ctx.beginPath(); ctx.moveTo(ax, ay + 60); ctx.lineTo(ax, ay - 40); ctx.moveTo(ax - 20, ay - 20); ctx.lineTo(ax + 20, ay - 20); ctx.stroke(); }
  // a few lit windows
  for (let k = 0; k < 12; k++) { ctx.fillStyle = `rgba(255,190,110,${0.5 + hash(k) * 0.4})`; ctx.fillRect(hash(k * 3.3) * SW, base - 30 + hash(k * 1.7) * 200, 10, 14); }
}
// ---- the peephole view: fisheye hallway
function peepholeView(ctx, o) {
  o = o || {};
  ctx.fillStyle = '#050403'; ctx.fillRect(0, 0, SW, SH);
  const cx = SW / 2, cy = SH / 2, R = 360;
  ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R, 0, TAU); ctx.clip();
  ctx.fillStyle = radial(ctx, cx, cy - 60, 10, R, [[0, '#8a6f4e'], [0.5, '#4a3a2a'], [1, '#120d09']]); ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
  // bent perspective lines of the corridor
  ctx.strokeStyle = 'rgba(20,14,10,0.7)'; ctx.lineWidth = 4;
  for (const sg of [-1, 1]) { ctx.beginPath(); ctx.moveTo(cx + sg * R * 0.95, cy - R * 0.5); ctx.quadraticCurveTo(cx + sg * R * 0.35, cy - R * 0.1, cx + sg * R * 0.18, cy - R * 0.06); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + sg * R * 0.95, cy + R * 0.55); ctx.quadraticCurveTo(cx + sg * R * 0.35, cy + R * 0.2, cx + sg * R * 0.18, cy + R * 0.12); ctx.stroke(); }
  // the far end: a window, and a wall lamp
  ctx.fillStyle = '#1c150f'; ctx.fillRect(cx - R * 0.18, cy - R * 0.06, R * 0.36, R * 0.18);
  glowAt(ctx, cx - R * 0.55, cy - R * 0.35, 110, [255, 190, 120], 0.8); ctx.fillStyle = '#ffe4b0'; ell(ctx, cx - R * 0.55, cy - R * 0.35, 14, 20); ctx.fill();
  // floor runner
  ctx.fillStyle = 'rgba(90,30,30,0.6)'; ctx.beginPath(); ctx.moveTo(cx - R * 0.08, cy + R * 0.12); ctx.lineTo(cx + R * 0.08, cy + R * 0.12); ctx.quadraticCurveTo(cx + R * 0.35, cy + R * 0.5, cx + R * 0.45, cy + R); ctx.lineTo(cx - R * 0.45, cy + R); ctx.quadraticCurveTo(cx - R * 0.35, cy + R * 0.5, cx - R * 0.08, cy + R * 0.12); ctx.fill();
  if (o.ghost) sheetGhost(ctx, cx + R * 0.05, cy + R * 0.25, R * 0.42, { t: o.t || 0 });
  ctx.restore();
  // lens vignette + glass reflection
  ctx.fillStyle = radial(ctx, cx, cy, R * 0.55, R * 1.02, [[0, 'rgba(0,0,0,0)'], [0.8, 'rgba(0,0,0,0.65)'], [1, 'rgba(0,0,0,1)']]); ctx.beginPath(); ctx.arc(cx, cy, R, 0, TAU); ctx.fill();
  ctx.strokeStyle = 'rgba(255,240,210,0.12)'; ctx.lineWidth = 16; ctx.beginPath(); ctx.arc(cx, cy, R * 0.8, -2.5, -1.6); ctx.stroke();
}
