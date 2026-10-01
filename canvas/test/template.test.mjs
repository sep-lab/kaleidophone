// The template's drawing, without a browser: its lib and its own code in a node vm, against a 2D context
// that takes every call and draws nothing, driven in render mode from its synthetic twin. What is checked
// is what the piece decides -- where text and subjects sit against the safe frame, where the walker is,
// what the endings' cameras do, what the song's events set, that every contact holds -- not pixels: those
// are looked at in QA stills (still.mjs --qa).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { synthesize } from '../tools/synth.mjs';
import { CANVAS } from './helpers.mjs';

const DIR = path.join(CANVAS, 'pieces', 'template');
const SPEC = JSON.parse(fs.readFileSync(path.join(DIR, 'piece.json'), 'utf8'));
const TWIN = JSON.parse(fs.readFileSync(path.join(DIR, 'synthetic.json'), 'utf8'));
const ENDINGS = SPEC.variants.ending.options;
const EXPORTS = ['CONTACTS', 'SAFE_FRAME', 'W', 'H', 'G', 'LW', 'wordFit', 'wordW', 'TITLE', 'TITLE_FIT', 'LAMP_REST', 'LAST',
  'walkX', 'walkerIn', 'CHAIR', 'EXIT', 'exitCamera', 'drosteCamera', 'drosteTurn', 'eventsAt'];

// Anything: a function that returns itself for every property read and every call, and keeps what is
// set on it -- enough of a 2D context, an image, a gradient or a pattern for code that only draws.
function anything() {
  const kept = {};
  const it = new Proxy(function () {}, {
    get: (_, k) => (k in kept ? kept[k] : k === Symbol.toPrimitive ? () => 0 : it),
    set: (_, k, v) => { kept[k] = v; return true; },
    apply: () => it,
  });
  return it;
}
// The page as built: the lib files piece.json lists, then src/ in name order, one script, in render mode.
function template() {
  const canvas = { width: 0, height: 0, style: {}, getContext: anything, addEventListener() {} };
  const g = {
    console, URLSearchParams, setTimeout, clearTimeout,
    location: { search: '?render=1&w=270&h=480' },
    document: { getElementById: id => (id === 'c' ? canvas : null), fonts: { load: () => Promise.resolve(), ready: Promise.resolve() } },
    Path2D: class { moveTo() {} lineTo() {} closePath() {} rect() {} },
    OffscreenCanvas: class { constructor(w, h) { this.width = w; this.height = h; } getContext() { return anything(); } },
    addEventListener() {}, requestAnimationFrame() {},
  };
  g.window = g;
  vm.createContext(g);
  const files = [...SPEC.lib.map(n => path.join(CANVAS, 'lib', `${n}.js`)), ...fs.readdirSync(path.join(DIR, 'src')).sort().map(f => path.join(DIR, 'src', f))];
  vm.runInContext(`${files.map(f => fs.readFileSync(f, 'utf8')).join('\n')}\n;globalThis.__lib = { ${EXPORTS.join(', ')} };`, g);
  g.__init(synthesize(TWIN));
  return g;
}
const plain = x => JSON.parse(JSON.stringify(x));                          // out of the vm's realm
const P = template(), L = P.__lib, F = plain(L.SAFE_FRAME);
const frame = (t, ending = SPEC.variants.ending.default) => plain(P.__frame({ t, variant: { ending } }).contacts);
const contacts = () => plain(L.CONTACTS);
const beat = L.G.beat, bar7 = L.G.bt(7), inside = ([x0, y0, x1, y1]) => x0 >= F.x0 && y0 >= F.y0 && x1 <= F.x1 && y1 <= F.y1;

test('the whole loop, every ending, every frame at 24 fps: no failing contact', () => {
  for (const ending of ENDINGS) {
    let checked = 0;
    for (let i = 0; i < 16 * 24; i++) {
      const c = frame(i / 24, ending);
      if (c) { checked++; assert.equal(c.failing, 0, `${ending} at ${(i / 24).toFixed(3)} s: ${JSON.stringify(c)}`); }
    }
    assert.ok(checked > 300, `${ending}: contacts on ${checked} frames`);
  }
});

