import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { synthesize, drumEvents, drumMidi, chordEvents, twin, formatSpec, distribution, levelMap, defaultPeaks, ENVELOPES, FLUX_CEILING, MIDI_DRUMS, STEMS } from '../tools/synth.mjs';
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
    for (const groups of Object.values(s.events || {})) for (const wins of Object.values(groups)) {
      assert.ok(wins.length <= 8, `${id}: event windows, not onsets`);
      // a window's pitches: a made-up scale to draw from, not a line of notes
      for (const w of wins) if (w[4] !== undefined) assert.ok(w[4].length <= 16, `${id}: a window's pitches are a scale, not a transcription`);
    }
    // chords: a short progression the grid plays round, never the song's changes in time
    if (s.chords) {
      assert.deepEqual(Object.keys(s.chords).filter(k => !['track', 'progression', 'every'].includes(k)), [], `${id}: chords are a track, a progression and a period`);
      assert.ok(s.chords.progression.length <= 16, `${id}: a progression, not a transcription`);
    }
  }
});

test('quantize stores bytes, like the toolkit-era packs', () => {
  const p = synthesize({ ...spec, quantize: 255 });
  assert.ok(p.bass.every(v => Number.isInteger(v) && v >= 0 && v <= 255));
});

// ---------------------------------------------------------------- the drums as MIDI, and stems
test('the drums it plays are in the pack as MIDI: events.midi.kick / .snare / .hat / .crash, [t, velocity, 0.05, pitch]', () => {
  const s = { seed: 7, fps: 100, dur: 64, bpm: 100, downbeat: 0.6,
    sections: [{ from: 0, kick: 'none', snare: false }, { from: 20.6, kick: '1-3' }, { from: 40.6, kick: 'none', snare: false, hats: false }, { from: 50.2 }] };
  const M = synthesize(s).events.midi, ev = drumEvents(s);
  assert.deepEqual(Object.keys(M), ['kick', 'snare', 'hat', 'crash']);
  assert.deepEqual(M, drumMidi(ev));
  for (const [track, list] of Object.entries(M)) {
    assert.ok(list.length > 0, track);
    list.forEach(([t, v, d, pitch], i) => {
      assert.ok(t >= 0 && t < s.dur && (!i || t >= list[i - 1][0]), `${track}: in order, inside the song`);
      assert.ok(v > 0 && v <= 1 && d === 0.05 && Number.isInteger(pitch), `${track}: [${t}, ${v}, ${d}, ${pitch}]`);
    });
  }
  // the hits the envelopes were built from, rounded to 0.1 ms; the open hats ride in `hat` as note 46
  assert.deepEqual(M.kick.map(e => e[0]), ev.kick.map(([t]) => +t.toFixed(4)));
  assert.deepEqual(M.snare.map(e => e[0]), ev.snare.map(([t]) => +t.toFixed(4)));
  assert.equal(M.hat.length, ev.hat.length + ev.open.length);
  assert.deepEqual(M.hat.filter(e => e[3] === MIDI_DRUMS.open).map(e => e[0]), ev.open.map(([t]) => +t.toFixed(4)));
  assert.ok(M.kick.every(e => e[3] === 36) && M.snare.every(e => e[3] === 38) && M.hat.every(e => e[3] === 42 || e[3] === 46) && M.crash.every(e => e[3] === 49));
  assert.deepEqual(M.crash.map(e => e[0]), [20.6, 50.2], 'a crash opens each section with drums');
  assert.ok(M.snare.some(e => e[1] < 0.5), 'the ghost notes are soft');
  assert.ok(M.kick.every(([t]) => t >= 20.6 && (t < 40.6 || t >= 50.2)), 'no kick where a section has none');
  // a spec's own events sit beside it; a group of its own named "midi" would be overwritten, so it is refused
  const both = synthesize({ ...spec }).events;
  assert.deepEqual(Object.keys(both), ['stutter', 'midi']);
  assert.throws(() => synthesize({ ...spec, events: { midi: { k: [[1, 2]] } } }), /can't have a group named "midi"/);
});

// sha256 of each piece's v0.3.0 twin pack as JSON (Node 22): the gallery and CI render from these, so a
// spec must still produce them byte for byte, apart from what is new since: events.midi, and stems and
// events.chords where the spec asks for them (the template's twin plays chords now; nothing else moved).
const V030 = {
  'hamechi-manzor-dare': '24a17ceb9667c5d0a06a2095bade3481f65c580d30a7b90c0669ba9ff1c7c5f3',
  minus: '77a00c7c595cd6ff2fefbf4282f9fa52a6a1c3c966b70ad66e62a680ba423149',
  'same-as-you': 'b5a2b7e32dfd0c4ec4aadf42aa50d4f426ce06fd8d6df77987c848d47e406344',
  'should-i': '2336386ecbbb916fd52a7e94bb7a4bd44fe83363eb4ee86392da05ff8d8f04d9',
  template: 'bfd62876e947b37a1ead7d8b59584e53ae9a687c71cd3c54c8e5ffd5b1db2851',
};
const withoutNew = p => { const q = { ...p, events: { ...p.events } }; delete q.events.midi; delete q.events.chords; if (!Object.keys(q.events).length) delete q.events; delete q.stems; return q; };

test('every piece\'s twin is byte-identical to v0.3.0\'s, apart from events.midi (and stems and events.chords, where asked for)', () => {
  for (const [id, sha] of Object.entries(V030)) {
    const spec = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'synthetic.json'), 'utf8'));
    const got = crypto.createHash('sha256').update(JSON.stringify(withoutNew(synthesize(spec)))).digest('hex');
    assert.equal(got, sha, `${id}: its twin pack changed. If you re-measured or edited pieces/${id}/synthetic.json on purpose, update its hash here; if not, the generator changed what every render and the gallery see`);
  }
});

