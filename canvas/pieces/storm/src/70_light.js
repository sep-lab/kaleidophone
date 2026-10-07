// ---------------------------------------------------------------- light
// Two layers lit by one light map: the ground (with the puddles' sky laid on after, since a
// mirror isn't lit, it reflects) and everything standing on it. The light map is the night's
// ambient, a pool under every lamp, the cafés' spill, headlights, his lighter -- and the storm.
let LBUF = null, GBUF = null, OBUF = null, ABUF = null, FRAME = null;
function buffers() {
  if (LBUF && LBUF.width === BW && LBUF.height === BH) return;
  LBUF = mkCanvas(BW, BH); GBUF = mkCanvas(BW, BH); OBUF = mkCanvas(BW, BH); ABUF = mkCanvas(BW, BH); FRAME = mkCanvas(BW, BH);
  LBUF.getContext('2d', { willReadFrequently: true }); FRAME.getContext('2d', { willReadFrequently: true });
}
function ambient(t) {
  const tt = Math.min(t, SONG.stop), clear = step(tt, SONG.fadeA, SONG.fadeB + 2);
  let a = mix3([46, 52, 88], [60, 70, 116], clear);
  return mix3(a, [176, 182, 208], dawnOf(tt));
}
const POOLS = {};
function poolSprite(c) {
  const key = c.map(v => Math.round(v / 8)).join(',');
  if (POOLS[key]) return POOLS[key];
  const s = 96, cv = mkCanvas(s, s), x = cv.getContext('2d'), gr = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  gr.addColorStop(0, css(c, 1)); gr.addColorStop(0.3, css(c, 0.78)); gr.addColorStop(0.65, css(c, 0.3)); gr.addColorStop(1, css(c, 0));
  x.fillStyle = gr; x.fillRect(0, 0, s, s);
  return (POOLS[key] = cv);
}
function lightPass(t, L) {
  const x = LBUF.getContext('2d');
  x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'source-over';
  x.fillStyle = css(ambient(t)); x.fillRect(0, 0, BW, BH);
  x.globalCompositeOperation = 'lighter';
  const k0 = kAt(0);
  for (const l of LIGHTS) {
    if (l.cone) {
      const a = proj(l.cone.from[0], l.cone.from[1]), d = l.cone.dir, n = [-d[1], d[0]], Lc = l.cone.len, sp = l.cone.spread;
      const e1 = proj(l.cone.from[0] + (d[0] + n[0] * sp) * Lc, l.cone.from[1] + (d[1] + n[1] * sp) * Lc), e2 = proj(l.cone.from[0] + (d[0] - n[0] * sp) * Lc, l.cone.from[1] + (d[1] - n[1] * sp) * Lc);
      const far = proj(l.cone.from[0] + d[0] * Lc, l.cone.from[1] + d[1] * Lc);
      const gr = x.createLinearGradient(a[0], a[1], far[0], far[1]);
      gr.addColorStop(0, css(l.c, 0.85 * l.a)); gr.addColorStop(1, css(l.c, 0));
      x.fillStyle = gr; x.beginPath(); x.moveTo(a[0], a[1]); x.lineTo(e1[0], e1[1]); x.lineTo(e2[0], e2[1]); x.closePath(); x.fill();
      continue;
    }
    const c = proj(l.p[0], l.p[1]), R = l.r * k0;
    if (c[0] < -R || c[0] > BW + R || c[1] < -R || c[1] > BH + R) continue;
    x.globalAlpha = clamp(l.a); x.drawImage(poolSprite(l.c), c[0] - R, c[1] - R, R * 2, R * 2); x.globalAlpha = 1;
  }
  // his thunder lights the street under the cloud; the city's lights everything
  const tt = Math.min(t, SONG.stop), fl = Math.max(flicker(t), L.me);
  if (fl > 0.01 && tt > SONG.beatIn - 1) {
    const cg = cloudGround(tt), c = proj(cg[0], cg[1]), R = RAIN_R * 2.4 * k0;
    x.globalAlpha = clamp(fl); x.drawImage(poolSprite([200, 196, 255]), c[0] - R, c[1] - R, R * 2, R * 2); x.globalAlpha = 1;
  }
  if (L.city > 0.01) { x.fillStyle = css([126, 134, 190], Math.min(1, L.city * 0.85)); x.fillRect(0, 0, BW, BH); }
  if (L.me > 0.45) { x.fillStyle = css([110, 108, 160], (L.me - 0.45) * 0.6); x.fillRect(0, 0, BW, BH); }
  x.globalCompositeOperation = 'source-over';
}
// multiply a layer by the light map, keeping its own alpha
function lightLayer(buf, keepAlpha) {
  const x = buf.getContext('2d');
  if (keepAlpha) { const a = ABUF.getContext('2d'); a.globalCompositeOperation = 'copy'; a.drawImage(buf, 0, 0); a.globalCompositeOperation = 'source-over'; }
  x.globalCompositeOperation = 'multiply'; x.drawImage(LBUF, 0, 0);
  if (keepAlpha) { x.globalCompositeOperation = 'destination-in'; x.drawImage(ABUF, 0, 0); }
  x.globalCompositeOperation = 'source-over';
}

// ---------------------------------------------------------------- the console's colour: 5 bits a channel, ordered dither
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(v => (v + 0.5) / 16 - 0.5);
// a tone curve first (shadows lifted, a little contrast through the middle), then 5 bits a channel
const TONE = (() => { const a = new Float32Array(256); for (let v = 0; v < 256; v++) { const u = v / 255, l = Math.pow(u, 0.8); a[v] = 255 * (l + 0.12 * Math.sin(Math.PI * l) * (l - 0.5)); } return a; })();
function dither(g) {
  const im = g.getImageData(0, 0, BW, BH), d = im.data, step8 = 8;
  for (let y = 0; y < BH; y++) {
    const row = (y & 3) * 4;
    for (let x = 0; x < BW; x++) {
      const o = (y * BW + x) * 4, b = BAYER[row + (x & 3)] * step8;
      d[o] = Math.min(255, Math.max(0, Math.round((TONE[d[o]] + b) / step8) * step8));
      d[o + 1] = Math.min(255, Math.max(0, Math.round((TONE[d[o + 1]] + b) / step8) * step8));
      d[o + 2] = Math.min(255, Math.max(0, Math.round((TONE[d[o + 2]] + b) / step8) * step8));
    }
  }
  g.putImageData(im, 0, 0);
}
