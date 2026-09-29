import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { loadLib, loadLibWith, CANVAS } from './helpers.mjs';

const L = loadLib(['core']);

test('clamp defaults to 0..1 and honours explicit bounds', () => {
  assert.equal(L.clamp(2), 1); assert.equal(L.clamp(-1), 0); assert.equal(L.clamp(5, 0, 10), 5);
});

test('kf holds the ends and eases between keys', () => {
  const keys = [[0, 0], [1, 10], [2, 10], [3, 0]];
  assert.equal(L.kf(-1, keys), 0); assert.equal(L.kf(1.5, keys), 10); assert.equal(L.kf(9, keys), 0);
  assert.equal(L.kf(0.5, keys), 5);                   // smoothstep is symmetric at the midpoint
  assert.ok(L.kf(0.25, keys) < 2.5);                  // ...and slow at the start
});

test('pulse: linear attack, exponential decay, zero before the hit', () => {
  assert.equal(L.pulse(0.9, 1, 0.01, 0.1), 0);
  assert.ok(Math.abs(L.pulse(1.01, 1, 0.01, 0.1) - 1) < 1e-9);
  assert.ok(Math.abs(L.pulse(1.11, 1, 0.01, 0.1) - Math.exp(-1)) < 1e-9);
});

test('the grid puts bars, beats and backbeats where the tempo says', () => {
  const G = L.makeGrid({ bpm: 120, downbeat: 0.255 });
  assert.equal(G.beat, 0.5); assert.equal(G.bar, 2);
  assert.equal(G.bt(36), 72.255);                     // SAME AS YOU's reel ends on bar 36
  assert.ok(Math.abs(G.barOf(72.255) - 36) < 1e-12);
  assert.equal(G.beatInBar(0.255 + 0.5), 1);
  assert.ok(G.isBackbeat(0.255 + 0.5 + 0.01) && G.isBackbeat(0.255 + 1.5 + 0.01) && !G.isBackbeat(0.255 + 1.0 + 0.01));
  assert.equal(G.onTwos(1.0 / 12 * 5 + 0.03), 5 / 12);   // drawn on twos: 12 drawings a second
});

test('hashes are deterministic and in [0, 1)', () => {
  const a = [], b = [];
  for (let i = 0; i < 200; i++) { a.push(L.hsh(i, 7)); b.push(L.hsh(i, 7)); }
  assert.deepEqual(a, b);
  assert.ok(a.every(v => v >= 0 && v < 1));
  assert.notEqual(L.hsh(1, 2), L.hsh(2, 1));
  const r1 = L.mulberry32(42), r2 = L.mulberry32(42);
  for (let i = 0; i < 50; i++) assert.equal(r1(), r2());
});

test('envAt interpolates the 100 Hz pack linearly and clamps at the ends', () => {
  L.envInit({ fps: 100, bass: [0, 1, 0.5] });
  assert.equal(L.envAt('bass', -1), 0);
  assert.equal(L.envAt('bass', 0.005), 0.5);
  assert.equal(L.envAt('bass', 0.015), 0.75);
  assert.equal(L.envAt('bass', 9), 0.5);
  assert.equal(L.envAt('missing', 0.01), 0);
});

test('strokeScale keeps covers from going hairline', () => {
  assert.equal(L.strokeScale(100), 0.8);
  assert.equal(L.strokeScale(600), 3);
});

test('two-bone IK keeps bone lengths and puts the joint on the pole side', () => {
  const { ik } = loadLibWith(['core', 'rig'], ['ik']);
  const s = ik(0, 0, 100, 0, 60, 60, 50, -100);        // pole above the line
  const d1 = Math.hypot(s.j[0], s.j[1]), d2 = Math.hypot(s.e[0] - s.j[0], s.e[1] - s.j[1]);
  assert.ok(Math.abs(d1 - 60) < 1e-9 && Math.abs(d2 - 60) < 1e-9);
  assert.ok(s.j[1] < 0, 'joint on the pole side');
  const t = ik(0, 0, 100, 0, 60, 60, 50, 100);
  assert.ok(t.j[1] > 0);
  const far = ik(0, 0, 500, 0, 60, 60, 0, -1);         // out of reach: straight, flagged
  assert.equal(far.reach, false);
  assert.ok(Math.abs(far.e[0] - 120 * 0.9995) < 1e-6);
});

