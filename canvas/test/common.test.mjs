// The tools' shared plumbing (tools/lib/common.mjs): the envelope sampler the released films were
// verified against, file URLs, argument parsing, and how a window is split into workers.
import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sampleLinear, pieceUrl, parseArgs, helpText, planParts, keyTimesToFrames, UsageError } from '../tools/lib/common.mjs';

// ---------------------------------------------------------------- sampleLinear
// The formula as it shipped (SAME AS YOU and ( - ) were rendered and verified with it). Inside the
// song the tool must still give exactly these doubles.
function shipped(pack, keys, t) {
  const o = {};
  for (const k of keys) {
    const a = pack[k];
    if (!a || !a.length) { o[k] = 0; continue; }
    const n = a.length;
    const i = Math.max(0, Math.min(n - 2, Math.floor(t * pack.fps)));
    const f = t * pack.fps - i;
    o[k] = a[i] + (a[i + 1] - a[i]) * f;
  }
  return o;
}

function pack(n = 1501, seed = 1) {
  let s = seed;
  const r = () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9E3779B9 | 0) >>> 0) / 4294967296;
  const f = () => Array.from({ length: n }, () => Math.round(r() * 1000) / 1000);
  return { fps: 100, bass: f(), mid: f(), flux: f(), rms: Array.from({ length: n }, () => Math.round(r() * 255)) };
}

test('sampleLinear: bit-identical to the shipped formula everywhere inside the song', () => {
  const p = pack(), keys = ['bass', 'mid', 'flux', 'rms'];
  const last = (p.bass.length - 1) / p.fps;
  const ts = [0, 1e-9, 0.005, 0.01, 1 / 24, 62.255 / 10, 7.123456, last - 0.004, last - 1e-9, last];
  for (let i = 0; i <= 3000; i++) ts.push(i * last / 3000);
  for (let i = 0; i < 500; i++) ts.push(i / 24, i / 30, i * 0.0123);
  for (const t of ts.filter(t => t >= 0 && t <= last)) {
    const a = sampleLinear(p, keys, t), b = shipped(p, keys, t);
    for (const k of keys) assert.ok(Object.is(a[k], b[k]), `${k} at t=${t}: ${a[k]} vs ${b[k]}`);
  }
});

test('sampleLinear: outside the song it holds the first / last frame instead of extrapolating', () => {
  const p = pack(), keys = ['bass', 'mid', 'flux', 'rms'], n = p.bass.length;
  // what the shipped formula did out there: the edge slope, carried on, far outside the pack's range
  assert.notEqual(shipped(p, ['flux'], 500).flux, p.flux[n - 1]);
  for (const t of [-3, -0.001, -1e-9]) for (const k of keys) assert.equal(sampleLinear(p, keys, t)[k], p[k][0], `${k} at ${t}`);
  for (const t of [(n - 1) / p.fps + 1e-9, 15.01, 500, 1e6]) for (const k of keys) assert.equal(sampleLinear(p, keys, t)[k], p[k][n - 1], `${k} at ${t}`);
  for (const t of [-3, 500]) for (const k of keys) {
    const v = sampleLinear(p, keys, t)[k], lo = Math.min(...p[k]), hi = Math.max(...p[k]);
    assert.ok(v >= lo && v <= hi, `${k} at ${t} stays within the pack's own range`);
  }
});

test('sampleLinear: a missing envelope is 0, a one-frame envelope is that frame', () => {
  assert.deepEqual(sampleLinear({ fps: 100, bass: [0.4] }, ['bass', 'voc'], 3), { bass: 0.4, voc: 0 });
  assert.deepEqual(sampleLinear({ fps: 100, bass: [] }, ['bass'], 1), { bass: 0 });
});

// ---------------------------------------------------------------- pieceUrl
test('pieceUrl: ?, #, spaces and quotes in the path stay in the path; the query stays the query', () => {
  for (const name of ['SHOULD I ?.html', 'a #1.html', 'it\'s "quoted".html', 'x?y#z w.html', '100% ?#.html']) {
    const f = path.join(os.tmpdir(), 'kp dir #?', name);
    const u = new URL(pieceUrl(f, { render: 1, w: 540, h: 960 }));
    assert.equal(u.protocol, 'file:');
    assert.equal(u.hash, '', name);
    assert.deepEqual(Object.fromEntries(u.searchParams), { render: '1', w: '540', h: '960' }, name);
    u.search = '';
    assert.equal(fileURLToPath(u), f, name);
  }
});

// ---------------------------------------------------------------- parseArgs
const SPEC = {
  usage: 'tool <piece> [flags]',
  positional: [1, 1],
  flags: {
    song: { type: 'string' }, t0: { type: 'number' }, dur: { type: 'number' }, fps: { type: 'number' },
    workers: { type: 'int' }, card: { type: 'bool' }, snap: { type: 'bool' }, keys: { type: 'ints' },
    't': { type: 'numbers' }, cover: { type: 'optional' }, flags: { type: 'json' },
    mode: { type: 'string', choices: ['reel', 'story', 'none'] },
  },
};
const usageError = re => err => err instanceof UsageError && err.exitCode === 2 && re.test(err.message);

