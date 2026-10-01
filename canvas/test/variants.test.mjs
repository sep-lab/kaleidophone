// Variants and endings (issue #58), without a browser: piece.json's "variants" as the tools check it,
// --variant as the tools resolve it, and the arithmetic of render.mjs --endings -- the join frame, the
// frames and keyframes of every file, the pages that draw them -- plus the checks it makes on what
// ffprobe says and the manifest it writes. The renders themselves run in CI (the canvas job).
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  checkVariants, resolveVariant, variantTag, withVariant, joinFrame, planEncodes, planRender, planParts,
  timelineProblems, streamDifference, variantsManifest, concatList, JOIN_PARAMS, UsageError, SLUG,
} from '../tools/lib/common.mjs';

const ENDING = { at: 14, options: ['droste', 'lamp', 'exit'], default: 'droste', note: 'how the loop ends' };
const spec = (variants, grid = { bpm: 120, dur: 16 }) => ({ title: 'T', grid, variants });
const usage = re => err => err instanceof UsageError && err.exitCode === 2 && re.test(err.message) && !err.message.includes('\n');

// ---------------------------------------------------------------- piece.json "variants"
test('checkVariants: none is null; a good block comes back as it is', () => {
  assert.equal(checkVariants('p', { title: 'T' }), null);
  const V = { ending: ENDING, palette: { at: 0, options: ['day', 'night'], default: 'night' } };
  assert.equal(checkVariants('p', spec(V)), V);
  assert.ok(checkVariants('p', spec({ ending: { ...ENDING, at: 16 } })), 'at may be the song\'s end (grid.dur)');
  assert.ok(checkVariants('p', spec({ ending: { ...ENDING, at: 99 } }, {})), 'no grid.dur: only at >= 0 is checked');
});

test('checkVariants: every problem is one line naming the piece and the axis', () => {
  const bad = (V, re, grid) => assert.throws(() => checkVariants('tpl', spec(V, grid)), err => {
    assert.ok(!err.message.includes('\n'), `one line: ${err.message}`);
    assert.match(err.message, /^tpl: piece\.json /);
    assert.match(err.message, re);
    return true;
  });
  bad(['ending'], /"variants": must be an object of axes/);
  bad(null, /"variants": must be an object of axes/);
  bad({}, /"variants": declares no axes/);
  bad({ Ending: ENDING }, /variants\["Ending"\]: an axis name must be a slug/);
  bad({ 'end ing': ENDING }, /variants\["end ing"\]: an axis name must be a slug/);
  bad({ ending: 'droste' }, /variants\.ending: must be an object with "at", "options" and "default"/);
  bad({ ending: { ...ENDING, options: [] } }, /variants\.ending: "options" must be a non-empty list/);
  bad({ ending: { ...ENDING, options: 'droste,lamp' } }, /variants\.ending: "options" must be a non-empty list/);
  bad({ ending: { ...ENDING, options: ['droste', 'Lamp'] } }, /variants\.ending: option "Lamp" must be a slug .*<out>\.ending-<option>\.mp4/);
  bad({ ending: { ...ENDING, options: ['droste', 7] } }, /variants\.ending: option 7 must be a slug/);
  bad({ ending: { ...ENDING, options: ['droste', 'lamp', 'droste'] } }, /variants\.ending: option "droste" is listed twice/);
  bad({ ending: { at: 14, options: ['droste', 'lamp'] } }, /variants\.ending: has no "default" \(one of droste, lamp\)/);
  bad({ ending: { ...ENDING, default: 'door' } }, /variants\.ending: "default" must be one of its options \(droste, lamp, exit\), got "door"/);
  bad({ ending: { ...ENDING, at: '14' } }, /variants\.ending: "at" must be a number of song seconds, got "14"/);
  bad({ ending: { ...ENDING, at: null } }, /variants\.ending: "at" must be a number/);
  bad({ ending: { ...ENDING, at: -1 } }, /variants\.ending: "at" -1 is outside the song \(0 to 16 s, grid\.dur\)/);
  bad({ ending: { ...ENDING, at: 16.5 } }, /variants\.ending: "at" 16\.5 is outside the song/);
  bad({ ending: { ...ENDING, note: 3 } }, /variants\.ending: "note" must be a string/);
  bad({ ending: ENDING, 'x-': ENDING }, /variants\["x-"\]: an axis name must be a slug/);
});

