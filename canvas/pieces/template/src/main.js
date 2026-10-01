// ============================================================================
//  TEMPLATE -- a new piece starts here.
//  Copy canvas/pieces/template/ to canvas/pieces/<your-piece>/, rename (piece.json, template.html
//  and TITLE below), keep the contract:
//    * the piece is a pure function of time and the song -- its envelope and its events: no state
//      carried between frames, so any window renders on its own, in parallel, and a new master with
//      the same grid is a constants change (docs/TECHNIQUES.md #30);
//    * everything is placed on the grid (makeGrid) -- count the bars before inventing (#47);
//    * one draw function serves live, render and cover (lib/live.js boot()).
//  Grid: 120 BPM, bar = 2 s, an 8-bar loop (16 s) that ends on its own first frame (#40).
//  The song's events -- what it PLAYED -- drive the small things: the bulb pops on each snare,
//  the figure nods on each kick, the droste turns a step on each chord change (evList, evPulse ...:
//  core.js; EV: live.js). Bar 7 has three endings, the piece's variants: droste, lamp, exit.
// ============================================================================
const TITLE = 'KALEIDOPHONE';                       // fitted to TITLE_FIT of the width; two lines if it would go under 64 px
const SUBTITLE = 'A NEW PIECE STARTS HERE';
// Titles are centred on the frame and fitted to this share of its width, so their ink -- stroke and boil
// included -- stays inside the safe frame (live.js SAFE_FRAME, x 65-940). TikTok's buttons take the
// right 140 px, so a centred line can be at most 2 x (940 - 540) = 800 px wide: 72% is 778, ink to x ~934.
const TITLE_FIT = 0.72;
const G = makeGrid({ bpm: 120, downbeat: 0, beatsPerBar: 4 });
const DUR = 16.0;
const FLOOR = 1500;
// The piece's variants, as piece.json declares them (npm test checks that the two agree). boot() checks what
// it is asked for against these and hands draw the choice: flags.variant.ending. Render one with
// `render.mjs template --variant ending=lamp`; live, open the page with ?variant=ending:lamp.
const VARIANTS = { ending: { at: 14.0, options: ['droste', 'lamp', 'exit'], default: 'droste' } };
// three greys + paper + ONE accent; the wall is paper in shadow, so the lamp's pool of light reads
Object.assign(C, { accent: '#c9301c', wall: '#dcd3c0' });
const GLASS = '#b9c3c8';
// The lamp's light between snares. Low, so a snare's flash -- the light to full and the bulb's pop --
// still reads after a platform has re-encoded the film (at 0.4 the flash was ~3% of the wall).
const LAMP_REST = 0.15;

