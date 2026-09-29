import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { synthesize, drumEvents, twin, formatSpec, distribution, levelMap, defaultPeaks, ENVELOPES, FLUX_CEILING } from '../tools/synth.mjs';
import { CANVAS } from './helpers.mjs';

const spec = {
  seed: 7, fps: 100, dur: 12, bpm: 120, downbeat: 0.25,
  keys: ['bass', 'mid', 'high', 'rms', 'flux', 'voc'],
  voc: [[4, 8, 0.8]],
  events: { stutter: { s1: [[6, 8, 6, 1.0]] } },
  sections: [{ from: 0, energy: 0.2, kick: 'none' }, { from: 4, bass: 0.8, mid: 0.5, energy: 0.8, kick: 'all' }],
};
const frames = (p, k, a, b) => p[k].slice(Math.round(a * p.fps), Math.round(b * p.fps));

test('a synthetic pack is deterministic for a seed', () => {
  assert.deepEqual(synthesize(spec), synthesize(spec));
  assert.notDeepEqual(synthesize(spec).bass, synthesize({ ...spec, seed: 8 }).bass);
});

test('it keeps the grid, the keys and the length it was asked for', () => {
  const p = synthesize(spec);
  assert.equal(p.beats[0], 0.25); assert.ok(Math.abs(p.beats[1] - p.beats[0] - 0.5) < 1e-6);
  for (const k of spec.keys) {
    assert.equal(p[k].length, 1201, k);
    assert.ok(p[k].every(v => v >= 0 && v <= (k === 'flux' ? FLUX_CEILING : 1)), k);
  }
  assert.equal(p.air, undefined);                                   // only the keys asked for
});

test('a pack carries the songpack/1 marker, its grid fields, and says it is synthetic', () => {
  const p = synthesize({ ...spec, keys: undefined });
  assert.equal(p.kaleidophone, 'songpack/1'); assert.equal(p.synthetic, true);
  for (const k of ['fps', 'dur', 'bpm', 'beat0', 'period', 'downbeat']) assert.equal(typeof p[k], 'number', k);
  assert.ok(p.beat0 >= 0 && p.beat0 < p.period);
  p.beats.forEach((b, k) => assert.ok(Math.abs(b - (p.beat0 + k * p.period)) < 1e-3, `beat ${k} on the grid`));
  assert.equal(p.loudest.start, 0); assert.equal(p.loudest.len, 12);  // shorter than a minute: all of it
  for (const k of ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'rmsdb', 'flux', 'bflux', 'hflux', 'cent', 'voc']) assert.equal(p[k].length, 1201, k);
  // a beat grid of its own (the paranoia piece's half-time pulse) is what the grid fields describe
  const h = synthesize({ ...spec, dur: 90, beatGrid: { bpm: 60, downbeat: 1.25 } });
  assert.equal(h.bpm, 60); assert.equal(h.beat0, 0.25); assert.equal(h.downbeat, 1.25);
  // the default reel opens on a bar line of the pack's own grid (envelope.py snaps it the same way)
  const bars = (h.loudest.start - h.downbeat) / (4 * h.period);
  assert.ok(h.loudest.len === 60 && Math.abs(bars - Math.round(bars)) < 1e-3, `loudest starts on a bar: ${h.loudest.start}`);
  assert.equal(synthesize({ ...spec, quantize: 255 }).quantize, 255);
});

test('sections set the level; the kick lands on the beat', () => {
  const p = synthesize(spec), at = t => p.bass[Math.round(t * 100)];
  const quiet = p.bass.slice(100, 350).reduce((a, b) => a + b) / 250, loud = p.bass.slice(500, 1150).reduce((a, b) => a + b) / 650;
  assert.ok(loud > quiet + 0.2, `loud ${loud} vs quiet ${quiet}`);
  assert.ok(at(6.26) > at(6.5), 'a kick decays after the beat');     // beat at 6.25
});

