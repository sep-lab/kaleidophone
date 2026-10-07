// ---------------------------------------------------------------- the frame
// every frame starts every context from the same state, so no frame depends on the one drawn before it
const reset = g => {
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over'; g.imageSmoothingEnabled = true;
  g.lineCap = 'butt'; g.lineJoin = 'miter'; g.lineWidth = 1; g.miterLimit = 10; g.setLineDash([]);
  g.fillStyle = '#000'; g.strokeStyle = '#000';
};
function renderGame(t, o = {}) {
  BW = Math.round(PXW / PX); BH = Math.round(PXH / PX);
  buffers(); stormEvents();
  EMIT.length = 0; LIGHTS.length = 0; STEAM.length = 0;
  const L = stormLight(t);
  const jolt = Math.max(t < SONG.stop ? L.me : 0, t > 26 && t < SONG.beatIn ? L.city : 0);
  setCamera(t, jolt > 0.5 ? 3 * jolt : 0);
  if (o.camH) CAM.h = o.camH;
  if (o.camOff) { CAM.x += o.camOff[0]; CAM.y += o.camOff[1]; }
  if (o.camAt) { CAM.shx = CAM.shy = 0; o.camAt(); }
  const W = visibleWorld(...viewRect(30));
  // T: the world's clock, which stops with the music (the pause); t keeps running for him, the
  // camera and the HUD
  const T = Math.min(t, SONG.stop);
  const g = GBUF.getContext('2d'); reset(g);
  drawGround(g, T, W); drawTrail(g, T);
  const ob = OBUF.getContext('2d'); reset(ob); ob.clearRect(0, 0, BW, BH);
  const cloudW = t > SONG.beatIn - 1 ? cloudGround(T) : null;
  drawCars(ob, T);
  drawStreetLow(ob, T, W, { cloud: cloudW });
  drawOthers(ob, T); drawPaper(ob, T);
  drawSax(ob, T); drawCouple(ob, T); drawPigeons(ob, T, false);
  const meP = o.noHim ? [-1e4, -1e4] : drawHim(ob, t);
  drawBuildings(ob, T, W);
  drawStreetHigh(ob, T, W, { p: meP, cloud: cloudW });
  drawPharmacies(ob, T);
  for (const S of W.segs) manholeSteam(S);
  drawPigeons(ob, T, true);
  lightPass(t, L);
  lightLayer(GBUF, false); lightLayer(OBUF, true);
  drawTrailSheen(g, T);
  drawPuddles(g, t, W, L);
  const f = FRAME.getContext('2d'); reset(f);
  f.drawImage(GBUF, 0, 0); f.drawImage(OBUF, 0, 0);
  for (const e of EMIT) e(f);
  const flash = Math.max(L.city * (t < SONG.beatIn + 1 ? 1 : 0), L.me * 0.75);
  if (flash > 0.6) { f.globalCompositeOperation = 'lighter'; f.fillStyle = css([200, 205, 255], (flash - 0.6) * 0.55); f.fillRect(0, 0, BW, BH); f.globalCompositeOperation = 'source-over'; }
  const lim = LBUF.getContext('2d').getImageData(0, 0, BW, BH);
  drawSteam(f, T, lim);
  drawSmoke(f, t);
  drawRain(f, t, lim);
  drawBolts(f, L);
  if (!o.noCloud) drawCloud(f, t, meP, L);
  drawGulls(f, T);
  if (o.fade) { f.fillStyle = `rgba(0,0,0,${o.fade})`; f.fillRect(0, 0, BW, BH); }
  // paused: the edges of the frame dim a little, the way a game dims behind its pause
  const pz = step(t, SONG.stop, SONG.stop + 0.7);
  if (pz > 0) {
    const R = Math.hypot(BW, BH) / 2, gr = f.createRadialGradient(BW / 2, BH / 2, R * 0.3, BW / 2, BH / 2, R);
    gr.addColorStop(0, 'rgba(8,8,20,0)'); gr.addColorStop(1, `rgba(8,8,20,${(0.42 * pz).toFixed(3)})`);
    f.fillStyle = gr; f.fillRect(0, 0, BW, BH);
  }
  dither(f);
  if (!o.noHud) drawHUD(f, t, o.cardT0);
  if (o.after) o.after(f);
  return FRAME;
}
function blit() {
  const c = MAINCTX; c.setTransform(1, 0, 0, 1, 0, 0); c.imageSmoothingEnabled = false;
  c.drawImage(FRAME, 0, 0, PXW, PXH);
}