// ---- the room: flat fills, boiled lines, a lamp whose bulb pops on the snare ----
// lamp: its light, 0..1. o.off: the bulb is out. o.pop: the bulb's pop, 0..1 (a snare). o.glass: the
// window's colour. o.mullions: how much of the window's cross is drawn (1: all; it un-draws towards 0).
// o.wide: the flats run on past the frame (a turned droste level shows past its own edges).
function room(lamp, o = {}) {
  const a = o.wide ? -W : 0, b = o.wide ? 2 * W : W;
  flat(a, o.wide ? -H : 0, b - a, o.wide ? 3 * H : H, C.wall);
  flat(a, FLOOR, b - a, (o.wide ? 2 * H : H) - FLOOR, C.grey2);
  stroke([[a, FLOOR], [b, FLOOR]], C.ink, LW(1));
  pane(o.glass || GLASS, o.mullions);                                        // the window = the droste portal
  if (!o.off) lampGlow(lamp);
  stroke([[360, 0], [360, 500]], C.ink, LW(0.6));
  bulb(!o.off, o.pop || 0);
  poly([[296, 500], [424, 500], [398, 556], [322, 556]], C.dark, C.ink, LW(0.8));
}
// the window: its glass and frame, and its cross (m: how much of it is drawn; undefined: as the draw-on has it)
function pane(glass, m) {
  rect(PORTAL.x, PORTAL.y, PORTAL.w, PORTAL.h, glass, C.ink, LW(0.9));
  stroke([[PORTAL.x + PORTAL.w / 2, PORTAL.y], [PORTAL.x + PORTAL.w / 2, PORTAL.y + PORTAL.h]], C.ink, LW(0.6), m);
  stroke([[PORTAL.x, PORTAL.y + PORTAL.h / 2], [PORTAL.x + PORTAL.w, PORTAL.y + PORTAL.h / 2]], C.ink, LW(0.6), m);
}
function lampGlow(lamp) {
  const k = 0.3 + 0.7 * lamp;
  glow(360, 600, 480 + 140 * lamp, `rgba(252,240,208,${(0.7 * k).toFixed(3)})`);   // fades to its own colour (ink.js)
}
// The bulb under the shade (the shade, drawn after it, hides its top half). On a pop it flares: a
// near-white halo on the wall and ink rays out of it -- ink, because a white flash alone barely shows on
// paper (docs/CREATIVE-GUIDE.md, "mind the medium's physics"). The rays shrink back as the hit decays and
// are gone by its third drawing (under a quarter of the hit), rather than left as specks round the bulb.
const BULB = { x: 360, y: 556, r: 17, rays: [22, 56, 90, 124, 158].map(rad) };
function bulb(lit, pop) {
  const u = revealU(), { x, y, r } = BULB;                                  // it draws on with the room: one stroke's turn
  if (lit && pop > 0.02) glow(x, y + 8, 50 + 90 * pop, `rgba(255,251,238,${(0.9 * pop).toFixed(3)})`);
  if (lit && pop > 0.25) {
    const r0 = 30 + 8 * (1 - pop), r1 = r0 + 48 * pop;
    for (const a of BULB.rays) stroke([[x + r0 * Math.cos(a), y + 6 + r0 * Math.sin(a)], [x + r1 * Math.cos(a), y + 6 + r1 * Math.sin(a)]], C.ink, LW(0.75), u);
  }
  circ(x, y, r, lit ? '#fbf3dd' : C.grey2, C.ink, LW(0.6), 14, u);
}
// The window has the frame's own aspect (9:16) and one quarter of its size, so the frame
// drawn at scale 1/4 about the map's fixed point lands exactly on it: an exact droste.
const PORTAL = { x: 680, y: 520, w: 270, h: 480 };
const DROSTE = { s: PORTAL.w / W, fx: PORTAL.x / (1 - PORTAL.w / W), fy: PORTAL.y / (1 - PORTAL.h / H) };

// Where he sits. The chair is built from this body (rig.js), and stays where it is when he gets up.
const SEAT = seated(300, FLOOR, 70, 1);
function chair(sitting) {
  if (sitting) return chairFor(SEAT, 'cafe');
  const n = CONTACTS.length, c = chairFor(SEAT, 'cafe'); CONTACTS.length = n;   // empty: no body, so no contacts to log
  return c;
}
// The empty chair's ink, as a box in stage units (a dry run of chairFor: rig.js's geometry, nothing drawn):
// from the bentwood back to the front leg, from the top of the back to the floor.
const CHAIR = (() => {
  const c = measure(() => chairFor(SEAT, 'cafe')), r = SEAT.r;
  return { x0: c.backX - 0.34 * r, x1: c.frontX + 0.08 * r, y0: c.topY, y1: SEAT.floorY };
})();
function table(beats) {                                                   // the table, a cup, and its steam on the beat
  const top = SEAT.P[1] - 0.55 * SEAT.r;
  tableSide(640, top, FLOOR, 170, SEAT.r);
  circ(700, top - 26, 22, C.paper, C.ink, LW(0.8));
  const steam = G.sinceBeat(beats * G.beat);
  stroke([[700, top - 60], [690 - 10 * steam, top - 110], [706, top - 160 - 30 * steam]], C.grey, LW(0.5));
  return top;
}

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
  const fit = wordFit(TITLE, TITLE_FIT * W, { max: 92, min: 64 }), h = fit.hgt, lead = 1.3 * h;
  const lw = LW(1.2 * h / 92), top = 866 - (h + lead * (fit.lines.length - 1)) / 2;   // centred where one line sits
  const n = fit.lines.map(s => s.replace(/ /g, '').length), all = n[0] + (n[1] || 0);
  const uT = clamp(u / 0.75) * all;                                          // letters: the first beat and a half
  fit.lines.forEach((s, i) => {
    const w = wordW(s, h), x = (W - w) / 2, y = top + i * lead, before = i ? n[0] : 0;
    word(s, x, y, h, C.ink, lw, clamp((uT - before) / n[i]));
    keepSafe('title', x, y, x + w, y + h);
  });
  const h2 = wordFit(SUBTITLE, TITLE_FIT * W, { max: 34, min: 0 }).hgt, w2 = wordW(SUBTITLE, h2), y2 = top + h + lead * (fit.lines.length - 1) + 68;
  word(SUBTITLE, (W - w2) / 2, y2, h2, C.grey, LW(0.6), clamp((u - 0.35) / 0.5));
  keepSafe('subtitle', (W - w2) / 2, y2, (W + w2) / 2, y2 + h2);
  stroke([[W / 2 - 60, y2 + h2 + 76], [W / 2 + 60, y2 + h2 + 76]], C.accent, LW(1.4), clamp((u - 0.7) / 0.3));
}