test('the title, its stroke and boil included, sits inside the safe frame: centred, fitted to 72% of the width', () => {
  assert.deepEqual(F, { x0: 65, y0: 269, x1: 940, y1: 1248 });
  assert.equal(L.TITLE_FIT, 0.72);
  frame(1.5);                                                              // written on, and holding
  const safe = contacts().filter(c => c.name.endsWith('safe frame'));
  assert.deepEqual(safe.map(c => [c.name, c.d]), [['title↔safe frame', 0], ['subtitle↔safe frame', 0]]);
  const fit = L.wordFit(L.TITLE, L.TITLE_FIT * L.W, { max: 92, min: 64 }), h = fit.hgt;
  for (const line of fit.lines) {
    const ink = L.LW(1.2 * h / 92) / 2 + 1.9;                              // half the stroke, and the boil at full loudness
    const x1 = (L.W + L.wordW(line, h)) / 2 + ink;
    assert.ok(x1 <= F.x1, `"${line}" inks to x ${x1.toFixed(1)}: past the safe frame's ${F.x1} (TikTok's buttons)`);
  }
});

test('bar 7: the walker is in the room as every ending begins, walks out during its first beats, and is gone by beat 3', () => {
  const feet = (t, ending) => { frame(t, ending); return contacts().filter(c => c.name.startsWith('foot↔floor')).map(c => c.a[0]); };
  assert.ok(L.walkX(8) < L.W - 100, `bar 7 starts with his pelvis at x ${L.walkX(8)}: in the room, not at its edge`);
  for (const ending of ENDINGS) {
    const now = feet(bar7, ending), next = feet(bar7 + 1 / 12, ending);
    assert.equal(now.length, 2, `${ending}: he is drawn as it begins`);
    assert.ok(Math.max(...now) < L.W, `${ending}: both feet in the frame at ${bar7} s (${now.map(x => x.toFixed(0))})`);
    assert.ok(Math.max(...next) > Math.max(...now), `${ending}: and walking`);
    assert.ok(feet(bar7 + 2 * beat, ending).every(x => x > L.W), `${ending}: out of the frame by beat 3`);
  }
  assert.ok(!L.walkerIn((bar7 + 3 * beat - L.G.bt(5)) / beat), 'and no longer drawn by beat 4');
});

test('exit: the camera pushes in ~1.8x on the empty chair, up out of the caption, and keeps it in the safe frame until it has un-drawn', () => {
  const C = L.CHAIR, E = L.EXIT, at = (x, y) => [E.fx + E.z * (x - E.fx), E.fy + E.z * (y - E.fy)];
  assert.ok(C.y1 > F.y1 + 200 && !inside([C.x0, C.y0, C.x1, C.y1]), 'where it stands, its legs are under the caption');
  assert.equal(E.z, 1.8);
  assert.equal(L.exitCamera(bar7).z, 1, 'no push while he is leaving');
  assert.ok(Math.abs(L.exitCamera(bar7 + 2.75 * beat).z - E.z) < 1e-12, 'in by beat 2.75, with the paper');
  assert.equal(L.exitCamera(bar7 + 2.75 * beat).fade, 1);
  const box = [...at(C.x0, C.y0), ...at(C.x1, C.y1)];
  assert.ok(inside(box), `pushed in, the chair is ${box.map(v => v.toFixed(0))}: inside ${JSON.stringify(F)}`);
  // the frames where it is the subject log it against the safe frame, as QA stills report it
  for (const t of [15.375, 15.5, 15.75, 15.833]) {
    frame(t, 'exit');
    const c = contacts().find(x => x.name === 'chair↔safe frame');
    assert.ok(c && c.d === 0, `at ${t} s: ${JSON.stringify(c)}`);
  }
  frame(L.LAST, 'exit');
  assert.ok(!contacts().some(x => x.name === 'chair↔safe frame'), 'un-drawn by the last drawing: blank paper');
});

