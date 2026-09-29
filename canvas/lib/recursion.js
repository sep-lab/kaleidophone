'use strict';
/* ============================================================================
   kaleidophone canvas lib -- recursion.js
   Vector droste and vector kaleidoscope, from SAME AS YOU.

   Recurse by REDRAWING, not by resampling. The first versions copied the
   rendered frame into itself (an image droste, an image kaleidoscope) and went
   blurry at depth. Here every level / every wedge is a full redraw of the scene
   under its own clip and transform, so it stays crisp at any depth. Cost =
   levels (or wedges) x one scene; worth it on a pure-function-of-time piece
   (docs/TECHNIQUES.md #38, #39).

   API
     drosteRedraw(drawScene, { cx, cy, s, u, portal(Z), levels: 3, portalSize, minPx: 6, bg })
       s        scale of one level: the frame drawn at scale s about (cx, cy) lands on the portal.
                For an exact droste, (cx, cy) is that map's fixed point: portal.x / (1 - s), ...
       u        0 = the scene as is, 1 = zoomed one level in (the portal fills the frame) -- a loop
       portal   Z -> Path2D of this level's portal, in virtual units after zooming by Z about (cx, cy);
                it clips the next level
     kaleidoRedraw(drawScene, { n, cx, cy, rot, zoom, amount, buffer })
   drawScene(ctx) must draw the whole frame in virtual units with the current transform.
   Needs: core.js, live.js (ctx, base, W, H, PXW, PXH).
   ============================================================================ */
function drosteRedraw(drawScene, o) {
  const s = o.s, levels = o.levels || 3, minPx = o.minPx || 6;
  const Z0 = Math.pow(1 / s, clamp(o.u || 0));     // u = 0: the scene; u = 1: one level deeper
  let prevClip = null;
  for (let L = 0; L < levels; L++) {
    const Z = Z0 * Math.pow(s, L);
    if (o.portalSize && Z * o.portalSize < minPx) break;
    ctx.save(); base();
    if (prevClip) ctx.clip(prevClip);
    ctx.translate(o.cx, o.cy); ctx.scale(Z, Z); ctx.translate(-o.cx, -o.cy);
    if (L > 0) { ctx.fillStyle = o.bg || '#000'; ctx.fillRect(-2000, -2000, W + 4000, H + 4000); }
    drawScene(ctx);
    ctx.restore();
    prevClip = o.portal(Z);                       // this level's portal becomes the window into the next
  }
}

let KALEIDO_BUF = null;
function kaleidoRedraw(drawScene, o) {
  const n = o.n || 6, a = TAU / n, R = 2600;
  if (!KALEIDO_BUF || KALEIDO_BUF.width !== PXW || KALEIDO_BUF.height !== PXH) KALEIDO_BUF = mkCanvas(PXW, PXH);
  const kx = KALEIDO_BUF.getContext('2d');
  withCtx(kx, () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; ctx.filter = 'none';
    base(); ctx.fillStyle = o.bg || '#000'; ctx.fillRect(0, 0, W, H);
    for (let i = 0; i < n; i++) {
      ctx.save(); base();
      ctx.beginPath(); ctx.moveTo(o.cx, o.cy); ctx.arc(o.cx, o.cy, R, (o.rot || 0) + i * a - a / 2 - 0.003, (o.rot || 0) + i * a + a / 2 + 0.003); ctx.closePath(); ctx.clip();
      ctx.translate(o.cx, o.cy); ctx.rotate((o.rot || 0) + i * a); if (i % 2) ctx.scale(1, -1); ctx.rotate(-(o.rot || 0)); ctx.scale(o.zoom || 1, o.zoom || 1); ctx.translate(-o.cx, -o.cy);
      drawScene(ctx);
      ctx.restore();
    }
  });
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = o.amount == null ? 1 : o.amount; ctx.drawImage(KALEIDO_BUF, 0, 0); ctx.restore();
  base();
}