// ---- bars 1-5: seated, the chair built from the body; he nods on every kick ---
function sceneSeated(beats, fx, env) {
  room(fx.lamp, { pop: fx.pop });
  const r = SEAT.r, g = SEAT;
  chair(true);
  const top = table(beats);
  const look = beats % 8 < 4 ? 0 : 1;                                        // looks up at the window on bar 3
  figure({
    view: 'side', x: g.P[0], y: g.P[1], r, dir: 1, hair: 'him',
    // the nod: the head drops forward on the kick and comes back up as the hit decays
    head: { eyes: env.bass > 0.75 ? 'closed' : 'open', up: look, dx: 0.1 * fx.nod, dy: 0.2 * fx.nod },
    legs: seatedLegs(g),
    arms: {
      far: { to: [560, top - 8], pole: [420, top + 140] },
      near: { to: [660, top - 18], pole: [480, top + 160], hand: 'fist' },
    },
  });
}

// ---- bars 5-7: a walk with planted feet, one step per beat --------------------
// He comes in from the left as bar 5 begins, passes the chair and the table, and is still in the room
// when bar 7 does: every ending opens on him walking out (his body is gone by about 14.9 s).
const WALK = { x0: -120, step: 130, r: 62 };                                 // pelvis x at bar 5, px per beat, head radius
const walkX = tau => WALK.x0 + WALK.step * tau;                              // tau: beats since bar 5
const walkerIn = tau => walkX(tau) < W + 2 * WALK.r;                         // drawn until his pelvis is this far past the edge: nothing of him trails further
function sceneWalk(beats, fx) {
  noDraw(() => { room(fx.lamp, { pop: fx.pop }); chair(false); table(beats); });   // the room and the chair he left are already there: only the walker draws on
  walker(beats);
}
function walker(beats) {
  const r = WALK.r;
  // The pelvis rides highest over the stance foot (on the beat) and dips at double support, when the
  // feet are half a stride either side -- an inverted pendulum. Dip too little, or rise there, and the
  // legs can't reach both planted feet: a foot lifts off the floor (both are logged below).
  const dip = 1 - Math.abs(Math.cos(beats * Math.PI));                      // 0 on the beat, 1 on the "and"
  const Py = standPelvisY(FLOOR, r, 0.975) + 17 * dip;
  const lg = walkLegs(walkX, beats, 1, FLOOR, r, 150), x = walkX(beats), sw = Math.sin(beats * Math.PI);
  const J = figure({
    view: 'side', x, y: Py, r, dir: 1, hair: 'him', lean: 0.06,
    head: { eyes: 'down' },
    legs: { near: { to: lg.A, pole: [x + 4 * r, Py] }, far: { to: lg.B, pole: [x + 4 * r, Py] } },
    arms: { far: { to: [x - 0.5 * r * sw, Py + 0.2 * r], pole: [x - 2 * r, Py] }, near: { to: [x + 0.5 * r * sw, Py + 0.2 * r], pole: [x - 2 * r, Py] } },
  });
  contact('foot↔floor', J.ankles.near, [J.ankles.near[0], FLOOR - LW(1) / 2], lg.A[2] ? 1.5 : 999);
  contact('foot↔floor (far)', J.ankles.far, [J.ankles.far[0], FLOOR - LW(1) / 2], lg.B[2] ? 1.5 : 999);
}