test('[mean, p95, max] levels are reproduced per section, flux up to its 1.5 ceiling', () => {
  const s = {
    seed: 3, fps: 100, dur: 40, bpm: 96, downbeat: 0.4,
    sections: [
      { from: 0, kick: 'none', snare: false, bass: [0.1, 0.3, 0.6], rms: [0.15, 0.35, 0.5], flux: [0.08, 0.2, 0.4] },
      { from: 10.4, kick: '1-3', bass: [0.2, 0.65, 1], mid: [0.45, 0.75, 0.95], high: [0.1, 0.4, 0.9], rms: [0.35, 0.65, 1], flux: [0.25, 0.55, 1] },
      { from: 25.4, bass: [0.8, 0.95, 1], air: [0.6, 0.95, 1], rms: [0.8, 0.9, 1], flux: [0.15, 0.45, 1.5], bflux: [0.25, 0.7, 1.5] },
    ],
  };
  const p = synthesize(s), cuts = [...s.sections.map(x => x.from), s.dur];
  s.sections.forEach((sec, i) => {
    for (const k of ENVELOPES) {
      const want = sec[k]; if (!Array.isArray(want)) continue;
      const got = distribution(frames(p, k, cuts[i], cuts[i + 1]));
      assert.ok(Math.abs(got.mean - want[0]) < 0.02, `${k} @${sec.from} mean ${got.mean} vs ${want[0]}`);
      assert.ok(Math.abs(got.p95 - want[1]) < 0.02, `${k} @${sec.from} p95 ${got.p95} vs ${want[1]}`);
      assert.ok(Math.abs(got.max - want[2]) < 0.005, `${k} @${sec.from} max ${got.max} vs ${want[2]}`);
    }
  });
  assert.equal(Math.max(...p.flux), 1.5);
});

test('a level given as a mean alone gets real-looking peaks, and the old generator\'s weak hits are gone', () => {
  const d = defaultPeaks(0.2);
  assert.ok(d.p95 > 0.5 && d.p95 < 0.8 && d.max > 0.85 && d.max <= 1, JSON.stringify(d));
  assert.deepEqual(defaultPeaks(0), { mean: 0, p95: 0, max: 0 });
  const p = synthesize(spec), loud = distribution(frames(p, 'bass', 4, 12));
  assert.ok(Math.abs(loud.mean - 0.8) < 0.02 && loud.max > 0.95, JSON.stringify(loud));
  // no flux level given: songpack/1's shape, the biggest onsets above 1
  const f = synthesize({ ...spec, keys: undefined });
  assert.ok(Math.max(...f.flux) > 1 && Math.max(...f.flux) <= FLUX_CEILING && Math.max(...f.bflux) > 1);
});

test('levelMap keeps order and hits its targets even for a sparse signal', () => {
  const sparse = Array.from({ length: 2000 }, (_, i) => (i % 50 === 0 ? 1 + (i % 7) / 10 : 0));  // 98 % silence, then hits
  const f = levelMap(sparse, { mean: 0.25, p95: 0.6, max: 1 }, 1.5), y = sparse.map(f);
  const d = distribution(y);
  assert.ok(Math.abs(d.mean - 0.25) < 0.02 && d.max === 1, JSON.stringify(d));
  for (let i = 1; i < sparse.length; i++) if (sparse[i] > sparse[i - 1]) assert.ok(y[i] >= y[i - 1]);
});