test('droste: the room inside dissolves in over beat 1, the fall is in by beat 3.5, and only the last half-beat goes to paper', () => {
  const cam = t => plain(L.drosteCamera(t)), b = n => bar7 + n * beat;
  assert.deepEqual(cam(bar7), { inner: 0, u: 0, fade: 0 }, 'it starts as the body ends: the window\'s glass, unzoomed');
  assert.ok(cam(b(0.5)).inner > 0.4 && cam(b(0.5)).inner < 0.6, 'half-way through by half a beat');
  assert.equal(cam(b(1)).inner, 1);
  for (let n = 0; n < 3.5; n += 0.25) assert.ok(cam(b(n)).u < cam(b(n + 0.25)).u, `falling at beat ${n}`);
  assert.equal(cam(b(3.5)).u, 1, 'the window fills the frame by beat 3.5');
  const zoom = n => Math.pow(4, cam(b(n)).u), rate = n => zoom(n + 0.5) / zoom(n);
  assert.ok(rate(3) > rate(2) && rate(2) > rate(1) && rate(1) > rate(0), 'and it speeds up, as a fall does');
  for (let n = 0; n <= 3.5; n += 0.25) assert.equal(cam(b(n)).fade, 0, `no paper over it at beat ${n}`);
  assert.ok(cam(b(3.5) + 1 / 24).fade > 0);
  assert.ok(Math.abs(L.LAST - (16 - 1 / 12)) < 1e-12);
  assert.equal(cam(L.LAST).fade, 1, 'all paper by the loop\'s last drawing, so it closes on the title card\'s first frame');
});

test('droste: the twin\'s chords turn it a step as bar 7 begins; a pack without chords doesn\'t turn it', () => {
  const step = 15 * Math.PI / 180;
  assert.equal(L.drosteTurn(bar7 - 0.1), 0);
  assert.ok(L.drosteTurn(bar7 + 0.1) > 0 && L.drosteTurn(bar7 + 0.1) < step, 'turning');
  assert.ok(Math.abs(L.drosteTurn(bar7 + 0.25) - step) < 1e-12, 'one step, in a quarter of a second');
  assert.ok(Math.abs(L.drosteTurn(L.LAST) - step) < 1e-12, 'and only one: the next change is the loop\'s');
  const Q = template();
  Q.__init({ ...synthesize(TWIN), events: { midi: synthesize(TWIN).events.midi } });
  assert.equal(Q.__lib.drosteTurn(bar7 + 0.5), 0);
});

test('the song\'s events: a snare takes the lamp from its low rest to full and pops the bulb; a kick\'s nod decays over a quarter-second', () => {
  const ev = synthesize(TWIN).events.midi;
  // a backbeat with nothing in the second before it (no ghost note), and a kick on the beat after another
  const snare = ev.snare.find(([t, v], i) => v > 0.8 && t > 4 && t - ev.snare[i - 1][0] > 0.9)[0], kick = ev.kick.find(([t]) => t > 4)[0];
  const at = t => plain(L.eventsAt(t, {}));
  assert.equal(L.LAMP_REST, 0.15);
  const on = at(snare), rest = at(snare - 1 / 12);
  assert.ok(Math.abs(rest.lamp - L.LAMP_REST) < 0.02 && rest.pop < 0.02, `between hits: ${JSON.stringify(rest)}`);
  assert.ok(on.lamp > 0.85 && on.pop > 0.8, `on the snare: ${JSON.stringify(on)}`);
  assert.ok(on.lamp / rest.lamp > 5, 'a flash, not a flicker: the light at least five times its rest');
  const decay = at(kick + 1 / 12).nod / at(kick).nod;
  assert.ok(Math.abs(decay - Math.exp(-1 / 12 / 0.25)) < 1e-9, `the nod one drawing on: ${decay.toFixed(3)} of the hit (a 0.25 s decay)`);
  // a dropped track has no MIDI: the envelope's onsets stand in
  const Q = template();
  Q.__init({ fps: 100, rms: [0, 0] });
  assert.deepEqual(plain(Q.__lib.eventsAt(1, { hflux: 1, bflux: 0.5 })), { lamp: 1, pop: 1, nod: 0 });
});