test('stems: true adds stems and changes nothing else', () => {
  const a = synthesize(spec), b = synthesize({ ...spec, stems: true });
  assert.equal(a.stems, undefined);
  assert.deepEqual(withoutNew(b), withoutNew(a));
  assert.deepEqual(b.events.midi, a.events.midi);
  assert.deepEqual(Object.keys(b).slice(-2), ['events', 'stems'], 'the new keys come last');
});

test('stems: the master\'s envelopes per part, each normalised on its own like a real pack\'s; a part that doesn\'t play reads 0', () => {
  const s = { ...spec, dur: 16, keys: undefined, stems: true };
  const p = synthesize(s), n = p.rms.length, keys = ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'rmsdb', 'flux', 'bflux', 'hflux', 'cent'];
  assert.deepEqual(Object.keys(p.stems), STEMS);
  for (const st of STEMS) {
    assert.deepEqual(Object.keys(p.stems[st]), keys, `${st}: the master's envelopes, voc aside`);
    for (const k of keys) {
      const a = p.stems[st][k], on = a.filter(v => (k === 'rmsdb' ? v > -100 : v > 0));
      assert.equal(a.length, n, `${st}.${k}`);
      if (k === 'rmsdb') { assert.ok(a.every((v, i) => v >= -100 && v <= p.rmsdb[i] + 0.05), `${st}.rmsdb: never louder than the whole`); continue; }
      assert.ok(a.every(v => v >= 0 && v <= (/flux/.test(k) ? FLUX_CEILING : 1)), `${st}.${k} in range`);
      const top = Math.max(...a);
      if (on.length && k !== 'cent') assert.ok(/flux/.test(k) ? top >= 1 && top <= FLUX_CEILING : top === 1, `${st}.${k}: its own loudest reads 1 (a flux: its 99.5th), got ${top}`);
    }
  }
  const at = (st, k, a, b) => p.stems[st][k].slice(Math.round(a * 100), Math.round(b * 100)), max = a => Math.max(...a);
  assert.ok(STEMS.filter(st => st !== 'vocals').every(st => max(p.stems[st].rms) === 1));
  assert.equal(max(at('vocals', 'rms', 0, 3.9)), 0, 'no vocals before the voc window');
  assert.ok(max(at('vocals', 'mid', 4.2, 7.8)) > 0.5 && max(at('vocals', 'cent', 4.2, 7.8)) > 0, 'singing in it');
  assert.ok(Math.min(...at('vocals', 'rmsdb', 0, 3.9)) === -100, 'digital silence in dB');
  assert.equal(max(p.stems.bass.mid), 0, 'the bassline is all bass');
  assert.equal(max(at('drums', 'bass', 0, 3.9)), 0, 'no kick in the first section: nothing in the drums\' bass');
  // consistent with the master: the drums' bass flux rises on the kicks the pack says were played
  const kickAt = p.events.midi.kick.map(([t]) => Math.round(t * 100)), bf = p.stems.drums.bflux;
  const onKick = kickAt.map(i => Math.max(...bf.slice(i, i + 3))), mean = a => a.reduce((x, y) => x + y, 0) / a.length;
  assert.ok(mean(onKick) > 5 * mean(bf), `the drums' bflux on the kicks ${mean(onKick).toFixed(2)} vs everywhere ${mean(bf).toFixed(2)}`);
  const q = synthesize({ ...s, quantize: 255 });
  assert.ok(STEMS.every(st => keys.filter(k => k !== 'rmsdb').every(k => q.stems[st][k].every(v => Number.isInteger(v) && v >= 0 && v <= 255))), 'quantize stores the stems as bytes too');
  assert.deepEqual(Object.keys(synthesize({ ...s, keys: ['bass', 'rms', 'voc'] }).stems.drums), ['bass', 'rms'], 'the spec\'s keys');
});