// ---- bar 7: three endings -- piece.json "variants": ending -----------------------
// Each picks up the room as bar 6 left it (the walker on his way out, the chair he left) and each ends
// on blank paper, the title card's first frame, so the loop still closes on its own seam (#40): blank
// by 16 - 1/12 s, the last drawing on twos, so at 12 fps as at 24.
// Drawings are on twos (tq); the camera -- the droste's fall, a push, a dissolve -- on the frame's own t.
const LAST = DUR - 1 / 12;
const beatsIn7 = t => (t - G.bt(7)) / G.beat;                                // beats since bar 7 began
// The droste's camera. inner: the room in the window comes through the glass over the first beat
// (instead of popping in on the bar line). u: the fall into the window, 0 -> 1 by beat 3.5,
// accelerating like a fall. fade: back to paper over the last half-beat only.
function drosteCamera(t) {
  const b = beatsIn7(t);
  return { inner: ease(b), u: Math.pow(clamp(b / 3.5), 2), fade: smooth(3.5, beatsIn7(LAST), b) };
}
// The exit's camera: a push of EXIT.z about EXIT's point from beat 1, and the paper fading in over the
// room round beat 3; both are in by beat 2.75, and the chair -- the subject now, in the safe frame --
// holds a moment, then un-draws on beat 4 (a drawing, on twos: in exit()).
function exitCamera(t) {
  const b = beatsIn7(t);
  return { z: 1 + (EXIT.z - 1) * ease((b - 1) / 1.75), fade: smooth(1.75, 2.75, b) };
}
// The push about the point that carries the chair's centre to EXIT.at at EXIT.z: the empty chair (stage
// y 1248-1500, half of it where the platforms put the caption) moves up into the safe frame, ~1.8x.
const EXIT = (() => {
  const z = 1.8, at = [480, 800], c = [(CHAIR.x0 + CHAIR.x1) / 2, (CHAIR.y0 + CHAIR.y1) / 2];
  return { z, at, fx: (at[0] - z * c[0]) / (1 - z), fy: (at[1] - z * c[1]) / (1 - z) };
})();
const ENDINGS = {
  // The view falls into the window: a vector droste, every level a full redraw (always crisp). It turns a
  // step on each chord change (events.chords: the synthetic twin plays a progression on the bar lines,
  // so it turns once, as bar 7 begins).
  droste(t, tq, beats, fx) {
    const cam = drosteCamera(t), turn = drosteTurn(t), Z0 = Math.pow(1 / DROSTE.s, cam.u);
    let level = -1;
    drosteRedraw(() => {
      level++;
      if (turn) { ctx.translate(DROSTE.fx, DROSTE.fy); ctx.rotate(level * turn); ctx.translate(-DROSTE.fx, -DROSTE.fy); }
      room(fx.lamp, { wide: !!turn, pop: fx.pop }); chair(false); table(beats - 20);
      if (!level && walkerIn(beats - 20)) walker(beats - 20);               // the walker finishes his exit on the outer level
    }, {
      cx: DROSTE.fx, cy: DROSTE.fy, s: DROSTE.s, u: cam.u, levels: 3, portalSize: PORTAL.w, bg: C.black,
      portal: Z => windowPath(Z, level * turn),                            // this level's window, in virtual units, clips the next
    });
    // until the room inside has come through, the window as the outer room draws it lies over it: its glass,
    // frame and cross, and the lamp's light on them
    if (cam.inner < 1) {
      ctx.save(); base(); ctx.clip(windowPath(Z0)); ctx.globalAlpha = 1 - cam.inner;
      zoomAbout(DROSTE.fx, DROSTE.fy, Z0); pane(GLASS); lampGlow(fx.lamp);
      ctx.restore();
    }
    base();
    if (cam.fade > 0) { ctx.globalAlpha = cam.fade; flat(0, 0, W, H, C.paper); ctx.globalAlpha = 1; }
  },
  // The lamp goes out. It stutters for a beat while he leaves, dies, and the room sinks into ink from the
  // lamp outward until the paper-white window is all that is left; its cross un-draws, and the camera
  // pushes into it until the paper fills the frame.
  lamp(t, tq, beats, fx) {
    const q = tq - G.bt(7), dead = q >= G.beat;
    const on = !dead && hsh(Math.round(tq * 12), 11) > 0.2 + 0.6 * q / G.beat;   // off more often as it dies
    const push = easeIn(clamp((t - G.bt(7) - 3 * G.beat) / (0.75 * G.beat)));  // on beat 4; overshoots the window's edges
    ctx.save(); zoomAbout(DROSTE.fx, DROSTE.fy, Math.pow(4.4, push));
    room(on ? Math.max(fx.lamp, 0.6) : 0, { off: !on, glass: dead ? C.paper : GLASS, mullions: 1 - clamp((q - 2.5 * G.beat) / (0.5 * G.beat)) });
    chair(false); table(beats - 20);
    if (walkerIn(beats - 20)) walker(beats - 20);
    if (dead) inkFlood(q - G.beat);
    ctx.restore();
  },
  // He walks out of the frame, and the chair he left stays: the camera pushes in on it, up out of the
  // caption's way, the paper fades in over the room but not over it, and on the last beat it un-draws
  // itself stroke by stroke (#43) -- a blank page again.
  exit(t, tq, beats, fx) {
    const cam = exitCamera(t), q = tq - G.bt(7);
    ctx.save(); zoomAbout(EXIT.fx, EXIT.fy, cam.z);
    room(fx.lamp, { pop: fx.pop, wide: true }); table(beats - 20);           // wide: the push lifts the room's bottom edge into the frame
    if (walkerIn(beats - 20)) walker(beats - 20);
    ctx.restore();
    base();
    if (cam.fade > 0) { ctx.globalAlpha = cam.fade; flat(0, 0, W, H, C.paper); ctx.globalAlpha = 1; }
    const all = 4 * 0.06 + 0.12, gone = clamp((q - 3 * G.beat) / (0.75 * G.beat));   // chairFor draws 5 strokes: 4 staggers + one stroke
    ctx.save(); zoomAbout(EXIT.fx, EXIT.fy, cam.z);
    drawOn(all * (1 - gone), { dur: 0.12, stagger: 0.06 });                  // erase = draw-on run backwards
    chair(false); drawOn(null);
    ctx.restore();
    // pushed in, the chair is what the frame is about: it must sit in the safe frame (QA, like the title)
    if (cam.z > EXIT.z - 1e-9 && gone < 1) {
      const P = (x, y) => [EXIT.fx + EXIT.z * (x - EXIT.fx), EXIT.fy + EXIT.z * (y - EXIT.fy)];
      keepSafe('chair', ...P(CHAIR.x0, CHAIR.y0), ...P(CHAIR.x1, CHAIR.y1));
    }
  },
};
// the window's outline after the droste's zoom Z about its fixed point and a turn by `a`: the next level's clip
function windowPath(Z, a = 0) {
  const c = Math.cos(a), s = Math.sin(a), p = new Path2D();
  [[0, 0], [1, 0], [1, 1], [0, 1]].forEach(([i, j], n) => {
    const dx = (PORTAL.x + i * PORTAL.w - DROSTE.fx) * Z, dy = (PORTAL.y + j * PORTAL.h - DROSTE.fy) * Z;
    const x = DROSTE.fx + dx * c - dy * s, y = DROSTE.fy + dx * s + dy * c;
    if (n) p.lineTo(x, y); else p.moveTo(x, y);
  });
  p.closePath();
  return p;
}
// A step of 15 degrees per chord change since bar 7 began, each turned in a quarter of a second. The
// chords are the pack's first chord track, if it has one (events.chords.<track> = [[t, 1, "Am"], ...]);
// a chord that repeats the one before it isn't a change.
function drosteTurn(t) {
  const g = EV.events.chords || {}, name = Object.keys(g).sort()[0], ch = name ? evList(EV, `chords.${name}`) : [];
  let a = 0;
  for (let i = evLast(ch, t); i >= 0 && ch[i][0] >= G.bt(7) - 1e-6; i--) if (!i || ch[i][2] !== ch[i - 1][2]) a += easeOut(clamp((t - ch[i][0]) / 0.25));
  return a * rad(15);
}
function zoomAbout(x, y, z) { ctx.translate(x, y); ctx.scale(z, z); ctx.translate(-x, -y); }
// Ink spreading from the lamp shade over everything but the window: a boiled blot, lumpy at its edge,
// past the farthest corner in a beat and a half (drawing time, so it spreads on twos).
function inkFlood(q) {
  const R = 1900 * easeIn(clamp(q / (1.5 * G.beat))) + 40 * clamp(q / 0.1);
  const pts = [];
  for (let i = 0; i < 120; i++) {                                           // lumps that go all the way round: no seam
    const a = i / 120 * TAU, rr = R * (1 + 0.09 * Math.sin(3 * a + 1.3) + 0.06 * Math.sin(5 * a + 4.1) + 0.035 * Math.sin(11 * a + 2.2) + 0.02 * Math.sin(23 * a + 0.7));
    pts.push([360 + Math.cos(a) * rr, 530 + Math.sin(a) * rr]);
  }
  ctx.save();
  const hole = new Path2D(); hole.rect(-W, -H, 3 * W, 3 * H); hole.rect(PORTAL.x, PORTAL.y, PORTAL.w, PORTAL.h);
  ctx.clip(hole, 'evenodd');
  poly(pts, C.ink, null);
  ctx.restore();
}

