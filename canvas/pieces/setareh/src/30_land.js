// ---- the land: the range and its cone, the valley, the hill they sit on ----------------------
// It never moves, so it is drawn whole on every frame; only the light on it changes (the exposure develops,
// the moon or the dawn reaches the snow).
const RIDGE = (() => { const p = []; for (let x = -10; x <= W + 10; x += 3) p.push([x, ridgeY(x)]); return p; })();
// the land's whole shape, down to the bottom of the frame: whatever is drawn on it lies behind the two of them
const LAND_CLIP = (() => { const p = new Path2D(); p.moveTo(-10, H + 10); for (const [x, y] of RIDGE) p.lineTo(x, y); p.lineTo(W + 10, H + 10); p.closePath(); return p; })();
function drawLand(X, t, o = {}) {
  const u = o.u != null ? o.u : expoU(X, t), dev = develop(u);
  const m = integ(X, X.M, t) / X.Tx, d = integ(X, X.D, t) / X.Tx;
  ctx.save();
  // the range: dark, a breath lighter than the hill in front (air between)
  const range = new Path2D();
  range.moveTo(-10, 1260);
  for (const [x, y] of RIDGE) range.lineTo(x, y);
  range.lineTo(W + 10, 1260); range.closePath();
  const air = tone(0.03 * dev + 0.05 * m + 0.10 * d);
  ctx.fillStyle = `rgb(${Math.round(6 + 40 * air)},${Math.round(8 + 46 * air)},${Math.round(14 + 64 * air)})`;
  ctx.fill(range);
  // the cone's snow: a cap, lit by whatever lights the sky -- the city a little, the moon, the dawn's alpenglow
  ctx.save(); ctx.clip(range);
  const cap = new Path2D();
  cap.moveTo(CONE.x - 92, CONE.y + 92 * CONE.k + 8);
  for (let i = 0; i <= 16; i++) {
    const x = CONE.x - 92 + i * 11.5, tooth = 6 * Math.sin(i * 2.3) + 9 * (i % 2);
    cap.lineTo(x, CONE.y + Math.abs(x - CONE.x) * CONE.k + 30 + tooth);
  }
  cap.lineTo(CONE.x + 92, CONE.y + 92 * CONE.k + 8);
  for (let i = 16; i >= 0; i--) { const x = CONE.x - 92 + i * 11.5; cap.lineTo(x, ridgeY(x) - 2); }
  cap.closePath();
  const snow = [0.05 * dev + 0.30 * m + 0.55 * d, 0.05 * dev + 0.34 * m + 0.30 * d, 0.07 * dev + 0.44 * m + 0.34 * d];
  ctx.fillStyle = `rgb(${Math.round(255 * tone(snow[0]))},${Math.round(255 * tone(snow[1]))},${Math.round(255 * tone(snow[2]))})`;
  ctx.globalAlpha = 0.9; ctx.fill(cap);
  ctx.restore();
  // the city's floor: dark, under a warm haze that thickens towards the range
  ctx.fillStyle = '#05060a'; ctx.fillRect(-10, 1232, W + 20, 300);
  const hz = ctx.createLinearGradient(0, 1190, 0, 1500);
  hz.addColorStop(0, `rgba(150,88,46,${(0.20 * dev).toFixed(3)})`); hz.addColorStop(0.25, `rgba(110,64,36,${(0.10 * dev).toFixed(3)})`); hz.addColorStop(1, 'rgba(40,24,16,0)');
  ctx.fillStyle = hz; ctx.fillRect(-10, 1190, W + 20, 310);
  ctx.restore();
}
// The hill in front: where the chairs stand. Drawn after the valley's lights.
function drawHill(X, t, o = {}) {
  ctx.save();
  const p = new Path2D();
  p.moveTo(-10, hillY(-10));
  for (let x = -10; x <= W + 10; x += 10) p.lineTo(x, hillY(x));
  p.lineTo(W + 10, H + 10); p.lineTo(-10, H + 10); p.closePath();
  const g = ctx.createLinearGradient(0, 1460, 0, H);
  g.addColorStop(0, '#07080c'); g.addColorStop(0.3, '#040507'); g.addColorStop(1, '#020203');
  ctx.fillStyle = g; ctx.fill(p);
  ctx.restore();
}