test('--twin keeps "stems" when it re-measures a piece', () => {
  const real = synthesize({ ...spec, keys: undefined });
  const t = twin(real, { base: { ...spec, stems: true } });
  assert.equal(t.stems, true);
  assert.deepEqual(Object.keys(t).slice(-2), ['stems', 'sections']);
});

// ---------------------------------------------------------------- chords
const CHORDS = { track: 'keys', progression: ['Am', 'F', 'C', 'G'], every: 'bar' };

test('chords: a progression on the bar lines, as a chord track -- events.chords.<track> = [[t, 1, name], ...]', () => {
  const p = synthesize({ ...spec, chords: CHORDS });                  // 120 BPM from 0.25 s: a bar line every 2 s
  assert.deepEqual(p.events.chords, { keys: [[0.25, 1, 'Am'], [2.25, 1, 'F'], [4.25, 1, 'C'], [6.25, 1, 'G'], [8.25, 1, 'Am'], [10.25, 1, 'F']] });
  assert.deepEqual(chordEvents({ ...spec, chords: CHORDS }), p.events.chords);
  // the progression starts on the first downbeat; a bar line before it plays the end of it, into chord 1
  const late = chordEvents({ bpm: 120, dur: 9, downbeat: 3, chords: CHORDS }).keys;
  assert.deepEqual(late, [[1, 1, 'G'], [3, 1, 'Am'], [5, 1, 'F'], [7, 1, 'C']]);
  // every beat, every n bars; the track named as asked; times rounded to 0.1 ms, like the drums
  assert.deepEqual(chordEvents({ bpm: 120, dur: 2, chords: { progression: ['C', 'G'], every: 'beat' } }), { keys: [[0, 1, 'C'], [0.5, 1, 'G'], [1, 1, 'C'], [1.5, 1, 'G']] });
  assert.deepEqual(chordEvents({ bpm: 120, dur: 12, chords: { track: 'pad', progression: ['Dm'], every: 2 } }), { pad: [[0, 1, 'Dm'], [4, 1, 'Dm'], [8, 1, 'Dm']] });
  assert.deepEqual(chordEvents({ bpm: 90, dur: 6, downbeat: 0.1234567, chords: CHORDS }).keys.map(e => e[0]), [0.1235, 2.7901, 5.4568]);
});

