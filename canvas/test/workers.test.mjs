// Worker identity: what a render captures doesn't depend on how many browser pages drew it.
//
// Never compare the MP4s: each worker's part is its own x264 encode, joined by stream copy, so the bytes,
// and the frames a lossy encode decodes to, change with --workers (canvas/README.md, "Variants"). The
// captures must not. Rendered lossless (--crf 0: x264's qp 0, High 4:4:4 Predictive), the decoded frames
// are exactly the captured ones, so their framemd5 compares the captures themselves.
//
// It needs Chromium and ffmpeg, so `npm test` skips it; CI runs it with KP_BROWSER_TESTS=1. The worker
// counts compared are KP_WORKER_COUNTS (default 2,4,8). A stateful piece always renders in one worker,
// so only stateless pieces are compared.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { CANVAS } from './helpers.mjs';

delete process.env.KALEIDOPHONE_PIECES;
const { listPieces, loadPiece, loadDriver } = await import('../tools/lib/common.mjs');
const { synthFor } = await import('../tools/synth.mjs');

const ON = process.env.KP_BROWSER_TESTS === '1';
const COUNTS = (process.env.KP_WORKER_COUNTS || '2,4,8').split(',').map(Number);
const FPS = 12, DUR = 2, FRAMES = FPS * DUR;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-workers-'));
test.after(() => fs.rmSync(tmp, { recursive: true, force: true }));
const run = (cmd, args) => execFileSync(cmd, args, { cwd: CANVAS, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64 << 20 });

// the decoded frames, one md5 per frame, in order
const framemd5 = file => run('ffmpeg', ['-v', 'error', '-i', file, '-f', 'framemd5', '-']).split('\n').filter(l => l && !l.startsWith('#')).map(l => l.split(',').pop().trim());

const stateless = [];
for (const id of listPieces()) if (!(await loadDriver(loadPiece(id))).stateful) stateless.push(id);

test('the stateless pieces are the ones compared', () => {
  assert.ok(stateless.includes('minus') && stateless.includes('template') && !stateless.includes('hamechi-manzor-dare'));
  assert.ok(COUNTS.length >= 2 && COUNTS.every(n => Number.isInteger(n) && n >= 1), `KP_WORKER_COUNTS=${process.env.KP_WORKER_COUNTS}`);
});

for (const id of stateless) {
  test(`${id}: ${FRAMES} frames captured alike by ${COUNTS.join(', ')} workers`, { skip: !ON && 'needs Chromium and ffmpeg: KP_BROWSER_TESTS=1 (CI sets it)' }, () => {
    const song = synthFor(id), t0 = loadPiece(id).spec.gallery.t0;
    const hashes = COUNTS.map(n => {
      const out = path.join(tmp, `${id}.w${n}.mp4`);
      run(process.execPath, ['tools/render.mjs', id, '--song', song, '--t0', String(t0), '--dur', String(DUR), '--fps', String(FPS),
        '--w', '270', '--h', '480', '--crf', '0', '--workers', String(n), '--out', out]);
      const side = JSON.parse(fs.readFileSync(`${out}.json`, 'utf8'));
      assert.equal(side.workers, Math.min(n, FRAMES), `${id}: rendered by ${n} pages`);
      const profile = run('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=profile', '-of', 'default=nw=1:nk=1', out]).trim();
      assert.equal(profile, 'High 4:4:4 Predictive', `${id}: --crf 0 must be lossless for the frames to be the captures (got ${profile})`);
      const md5 = framemd5(out);
      assert.equal(md5.length, FRAMES, `${id}: ${n} workers decoded to ${md5.length} frames`);
      assert.ok(new Set(md5).size > 1, `${id}: every frame alike would prove nothing`);
      return md5;
    });
    for (const [i, n] of COUNTS.entries()) {
      const first = hashes[i].findIndex((h, k) => h !== hashes[0][k]);
      assert.equal(first, -1, `${id}: frame ${first} differs between ${COUNTS[0]} and ${n} workers: a page's frame depends on what that page drew before it`);
    }
  });
}
