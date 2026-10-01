// The render, still and build commands as a person runs them: a request that can't be done is
// refused in one line with exit 2 before anything starts (no Chromium, no ffmpeg, no files), and
// a missing ffmpeg is said plainly before Chromium starts. No browser needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { synthesize } from '../tools/synth.mjs';
import { CANVAS } from './helpers.mjs';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-render-'));
// a synthetic pack of our own (other test files write out/songs/ at the same time)
const song = path.join(tmp, 'minus.songpack.json');
fs.writeFileSync(song, JSON.stringify(synthesize(JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', 'minus', 'synthetic.json'), 'utf8')))));

function run(tool, args, env = process.env) {
  const r = spawnSync(process.execPath, [path.join(CANVAS, 'tools', tool), ...args], { cwd: CANVAS, encoding: 'utf8', env, timeout: 60000 });
  return { code: r.status, out: r.stdout, err: r.stderr.trim() };
}

function refused(tool, args, re, env = process.env) {
  const dir = fs.mkdtempSync(path.join(tmp, 'out-'));
  const r = run(tool, [...args, '--out', path.join(dir, tool === 'still.mjs' ? 'stills' : 'x.mp4')], env);
  assert.equal(r.code, 2, `${tool} ${args.join(' ')}: exit ${r.code}\n${r.err}`);
  assert.equal(r.err.split('\n').length, 1, `one line, got:\n${r.err}`);
  assert.match(r.err, /^kaleidophone-canvas: /);
  assert.match(r.err, re);
  assert.deepEqual(fs.readdirSync(dir), [], 'nothing written');
}

const window12 = ['minus', '--song', song, '--t0', '30', '--dur', '1', '--fps', '12', '--w', '270', '--h', '480'];

test('render: frame ranges outside the window are refused, not rendered', () => {
  refused('render.mjs', ['minus', '--song', song, '--t0', '10', '--dur', '5', '--from', '20', '--to', '10'], /--to 10 must be after --from 20 and at most 120/);
  refused('render.mjs', [...window12, '--to', '30'], /--to 30 must be after --from 0 and at most 12, the window's frame count/);
  refused('render.mjs', [...window12, '--from', '12'], /--from 12 is outside the window's frames 0\.\.11/);
  refused('render.mjs', [...window12, '--png-frames', '12'], /--png-frames 12 is outside the frames being rendered/);
  refused('render.mjs', [...window12, '--keys', '0,12'], /--keys 12 is outside the window's frames 0\.\.11/);
  refused('render.mjs', [...window12, '--key-times', '29.5'], /--key-times 29\.5 is outside this render/);
  refused('render.mjs', [...window12, '--key-times', '30.04'], /isn't on the 12 fps frame grid/);
});

test('render: numbers that aren\'t, sizes that can\'t encode, less than a frame', () => {
  refused('render.mjs', ['minus', '--song', song, '--dur', 'abc'], /--dur expects a number, got "abc"/);
  refused('render.mjs', ['minus', '--song', song, '--dur', '0.01'], /less than one frame at 24 fps/);
  refused('render.mjs', ['minus', '--song', song, '--fps', '0'], /--fps must be positive/);
  refused('render.mjs', ['minus', '--song', song, '--w', '271'], /must be even/);
  refused('render.mjs', ['minus', '--song', song, '--t0', '-1'], /can't be negative/);
  refused('render.mjs', ['minus', '--song', song, '--workers', '0'], /--workers must be at least 1/);
  refused('render.mjs', ['minus', '--song', song, '--keys', '0,4', '--out-fps', '25'], /frame rates to match/);
});

test('render: unknown flags are refused with the valid ones; --key=value is understood', () => {
  refused('render.mjs', [...window12, '--worker', '2'], /unknown flag --worker \(did you mean --workers\?\)\. Valid flags: .*--workers/);
  // the review's command: --t0=30 --dur=0.5 --fps=12 rendered 10 s at 24 fps from 0. Parsed now,
  // it reaches range validation with those values: 6 frames, so --to 7 is refused
  refused('render.mjs', ['minus', '--song', song, '--t0=30', '--dur=0.5', '--fps=12', '--to=7'], /at most 6, the window's frame count \(0\.5 s at 12 fps\)/);
});

test('render: a missing song, piece or ffmpeg is said in one line', () => {
  refused('render.mjs', ['minus', '--t0', '1'], /--song is required/);
  refused('render.mjs', ['minus', '--song', path.join(tmp, 'nope.json')], /song pack not found/);
  refused('render.mjs', ['no-such-piece', '--song', song], /no piece "no-such-piece"/);
  refused('render.mjs', [], /^kaleidophone-canvas: usage: node tools\/render\.mjs/);
  // no ffmpeg on PATH: exit 1, said plainly, before Chromium or a build
  const bin = fs.mkdtempSync(path.join(tmp, 'bin-'));
  fs.symlinkSync(process.execPath, path.join(bin, 'node'));
  const dir = fs.mkdtempSync(path.join(tmp, 'out-'));
  const t = Date.now();
  const r = run('render.mjs', [...window12, '--out', path.join(dir, 'x.mp4')], { ...process.env, PATH: bin });
  assert.equal(r.code, 1, r.err);
  assert.match(r.err, /^kaleidophone-canvas: ffmpeg is not on PATH .*Install it/);
  assert.equal(r.err.split('\n').length, 1);
  assert.deepEqual(fs.readdirSync(dir), []);
  assert.ok(Date.now() - t < 20000, 'no Chromium was started');
});

test('render / still / build --help', () => {
  for (const tool of ['render.mjs', 'still.mjs', 'build.mjs']) {
    const r = run(tool, ['--help']);
    assert.equal(r.code, 0, `${tool}: ${r.err}`);
    assert.match(r.out, new RegExp(`^usage: node tools/${tool.replace('.', '\\.')}`));
  }
  assert.match(run('render.mjs', ['--help']).out, /--key-times s,s,\.\.\. +force keyframes at these song times/);
  assert.match(run('render.mjs', ['--help']).out, /--allow-page-errors/);
  assert.match(run('render.mjs', ['--help']).out, /--variant axis=option +.*\(repeatable\)/);
  assert.match(run('render.mjs', ['--help']).out, /--endings axis +the body once and every option of this axis after it/);
  assert.match(run('still.mjs', ['--help']).out, /--variant axis=option +.*\(repeatable\)/);
});

test('still: bad requests are refused in one line', () => {
  refused('still.mjs', ['minus', '--song', song, '--t', 'abc'], /--t expects a number, got "abc"/);
  refused('still.mjs', ['minus', '--song', song, '--t', '-1'], /can't be negative/);
  refused('still.mjs', ['minus', '--song', song, '--cover', 'nope'], /no cover "nope" \(have: plates, sunrise, window, title\)/);
  refused('still.mjs', ['minus', '--song', song], /give --t t1,t2,\.\.\. or --cover/);
  refused('still.mjs', ['minus', '--song', song, '--t', '1', '--cover', 'all'], /--t or --cover, not both/);
  refused('still.mjs', ['minus', '--song', song, '--t', '1', '--sise', '300'], /unknown flag --sise \(did you mean --size\?\)/);
});

test('build: bad requests are refused; --reserved lists the lib\'s names', () => {
  const b = args => run('build.mjs', args);
  let r = b(['--all', 'minus']); assert.equal(r.code, 2); assert.match(r.err, /piece ids or --all, not both/);
  r = b(['minus', 'template', '--out', path.join(tmp, 'x.html')]); assert.equal(r.code, 2); assert.match(r.err, /--out names one file/);
  r = b(['minus', '--sng', song]); assert.equal(r.code, 2); assert.match(r.err, /unknown flag --sng \(did you mean --song\?\)/);
  r = b(['--reserved']);
  assert.equal(r.code, 0, r.err);
  assert.match(r.out, /^core\.js \(\d+\): TAU rad clamp /m);
  assert.match(r.out, /^ink\.js \(\d+\): .*\bseed\b.*\bstroke\b.*\brect\b/m);
});

test('build.mjs reads its arguments only when run: the gallery imports it with flags of its own', () => {
  const url = pathToFileURL(path.join(CANVAS, 'tools', 'build.mjs')).href;
  const r = spawnSync(process.execPath, ['--input-type=module', '-e', `await import(${JSON.stringify(url)}); console.log('imported');`, '--', '--out', '../site', '--only', 'minus'], { cwd: CANVAS, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout.trim(), 'imported');
});

// ---------------------------------------------------------------- variants (issue #58)
// Fixture pieces in a folder of our own (KALEIDOPHONE_PIECES), never in canvas/pieces: one that can end
// three ways from 2.5 s, and one whose "variants" can't be right. None of these commands gets as far as
// building them.
const fixtures = path.join(tmp, 'pieces');
function fixturePiece(id, variants) {
  fs.mkdirSync(path.join(fixtures, id, 'src'), { recursive: true });
  fs.writeFileSync(path.join(fixtures, id, 'piece.json'), JSON.stringify({ title: id.toUpperCase(), template: 'template.html', src: 'src',
    lib: ['core', 'live'], grid: { bpm: 120, dur: 16 }, render: { fps: 24 }, variants }));
  fs.writeFileSync(path.join(fixtures, id, 'template.html'), '<!doctype html><canvas></canvas><script>/*__JS__*/</script>\n');
  fs.writeFileSync(path.join(fixtures, id, 'src', 'main.js'), 'boot({ bpm: 120, dur: 16, draw() {} });\n');
}
fixturePiece('ends', { ending: { at: 2.5, options: ['circle', 'square', 'cross'], default: 'circle' } });
fixturePiece('broken', { ending: { at: 2.5, options: ['circle', 'square'], default: 'oval' } });
const inFixtures = { ...process.env, KALEIDOPHONE_PIECES: fixtures };
const ends = ['ends', '--song', song, '--t0', '0', '--dur', '4', '--fps', '12', '--w', '270', '--h', '480'];

test('render --variant: an unknown axis or option is refused with the valid ones; a piece without variants refuses it', () => {
  refused('render.mjs', [...ends, '--variant', 'ending=oval'], /ends: "oval" is not an option of ending \(options: circle, square, cross\)$/, inFixtures);
  refused('render.mjs', [...ends, '--variant', 'mood=dark'], /ends has no variant axis "mood" \(axes: ending\)$/, inFixtures);
  refused('render.mjs', [...ends, '--variant', 'ending'], /--variant takes axis=option, e\.g\. --variant ending=cross \(got "ending"\)/, inFixtures);
  refused('render.mjs', [...ends, '--variant', 'ending=square', '--variant', 'ending=cross'], /--variant gives ending twice \(square, cross\): pick one/, inFixtures);
  refused('render.mjs', [...ends, '--variant', 'ending=square,ending=cross'], /--variant gives ending twice/, inFixtures);
  refused('render.mjs', [...ends, '--flags', '{"variant":{"ending":"square"}}'], /--flags can't set "variant": choose an option with --variant axis=option/, inFixtures);
  refused('render.mjs', [...window12, '--variant', 'ending=lamp'], /^kaleidophone-canvas: minus declares no variants in piece\.json/);
});

test('render --endings: refused unless the join is inside the window and the set can be joined by stream copy', () => {
  refused('render.mjs', [...ends, '--endings', 'mood'], /ends has no variant axis "mood" \(axes: ending\)$/, inFixtures);
  refused('render.mjs', [...ends, '--endings', 'ending', '--variant', 'ending=square'], /--endings ending renders every option of ending: leave ending out of --variant/, inFixtures);
  refused('render.mjs', [...ends, '--endings', 'ending', '--from', '3'], /--endings renders the whole window, a body and every ending: --from \/ --to/, inFixtures);
  refused('render.mjs', [...ends, '--endings', 'ending', '--out-fps', '24'], /--endings needs the render and output frame rates to match/, inFixtures);
  refused('render.mjs', ['ends', '--song', song, '--t0', '3', '--dur', '4', '--fps', '12', '--endings', 'ending'],
    /--endings ending: ending starts at 2\.5 s, outside this window \(song time 3 to 7 s\): give a window that starts before 2\.5 s and ends after it$/, inFixtures);
  refused('render.mjs', ['ends', '--song', song, '--t0', '0', '--dur', '2.5', '--fps', '12', '--endings', 'ending'], /outside this window \(song time 0 to 2\.5 s\)/, inFixtures);
  refused('render.mjs', [...ends, '--endings'], /--endings needs a value \(axis\)/, inFixtures);
  refused('render.mjs', [...window12, '--endings', 'ending'], /minus declares no variants in piece\.json: there are no endings to render$/);
});

test('still --variant: the same checks; a cover is chosen by its name', () => {
  refused('still.mjs', ['ends', '--song', song, '--t', '3', '--variant', 'ending=oval'], /"oval" is not an option of ending \(options: circle, square, cross\)$/, inFixtures);
  refused('still.mjs', ['ends', '--song', song, '--t', '3', '--variant', 'x=y'], /ends has no variant axis "x" \(axes: ending\)$/, inFixtures);
  refused('still.mjs', ['ends', '--song', song, '--cover', 'all', '--variant', 'ending=square'], /--variant is for --t stills: a cover is drawn by its name/, inFixtures);
  refused('still.mjs', ['minus', '--song', song, '--t', '1', '--variant', 'ending=lamp'], /minus declares no variants in piece\.json/);
});

test('render / still: a piece.json whose "variants" can\'t be right stops the command in one line, before anything starts', () => {
  for (const [tool, args] of [['render.mjs', ['broken', '--song', song, '--dur', '1']], ['still.mjs', ['broken', '--song', song, '--t', '1']]]) {
    const dir = fs.mkdtempSync(path.join(tmp, 'out-'));
    const r = run(tool, [...args, '--out', path.join(dir, 'x')], inFixtures);
    assert.equal(r.code, 1, r.err);
    assert.match(r.err, /^kaleidophone-canvas: broken: piece\.json variants\.ending: "default" must be one of its options \(circle, square\), got "oval"$/);
    assert.deepEqual(fs.readdirSync(dir), [], 'nothing written');
  }
});

// ---------------------------------------------------------------- what a run leaves behind
// A run that gets as far as starting Chromium and no further: an ffmpeg and an ffprobe that only say their
// version, and a Chromium that isn't there (KALEIDOPHONE_CHROMIUM). By then a run has done everything it
// does to the output folder before rendering; that it fails there is the point (exit 1, cleaned up).
function noBrowser(extra = {}) {
  const bin = fs.mkdtempSync(path.join(tmp, 'bin-'));
  for (const tool of ['ffmpeg', 'ffprobe']) fs.writeFileSync(path.join(bin, tool), `#!/bin/sh\necho "${tool} version 0-test"\n`, { mode: 0o755 });
  return { ...process.env, PATH: `${bin}${path.delimiter}${process.env.PATH}`, KALEIDOPHONE_CHROMIUM: path.join(tmp, 'no-chromium'), ...extra };
}

test('render: its work folder is its own, made for the run and gone after it; a folder of yours named <out>_parts is never touched', () => {
  const dir = fs.mkdtempSync(path.join(tmp, 'out-'));
  fs.mkdirSync(path.join(dir, 'x_parts'));
  fs.writeFileSync(path.join(dir, 'x_parts', 'mine.txt'), 'keep me');
  const r = run('render.mjs', [...window12, '--out', path.join(dir, 'x.mp4')], noBrowser());
  assert.equal(r.code, 1, r.err);
  assert.match(r.err, /could not start Chromium/);
  assert.deepEqual(fs.readdirSync(dir), ['x_parts'], 'nothing left behind, and nothing of yours gone');
  assert.equal(fs.readFileSync(path.join(dir, 'x_parts', 'mine.txt'), 'utf8'), 'keep me');
});

test('render --endings: a set rendered again loses its old manifest before anything renders; a refused command leaves it be', () => {
  const dir = fs.mkdtempSync(path.join(tmp, 'out-')), manifest = path.join(dir, 'x.variants.json');
  fs.writeFileSync(manifest, '{"kaleidophone": "canvas-variants/1"}\n');
  fs.writeFileSync(path.join(dir, 'x.body.mp4'), 'an old part');
  const set = ['ends', '--song', song, '--t0', '0', '--dur', '4', '--fps', '12', '--w', '270', '--h', '480', '--endings', 'ending', '--out', path.join(dir, 'x.mp4')];
  const env = noBrowser({ KALEIDOPHONE_PIECES: fixtures });
  const refusal = run('render.mjs', [...set, '--from', '3'], env);
  assert.equal(refusal.code, 2, refusal.err);
  assert.ok(fs.existsSync(manifest), 'a command refused before it starts changes nothing');
  const r = run('render.mjs', set, env);
  assert.equal(r.code, 1, r.err);
  assert.match(r.err, /could not start Chromium/);
  assert.deepEqual(fs.readdirSync(dir), ['x.body.mp4'], 'the old manifest is gone: whatever parts a failed run leaves, none of them sits beside a manifest that isn\'t theirs');
});

test('still: without --out, the PNGs go in canvas/out/stills (which git ignores), never the folder it is run from', () => {
  const cwd = fs.mkdtempSync(path.join(tmp, 'cwd-'));
  const r = spawnSync(process.execPath, [path.join(CANVAS, 'tools', 'still.mjs'), 'minus', '--song', song, '--t', '1'], { cwd, encoding: 'utf8', env: noBrowser(), timeout: 60000 });
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /could not start Chromium/);
  assert.deepEqual(fs.readdirSync(cwd), [], 'nothing in the folder it ran in (it used to make minus_stills/ there)');
  assert.ok(fs.statSync(path.join(CANVAS, 'out', 'stills')).isDirectory());
  assert.match(fs.readFileSync(path.join(CANVAS, '..', '.gitignore'), 'utf8'), /^canvas\/out\/$/m, 'canvas/out/ is ignored');
  assert.match(run('still.mjs', ['--help']).out, /--out dir +where the PNGs go \(default canvas\/out\/stills, which git ignores\)/);
});