test('chords change nothing else: the envelopes, the drums and the other events are the pack a spec without them makes', () => {
  const a = synthesize(spec), b = synthesize({ ...spec, chords: CHORDS });
  assert.deepEqual(withoutNew(b), withoutNew(a));
  assert.deepEqual(b.events.midi, a.events.midi);
  assert.deepEqual(Object.keys(b.events), ['stutter', 'midi', 'chords'], 'the new list comes last');
  assert.equal(JSON.stringify({ ...b, events: { stutter: b.events.stutter, midi: b.events.midi } }), JSON.stringify(a), 'byte for byte');
});

test('chords: a spec that can\'t be played is refused, saying what is wrong', () => {
  const bad = (chords, re) => assert.throws(() => synthesize({ ...spec, chords }), re);
  bad('Am F C G', /"chords" must be \{"track": "keys", "progression"/);
  bad([CHORDS], /"chords" must be \{"track"/);
  bad({ ...CHORDS, track: 'my.keys' }, /"track" must be a name of letters, digits, - and _ \(it is a key: events\.chords\.<track>\), got "my\.keys"/);
  bad({ ...CHORDS, progression: [] }, /"progression" must be a non-empty list of chord names, got \[\]/);
  bad({ ...CHORDS, progression: ['Am', ''] }, /"progression" must be a non-empty list of chord names/);
  bad({ ...CHORDS, every: 'bars' }, /"every" must be "bar", "beat" or a number of bars, got "bars"/);
  bad({ ...CHORDS, every: 0 }, /"every" must be "bar", "beat" or a number of bars, got 0/);
  // a spec's own events can't take the group the progression is written to
  assert.throws(() => synthesize({ ...spec, events: { chords: { k: [[1, 2]] } } }), /can't have a group named "chords": events\.chords is the chord progression/);
});

test('--twin keeps "chords" when it re-measures a piece; the template\'s twin changes chord into bar 7', () => {
  const t = twin(synthesize({ ...spec, keys: undefined }), { base: { ...spec, chords: CHORDS, stems: true } });
  assert.deepEqual(t.chords, CHORDS);
  assert.deepEqual(Object.keys(t).slice(-3), ['chords', 'stems', 'sections']);
  assert.deepEqual(JSON.parse(formatSpec(t)).chords, CHORDS);
  // what the template's droste turns on: a change of chord on the bar line where its endings start
  const tpl = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', 'template', 'synthetic.json'), 'utf8'));
  const at = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', 'template', 'piece.json'), 'utf8')).variants.ending.at;
  const ch = Object.values(synthesize(tpl).events.chords)[0], i = ch.findIndex(e => e[0] === at);
  assert.ok(i > 0 && ch[i][2] !== ch[i - 1][2], `a new chord at ${at} s: ${JSON.stringify(ch.slice(i - 1, i + 1))}`);
});

// ---------------------------------------------------------------- every twin, byte for byte
// sha256 of each piece's whole twin pack as JSON, events.midi and all: the gallery, CI's smoke render and
// the golden frames render from these. The five that shipped in v0.4.0 have not moved since (the pitch
// column and "alias" are new, and only a spec that asks for them gets them); ⛈️'s twin is pinned as it landed.
const TWINS = {
  'hamechi-manzor-dare': '06c2e4f33a314328026c26290b8af2c62ced272a2af8eead377a5a5e0c44ea44',
  minus: 'c0c393e42634089802a115ae957b537dcfa8ba2ad71181089000d92cf13041dc',
  'same-as-you': '24029df7e0b21ef6ebc8919738545442cdf5a8b65d170796a1bed333e562d843',
  'should-i': 'c573da10cc4ed0f16cc4dd2c2da3b687a2f2eb0efc54bd285733b97b95b4a7bd',
  template: '32d09db0e28fb90958e79b309c1d02fcda9ec151c4b1ef1d2ce6370a05106d84',
  storm: '5084e08150bc3fd38acab86f548e92be5785ae77babc78629a2b937de091071a',
};

test('every piece\'s twin pack is byte-identical to the one it was pinned with, events.midi and all', () => {
  for (const [id, sha] of Object.entries(TWINS)) {
    const spec = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'synthetic.json'), 'utf8'));
    const got = crypto.createHash('sha256').update(JSON.stringify(synthesize(spec))).digest('hex');
    assert.equal(got, sha, `${id}: its twin pack changed. If you re-measured or edited pieces/${id}/synthetic.json on purpose, update its hash here; if not, the generator changed what every render and the gallery see`);
  }
});