test('seated() builds the body from the floor up: ankle on the floor, pill on the seat', () => {
  const { seated, RG, LW } = loadLibWith(['core', 'ink', 'rig'], ['seated', 'RG', 'LW']);
  const g = seated(300, 1500, 70, 1);
  assert.ok(Math.abs(g.ankle[1] + LW(1) / 2 - 1500) < 1e-9);                 // the foot line sits on the floor
  assert.ok(Math.abs(g.P[1] + RG.tr * 70 - g.seatY) < 1e-9);                 // the pill bottom is the seat top
  assert.ok(Math.abs(g.knee[0] - (300 + RG.thigh * 70)) < 1e-9);            // horizontal thigh
});

test('the hand-lettered alphabet covers A-Z, 0-9 and the title punctuation', () => {
  const { GLYPH } = loadLibWith(['core', 'ink'], ['GLYPH']);
  for (const ch of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789?!-.(),\'') {
    assert.ok(GLYPH[ch] && GLYPH[ch].length, `glyph ${ch}`);
    for (const s of GLYPH[ch]) assert.ok(s.length >= 2 && s.every(p => p.length === 2 && isFinite(p[0]) && isFinite(p[1])), `strokes of ${ch}`);
  }
});

// ---- ink.js against a recording 2D context: glow's colour stops, the lettering ----------------
function inkWith() {
  const grads = [], paths = [], warns = [];
  const noop = () => {};
  const ctx = {
    fillStyle: '#000000', strokeStyle: '#000000', lineWidth: 1, lineCap: 'butt', lineJoin: 'miter', globalCompositeOperation: 'source-over',
    beginPath() { paths.push([]); }, moveTo(x, y) { paths[paths.length - 1].push([x, y]); }, lineTo(x, y) { paths[paths.length - 1].push([x, y]); },
    closePath: noop, stroke: noop, fill: noop, fillRect: noop,
    createRadialGradient(...args) { const g = { args, stops: [], addColorStop(o, c) { g.stops.push([o, c]); } }; grads.push(g); return g; },
  };
  const sandbox = { Math, console: { log: noop, error: noop, warn: (...a) => warns.push(a.join(' ')) }, ctx };
  vm.createContext(sandbox);
  const code = ['core', 'ink'].map(n => fs.readFileSync(path.join(CANVAS, 'lib', `${n}.js`), 'utf8')).join('\n');
  vm.runInContext(code + '\n;globalThis.__lib = { glow, withAlpha, word, wordW, wordFit, glyphSpan, measure, GLYPH, GLYPH_TRACK, GLYPH_NONE, CONTACTS, contactReport, heldEnv, envInit, envAt, ENV };', sandbox);
  return { ...sandbox.__lib, ctx, grads, paths, warns };
}

test('glow fades to its own colour at alpha 0, not through black', () => {
  const K = inkWith();
  K.glow(360, 600, 480, 'rgba(243,228,188,0.6)');
  assert.deepEqual(K.grads[0].stops, [[0, 'rgba(243,228,188,0.6)'], [1, 'rgba(243,228,188,0)']]);
  assert.deepEqual(K.grads[0].args, [360, 600, 0, 360, 600, 480]);
  K.glow(0, 0, 10, '#ffcc00'); K.glow(0, 0, 10, '#fc0'); K.glow(0, 0, 10, 'rgb(10, 20, 30)');
  assert.deepEqual(K.grads.slice(1).map(g => g.stops[1][1]), ['rgba(255,204,0,0)', 'rgba(255,204,0,0)', 'rgba(10,20,30,0)']);
  K.glow(0, 0, 10, 'rgba(1,2,3,0.5)', 'rgba(9,9,9,0)', 'screen');                // an explicit end colour is kept
  assert.deepEqual(K.grads[4].stops[1], [1, 'rgba(9,9,9,0)']);
  assert.equal(K.ctx.globalCompositeOperation, 'source-over');                     // and the blend mode restored
  assert.equal(K.withAlpha('#11223380', 0.25), 'rgba(17,34,51,0.25)');
});

