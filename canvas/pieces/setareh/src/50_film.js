// ---- the film: grain that settles as the exposure gathers light, a vignette, the shutter closing ----
// Grain: a live long exposure is noisy at first and cleaner the more light it has (noise ~ 1/sqrt(light)).
// When the shutter closes the photograph is done: its grain stops moving.
function drawGrain(X, t, o = {}) {
  const u = o.u != null ? o.u : expoU(X, t), done = o.still || t >= X.close;
  const amt = done ? 0.085 : lerp(0.26, 0.10, Math.sqrt(u));
  const fr = done ? 7 : Math.round(t * FPS);
  const tile = noiseTile(256, 5, 70, 'grain5');
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  overlayTile(ctx, tile, PXW, PXH, Math.floor(hsh(fr, 1) * 256), Math.floor(hsh(fr, 2) * 256), amt, 'overlay');
  ctx.restore();
}
function drawVignette() {
  ctx.save(); stage();
  const g = ctx.createRadialGradient(W / 2, 760, 300, W / 2, 900, 1250);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.42)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  ctx.restore();
}
// The shutter closing on the 32nd snare: the curtain crosses in two frames.
function drawShutter(X, t) {
  const k = (t - X.close) * FPS;
  if (k < 0 || k >= 2) return;
  ctx.save(); stage(); ctx.fillStyle = '#000'; ctx.globalAlpha = k < 1 ? 0.78 : 0.3; ctx.fillRect(0, 0, W, H); ctx.restore();
}
