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

function refused(tool, args, re) {
  const dir = fs.mkdtempSync(path.join(tmp, 'out-'));
  const r = run(tool, [...args, '--out', path.join(dir, tool === 'still.mjs' ? 'stills' : 'x.mp4')]);
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