// ---------------------------------------------------------------- covers (⛈️: the cloud is the title)
// Every cover is a frame of the game at the size asked: `across` is how many metres of street the
// frame is wide, `px` how big a game pixel is (3 for the 1080-wide formats, like the film; 6 at
// 3000, so the square keeps the console's chunk). The camera is placed so the cover's subject
// (`focus`) sits at `aim` of the height -- [square, 4:5, 9:16] -- and `dx` metres off the middle.
// The HUD's icon is the title; the only words are the credit, in the game's own letters.
const meAt = t => walker(Math.min(t, SONG.stop)).p;
const COVERS = {
  // the main one: the dawn grid from high up, his storm flickering on a snare, the last crossing above him
  map:    { t: 309.79, across: 90, hud: true, dx: 3, aim: [0.58, 0.56, 0.46], focus: meAt },
  // the frozen bolt, his face turned up to us
  pause:  { t: 338.85, across: 7.4, hud: true, dx: -0.25, aim: [0.42, 0.42, 0.37], focus: meAt, z: 1.4 },
  // the storm: the red umbrella dancing, him walking past
  couple: { t: 26.1, across: 20, hud: true, dx: 0, aim: [0.5, 0.5, 0.41], focus: t => lerp2(meAt(t), COUPLE.p, 0.5) },
  // the doorway: notes, the coin in the air
  sax:    { t: 13.6, across: 12.5, hud: true, dx: -0.2, aim: [0.5, 0.5, 0.41], focus: t => lerp2(meAt(t), SAX.p, 0.5) },
  // his cloud lit on a snare, beside the night café's awning
  night:  { t: 47.27, across: 46, hud: true, dx: -5, aim: [0.5, 0.5, 0.42], focus: t => lerp2(meAt(t), NIGHT_CAFE_AT, 0.5) },
  // the title, big, over the street
  icon:   { t: 12.0, across: 30, hud: false, icon: true },
};
const NIGHT_CAFE_AT = [17.07, 17.07];
let LAST_COVER = null;                 // where everything landed on the last cover drawn (game pixels; for QA)
function coverDraw(name, arg = {}) {
  const C = COVERS[name] || COVERS.map;
  const t = arg.t != null ? +arg.t : C.t;
  PX = PXW >= 2000 ? 6 : 3;
  try {
    const bw = Math.round(PXW / PX), ratio = PXW / PXH, tall = ratio < 0.7, fmt = tall ? 2 : ratio < 0.95 ? 1 : 0;
    const L = { name, fmt, px: PX };
    renderGame(t, {
      camH: C.across * F / bw, noHud: true,
      fade: C.icon ? 0.3 : 0,
      camAt: C.focus ? () => {
        const f = C.focus(t), k = kAt(C.z || 0);
        CAM.x = f[0] + (C.dx || 0);
        CAM.y = f[1] - (0.5 - C.aim[fmt]) * BH / k;
        L.focus = proj(f[0], f[1], C.z || 0);
      } : null,
      after: f => {
        if (C.icon) {
          const s = Math.max(4, Math.floor(Math.min(BW, BH) / 24)), x = Math.round((BW - 16 * s) / 2);
          const y = Math.round(tall ? BH * 0.42 - 7 * s : (BH - 14 * s) / 2 - BH * 0.03);
          icon(f, x, y, s); L.icon = [x, y, x + 16 * s, y + 14 * s];
        }
        if (C.hud) {
          // the game's corner. Tall: inside the 9:16 safe frame, and inside the square the grid crops to
          const s = 2, str = clockStr(t), w = textW(str, s);
          const x1 = tall ? Math.round(BW * 940 / 1080) - 2 : BW - Math.round(BW * 0.05);
          const y0 = tall ? Math.round(BH * 0.235) : Math.round(BW * 0.05);
          digits(f, str, x1 - w, y0, s, '#f2f2ea', 'rgba(0,0,0,0.75)');
          icon(f, x1 - w - 16 - 5, y0 - 3, 1);
          L.hud = [x1 - w - 21, y0 - 3, x1 + 2, y0 + 12];
        }
        // the credit, in the game's letters, outlined so it reads on any frame
        const s = 2, str = 'SEP THE CONCEPT', w = lettersW(str, s, 1);
        const x = Math.round((BW - w) / 2), y = tall ? Math.round(BH * 0.615) : Math.round(BH * 0.91);
        lettersOutlined(f, str, x, y, s, '#f2efe6', 1);
        L.credit = [x - 1, y - 1, x + w + 2, y + 7 * s + 2];
      },
    });
    blit();
    LAST_COVER = L;
  } finally { PX = 3; }
}

boot({
  bpm: BPM, dur: 337.3, downbeat: DOWNBEAT, idleT: 2.0, root: 98,
  hint: '⛈️ · click to begin · or drop the track',
  init() { stormReset(); },
  draw(t, env, flags) {
    PX = PXW / 360;                                        // the game frame is 360 wide at any output size
    renderGame(t, { cardT0: flags && flags.cardT0 != null ? +flags.cardT0 : null });
    blit();
  },
  cover(name, arg) { coverDraw(name, arg); },
});