test('lettering: every glyph advances by its own ink width, so I, 1 and punctuation leave no holes', () => {
  const K = inkWith();
  const s = 'HI1.H:I/&H';
  assert.equal(K.word(s, 100, 0, 84, '#000', 5), K.wordW(s, 84));                 // the width drawn is the width measured
  assert.equal(K.measure(() => K.word(s, 100, 0, 84, '#000', 5)), K.wordW(s, 84));
  // the ink box of each glyph as drawn (every point is boiled by at most 1.3 px)
  let at = 0; const boxes = [];
  for (const ch of s) {
    const xs = K.paths.slice(at, at + K.GLYPH[ch].length).flat().map(p => p[0]); at += K.GLYPH[ch].length;
    boxes.push([Math.min(...xs), Math.max(...xs)]);
  }
  assert.equal(at, K.paths.length);
  for (let i = 1; i < boxes.length; i++) {
    const gap = boxes[i][0] - boxes[i - 1][1];
    assert.ok(Math.abs(gap - K.GLYPH_TRACK) <= 2.6, `${s[i - 1]}${s[i]}: ink gap ${gap.toFixed(1)}, want ${K.GLYPH_TRACK}`);
  }
  assert.ok(K.wordW('I', 84) < 0.65 * K.wordW('M', 84) && K.wordW('.', 84) < K.wordW('I', 84));
  for (const ch of '/&:') assert.ok(K.GLYPH[ch] && K.glyphSpan(ch)[1] >= 0, `glyph ${ch}`);
  assert.equal(K.warns.length, 0);
});

test('a missing glyph is a gap that warns once and fails the QA contact report', () => {
  const K = inkWith();
  const w = K.word('A@B@', 0, 0, 84, '#000', 5);
  assert.equal(K.warns.length, 1);
  assert.match(K.warns[0], /no glyph for "@"/);
  assert.equal(w, K.wordW('A', 84) + K.wordW('B', 84) + 2 * K.GLYPH_NONE + 3 * K.GLYPH_TRACK);
  assert.deepEqual({ ...K.contactReport() }, { n: 2, worst: 'glyph "@" missing', d: K.GLYPH_NONE, failing: 2 });   // (copied out of the vm's realm)
  K.CONTACTS.length = 0;
  K.word('@', 0, 0, 84, '#000', 5); K.measure(() => K.word('@@', 0, 0, 84, '#000', 5));
  assert.equal(K.warns.length, 1, 'one warning per missing character');
  assert.equal(K.CONTACTS.length, 1, 'a dry run logs no contact');
});

test('wordFit: one line up to the width, two balanced lines rather than going under the minimum', () => {
  const K = inkWith(), maxW = 0.78 * 1080;
  const one = K.wordFit('KALEIDOPHONE', maxW, { max: 92, min: 64 });
  assert.equal(one.lines.length, 1);
  assert.ok(one.hgt >= 64 && one.hgt <= 92 && K.wordW('KALEIDOPHONE', one.hgt) <= maxW + 1e-9);
  assert.equal(K.wordFit('SHOULD I ?', maxW).hgt, 92);                            // short titles stay at the design size
  const two = K.wordFit('HAMECHI MANZOR DARE', maxW, { max: 92, min: 64 });
  assert.deepEqual([...two.lines], ['HAMECHI', 'MANZOR DARE']);
  assert.ok(two.hgt >= 64 && Math.max(...two.lines.map(l => K.wordW(l, two.hgt))) <= maxW + 1e-9);
  const word = K.wordFit('SUPERCALIFRAGILISTIC', maxW, { max: 92, min: 64 });     // one word can't break: it shrinks
  assert.equal(word.lines.length, 1);
  assert.ok(Math.abs(K.wordW(word.lines[0], word.hgt) - maxW) < 1e-9);
});

test('heldEnv reads the song pack at the drawing time, and passes live values through', () => {
  const K = inkWith();
  assert.deepEqual(K.heldEnv({ bass: 0.3 }, 0.5), { bass: 0.3 });                  // no pack: live mode
  K.envInit({ fps: 100, bass: [0, 1, 0.5, 0.25], rms: [0.2, 0.4, 0.6, 0.8] });
  const e = K.heldEnv({ bass: 0.9, rms: 0.9 }, 0.01);
  assert.equal(e.bass, 1); assert.ok(Math.abs(e.rms - 0.4) < 1e-12);
});