test('parseArgs() with no spec: permissive, strings, as the gallery and synth use it', () => {
  assert.deepEqual(parseArgs(['minus', '--song', 'a.json', '--card', '--t0', '30', '--only', 'x,y']),
    { _: ['minus'], song: 'a.json', card: true, t0: '30', only: 'x,y' });
  assert.deepEqual(parseArgs(['--out=../site', '--w=360', 'p']), { _: ['p'], out: '../site', w: '360' });
  assert.deepEqual(parseArgs(['--flag', '--other']), { _: [], flag: true, other: true });
});

test('parseArgs: --key=value and --key value mean the same, typed', () => {
  // the review ran exactly this and got a 10 s render at 24 fps from t=0
  const a = parseArgs(['p', '--t0=30', '--dur=0.5', '--fps=12'], SPEC);
  const b = parseArgs(['p', '--t0', '30', '--dur', '0.5', '--fps', '12'], SPEC);
  assert.deepEqual(a, { _: ['p'], t0: 30, dur: 0.5, fps: 12 });
  assert.deepEqual(a, b);
  assert.deepEqual(parseArgs(['p', '--flags={"a":"b=c"}', '--keys=0,630,1014', '--t', '1.5,2'], SPEC),
    { _: ['p'], flags: { a: 'b=c' }, keys: [0, 630, 1014], t: [1.5, 2] });
  assert.equal(parseArgs(['p', '--t0', '-3'], SPEC).t0, -3, 'a negative number is a value, not a flag');
});

test('parseArgs: switches, and values that are optional', () => {
  assert.deepEqual(parseArgs(['--card', 'p'], SPEC), { _: ['p'], card: true }, 'a switch never swallows the piece id');
  assert.equal(parseArgs(['p', '--snap', 'false'], SPEC).snap, false);
  assert.equal(parseArgs(['p', '--snap=false'], SPEC).snap, false);
  assert.equal(parseArgs(['p', '--snap=true'], SPEC).snap, true);
  assert.equal(parseArgs(['p', '--cover'], SPEC).cover, true);
  assert.equal(parseArgs(['p', '--cover', 'main,drift'], SPEC).cover, 'main,drift');
  assert.equal(parseArgs(['p', '--help'], SPEC).help, true);
  assert.equal(parseArgs(['-h'], SPEC).help, true, '--help needs no piece');
});

test('parseArgs: unknown and misspelled flags are refused, naming the valid ones', () => {
  assert.throws(() => parseArgs(['p', '--worker', '2'], SPEC), usageError(/unknown flag --worker \(did you mean --workers\?\).*--song.*--workers/));
  assert.throws(() => parseArgs(['p', '--fsp=12'], SPEC), usageError(/unknown flag --fsp \(did you mean --fps\?\)/));
  assert.throws(() => parseArgs(['p', '--zzzzzz'], SPEC), usageError(/^unknown flag --zzzzzz\. Valid flags: /));
  assert.throws(() => parseArgs(['p', '-x'], SPEC), usageError(/unknown option -x/));
});

test('parseArgs: bad values are usage errors, with the value quoted', () => {
  assert.throws(() => parseArgs(['p', '--dur', 'abc'], SPEC), usageError(/--dur expects a number, got "abc"/));
  assert.throws(() => parseArgs(['p', '--dur=Infinity'], SPEC), usageError(/--dur expects a number/));
  assert.throws(() => parseArgs(['p', '--workers', '1.5'], SPEC), usageError(/--workers expects a whole number/));
  assert.throws(() => parseArgs(['p', '--keys', '0,,630'], SPEC), usageError(/--keys expects a comma-separated list/));
  assert.throws(() => parseArgs(['p', '--keys', '0,x'], SPEC), usageError(/--keys expects a whole number/));
  assert.throws(() => parseArgs(['p', '--song'], SPEC), usageError(/--song needs a value/));
  assert.throws(() => parseArgs(['p', '--song', '--card'], SPEC), usageError(/--song needs a value/));
  assert.throws(() => parseArgs(['p', '--song='], SPEC), usageError(/--song needs a value/));
  assert.throws(() => parseArgs(['p', '--card=maybe'], SPEC), usageError(/--card is a switch/));
  assert.throws(() => parseArgs(['p', '--flags', '{bad'], SPEC), usageError(/--flags is not valid JSON/));
  assert.throws(() => parseArgs(['p', '--mode', 'reeel'], SPEC), usageError(/--mode must be one of reel, story, none/));
});

