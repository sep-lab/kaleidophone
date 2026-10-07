'use strict';
/* ============================================================================
   ⛈️  -- Sep The Concept, 2026. A canvas piece: a top-down pixel city at night, in the rain.

   THE RULE: at 0:33 the rain stops for everyone but him.

   1. The storm comes for him. Light arrives before sound: every thunder in the intro's
      field recording is preceded by its flash, and the gap is the distance, 343 m a second.
      The gaps shrink -- the storm is walking toward him -- and at 0:33, when the beat
      lands, the gap is zero.
   2. There the city's rain gathers into one small cloud over one man -- the emoji -- and
      follows him through a city that is drying out. Umbrellas close. From then on its
      thunder is the beat: it flickers on 2 and 4, and strikes the ground where the song
      changes rooms.
   3. Game time: a second is a minute. The song is one sleepless night, 02:00 -> 07:36.
      The city wakes up around him; his storm leaves a wet trail -- the night's route.
   4. He never stops: a step on every beat. At 5:36 the music stops dead and the game
      pauses -- the streetlights go out for dawn, the rain hangs in the air, a bolt hangs
      over the crossing -- and the only thing still moving is him. He looks up, at us.

   The frame is drawn at a third of the resolution (360 x 640 for 1080 x 1920) and scaled
   up by three with no smoothing; colour is quantised to 5 bits a channel through a 4x4
   ordered dither, the way the consoles of that era drew. Everything is a pure function of
   (t, song pack): any frame renders on its own.
   ============================================================================ */

// ---------------------------------------------------------------- the song (80 BPM, bar = 3 s)
const BPM = 80, DOWNBEAT = 0.02, BEAT = 60 / BPM, BAR = 4 * BEAT;
const GRID = makeGrid({ bpm: BPM, downbeat: DOWNBEAT });
let PX = 3;                                     // one game pixel = 3 output pixels (covers may use more)
const FPS = 24;
const CLOCK0 = 120;                             // game minutes at t = 0: 02:00
const SPEED = 1.2;                              // m/s: one 0.9 m step per beat

// The storm's events: the song pack's (render, cover), baked into the build (live), or -- for a
// pack that has none, a synthetic twin -- made from the grid, so the piece always has a storm.
const STORM_DEFAULT = {
  thunder: [[2.88, 1.0], [8.28, 0.45], [11.2, 0.3], [17.93, 0.75], [18.55, 0.55], [19.06, 0.4], [28.19, 0.95], [29.33, 1.0]],
  rain_fade: [31.5, 34.0], beat_in: 33.02, stop: 336.02,
  rooms: [[45.02, 0.8], [57.02, 0.5], [63.02, 0.9], [81.02, 0.8], [105.02, 0.6], [129.02, 0.7], [177.02, 0.5],
    [189.02, 0.9], [201.02, 0.9], [213.02, 0.6], [246.02, 0.7], [258.02, 0.8], [288.02, 0.5],
    [300.02, 1.0], [312.02, 0.6], [318.02, 0.5], [324.02, 0.9], [336.02, 1.0]],
};
let STORM = null;
function stormEvents() {
  if (STORM) return STORM;
  const fromPack = EV && EV.events && EV.events.storm;
  const baked = typeof __STORM__ !== 'undefined' ? __STORM__ : null;
  const s = Object.assign({}, STORM_DEFAULT, baked || {}, fromPack || {});
  if (!s.kick || !s.kick.length || !s.snare || !s.snare.length) {   // the grid's own drums
    const k = [], sn = [];
    for (let b = Math.ceil((s.beat_in - DOWNBEAT) / BEAT - 1e-6); DOWNBEAT + b * BEAT < s.stop - 1e-6; b++) {
      const t = DOWNBEAT + b * BEAT;
      if (b % 2 === 0) k.push([t, 0.9]); else sn.push([t, 0.9]);
    }
    s.kick = s.kick && s.kick.length ? s.kick : k; s.snare = s.snare && s.snare.length ? s.snare : sn;
  }
  return (STORM = s);
}
function stormReset() { STORM = null; }
const SONG = {
  get beatIn() { return stormEvents().beat_in; },
  get stop() { return stormEvents().stop; },
  get fadeA() { return stormEvents().rain_fade[0]; },
  get fadeB() { return stormEvents().rain_fade[1]; },
};

// ---------------------------------------------------------------- game time
const gameMin = t => CLOCK0 + Math.min(t, SONG.stop);           // a second is a minute (the clock stops at the stop)
// 0 = deep night, 1 = full civil dawn: astronomical twilight from ~06:30, civil dawn ~07:31 (mid-latitudes, October)
function dawnOf(t) {
  const m = gameMin(t);
  return clamp((m - 390) / 70) ** 1.5;
}

// ---------------------------------------------------------------- deterministic helpers
const H1 = (a, b = 0, c = 0) => hsh((a * 73856093) ^ (b * 19349663) ^ (c * 83492791) | 0, (a + 7 * b + 13 * c) | 0);
const pick = (arr, u) => arr[Math.min(arr.length - 1, Math.floor(u * arr.length))];
const mix3 = (a, b, u) => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
const css = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
const mul3 = (c, k) => [c[0] * k, c[1] * k, c[2] * k];

// ---------------------------------------------------------------- palette (albedo: lit by the light buffer later)
const PAL = {
  asphalt: [104, 106, 116], asphaltWet: [74, 78, 94], marking: [226, 224, 210], curb: [196, 192, 184],
  sidewalk: [176, 172, 164], sidewalkWet: [140, 140, 146],
  walls: [[214, 200, 172], [204, 168, 120], [206, 166, 152], [176, 172, 166], [194, 180, 152], [222, 214, 196], [168, 150, 134]],
  roofs: [[146, 96, 76], [104, 102, 104], [170, 160, 146], [132, 126, 118], [156, 120, 92]],
  garden: [64, 92, 58], courtRoof: [124, 118, 112], tree: [[70, 100, 58], [96, 112, 50], [150, 128, 52], [60, 88, 62], [128, 96, 46]],
  bins: [[112, 114, 112], [124, 86, 52], [214, 182, 44], [52, 94, 172], [52, 132, 74]],
  coats: [[44, 46, 54], [92, 60, 52], [60, 70, 92], [120, 110, 92], [36, 38, 40], [140, 64, 60], [72, 84, 70]],
  hair: [[22, 18, 16], [60, 40, 28], [120, 90, 60], [30, 24, 22], [150, 140, 130]],
  skin: [[196, 156, 124], [150, 110, 84], [222, 184, 152]],
  cars: [[160, 30, 36], [200, 200, 204], [40, 42, 48], [64, 92, 140], [120, 124, 128], [180, 168, 140]],
};
