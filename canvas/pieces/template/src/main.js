// ============================================================================
//  TEMPLATE -- a new piece starts here.
//  Copy canvas/pieces/template/ to canvas/pieces/<your-piece>/, rename (piece.json, template.html
//  and TITLE below), keep the contract:
//    * the piece is a pure function of (t, envelope): no state carried between frames,
//      so any window renders on its own, in parallel, and a new master with the same grid
//      is a constants change (docs/TECHNIQUES.md #30);
//    * everything is placed on the grid (makeGrid) -- count the bars before inventing (#47);
//    * one draw function serves live, render and cover (lib/live.js boot()).
//  Grid: 120 BPM, bar = 2 s, an 8-bar loop (16 s) that ends on its own first frame (#40).
// ============================================================================
const TITLE = 'KALEIDOPHONE';                       // fitted to <= 80% of the width; two lines if it would go under 64 px
const SUBTITLE = 'A NEW PIECE STARTS HERE';
const G = makeGrid({ bpm: 120, downbeat: 0, beatsPerBar: 4 });
const DUR = 16.0;
const FLOOR = 1500;
// three greys + paper + ONE accent; the wall is paper in shadow, so the lamp's pool of light reads
Object.assign(C, { accent: '#c9301c', wall: '#dcd3c0' });

// ---- the room: flat fills, boiled lines, a lamp that breathes with the kick ----
function room(lamp) {
  flat(0, 0, W, H, C.wall);
  flat(0, FLOOR, W, H - FLOOR, C.grey2);
  stroke([[0, FLOOR], [W, FLOOR]], C.ink, LW(1));
  rect(PORTAL.x, PORTAL.y, PORTAL.w, PORTAL.h, '#b9c3c8', C.ink, LW(0.9));   // the window = the droste portal
  stroke([[PORTAL.x + PORTAL.w / 2, PORTAL.y], [PORTAL.x + PORTAL.w / 2, PORTAL.y + PORTAL.h]], C.ink, LW(0.6));
  stroke([[PORTAL.x, PORTAL.y + PORTAL.h / 2], [PORTAL.x + PORTAL.w, PORTAL.y + PORTAL.h / 2]], C.ink, LW(0.6));
  const k = 0.3 + 0.7 * lamp;
  glow(360, 600, 480 + 140 * lamp, `rgba(252,240,208,${(0.7 * k).toFixed(3)})`);   // fades to its own colour (ink.js)
  stroke([[360, 0], [360, 500]], C.ink, LW(0.6));
  poly([[296, 500], [424, 500], [398, 556], [322, 556]], C.dark, C.ink, LW(0.8));
}
// The window has the frame's own aspect (9:16) and one quarter of its size, so the frame
// drawn at scale 1/4 about the map's fixed point lands exactly on it: an exact droste.
const PORTAL = { x: 680, y: 520, w: 270, h: 480 };
const DROSTE = { s: PORTAL.w / W, fx: PORTAL.x / (1 - PORTAL.w / W), fy: PORTAL.y / (1 - PORTAL.h / H) };

// Anything that must be read stays inside the 9:16 safe frame (live.js SAFE_FRAME; ?qa=1 draws it).
// Checked like a contact -- how far a box of text pokes out of it, 0 inside -- so a title that
// outgrows it shows up in the QA report.
function keepSafe(name, x0, y0, x1, y1) {
  const F = SAFE_FRAME, into = p => [clamp(p[0], F.x0, F.x1), clamp(p[1], F.y0, F.y1)];
  const a = [x0, y0], b = [x1, y1], ai = into(a), bi = into(b);
  if (Math.hypot(a[0] - ai[0], a[1] - ai[1]) >= Math.hypot(b[0] - bi[0], b[1] - bi[1])) contact(`${name}↔safe frame`, a, ai, 0);
  else contact(`${name}↔safe frame`, b, bi, 0);
}

// ---- bar 0: the title writes itself on in two beats, and holds for two -------
function sceneTitle(u) {
  flat(0, 0, W, H, C.paper);
  const fit = wordFit(TITLE, 0.78 * W, { max: 92, min: 64 }), h = fit.hgt, lead = 1.3 * h;   // 78% + the stroke and boil <= 80%
  const lw = LW(1.2 * h / 92), top = 866 - (h + lead * (fit.lines.length - 1)) / 2;   // centred where one line sits
  const n = fit.lines.map(s => s.replace(/ /g, '').length), all = n[0] + (n[1] || 0);
  const uT = clamp(u / 0.75) * all;                                          // letters: the first beat and a half
  fit.lines.forEach((s, i) => {
    const w = wordW(s, h), x = (W - w) / 2, y = top + i * lead, before = i ? n[0] : 0;
    word(s, x, y, h, C.ink, lw, clamp((uT - before) / n[i]));
    keepSafe('title', x, y, x + w, y + h);
  });
  const h2 = wordFit(SUBTITLE, 0.78 * W, { max: 34, min: 0 }).hgt, w2 = wordW(SUBTITLE, h2), y2 = top + h + lead * (fit.lines.length - 1) + 68;
  word(SUBTITLE, (W - w2) / 2, y2, h2, C.grey, LW(0.6), clamp((u - 0.35) / 0.5));
  keepSafe('subtitle', (W - w2) / 2, y2, (W + w2) / 2, y2 + h2);
  stroke([[W / 2 - 60, y2 + h2 + 76], [W / 2 + 60, y2 + h2 + 76]], C.accent, LW(1.4), clamp((u - 0.7) / 0.3));
}