test('parseArgs: a repeatable flag collects every value, given again or comma-separated', () => {
  const R = { ...SPEC, flags: { ...SPEC.flags, variant: { type: 'list', repeat: true, arg: 'axis=option' } } };
  const want = { _: ['p'], variant: ['ending=lamp', 'palette=night'] };
  assert.deepEqual(parseArgs(['p', '--variant', 'ending=lamp', '--variant', 'palette=night'], R), want);
  assert.deepEqual(parseArgs(['p', '--variant', 'ending=lamp,palette=night'], R), want);
  assert.deepEqual(parseArgs(['p', '--variant=ending=lamp', '--variant=palette=night'], R), want, '--flag=value keeps the = in the value');
  assert.deepEqual(parseArgs(['p', '--variant', 'ending=lamp'], R).variant, ['ending=lamp'], 'one is a list of one');
  assert.equal(parseArgs(['p'], R).variant, undefined);
  assert.equal(parseArgs(['p', '--t0', '1', '--t0', '2'], R).t0, 2, 'a flag that doesn\'t repeat: the last one wins, as before');
  assert.throws(() => parseArgs(['p', '--variant', 'a=b,,c=d'], R), usageError(/--variant expects a comma-separated list with no empty items/));
  assert.match(helpText({ usage: 'u', flags: R.flags }), /--variant axis=option +\(repeatable\)/);
});

test('parseArgs: the positional count is checked', () => {
  assert.throws(() => parseArgs(['--song', 'a.json'], SPEC), usageError(/^usage: tool <piece>/));
  assert.throws(() => parseArgs(['p', 'q'], SPEC), usageError(/unexpected argument "q"/));
});

// ---------------------------------------------------------------- workers and keyframes
test('planParts: never more workers than frames, contiguous, every frame once', () => {
  assert.deepEqual(planParts(100, 101, 2), [{ k: 0, a: 100, b: 101, keys: [] }]);
  for (let from = 0; from < 7; from++) for (let n = 1; n < 40; n++) for (let workers = 1; workers < 9; workers++) {
    const to = from + n, parts = planParts(from, to, workers);
    assert.equal(parts.length, Math.min(workers, n));
    assert.equal(parts[0].a, from); assert.equal(parts.at(-1).b, to);
    for (const [i, p] of parts.entries()) {
      assert.ok(p.b > p.a, 'no empty part');
      if (i) assert.equal(p.a, parts[i - 1].b, 'contiguous');
    }
  }
  assert.throws(() => planParts(20, 10, 1), RangeError);
});

test('planParts: the same split the tool always made when there were enough frames', () => {
  const old = (from, to, workers, k) => [from + Math.floor(k * (to - from) / workers), from + Math.floor((k + 1) * (to - from) / workers)];
  for (const [from, to, w] of [[0, 3324, 2], [0, 240, 2], [15, 30, 1], [0, 1441, 3], [100, 101, 1]]) {
    assert.deepEqual(planParts(from, to, w).map(p => [p.a, p.b]), Array.from({ length: w }, (_, k) => old(from, to, w, k)));
  }
});

test('planParts: each forced keyframe lands in exactly one part, counted from that part\'s first frame', () => {
  assert.deepEqual(planParts(0, 12, 2, [0, 9]).map(p => p.keys), [[0], [3]]);
  const keys = [0, 630, 1014, 1350, 1734, 1926, 2310];
  for (const w of [1, 2, 3, 4, 7]) {
    const parts = planParts(0, 3324, w, keys);
    assert.deepEqual(parts.flatMap(p => p.keys.map(k => p.a + k)), keys, `${w} workers`);
  }
  // a resumed window: keys before --from (and from --to on) belong to renders made separately
  assert.deepEqual(planParts(1000, 2000, 2, keys).map(p => [p.a, p.keys]), [[1000, [14, 350]], [1500, [234, 426]]]);
});

test('keyTimesToFrames: song seconds -> frames of the window, on its grid, inside it', () => {
  assert.deepEqual(keyTimesToFrames([30, 30.5, 30.958333], { t0: 30, fps: 24, frames: 24 }), [0, 12, 23]);
  // `kaleidophone deliver` prints times floored to the microsecond: 10.041666 is frame 241
  assert.deepEqual(keyTimesToFrames([10.041666, 26.25], { t0: 0, fps: 24, frames: 3324 }), [241, 630]);
  // canvas/README.md's example: SAME AS YOU's cut points in seconds are piece.json's keyframes
  assert.deepEqual(keyTimesToFrames([0, 26.25, 42.25, 56.25, 72.25, 80.25, 96.25], { t0: 0, fps: 24, frames: Math.round(138.5 * 24) }),
    [0, 630, 1014, 1350, 1734, 1926, 2310]);
  // a snapped window (a stateful piece): times are still song time
  assert.deepEqual(keyTimesToFrames([60.282, 61.282], { t0: 60.282, fps: 30, frames: 60 }), [0, 30]);
  assert.throws(() => keyTimesToFrames([30.52], { t0: 30, fps: 24, frames: 24 }), usageError(/isn't on the 24 fps frame grid .* 30\.5 \/ 30\.541667 s/));
  assert.throws(() => keyTimesToFrames([29], { t0: 30, fps: 24, frames: 24 }), usageError(/outside this render \(song time 30 to 31 s/));
  assert.throws(() => keyTimesToFrames([31], { t0: 30, fps: 24, frames: 24 }), usageError(/outside this render/));
});