test('slugs: what can name a file', () => {
  for (const s of ['a', 'droste', 'lamp-2', 'x1-y2-z3']) assert.ok(SLUG.test(s), s);
  for (const s of ['', 'A', 'a b', '-a', 'a-', 'a--b', 'a_b', 'a.b', 'a/b', 'é']) assert.ok(!SLUG.test(s), s);
});

// ---------------------------------------------------------------- --variant
test('resolveVariant: every axis, the default where none is asked for', () => {
  const V = { ending: ENDING, palette: { at: 0, options: ['day', 'night'], default: 'night' } };
  assert.deepEqual(resolveVariant('p', V, []), { choice: { ending: 'droste', palette: 'night' }, given: {} });
  assert.deepEqual(resolveVariant('p', V, ['ending=lamp']), { choice: { ending: 'lamp', palette: 'night' }, given: { ending: 'lamp' } });
  assert.deepEqual(resolveVariant('p', V, ['palette=day', 'ending=exit']).choice, { ending: 'exit', palette: 'day' }, 'in the piece\'s order');
  assert.deepEqual(resolveVariant('p', V, ['ending=lamp', 'ending=lamp']).given, { ending: 'lamp' }, 'the same choice twice is one');
  assert.deepEqual(resolveVariant('p', null, []), { choice: null, given: {} }, 'no variants, none asked: nothing on the frame');
});

test('resolveVariant: refusals list what there is', () => {
  const V = { ending: ENDING };
  assert.throws(() => resolveVariant('minus', null, ['ending=lamp']), usage(/^minus declares no variants in piece\.json/));
  assert.throws(() => resolveVariant('p', V, ['ending=door']), usage(/^p: "door" is not an option of ending \(options: droste, lamp, exit\)$/));
  assert.throws(() => resolveVariant('p', V, ['end=lamp']), usage(/^p has no variant axis "end" \(axes: ending\)$/));
  for (const item of ['ending', 'ending:lamp', '=lamp', 'ending=', 'a=b=c']) {
    assert.throws(() => resolveVariant('p', V, [item]), usage(/^--variant takes axis=option, e\.g\. --variant ending=exit/), item);
  }
  assert.throws(() => resolveVariant('p', V, ['ending=lamp', 'ending=exit']), usage(/--variant gives ending twice \(lamp, exit\): pick one/));
});

test('variantTag: the axes asked for, as file names carry them', () => {
  const V = { ending: ENDING, palette: { at: 0, options: ['day', 'night'], default: 'night' } };
  assert.equal(variantTag(V, {}), '');
  assert.equal(variantTag(V, { ending: 'lamp' }), 'ending-lamp');
  assert.equal(variantTag(V, { palette: 'day', ending: 'lamp' }), 'ending-lamp.palette-day');
  assert.equal(variantTag(null, {}), '');
});

test('withVariant: the harness puts the choice on whatever frame() made; no variants, nothing changes', () => {
  const p = { t: 1, bass: 0.5 };
  assert.equal(withVariant(p, null), p, 'the same object: a piece without variants gets exactly what it got before');
  const q = withVariant(p, { ending: 'lamp' });
  assert.deepEqual(q, { t: 1, bass: 0.5, variant: { ending: 'lamp' } });
  assert.deepEqual(p, { t: 1, bass: 0.5 }, 'not modified');
  // a driver whose frame() builds its own object (HAMECHI MANZOR DARE's) gets it too
  assert.deepEqual(withVariant({ dt: 1 / 30, beat: true }, { ending: 'exit' }).variant, { ending: 'exit' });
});