// ---- bars 1-5: seated, the chair built from the body -------------------------
function sceneSeated(beats, env) {
  room(env.bass);
  const r = 70, g = seated(300, FLOOR, r, 1);
  chairFor(g, 'cafe');
  const top = g.P[1] - 0.55 * r;
  tableSide(640, top, FLOOR, 170, r);
  circ(700, top - 26, 22, C.paper, C.ink, LW(0.8));                         // a cup, and its steam on the beat
  const steam = G.sinceBeat(beats * G.beat);
  stroke([[700, top - 60], [690 - 10 * steam, top - 110], [706, top - 160 - 30 * steam]], C.grey, LW(0.5));
  const look = beats % 8 < 4 ? 0 : 1;                                        // looks up at the window on bar 3
  figure({
    view: 'side', x: g.P[0], y: g.P[1], r, dir: 1, hair: 'him',
    head: { eyes: env.bass > 0.75 ? 'closed' : 'open', up: look },
    legs: seatedLegs(g),
    arms: {
      far: { to: [560, top - 8], pole: [420, top + 140] },
      near: { to: [660, top - 18], pole: [480, top + 160], hand: 'fist' },
    },
  });
}

// ---- bars 5-7: a walk with planted feet, one step per beat --------------------
function sceneWalk(beats, env) {
  noDraw(() => room(env.bass * 0.6));                                       // the room is already there: only the walker draws on
  walker(beats);
}
function walker(beats) {
  const r = 62, xAt = tau => -120 + 150 * tau;
  // The pelvis rides highest over the stance foot (on the beat) and dips at double support, when the
  // feet are half a stride either side -- an inverted pendulum. Dip too little, or rise there, and the
  // legs can't reach both planted feet: a foot lifts off the floor (both are logged below).
  const dip = 1 - Math.abs(Math.cos(beats * Math.PI));                      // 0 on the beat, 1 on the "and"
  const Py = standPelvisY(FLOOR, r, 0.975) + 17 * dip;
  const lg = walkLegs(xAt, beats, 1, FLOOR, r, 150), x = xAt(beats), sw = Math.sin(beats * Math.PI);
  const J = figure({
    view: 'side', x, y: Py, r, dir: 1, hair: 'him', lean: 0.06,
    head: { eyes: 'down' },
    legs: { near: { to: lg.A, pole: [x + 4 * r, Py] }, far: { to: lg.B, pole: [x + 4 * r, Py] } },
    arms: { far: { to: [x - 0.5 * r * sw, Py + 0.2 * r], pole: [x - 2 * r, Py] }, near: { to: [x + 0.5 * r * sw, Py + 0.2 * r], pole: [x - 2 * r, Py] } },
  });
  contact('foot↔floor', J.ankles.near, [J.ankles.near[0], FLOOR - LW(1) / 2], lg.A[2] ? 1.5 : 999);
  contact('foot↔floor (far)', J.ankles.far, [J.ankles.far[0], FLOOR - LW(1) / 2], lg.B[2] ? 1.5 : 999);
}

// ---- the frame --------------------------------------------------------------
function draw(t, env, flags = {}) {
  t = ((t % DUR) + DUR) % DUR;
  // Characters on twos: every drawing holds for two frames at 24 fps. Poses, draw-ons, the title, the
  // boil and the envelope they react to all read the drawing's time tq; only the camera (the droste
  // zoom, the fade) reads t and stays smooth.
  const tq = G.onTwos(t);
  env = heldEnv(env, tq);
  CONTACTS.length = 0;
  boilFrame(tq, env.rms || 0);
  base(); flat(0, 0, W, H, C.black);
  const bar = G.barOf(tq), beats = G.beatOf(tq);
  if (bar < 1) sceneTitle(clamp(tq / (2 * G.beat)));
  else if (bar < 5) { drawOn(tq - G.bt(1)); sceneSeated(beats - 4, env); drawOn(null); }
  else if (bar < 7) { drawOn(tq - G.bt(5)); sceneWalk(beats - 20, env); drawOn(null); }
  else {
    // bar 7: fall into the window -- a vector droste, every level a full redraw (always crisp)
    const u = easeIn(clamp((t - G.bt(7)) / G.bar));
    let outer = true;                                                        // the walker finishes his exit on the outer level
    drosteRedraw(() => { room(env.bass); if (outer && beats < 29) walker(beats - 20); outer = false; }, {
      cx: DROSTE.fx, cy: DROSTE.fy, s: DROSTE.s, u, levels: 3, portalSize: PORTAL.w, bg: C.black,
      // this level's window, in virtual units, becomes the clip for the next level
      portal: Z => { const p = new Path2D(); p.rect(DROSTE.fx + (PORTAL.x - DROSTE.fx) * Z, DROSTE.fy + (PORTAL.y - DROSTE.fy) * Z, PORTAL.w * Z, PORTAL.h * Z); return p; },
    });
    base();
    const fade = smooth(0.5, 1, (t - G.bt(7)) / G.bar);                      // the last half-bar goes back to paper:
    if (fade > 0) { ctx.globalAlpha = fade; flat(0, 0, W, H, C.paper); ctx.globalAlpha = 1; }   // the loop's seam
  }
  base(); paperGrain(0.05 + 0.03 * (env.rms || 0));
  if (QA) drawContacts();
  return { contacts: contactReport() };
}

function cover(name) {
  const e = { bass: 0.6, rms: 0.5 };
  boilFrame(3.1, 0.4); CONTACTS.length = 0;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = C.paper; ctx.fillRect(0, 0, PXW, PXH);
  if (name === 'title') { coverCrop(0.28); sceneTitle(1); }
  else { coverCrop(0.4); sceneSeated(2, e); }
  base(); paperGrain(0.05);
}

boot({ bpm: G.bpm, dur: DUR, draw, cover, idleT: 1.6, root: 110 });