// ---- the frame --------------------------------------------------------------
// The song's events at the drawing's time tq, as what they move (0..1): the lamp's light and the bulb's pop
// on each snare, the nod on each kick. The twin has its drums as MIDI (a real Session pack, every part);
// live, the fallback's own beat. With none -- a dropped track, a pack without events -- they follow the
// envelope's high and low onsets instead.
function eventsAt(tq, env) {
  const kicks = evList(EV, 'midi.kick'), snares = evList(EV, 'midi.snare');
  const hit = snares.length ? evPulse(snares, tq, 0, 0.1) : clamp(2 * (env.hflux || 0) - 1);
  return {
    lamp: LAMP_REST + (1 - LAMP_REST) * hit,                                 // the light: low between snares, full on one
    pop: hit,                                                                // ...and the bulb's pop
    nod: kicks.length ? evPulse(kicks, tq, 0, 0.25) : clamp(2 * (env.bflux || 0) - 1),   // a quarter-second decay: a nod, not a twitch
  };
}
function draw(t, env, flags = {}) {
  t = ((t % DUR) + DUR) % DUR;
  // Characters on twos: every drawing holds for two frames at 24 fps. Poses, draw-ons, the title, the
  // boil and the envelope and events they react to all read the drawing's time tq; only the camera (the
  // droste zoom, the fade) reads t and stays smooth.
  const tq = G.onTwos(t);
  env = heldEnv(env, tq);
  CONTACTS.length = 0;
  boilFrame(tq, env.rms || 0);
  base(); flat(0, 0, W, H, C.black);
  const bar = G.barOf(tq), beats = G.beatOf(tq), fx = eventsAt(tq, env);
  if (bar < 1) sceneTitle(clamp(tq / (2 * G.beat)));
  else if (bar < 5) { drawOn(tq - G.bt(1)); sceneSeated(beats - 4, fx, env); drawOn(null); }
  else if (bar < 7) { drawOn(tq - G.bt(5)); sceneWalk(beats - 20, fx); drawOn(null); }
  else ENDINGS[(flags.variant && flags.variant.ending) || VARIANTS.ending.default](t, tq, beats, fx);
  base(); paperGrain(0.05 + 0.03 * (env.rms || 0));
  if (QA) drawContacts();
  return { contacts: contactReport() };
}

function cover(name) {
  const e = { bass: 0.6, rms: 0.5 };
  boilFrame(3.1, 0.4); CONTACTS.length = 0;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = C.paper; ctx.fillRect(0, 0, PXW, PXH);
  if (name === 'title') { coverCrop(0.28); sceneTitle(1); }
  else { coverCrop(0.4); sceneSeated(2, { lamp: e.bass, pop: 0, nod: 0 }, e); }
  base(); paperGrain(0.05);
}

boot({ bpm: G.bpm, dur: DUR, draw, cover, idleT: 1.6, root: 110, variants: VARIANTS });