// ---------------------------------------------------------------- the join frame
test('joinFrame: the first frame at or after "at"', () => {
  assert.equal(joinFrame(14, { t0: 0, fps: 24 }), 336);
  assert.equal(joinFrame(14, { t0: 13, fps: 12 }), 12);
  assert.equal(joinFrame(14, { t0: 0.1, fps: 24 }), 334, '13.9 s is 333.6 frames: frame 334 (14.017 s) is the first at or after 14');
  assert.equal(joinFrame(14, { t0: 13.95, fps: 24 }), 2);
  assert.equal(joinFrame(2.5, { t0: 0.5, fps: 12 }), 24);
  // on the grid it is that frame, whatever the float arithmetic makes of it
  for (const fps of [12, 15, 24, 25, 30, 60]) for (let k = 1; k < 400; k += 7) {
    const t0 = 0.1 * (k % 11), at = t0 + k / fps;
    assert.equal(joinFrame(at, { t0, fps }), k, `fps ${fps}, t0 ${t0}, frame ${k}`);
  }
  assert.equal(joinFrame(3, { t0: 5, fps: 24 }), -48, 'before the window: negative (planRender refuses it)');
});

// ---------------------------------------------------------------- planning
test('planEncodes: with no join inside it is planParts; a join inside starts a new encode there', () => {
  for (const [from, to, w] of [[0, 3324, 2], [0, 240, 2], [15, 30, 1], [0, 1441, 3], [100, 101, 1]]) {
    assert.deepEqual(planEncodes(from, to, w, [0, 100, 1000]), planParts(from, to, w, [0, 100, 1000]));
    assert.deepEqual(planEncodes(from, to, w, [], [from, to, to + 5]), planParts(from, to, w), 'a join on an edge cuts nothing');
  }
  assert.deepEqual(planEncodes(0, 48, 2, [3, 40], [30]).map(e => [e.k, e.a, e.b, e.keys]),
    [[0, 0, 15, [3]], [1, 15, 30, []], [2, 30, 39, []], [3, 39, 48, [1]]]);
  assert.deepEqual(planEncodes(0, 48, 1, [], [30, 12, 30]).map(e => [e.a, e.b]), [[0, 12], [12, 30], [30, 48]]);
});

const V = { ending: ENDING };
const endings = (o = {}) => planRender({ id: 'tpl', variants: V, choice: { ending: 'droste' }, endings: 'ending', t0: 0, fps: 24, frames: 384, workers: 2, keys: [], ...o });

test('planRender --endings: a body to the join and one ending per option from it', () => {
  const plan = endings({ keys: [0, 100, 340] });
  assert.deepEqual(plan.join, { axis: 'ending', at: 14, frame: 336, song_t: 14 });
  assert.deepEqual(plan.parts.map(p => [p.name, p.role, p.from, p.to, p.frames, p.variant.ending, p.option ?? null, !!p.default]), [
    ['body', 'body', 0, 336, 336, 'droste', null, false],
    ['ending-droste', 'ending', 336, 384, 48, 'droste', 'droste', true],
    ['ending-lamp', 'ending', 336, 384, 48, 'lamp', 'lamp', false],
    ['ending-exit', 'ending', 336, 384, 48, 'exit', 'exit', false],
  ]);
  // --keys / --key-times: each part forces the ones inside it, on its own clock (encodes count from their own 0)
  const [body, drosteEnd] = plan.parts;
  assert.deepEqual(body.keys, [0, 100]);
  assert.deepEqual(drosteEnd.keys, [340]);
  assert.deepEqual(body.encodes.map(e => [e.a, e.b, e.keys]), [[0, 168, [0, 100]], [168, 336, []]]);
  assert.deepEqual(drosteEnd.encodes.map(e => [e.a, e.b, e.keys]), [[336, 360, [4]], [360, 384, []]]);
  // every file starts an encode, so on a keyframe
  for (const p of plan.parts) assert.equal(p.encodes[0].a, p.from);
});

