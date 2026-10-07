// ============================================================================
//  SETAREH -- Sep The Concept, 2026.
//
//  THE RULE: each cut is ONE long exposure, developing live. Everything that moves leaves only its
//  light; only what stays, stays.
//    1. Every star moves except one: the pole star. It never draws a trail, and because its light
//       piles up in one place it is the only star that keeps getting brighter.
//    2. The sky turns one step on every snare. 32 snares in a cut = 32 steps of 11.25 degrees = one
//       full turn, so the trails close into rings exactly on the 32nd snare -- and the shutter closes
//       there. Each step is fast at the snare and slow after it: the trails come out dashed, 32 dashes
//       to a ring, like the centre lines of empty roads.
//    3. Every sung line is a shooting star. Its streak stays; together they radiate from the pole star.
//    4. Cars in the valley leave only their light: the road looks empty.
//    5. The exposure keeps a person exactly as much as they stayed. The figure on the left never moves,
//       so it is kept whole. The figure on the right is drawn as the poses it held, each as opaque as
//       the share of the sky's light it blocked while it held it: in the night cut it leans and stays;
//       in the dawn cut it gets up and goes, and the dawn coming up behind it washes it out.
//  The picture is a pure function of (t, the song pack, the exposure's opening time).
// ============================================================================
const TITLE = 'SETAREH';
const ARTIST = 'SEP THE CONCEPT';
const G = makeGrid({ bpm: 64, downbeat: 0.01, beatsPerBar: 4 });
const DUR = 218.0;
const FPS = 24;
const STEPS = 32;                         // a full turn of the sky: 32 snares
const STEP_A = TAU / STEPS;               // 11.25 degrees a snare
const KICK_U = 0.28, KICK_SHARE = 0.55;   // each step: 55% of its angle eased out over its first 28%, the rest steady
const FAST = KICK_SHARE + (1 - KICK_SHARE) * KICK_U;   // share of a step's angle swept fast: dim in the trail (0.676)
const POLE = { x: 540, y: 520 };          // Setareh. In the safe frame (y 269-1248).
const RMAX = 890;                         // no circle wider than this reaches the sky inside the frame

// The cuts, as the release has them (piece.json "cuts"). Both are 1439 frames at 24 fps (59.96 s): either one
// works as the reel or the story. Cue times are the song's (events.setareh.* in the pack; these are fallbacks).
const CUTS = {
  night: { open: 13.75, frames: 1439, moon: 63.70 },
  dawn: { open: 89.99, frames: 1439, dawn: 131.14, leave: 138.45 },
};
function cutFor(open) {
  let best = null;
  for (const [name, c] of Object.entries(CUTS)) if (Math.abs(c.open - open) < 1.5) best = { name, ...c };
  return best;
}
// live mode / no flag: the cut that contains t (else a generic 60 s exposure starting at the last minute mark)
function defaultOpen(t) {
  for (const c of Object.values(CUTS)) if (t >= c.open && t < c.open + c.frames / FPS) return c.open;
  return Math.max(0, Math.floor(t / 60) * 60);
}
// The song's events. Render/cover: from the pack (EV). Live: what the build baked in, if it baked any.
function sEv(name) {
  const l = evList(EV, `setareh.${name}`);
  if (l.length) return l;
  return (typeof __SETAREH__ !== 'undefined' && __SETAREH__ && __SETAREH__[name]) || [];
}
function cueTime(name, fallback) { const l = sEv(name); return l.length ? l[0][0] : fallback; }

// ---- palette ---------------------------------------------------------------------
const INK = '#030407';                    // the silhouettes: him, her, the chairs
const STAR_COLORS = [                     // [weight, rgb]: colour temperature, blue-white to orange
  [0.18, [188, 210, 255]], [0.30, [226, 234, 255]], [0.22, [255, 248, 236]],
  [0.15, [255, 231, 186]], [0.10, [255, 203, 148]], [0.05, [255, 164, 120]],
];
function pickColor(u) { let a = 0; for (const [w, c] of STAR_COLORS) { a += w; if (u < a) return c; } return STAR_COLORS[0][1]; }

// ---- the star field, around the pole ------------------------------------------------
// Seeded once. r is uniform over the disc's area; brightness is a steep power law (most stars faint).
const STARS = (() => {
  const R = mulberry32(20261002), out = [];
  for (let i = 0; i < 950; i++) {
    const r = 30 + (RMAX - 30) * Math.sqrt(R()), a = R() * TAU, u = R(), m = Math.pow(u, 7);
    out.push({ r, a, b: 0.09 + 0.91 * m, w: 0.85 + 2.6 * Math.pow(m, 0.7), c: pickColor(R()), tw: R() });
  }
  out.sort((p, q) => p.b - q.b);          // faint first: the bright ones land on top
  return out;
})();

// ---- the land ----------------------------------------------------------------------
// The ridge across the frame, and the cone on the right (snow-capped): the camera faces north over a city.
const CONE = { x: 905, y: 1072, k: 0.56 };
function ridgeY(x) {
  const b0 = 1203 + 13 * Math.sin(x / 97 + 1.3) + 8 * Math.sin(x / 41 + 0.4) + 4 * Math.sin(x / 17 + 2.0) - 36 * Math.exp(-(((x - 150) / 150) ** 2));
  return Math.min(b0, CONE.y + Math.abs(x - CONE.x) * CONE.k + 3 * Math.sin(x / 9));
}
const VALLEY = { y0: 1214, vp: [585, 1209] };    // the city: from the range's foot to the edge of their hill
const hillY = x => 1478 + 9 * Math.sin(x / 83 + 0.6) + 5 * Math.sin(x / 29 + 2.2) - 26 * Math.exp(-(((x - 120) / 260) ** 2));

// ---- the people ------------------------------------------------------------------
// Seen from behind, in two armchairs. He is on the left; she is on the right.
const HIM = { x: 405, head: [405, 1034], hr: 57, hry: 65 };
const HER = { x: 683, head: [683, 1050], hr: 51, hry: 59 };
const CHAIR_TOP = 1188;