// ---------------------------------------------------------------- pitches
const PITCHED = { seed: 7, fps: 100, dur: 20, bpm: 80, downbeat: 0.02, keys: ['rms'], sections: [{ from: 0 }] };
const SCALE = [9, 12, 14, 16, 19];

test('pitches: a window with a list gives every onset a third column, drawn from it; the onsets don\'t move', () => {
  const plain = synthesize({ ...PITCHED, events: { storm: { melody: [[1, 15, 3, 0.9]] } } }).events.storm.melody;
  const P = synthesize({ ...PITCHED, events: { storm: { melody: [[1, 15, 3, 0.9, SCALE]] } } });
  const mel = P.events.storm.melody;
  assert.ok(plain.length > 20 && plain.every(e => e.length === 2), 'no list: [t, s], as before');
  assert.ok(mel.every(e => e.length === 3 && SCALE.includes(e[2])), 'every onset gets a pitch from the list');
  assert.deepEqual(mel.map(([t, s]) => [t, s]), plain, 'the same onsets, with or without pitches');
  assert.ok(new Set(mel.map(e => e[2])).size >= 4, 'it plays round the list, not one note');
  // a piece reading the pitch as ⛈️ does, clamp(bin / 47), gets a number for every note
  assert.ok(mel.every(([, , bin]) => Number.isFinite(Math.min(1, Math.max(0, bin / 47)))));
  // windows mix: one with pitches, one without; the drums and the envelopes are untouched
  const mixed = synthesize({ ...PITCHED, events: { storm: { melody: [[1, 8, 3, 0.9, SCALE], [10, 15, 3, 0.9]] } } }).events.storm.melody;
  assert.ok(mixed.filter(([t]) => t < 8).every(e => e.length === 3) && mixed.filter(([t]) => t >= 10).every(e => e.length === 2));
  const { events: a, ...ra } = P, { events: b, ...rb } = synthesize({ ...PITCHED, events: { storm: { melody: [[1, 15, 3, 0.9]] } } });
  assert.deepEqual(ra, rb); assert.deepEqual(a.midi, b.midi);
});

test('pitches: a list that can\'t be drawn from is refused, naming the window', () => {
  const bad = (p, re) => assert.throws(() => synthesize({ ...PITCHED, events: { storm: { melody: [[1, 15, 3, 0.9, p]] } } }), re);
  for (const p of [[], 'C4', [9, 'E4'], [9, null], [9, NaN], {}]) bad(p, /events\.storm\.melody window \[1, 15, \.\.\.\]: its pitches must be a non-empty list of numbers/);
});

// ---------------------------------------------------------------- alias
test('alias: {"vstem": "voc"} writes the voc envelope again under the name a piece reads', () => {
  const s = { ...spec, keys: ['bass', 'rms', 'voc'], alias: { vstem: 'voc' } };
  const p = synthesize(s), q = synthesize({ ...s, alias: undefined });
  assert.deepEqual(p.vstem, p.voc); assert.ok(Math.max(...p.vstem) > 0.3, 'the syllables are in it');
  const { vstem, ...rest } = p;
  assert.equal(JSON.stringify(rest), JSON.stringify(q), 'nothing else changes');
  assert.deepEqual(Object.keys(p).slice(-3), ['voc', 'vstem', 'events'], 'right after the envelopes');
});