test('planRender --endings: the pages that draw it, and the frame before the join every option must agree on', () => {
  const plan = endings();
  // stateless: every encode on its own page, drawing only the frames it encodes (the options are
  // checked on pages of their own), as a whole-window render's pages do
  assert.equal(plan.runs.length, 2 + 3 * 2);
  assert.deepEqual(plan.runs.map(r => [plan.parts[r.part].name, r.a, r.b]), [['body', 0, 168], ['body', 168, 336],
    ['ending-droste', 336, 360], ['ending-droste', 360, 384], ['ending-lamp', 336, 360], ['ending-lamp', 360, 384], ['ending-exit', 336, 360], ['ending-exit', 360, 384]]);
  assert.ok(plan.runs.every(r => r.probe === null));
  // stateful: one page per file, in order from its warm-up; the ending's replay passes through frame J-1
  const st = endings({ stateful: true, workers: 4 });
  assert.deepEqual(st.runs.map(r => [plan.parts[r.part].name, r.a, r.b, r.encodes, r.probe]), [
    ['body', 0, 336, [0], 335], ['ending-droste', 336, 384, [0], 335], ['ending-lamp', 336, 384, [0], 335], ['ending-exit', 336, 384, [0], 335],
  ]);
});

test('planRender: the whole window, rendered alone, is cut exactly where body and ending are', () => {
  // what makes a whole render and body + default ending decode to the same frames: the same encodes
  for (const [t0, fps, frames, at, workers, keys] of [[0, 24, 384, 14, 2, []], [13, 12, 24, 14, 2, [0, 9]], [0, 30, 900, 14, 3, [5, 420, 899]],
    [0.1, 24, 400, 14, 1, [7]], [10, 24, 241, 14, 4, []], [13.95, 24, 5, 14, 2, [3]]]) {
    const W = { ending: { ...ENDING, at } };
    const whole = planRender({ variants: W, choice: { ending: 'droste' }, t0, fps, frames, workers, keys });
    const set = planRender({ id: 'x', variants: W, choice: { ending: 'droste' }, endings: 'ending', t0, fps, frames, workers, keys });
    const def = set.parts.find(p => p.default);
    const cuts = parts => parts.flatMap(p => p.encodes.map(e => [e.a, e.b, e.keys]));
    assert.deepEqual(cuts(whole.parts), cuts([set.parts[0], def]), `t0 ${t0} fps ${fps} ${frames} frames, ${workers} workers`);
    assert.deepEqual(whole.parts[0].joins.map(j => [j.axis, j.frame]), [['ending', set.join.frame]]);
    assert.equal(set.parts[0].frames + def.frames, frames);
  }
});

test('planRender: a window without a join inside is planned as it always was', () => {
  for (const [from, to, w] of [[0, 12, 2], [0, 3324, 2], [15, 30, 1], [1000, 2000, 2]]) {
    const keys = [0, 9, 630, 1014, 1350];
    const plan = planRender({ fps: 24, frames: 3324, from, to, workers: w, keys });
    assert.equal(plan.join, null);
    assert.equal(plan.parts.length, 1);
    assert.deepEqual(plan.parts[0].encodes, planParts(from, to, w, keys));
    assert.deepEqual(plan.runs.map(r => [r.a, r.b]), planParts(from, to, w).map(p => [p.a, p.b]));
    assert.ok(plan.runs.every(r => r.probe === null));
  }
  // variants declared but the join outside the window: no cut, the choice still on every frame
  const out = planRender({ variants: V, choice: { ending: 'lamp' }, t0: 0, fps: 12, frames: 12, workers: 2 });
  assert.deepEqual(out.parts[0].encodes.map(e => [e.a, e.b]), [[0, 6], [6, 12]]);
  assert.deepEqual(out.parts[0].variant, { ending: 'lamp' });
  assert.deepEqual(out.parts[0].joins, []);
});