test('a section starts on its boundary: nothing before it hears it coming', () => {
  const base = { seed: 5, fps: 100, dur: 12, bpm: 120, downbeat: 0, keys: undefined };
  const quiet = { ...base, sections: [{ from: 0, kick: 'none', snare: false, hats: false, bass: [0.1, 0.2, 0.3], energy: 0.15 }, { from: 6, kick: 'none', snare: false, hats: false, bass: [0.1, 0.2, 0.3], energy: 0.15 }] };
  const drop = { ...base, sections: [quiet.sections[0], { from: 6, kick: 'all', bass: [0.85, 0.95, 1], mid: [0.6, 0.9, 1], high: [0.6, 0.95, 1], rms: [0.8, 0.95, 1] }] };
  const a = synthesize(quiet), b = synthesize(drop), edge = 600;
  for (const k of ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent'])
    assert.deepEqual(a[k].slice(0, edge), b[k].slice(0, edge), `${k} before the drop`);
  assert.ok(b.bass[edge] > a.bass[edge] + 0.3, 'the drop lands on its first frame');
  assert.ok(b.hflux[edge] === Math.max(...b.hflux.slice(edge)), 'a crash opens the section');
});

test('stutter onsets sit on the 16th grid (32nds above its rate), within 20 ms', () => {
  const s = { seed: 7, fps: 100, dur: 60, bpm: 80, downbeat: 0, keys: ['rms'], sections: [{ from: 0 }],
    events: { stutter: { slow: [[10.03, 30, 4, 1]], fast: [[31, 51, 7, 1]] } } };
  const E = synthesize(s).events.stutter, six = 60 / 80 / 4;
  const off = (t, g) => Math.abs(t / g - Math.round(t / g)) * g;
  for (const [key, a, b, rate, grid] of [['slow', 10.03, 30, 4, six], ['fast', 31, 51, 7, six / 2]]) {
    const L = E[key];
    assert.ok(L.every(([t]) => t >= a && t < b), `${key} inside its window`);
    assert.ok(L.every(([t], i) => i === 0 || t > L[i - 1][0]), `${key} in order`);
    const worst = Math.max(...L.map(([t]) => off(t, grid)));
    assert.ok(worst <= 0.0205, `${key}: worst ${Math.round(worst * 1000)} ms off the grid`);
    const r = L.length / (b - a);
    assert.ok(Math.abs(r - rate) / rate < 0.15, `${key}: ${r.toFixed(2)} onsets/s for ${rate}`);
  }
  assert.ok(E.fast.some(([t]) => off(t, six) > 0.05), 'some 32nds in the fast window');
  assert.ok(E.slow.every(([t]) => off(t, six) <= 0.0205), 'the slow one stays on 16ths');
});

test('syllables come 4-7 a second, only inside the voc windows', () => {
  const p = synthesize({ ...spec, dur: 40, voc: [[2, 32, 0.8]] });
  let peaks = 0; for (let i = 201; i < 3199; i++) if (p.voc[i] > p.voc[i - 1] && p.voc[i] >= p.voc[i + 1]) peaks++;
  const rate = peaks / 30;
  assert.ok(rate >= 4 && rate <= 7, `${rate.toFixed(2)} syllables/s`);
  assert.ok(Math.max(...p.voc.slice(0, 199)) === 0 && Math.max(...p.voc.slice(3202)) === 0);
});

test('vocal activity and events appear only where the spec puts them', () => {
  const p = synthesize(spec);
  assert.ok(Math.max(...p.voc.slice(0, 390)) === 0);
  assert.ok(Math.max(...p.voc.slice(400, 800)) > 0.3);
  const s1 = p.events.stutter.s1;
  assert.ok(s1.length >= 8 && s1.every(([t]) => t >= 6 && t < 8));
});

test('the drums breathe: accented and dropped hats, pickups, open hats, ghost notes, a crash on each section with drums', () => {
  const s = { seed: 7, fps: 100, dur: 64, bpm: 100, downbeat: 0.6,
    sections: [{ from: 0, kick: 'none', snare: false }, { from: 20.6, kick: '1-3' }, { from: 40.6, kick: 'none', snare: false, hats: false }, { from: 50.2 }] };
  const ev = drumEvents(s), six = 0.15, v = ev.hat.map(h => h[1]);
  assert.ok(Math.max(...v) - Math.min(...v) > 0.3, 'hat velocities vary');
  assert.ok(ev.hat.some(([t]) => Math.round((t - 0.6) / six) % 2 === 1), 'some 16th pickups');
  assert.ok(ev.open.length > 3, 'open hats');
  assert.ok(ev.snare.some(([, x]) => x < 0.5), 'ghost notes');
  const before = ([t]) => t < 40.6, eighths = Math.round((40.6 - 0.6) / (2 * six));
  const played = ev.hat.filter(h => before(h) && Math.round((h[0] - 0.6) / six) % 2 === 0).length + ev.open.filter(before).length;
  assert.ok(played < eighths && played > 0.9 * eighths, `the odd 8th drops out (${played} of ${eighths})`);
  assert.deepEqual(ev.crash.map(c => c[0]), [20.6, 50.2]);   // not the intro, not the section without drums
});

test('--twin measures [mean, p95, max] rounded to 0.05, keeps what was written by hand, and reads old packs', () => {
  const s = { seed: 11, fps: 100, dur: 30, bpm: 90, downbeat: 0.5, keys: ['bass', 'mid', 'rms', 'flux'],
    sections: [{ from: 0, kick: 'none', bass: [0.1, 0.3, 0.5], rms: [0.2, 0.4, 0.6] }, { from: 11.17, bass: [0.7, 0.95, 1], mid: [0.5, 0.8, 1], rms: [0.7, 0.9, 1], flux: [0.2, 0.5, 1.5] }] };
  const real = synthesize(s);
  const base = { _comment: 'hand', seed: 11, dur: 30, bpm: 90, downbeat: 0.5, keys: s.keys, voc: [[2, 4, 0.5]], events: { e: { k: [[1, 2, 5, 1]] } },
    sections: [{ from: 0, kick: 'none', bass: 0.1, energy: 0.2 }, { from: 11.17, snare: false, bass: 0.7, energy: 0.7 }] };
  const t = twin(real, { base });
  assert.equal(t._comment, 'hand'); assert.deepEqual(t.voc, base.voc); assert.deepEqual(t.events, base.events); assert.deepEqual(t.keys, s.keys);
  assert.equal(t.sections[0].kick, 'none'); assert.equal(t.sections[1].snare, false); assert.equal(t.sections[1].energy, undefined);
  for (const sec of t.sections) for (const k of ['bass', 'mid', 'rms', 'flux']) {
    assert.ok(Array.isArray(sec[k]) && sec[k].length === 3, `${k} is [mean, p95, max]`);
    for (const x of sec[k]) assert.ok(Math.abs(x * 20 - Math.round(x * 20)) < 1e-9, `${k}: ${x} is on the 0.05 grid`);
  }
  s.sections.forEach((sec, i) => { for (const k of ['bass', 'rms', 'flux']) if (sec[k]) sec[k].forEach((x, j) => assert.ok(Math.abs(t.sections[i][k][j] - x) <= 0.05 + 1e-9, `${k}[${j}] @${sec.from}: ${t.sections[i][k][j]} vs ${x}`)); });
  assert.deepEqual(JSON.parse(formatSpec(t)), t);
  // a toolkit-era pack stored bytes, and some packs store the centroid in Hz: both come back as 0..1
  const bytes = { ...real, rms: real.rms.map(x => Math.round(x * 255)), bass: real.bass.map(x => Math.round(x * 255)), cent: undefined };
  const tb = twin(bytes, { sections: [0, 11.17] });
  assert.ok(Math.abs(tb.sections[1].bass[0] - t.sections[1].bass[0]) <= 0.05 + 1e-9);
  const hz = twin({ fps: 100, dur: 5, rms: Array(500).fill(0.5), cent: Array(500).fill(4000) }, { sections: [0] });
  assert.deepEqual(hz.sections[0].cent, [0.5, 0.5, 0.5]);
});

test('every piece ships a synthetic twin spec that synthesizes', () => {
  const pieces = fs.readdirSync(path.join(CANVAS, 'pieces')).filter(d => fs.existsSync(path.join(CANVAS, 'pieces', d, 'piece.json')));
  assert.ok(pieces.length >= 5);
  for (const id of pieces) {
    const s = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'synthetic.json'), 'utf8'));
    const p = synthesize(s);
    assert.ok(p.rms.length > 100, id);
    assert.equal(p.synthetic, true, id);
    const grid = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'piece.json'), 'utf8')).grid;
    assert.ok(Math.abs(s.dur - grid.dur) < 6, `${id}: synthetic duration matches the piece`);
  }
});

