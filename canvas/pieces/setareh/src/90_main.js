// ---- the frame ----------------------------------------------------------------------------
// One exposure, drawn as it stands at t: the sky's light so far; her, as much as she stayed; every light that
// moved, era by era (cut where she was in front of it); the pole star; the land; the valley's lights; him and the
// chairs, whole. After the close (the 32nd snare) the photograph is finished and holds.
let VIEW = null;                                      // covers: { cx, cy, z } -- the stage point at the canvas centre, and a zoom
function stage() {
  base();
  if (VIEW) { const s = S * VIEW.z; ctx.setTransform(s, 0, 0, s, PXW / 2 - VIEW.cx * s, PXH / 2 - VIEW.cy * s); }
}
function frame(X, t, env, o = {}) {
  const tc = Math.min(t, X.close), live = t < X.close && !o.still;
  stage();
  drawSky(X, tc, o);
  const eras = herEras(X, tc);
  stage(); drawHerGhost(X, tc, eras);
  stage(); drawHerRim(X, tc, eras);
  eras.forEach((e, i) => {
    const last = i === eras.length - 1;
    stage();
    eraLights(X, e, `${X.open.toFixed(3)}:${i}:${e.pose}`, tc, () => {
      if (!o.noPlane) drawPlane(X, e.a, e.b, { live: live && last, still: o.still });
    }, () => {
      for (const m of X.meteors) if (m.t >= e.a && m.t < e.b) drawMeteor(m, tc, o);
      if (last && !o.noMoon) drawMoon(X, tc, o);
      if (live && last && !o.noHeads) drawHeads(thetaAt(X, tc), tc, env, o);
    }, o);
  });
  stage(); drawSetareh(X, tc, o);
  stage(); drawLand(X, tc, o);
  stage(); drawCity(X, tc, o);
  if (!o.noCars) { stage(); drawCars(X, tc); }
  // she sits in front of the land: lay her ghost (still in LAYER) on it again, inside the land's own shape
  stage(); ctx.save(); ctx.clip(LAND_CLIP); blit(LAYER); ctx.restore();
  stage(); drawHill(X, tc, o);
  stage(); drawPhone(X, tc, o);
  stage(); drawHim(X, tc);
  stage(); drawChairs(X, tc);
  stage(); drawVignette();
  drawGrain(X, t, o);
  stage(); drawShutter(X, t);
}
function draw(t, env, flags = {}) {
  const open = flags.open != null ? +flags.open : defaultOpen(t);
  VIEW = null;
  frame(expo(open), t, env || {}, { still: false });
  return null;
}
function cover(name, arg = {}) {
  VIEW = null;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, PXW, PXH);
  drawCover(name, arg);
}
boot({
  bpm: G.bpm, dur: DUR, downbeat: G.downbeat, draw, cover, idleT: 70.5, root: 98,
  fonts: ['500 40px "Cormorant Garamond"', '600 40px "Barlow Condensed"', '400 40px "Mrs Saint Delafield"'],
});