test('planRender: a stateful whole window is one page, its encoder restarting at the join', () => {
  const plan = planRender({ variants: V, choice: { ending: 'droste' }, t0: 0, fps: 24, frames: 384, workers: 2, stateful: true, keys: [340] });
  assert.equal(plan.runs.length, 1);
  assert.deepEqual(plan.runs[0], { part: 0, a: 0, b: 384, encodes: [0, 1], probe: null });
  assert.deepEqual(plan.parts[0].encodes.map(e => [e.a, e.b, e.keys]), [[0, 336, []], [336, 384, [4]]]);
  assert.deepEqual(plan.parts[0].joins, [{ axis: 'ending', at: 14, frame: 336, file_frame: 336 }]);
  // resumed from --from 200: the join is still where the encoder restarts, counted in this file
  const resumed = planRender({ variants: V, choice: { ending: 'droste' }, t0: 0, fps: 24, frames: 384, from: 200, workers: 1, stateful: true });
  assert.deepEqual(resumed.parts[0].encodes.map(e => [e.a, e.b]), [[200, 336], [336, 384]]);
  assert.equal(resumed.parts[0].joins[0].file_frame, 136);
});

test('planRender --endings: another axis joining inside a part cuts that part, and the whole window, alike', () => {
  const W2 = { ending: ENDING, light: { at: 6, options: ['on', 'off'], default: 'on' } };
  const choice = { ending: 'droste', light: 'off' };
  const set = planRender({ id: 'x', variants: W2, choice, endings: 'ending', t0: 0, fps: 24, frames: 384, workers: 1 });
  assert.deepEqual(set.parts[0].encodes.map(e => [e.a, e.b]), [[0, 144], [144, 336]]);
  assert.deepEqual(set.parts[0].joins.map(j => [j.axis, j.frame]), [['light', 144]]);
  assert.deepEqual(set.parts.map(p => p.variant), [
    { ending: 'droste', light: 'off' }, { ending: 'droste', light: 'off' }, { ending: 'lamp', light: 'off' }, { ending: 'exit', light: 'off' }]);
  const whole = planRender({ variants: W2, choice, t0: 0, fps: 24, frames: 384, workers: 1 });
  assert.deepEqual(whole.parts[0].encodes.map(e => [e.a, e.b]), [[0, 144], [144, 336], [336, 384]]);
});

test('planRender --endings: refused when the join is not inside the window', () => {
  const at = (t0, frames, re) => assert.throws(() => endings({ t0, frames, fps: 12 }), usage(re));
  at(15, 24, /^--endings ending: ending starts at 14 s, outside this window \(song time 15 to 17 s\): give a window that starts before 14 s and ends after it$/);
  at(14, 24, /outside this window \(song time 14 to 16 s\)/);           // no body
  at(12, 24, /outside this window \(song time 12 to 14 s\)/);           // no ending
  at(0, 12, /outside this window \(song time 0 to 1 s\)/);
  // 13.95 s + 2 frames at 24 fps ends after 14 s, but no frame of it is at or after 14 s: no ending
  assert.throws(() => endings({ t0: 13.95, frames: 2, fps: 24 }), usage(/outside this window \(song time 13\.95 to 14\.033333 s\)/));
  const tiny = endings({ t0: 13.95, frames: 3, fps: 24 });               // frames at 13.95, 13.992 | 14.033
  assert.deepEqual(tiny.parts.map(p => p.frames), [2, 1, 1, 1], 'one frame after the join is enough');
  const whole = { palette: { at: 0, options: ['day', 'night'], default: 'day' } };
  assert.throws(() => planRender({ id: 'p', variants: whole, choice: { palette: 'day' }, endings: 'palette', t0: 0, fps: 24, frames: 48 }),
    usage(/an axis that changes the whole piece has no body -- render each option with --variant palette=<option>/));
  assert.throws(() => endings({ endings: 'ends' }), usage(/^tpl has no variant axis "ends" \(axes: ending\)$/));
  assert.throws(() => planRender({ id: 'minus', endings: 'ending', fps: 24, frames: 48 }), usage(/^minus declares no variants in piece\.json: there are no endings to render$/));
});