test('alias: one that would shadow a key or name no envelope in the pack is refused', () => {
  const bad = (alias, re, keys = ['bass', 'rms', 'voc']) => assert.throws(() => synthesize({ ...spec, keys, alias }), re);
  bad(['vstem', 'voc'], /"alias" must be \{"name": "envelope"\}/);
  bad({ 'v.stem': 'voc' }, /names a key "v\.stem": use letters, digits and _/);
  for (const k of ['rms', 'bpm', 'events', 'stems', 'cent']) bad({ [k]: 'voc' }, new RegExp(`can't name "${k}": the pack has a key of that name already`));
  bad({ vstem: 'vocals' }, /"vstem" must name an envelope \(bass, .*\), got "vocals"/);
  bad({ vstem: 'voc' }, /"vstem" names "voc", which the spec's "keys" leave out of the pack/, ['bass', 'rms']);
});

test('alias: --twin keeps it, and measures the envelope from the real pack\'s key of that name', () => {
  const real = synthesize({ ...spec, keys: undefined });
  const flat = { ...real, vstem: real.voc.map(() => 0.5) };     // the real vocal stem: what the piece reads
  const base = { ...spec, keys: ['bass', 'rms', 'voc'], alias: { vstem: 'voc' } };
  const t = twin(flat, { base });
  assert.deepEqual(t.alias, { vstem: 'voc' });
  assert.deepEqual(Object.keys(t).slice(0, 9), ['seed', 'fps', 'dur', 'bpm', 'downbeat', 'keys', 'alias', 'voc', 'events']);
  assert.ok(t.sections.every(sec => sec.voc.join() === '0.5,0.5,0.5'), 'voc measured from vstem');
  assert.notDeepEqual(twin(flat, { base: { ...base, alias: undefined } }).sections.map(sec => sec.voc), t.sections.map(sec => sec.voc));
  assert.deepEqual(twin(real, { base }).sections, twin(real, { base: { ...base, alias: undefined } }).sections, 'a pack without the key: its own voc');
});

// ---------------------------------------------------------------- ⛈️'s twin
test('⛈️\'s twin: sections at the beat-in and every room, invented melody pitches, and no storm events the piece keeps itself', () => {
  const dir = path.join(CANVAS, 'pieces', 'storm'), s = JSON.parse(fs.readFileSync(path.join(dir, 'synthetic.json'), 'utf8'));
  const rule = fs.readFileSync(path.join(dir, 'src', '00_rule.js'), 'utf8');
  const num = re => +rule.match(re)[1];
  const rooms = JSON.parse(rule.match(/rooms: (\[[\s\S]*?\]\]),\n/)[1].replace(/\s+/g, ''));
  assert.deepEqual(s.sections.map(x => x.from), [0, num(/beat_in: ([\d.]+)/), ...rooms.map(r => r[0])]);
  assert.equal(s.sections.at(-1).from, num(/stop: ([\d.]+)/), 'the last section is the stop');
  const P = synthesize(s), st = P.events.storm;
  assert.deepEqual(Object.keys(st), ['melody'], 'thunder, rooms, kicks and snares: the piece\'s own constants and its grid');
  const scale = s.events.storm.melody[0][4];
  assert.ok(st.melody.length > 40 && st.melody.every(([t, , bin]) => t >= 1 && t < 33 && scale.includes(bin) && bin >= 0 && bin <= 47));
  assert.ok(st.melody.every(e => e.length === 3), 'a pitch on every note: no NaN colour in 52_cast.js');
  assert.ok(P.events.midi.kick.every(([t]) => t >= 33.02 && t < 336.02), 'no drums in the intro or after the stop');
});