test('a twin spec says nothing about the sound: coarse levels per section, no per-hit lists', () => {
  const SECTION_KEYS = new Set(['from', 'kick', 'snare', 'hats', 'crash', 'energy', ...ENVELOPES]);
  for (const id of fs.readdirSync(path.join(CANVAS, 'pieces'))) {
    const f = path.join(CANVAS, 'pieces', id, 'synthetic.json');
    if (!fs.existsSync(f)) continue;
    const s = JSON.parse(fs.readFileSync(f, 'utf8'));
    assert.ok(s.sections.length <= 32, `${id}: a handful of sections`);
    for (const sec of s.sections) for (const [k, v] of Object.entries(sec)) {
      assert.ok(SECTION_KEYS.has(k), `${id}: unexpected section field "${k}"`);
      if (!ENVELOPES.includes(k) && k !== 'energy') continue;
      const xs = Array.isArray(v) ? v : [v];
      assert.ok(xs.length <= 3, `${id}.${k}: a level is at most [mean, p95, max]`);
      for (const x of xs) assert.ok(x >= 0 && x <= FLUX_CEILING && Math.abs(x * 20 - Math.round(x * 20)) < 1e-9, `${id}.${k}: ${x} is rounded to 0.05`);
    }
    assert.ok((s.voc || []).length <= 16, `${id}: voc windows, not syllables`);
    for (const groups of Object.values(s.events || {})) for (const wins of Object.values(groups)) assert.ok(wins.length <= 8, `${id}: event windows, not onsets`);
  }
});

test('quantize stores bytes, like the toolkit-era packs', () => {
  const p = synthesize({ ...spec, quantize: 255 });
  assert.ok(p.bass.every(v => Number.isInteger(v) && v >= 0 && v <= 255));
});