// ---------------------------------------------------------------- what ffprobe says, checked
const packets = (n, step, keys = [0], order = 'pts') => {
  const out = Array.from({ length: n }, (_, i) => ({ pts: i * step, key: keys.includes(i) }));
  return order === 'decode' ? out.flatMap((p, i, a) => i % 3 === 1 && a[i + 1] ? [a[i + 1], p] : i % 3 === 2 ? [] : [p]) : out;
};

test('timelineProblems: every frame once, one frame apart from 0, keyframes where asked', () => {
  const tb = '1/12288';
  assert.deepEqual(timelineProblems(packets(48, 1024, [0, 30]), { frames: 48, fps: 12, timeBase: tb, keys: [0, 30] }), []);
  assert.deepEqual(timelineProblems(packets(48, 1024, [0, 30], 'decode'), { frames: 48, fps: 12, timeBase: tb, keys: [0, 30] }), [], 'in decode order (B-frames): sorted first');
  assert.deepEqual(timelineProblems(packets(10, 512), { frames: 12, fps: 24, timeBase: tb }), ['10 frames, expected 12']);
  const gap = packets(10, 512); for (const p of gap.slice(5)) p.pts += 512;
  assert.match(timelineProblems(gap, { frames: 10, fps: 24, timeBase: tb })[0], /^a gap between frames 4 and 5 \(pts 2048 -> 3072, one frame is 512\)$/);
  const rep = packets(10, 512); rep[6].pts = rep[5].pts;
  assert.match(timelineProblems(rep, { frames: 10, fps: 24, timeBase: tb }).join(), /a repeated timestamp between frames/);
  const late = packets(10, 512).map(p => ({ ...p, pts: p.pts + 1024 }));
  assert.deepEqual(timelineProblems(late, { frames: 10, fps: 24, timeBase: tb }), ['the first frame is at pts 1024, not 0']);
  assert.deepEqual(timelineProblems(packets(48, 1024, [0]), { frames: 48, fps: 12, timeBase: tb, keys: [0, 30] }), ['frame 30 is not a keyframe']);
  // a frame rate the time base doesn't divide: one tick of rounding either way is not a gap
  const odd = Array.from({ length: 30 }, (_, i) => ({ pts: Math.round(i * 30000 / 29.97 / 1000), key: i === 0 }));
  assert.deepEqual(timelineProblems(odd, { frames: 30, fps: 29.97, timeBase: '1/30' }), []);
});

test('streamDifference: the first parameter a join by stream copy would trip on', () => {
  const a = Object.fromEntries(JOIN_PARAMS.map(k => [k, `${k}-value`]));
  assert.equal(streamDifference(a, { ...a }), null);
  assert.deepEqual(streamDifference(a, { ...a, level: 31 }), ['level', 'level-value', 31]);
  assert.deepEqual(streamDifference(a, { ...a, extradata_hash: 'SHA256:x' }), ['extradata_hash', 'extradata_hash-value', 'SHA256:x']);
  for (const k of ['codec_name', 'profile', 'level', 'pix_fmt', 'width', 'height', 'r_frame_rate', 'time_base', 'sample_aspect_ratio']) {
    assert.ok(JOIN_PARAMS.includes(k), `${k} is compared`);
  }
  assert.equal(streamDifference({ color_transfer: undefined }, { color_transfer: null }), null, 'absent is absent');
});

test('concatList: one quoted file per line, a quote in a name escaped', () => {
  assert.equal(concatList(['/a/b.mp4', "/it's/c.mp4"]), "file '/a/b.mp4'\nfile '/it'\\''s/c.mp4'\n");
});

