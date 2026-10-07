// ---- covers ---------------------------------------------------------------------------------
// Every cover is a frame of the piece (its own draw code, #31): the photograph a cut ends on, or a moment of one,
// with the title set over the dark of the chairs. Formats (the canvas size comes from the page's ?w=&h=):
// sq (a square: streaming, the feed's square), reel (the whole 9:16 frame: the Reels cover), feed (4:5).
// A view is the stage point at the canvas centre and a zoom (90_main.js stage()).
function coverView(fmt, z = 1, cx = 540, cy = null) {
  const visH = PXH / (S * z);                           // stage units visible, top to bottom
  if (cy == null) cy = fmt === 'reel' ? 960 : fmt === 'feed' ? 965 : 870;
  return { cx, cy, z, visH };
}
// The title, in the canvas's own 1080-wide units (so it is the same size on every cover of a format).
function titleBlock(o = {}) {
  const hv = PXH / S, size = o.size || 96;
  const y = o.y != null ? o.y : hv > 1700 ? 1428 : hv > 1200 ? hv - 250 : hv - 128;
  ctx.save(); ctx.setTransform(S, 0, 0, S, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  if (!o.noTitle) {
    ctx.font = `500 ${size}px "Cormorant Garamond"`;
    ctx.letterSpacing = `${Math.round(size * 0.36)}px`;
    ctx.shadowColor = o.glow || 'rgba(255,236,214,0.55)'; ctx.shadowBlur = 26 * S;
    ctx.fillStyle = o.col || '#f6efe6';
    ctx.fillText(TITLE, W / 2 + size * 0.18, y);       // tracking adds space after the last letter: re-centre
    ctx.shadowBlur = 0;
  }
  ctx.font = '600 25px "Barlow Condensed"'; ctx.letterSpacing = '13px';
  ctx.fillStyle = o.sub || 'rgba(246,239,230,0.72)';
  ctx.fillText(ARTIST, W / 2 + 6, o.noTitle ? y : y + 56);
  ctx.restore();
}
// the stars as points, before the shutter opens; the bright ones with a four-pointed sparkle
function drawStarPoints() {
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  for (const s of STARS) {
    const x = POLE.x + s.r * Math.cos(s.a), y = POLE.y + s.r * Math.sin(s.a);
    if (y > 1215 || x < -10 || x > W + 10) continue;
    const col = `rgb(${s.c[0]},${s.c[1]},${s.c[2]})`;
    ctx.globalAlpha = clamp(0.35 + 0.9 * s.b); ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x, y, 0.7 + 0.9 * s.w, 0, TAU); ctx.fill();
    if (s.b > 0.62) {                                  // a sparkle only on the brightest few
      const L = 10 + 30 * s.b;
      drawSprite(ctx, glowSprite(s.c[0], s.c[1], s.c[2], 'p' + s.c), x, y, 6 + 16 * s.b, 0.5);
      ctx.strokeStyle = col; ctx.lineWidth = 1.1; ctx.globalAlpha = 0.75;
      ctx.beginPath(); ctx.moveTo(x - L, y); ctx.lineTo(x + L, y); ctx.moveTo(x, y - L); ctx.lineTo(x, y + L); ctx.stroke();
    }
  }
  ctx.restore();
}
function drawWish() { drawMeteor({ t: 0, dur: 1, ang: rad(152), r0: 300, len: 420, s: 1, w: 3.2, hue: 0.2 }, 2, { still: true }); }
// the title written in light across the sky, as if with a sparkler during the exposure
function drawWritten() {
  ctx.save(); stage(); ctx.globalCompositeOperation = 'lighter';
  ctx.translate(W / 2 + 10, 830); ctx.rotate(rad(-7));
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  ctx.font = '400 250px "Mrs Saint Delafield"';
  ctx.globalCompositeOperation = 'source-over';                  // a soft dark bed under the light, so it reads over the rings
  ctx.shadowColor = 'rgba(0,0,0,0.85)'; ctx.shadowBlur = 46 * S; ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillText('Setareh', 0, 0);
  ctx.lineWidth = 3.2; ctx.strokeStyle = 'rgba(255,214,160,0.9)'; ctx.shadowBlur = 0; ctx.strokeText('Setareh', 0, 0);
  ctx.globalCompositeOperation = 'lighter';
  ctx.shadowColor = 'rgba(255,170,90,0.9)'; ctx.shadowBlur = 30 * S;
  ctx.fillStyle = 'rgba(255,214,160,0.85)'; ctx.fillText('Setareh', 0, 0);
  ctx.shadowBlur = 8 * S; ctx.shadowColor = 'rgba(255,240,220,1)';
  ctx.fillStyle = 'rgba(255,248,236,0.95)'; ctx.fillText('Setareh', 0, 0);
  ctx.restore();
}
const COVERS = {
  // the night's photograph: the leaning figure, the rings closed, a ray for every line, the moon
  night: fmt => { VIEW = coverView(fmt); const X = expo(CUTS.night.open); frame(X, X.close + 1, {}, { still: true, noCars: true }); titleBlock(); },
  // the dawn's: the figure on the left never moved; the one on the right is what is left of the time it stayed
  dawn: fmt => { VIEW = coverView(fmt); const X = expo(CUTS.dawn.open); frame(X, X.close + 1, {}, { still: true, noCars: true }); titleBlock({ glow: 'rgba(255,214,190,0.6)' }); },
  // the moment before the shutter opens: the stars as points, one wish
  before: fmt => {
    VIEW = coverView(fmt);
    const X = expo(CUTS.dawn.open), t = X.open, eras = [{ pose: 'up', a: t, b: t, alpha: 1 }];
    stage(); drawSky(X, t, { u: 0.9 });
    stage(); drawStarPoints(); drawWish();
    stage(); drawSetareh(X, X.close, { still: true, u: 0.45 });
    stage(); drawHerGhost(X, t, eras); stage(); drawHerRim(X, t, eras);
    stage(); drawLand(X, t, { u: 0.9 }); stage(); drawCity(X, t, { u: 0.9 }); stage(); drawHill(X, t);
    stage(); drawHim(X, t + 30); stage(); drawChairs(X, t + 30);
    stage(); drawVignette(); drawGrain(X, t, { still: true });
    titleBlock();
  },
  // only the sung lines: the pole star and its rays, the stars left out
  rays: fmt => {
    VIEW = coverView(fmt); const X = expo(CUTS.night.open);
    frame(X, X.close + 1, {}, { still: true, noTrails: true, noPlane: true, noMoon: true, noCars: true });
    titleBlock();
  },
  // close on the two chairs at dawn
  close: fmt => {
    VIEW = coverView(fmt, fmt === 'reel' ? 1.25 : 1.5, 575, fmt === 'reel' ? 960 : 985);
    const X = expo(CUTS.dawn.open); frame(X, X.close + 1, {}, { still: true, noCars: true });
    titleBlock({ glow: 'rgba(255,214,190,0.6)' });
  },
  // the title written in light across the night's sky
  written: fmt => {
    VIEW = coverView(fmt); const X = expo(CUTS.night.open);
    frame(X, X.close + 1, {}, { still: true, noCars: true }); drawWritten();
    titleBlock({ noTitle: true });
  },
};
function drawCover(name, arg = {}) {
  (COVERS[name] || COVERS.night)(arg.fmt || 'sq');
  VIEW = null;
}