// ---------------------------------------------------------------- the manifest
test('variantsManifest: the files, the join, the stream -- names, never paths', () => {
  const plan = planRender({ id: 'template', variants: V, choice: { ending: 'droste' }, endings: 'ending', t0: 13, fps: 12, frames: 24, workers: 2 });
  const files = Object.fromEntries(plan.parts.map(p => [p.name, { file: `s.${p.name}.mp4`, sidecar: `s.${p.name}.mp4.json` }]));
  const stream = Object.fromEntries(JOIN_PARAMS.map(k => [k, 'x']));
  const joined = Object.fromEntries(plan.parts.filter(p => p.role === 'ending').map(p => [p.name, { frames: 24, gapless: true, keyframe_at_join: true }]));
  const m = variantsManifest({
    piece: 'template', song: 'template.songpack.json', synthetic: true, axis: { name: 'ending', spec: ENDING },
    t0: 13, dur: 2, fps: 12, size: { w: 270, h: 480 }, plan, files, stream, joined,
    encode: { codec: 'libx264', crf: 28 }, tools: { node: 'v22' },
  });
  assert.deepEqual(Object.keys(m), ['kaleidophone', 'piece', 'axis', 't0', 'dur', 'fps', 'at', 'options', 'default', 'note', 'song',
    'synthetic_song', 'silent_start', 'size', 'join', 'frames', 'body', 'endings', 'stream', 'encode', 'tools']);
  assert.equal(m.kaleidophone, 'canvas-variants/1');
  // what `kaleidophone deliver` holds a cut to: the window (t0, dur, fps), the join (at), the files and their frames
  assert.deepEqual([m.piece, m.axis, m.t0, m.dur, m.fps, m.at], ['template', 'ending', 13, 2, 12, 14]);
  assert.equal(Math.round((m.at - m.t0) * m.fps), m.body.frames, 'the body runs from t0 to at');
  assert.deepEqual([m.default, m.note], ['droste', 'how the loop ends']);
  assert.deepEqual(m.options, ['droste', 'lamp', 'exit']);
  assert.equal(m.silent_start, 13, 'the joined film starts where the body does');
  assert.deepEqual(m.join, { frame: 12, t: 1, declared_at: 14 });
  assert.deepEqual(m.frames, { window: 24, body: 12, ending: 12 });
  assert.deepEqual(m.body, { file: 's.body.mp4', sidecar: 's.body.mp4.json', frames: 12, variant: { ending: 'droste' } });
  assert.deepEqual(m.endings.map(e => [e.option, e.default, e.file, e.frames, e.variant.ending, e.joined.frames]), [
    ['droste', true, 's.ending-droste.mp4', 12, 'droste', 24], ['lamp', false, 's.ending-lamp.mp4', 12, 'lamp', 24], ['exit', false, 's.ending-exit.mp4', 12, 'exit', 24]]);
  assert.equal(m.stream, stream);
  for (const f of [m.song, m.body.file, m.body.sidecar, ...m.endings.flatMap(e => [e.file, e.sidecar])]) assert.ok(!/[\\/]/.test(f), `a name, not a path: ${f}`);
  assert.deepEqual(JSON.parse(JSON.stringify(m)), m, 'plain JSON');
});

test('variantsManifest: a join between two frames -- "at" is where the files meet, on the frame grid', () => {
  // a stateful piece snaps t0 to a beat: 60.282 s at 30 fps puts piece.json's 75 s between frames 441 and 442
  const W = { ending: { ...ENDING, at: 75 } };
  const plan = planRender({ id: 'p', variants: W, choice: { ending: 'droste' }, endings: 'ending', t0: 60.282, fps: 30, frames: 600, workers: 1, stateful: true });
  const files = Object.fromEntries(plan.parts.map(p => [p.name, { file: `${p.name}.mp4`, sidecar: `${p.name}.mp4.json` }]));
  const m = variantsManifest({ piece: 'p', song: 's.json', axis: { name: 'ending', spec: W.ending }, t0: 60.282, dur: 20, fps: 30,
    size: { w: 270, h: 480 }, plan, files, stream: {}, joined: {}, encode: {}, tools: {} });
  assert.equal(m.join.frame, 442);
  assert.equal(m.at, 75.015333, 'frame 442, the first at or after 75 s');
  assert.equal(m.join.declared_at, 75);
  assert.equal(Math.round((m.at - m.t0) * m.fps), m.body.frames);
  assert.equal(m.body.frames + m.endings[0].frames, m.frames.window);
});
