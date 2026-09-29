#!/usr/bin/env node
// render.mjs -- deterministic, SILENT render of a piece, driven by a song pack.
//
//   node tools/render.mjs <piece> --song pack.json --t0 0 --dur 72.25 --out reel_silent.mp4
//        [--fps 24] [--out-fps 24] [--w 1080] [--h 1920] [--workers 2] [--crf 18] [--q 0.92]
//        [--keys 0,630,1014]       force keyframes at these frames of the window (for -c:v copy cuts later)
//        [--key-times 26.25,42.25] the same as song times, in seconds (what `kaleidophone deliver` prints)
//        [--card]                  the piece's signature card over the first frames (pieces that have one)
//        [--mode reel|story|none]  stateful pieces: which cards to draw
//        [--flags '{"noSpots":true}'] extra per-frame flags
//        [--from N --to M]         render only frames [N, M) of the window (resume / split by hand)
//        [--html file.html]        render this HTML instead of building the piece now (golden-frame checks)
//        [--png-frames 60,450]     also save these window frames as lossless PNGs next to the output (QA)
//        [--allow-page-errors]     keep going when the page throws or asks for anything but a local file
//
// Writes <out> and <out>.json: what was rendered and how -- piece, t0 asked for and snapped, the
// frames and keyframes (as frames and as seconds), size, workers, the tool, Chromium and ffmpeg
// versions, and the song pack's file name (never a path). The audio is never touched here. Mux it
// afterwards where the WAV lives (the device), from the sidecar's silent_start: see
// `kaleidophone deliver` and docs/TECHNIQUES.md, "silent render, mux on the device".
//
// The piece is built from its source with THIS song pack before it's opened (never dist/, which
// the gallery fills with synthetic twins). Stateless pieces are split into contiguous chunks, one
// browser page per worker, and joined with the concat demuxer (segment-then-concat: the answer
// every one of these releases re-derived). Stateful pieces render in one worker, in order, and any
// window -- a resumed one included -- replays its history from the warm-up first.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import {
  UsageError, RunError, main, onCleanup, parseArgs, helpText, firstLine, loadPiece, loadDriver, loadSong,
  launch, openPiece, assertPageOk, buildForRun, requireFfmpeg, ffmpegSink, dataUrlToBuffer, planParts,
  keyTimesToFrames, toolVersion,
} from './lib/common.mjs';

const SPEC = {
  usage: 'node tools/render.mjs <piece> --song pack.json [--t0 s] [--dur s] [--out file.mp4] [flags]',
  positional: [1, 1],
  flags: {
    song: { type: 'string', arg: 'pack.json', help: 'the song pack that drives the piece (required)' },
    t0: { type: 'number', arg: 's', help: 'window start, song seconds (default 0; stateful pieces snap it to a beat)' },
    dur: { type: 'number', arg: 's', help: 'window length in seconds (default 10)' },
    out: { type: 'string', arg: 'file.mp4', help: 'the silent video (default <piece>_silent.mp4); <out>.json is written next to it' },
    fps: { type: 'number', help: 'render frame rate (default: piece.json, else 24)' },
    'out-fps': { type: 'number', help: 'deliver at another rate: ffmpeg repeats frames (re-encodes once)' },
    w: { type: 'int', arg: 'px', help: 'width (default: piece.json, else 1080; even)' },
    h: { type: 'int', arg: 'px', help: 'height (default: piece.json, else 1920; even)' },
    workers: { type: 'int', arg: 'n', help: 'browser pages in parallel (default 2; never more than frames; stateful pieces: 1)' },
    crf: { type: 'number', help: 'x264 quality (default: piece.json, else 18)' },
    tune: { type: 'string', choices: ['animation', 'film', 'grain', 'stillimage', 'psnr', 'ssim', 'fastdecode', 'zerolatency'], help: 'x264 tune (default: piece.json, else animation)' },
    q: { type: 'number', help: 'JPEG quality of the captured frames, 0-1 (default 0.92)' },
    keys: { type: 'ints', arg: 'n,n,...', help: 'force keyframes at these frames of the window' },
    'key-times': { type: 'numbers', arg: 's,s,...', help: 'force keyframes at these song times (seconds, on the frame grid)' },
    card: { type: 'bool', help: 'the piece\'s signature card over the first frames' },
    mode: { type: 'string', choices: ['reel', 'story', 'none'], help: 'stateful pieces: which cards to draw (default reel)' },
    flags: { type: 'json', arg: '{...}', help: 'extra per-frame flags, as JSON' },
    seed: { type: 'number', help: 'the piece\'s seed (default: piece.json)' },
    snap: { type: 'bool', help: 'stateful pieces: snap t0 to the nearest beat (default true; --snap=false to keep it)' },
    from: { type: 'int', arg: 'N', help: 'render frames [N, M) of the window only (resume / split by hand)' },
    to: { type: 'int', arg: 'M', help: 'see --from (default: the window\'s frame count)' },
    html: { type: 'string', arg: 'file.html', help: 'render this HTML instead of building the piece now' },
    'png-frames': { type: 'ints', arg: 'n,n,...', help: 'also save these window frames as lossless PNGs (QA)' },
    'allow-page-errors': { type: 'bool', help: 'keep rendering when the page throws or requests anything but a local file' },
  },
};

const need = (ok, msg) => { if (!ok) throw new UsageError(msg); };
const r6 = x => +x.toFixed(6);

await main(async () => {
  const A = parseArgs(process.argv.slice(2), SPEC);
  if (A.help) { console.log(helpText(SPEC)); return; }
  const id = A._[0];
  const piece = loadPiece(id);
  const drv = await loadDriver(piece);
  const R = piece.spec.render || {};
  need(A.song, `--song is required: the song pack to render from (usage: ${SPEC.usage})`);
  const pack = loadSong(A.song);

  // ---- everything that can be wrong with the request is caught here, before anything starts
  const fps = A.fps ?? +(R.fps || 24), outFps = A['out-fps'] ?? fps;
  need(fps > 0, `--fps must be positive (got ${fps})`);
  need(outFps > 0, `--out-fps must be positive (got ${outFps})`);
  const w = A.w ?? +(R.w || 1080), h = A.h ?? +(R.h || 1920);
  need(Number.isInteger(w) && Number.isInteger(h) && w > 0 && h > 0, `--w and --h must be positive whole numbers (got ${w}x${h})`);
  need(w % 2 === 0 && h % 2 === 0, `--w and --h must be even: H.264 in yuv420p can't encode ${w}x${h}`);
  const t0Asked = A.t0 ?? 0;
  need(t0Asked >= 0, `--t0 is song time and can't be negative (got ${t0Asked})`);
  let t0 = t0Asked;
  const dur = A.dur ?? 10;
  need(dur > 0, `--dur must be positive (got ${dur})`);
  const N = Math.round(dur * fps);
  need(N >= 1, `--dur ${dur} is less than one frame at ${fps} fps`);
  const from = A.from ?? 0, to = A.to ?? N;
  need(from >= 0 && from < N, `--from ${from} is outside the window's frames 0..${N - 1} (${dur} s at ${fps} fps)`);
  need(to > from && to <= N, `--to ${to} must be after --from ${from} and at most ${N}, the window's frame count (${dur} s at ${fps} fps)`);
  const crf = A.crf ?? +(R.crf ?? 18), tune = A.tune ?? R.tune ?? 'animation', q = A.q ?? 0.92;
  need(crf >= 0 && crf <= 51, `--crf must be 0..51 (got ${crf})`);
  need(q > 0 && q <= 1, `--q is a JPEG quality, 0..1 (got ${q})`);
  const flags = A.flags ?? {};
  need(flags && typeof flags === 'object' && !Array.isArray(flags), '--flags must be a JSON object, e.g. \'{"noSpots":true}\'');
  const requested = A.workers ?? 2;
  need(requested >= 1, `--workers must be at least 1 (got ${requested})`);
  const keysGiven = (A.keys || []).length || (A['key-times'] || []).length;
  need(!keysGiven || outFps === fps, '--keys / --key-times need the render and output frame rates to match (a frame-rate change re-encodes)');
  for (const k of A.keys || []) need(k >= 0 && k < N, `--keys ${k} is outside the window's frames 0..${N - 1}`);
  const pngFrames = new Set(A['png-frames'] || []);
  for (const k of pngFrames) need(k >= from && k < to, `--png-frames ${k} is outside the frames being rendered (${from}..${to - 1})`);
  const out = path.resolve(A.out || `${id}_silent.mp4`);
  need(!fs.existsSync(out) || fs.statSync(out).isFile(), `--out ${A.out} is a directory: give a file name`);

  const opts = { t0, dur, fps, w, h, card: !!A.card, mode: A.mode || 'reel', flags, seed: A.seed ?? R.seed, snap: A.snap ?? true };
  if (drv.plan) {
    let planned;
    try { planned = drv.plan(pack, opts); } catch (e) { throw new RunError(`${id}: its driver could not plan the window from this song pack: ${firstLine(e.message)}`); }
    if (planned && planned.t0 !== undefined && Math.abs(planned.t0 - t0) > 1e-9) {
      console.log(`t0 snapped to the nearest beat: ${t0} -> ${planned.t0.toFixed(3)}  (use THIS value for the audio -ss; it is silent_start in ${path.basename(out)}.json)`);
      t0 = planned.t0; opts.t0 = t0;
    }
  }
  // keyframes: frames of the window, from --keys and from --key-times (song seconds, on this window's grid)
  const keys = [...new Set([...(A.keys || []), ...keyTimesToFrames(A['key-times'] || [], { t0, fps, frames: N })])].sort((a, b) => a - b);
  let workers = requested;
  if (drv.stateful && requested > 1) {
    if (A.workers > 1) console.log(`${id} is stateful: rendering in one worker (every frame depends on the ones before it)`);
    workers = 1;
  }
  const parts = planParts(from, to, workers, keys);

  // ---- then the machinery: ffmpeg first (no point starting Chromium without it), the build, the browser
  const ffmpegVersion = requireFfmpeg();
  const { file: html, built } = await buildForRun(piece, A.song, A.html);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const tmp = out.replace(/\.mp4$/, '') + '_parts';
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  onCleanup(() => fs.rmSync(tmp, { recursive: true, force: true }));
  const browser = await launch();
  onCleanup(() => browser.close());
  const sinks = [];
  onCleanup(() => sinks.forEach(s => s.kill()));
  const allowPageErrors = !!A['allow-page-errors'];
  const T = Date.now(), total = to - from;
  let done = 0, failed = false;

  async function work(part) {
    const page = await openPiece(browser, html, drv.query({ w, h, seed: opts.seed }), { width: Math.min(w, 1080), height: Math.min(h, 1920) }, { allowPageErrors });
    await drv.init(page, pack, opts);
    assertPageOk(page, `${id}: init`);
    const file = path.join(tmp, `part${String(part.k).padStart(2, '0')}.mp4`);
    // forced keyframes are in frame numbers of the whole window; each part counts from its own 0
    const sink = ffmpegSink(file, { fps, crf, tune, keyframes: part.keys });
    sinks.push(sink);
    const draw = async i => {
      const t = t0 + i / fps;
      try { await drv.draw(page, drv.frame(t, pack, opts)); } catch (e) {
        throw new RunError(`${id}: frame ${i} (t ${t.toFixed(3)} s) failed: ${firstLine(e.message)}`);
      }
      assertPageOk(page, `${id}: frame ${i} (t ${t.toFixed(3)} s)`);
    };
    // a stateful piece has no frame N without the frames before it: replay them (from the warm-up,
    // or from the window's first frame) without writing, so a resumed window matches a whole one
    if (drv.stateful) {
      const wn = Math.round((drv.warmup || 0) * fps);
      for (let i = -wn; i < part.a && !failed; i++) await draw(i);
    }
    for (let i = part.a; i < part.b && !failed; i++) {
      await draw(i);
      const d = await page.evaluate(([sel, qq]) => document.querySelector(sel).toDataURL('image/jpeg', qq), [drv.canvasSelector, q]);
      await sink.write(dataUrlToBuffer(d));
      if (pngFrames.has(i)) {
        const p = await page.evaluate(sel => document.querySelector(sel).toDataURL('image/png'), drv.canvasSelector);
        const dir = out.replace(/\.mp4$/, '') + '_frames'; fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, `frame_${String(i).padStart(5, '0')}.png`), dataUrlToBuffer(p));
      }
      if (++done % 120 === 0) { const el = (Date.now() - T) / 1000; console.log(`${done}/${total} frames  ${(done / el).toFixed(1)} fps  eta ${((total - done) / (done / el)).toFixed(0)}s`); }
    }
    await sink.end();
    await page.close();
    return file;
  }

  const files = await Promise.all(parts.map(p => work(p).catch(e => { failed = true; throw e; })));
  const chromium = browser.version();
  await browser.close();

  // join the parts into a file next to the output, then move it into place: <out> is either the
  // previous render or this complete one, never half of one
  const list = path.join(tmp, 'list.txt');
  fs.writeFileSync(list, files.map(p => `file '${p.replace(/'/g, "'\\''")}'`).join('\n') + '\n');
  const joined = path.join(tmp, 'joined' + (path.extname(out) || '.mp4'));
  const reencode = outFps !== fps
    // e.g. a piece drawn on twos at 12 fps delivered at 24: ffmpeg duplicates every frame (re-encode once)
    ? ['-r', String(outFps), '-c:v', 'libx264', '-preset', 'medium', '-tune', tune, '-crf', String(crf), '-pix_fmt', 'yuv420p']
    : ['-c', 'copy'];
  const ff = spawnSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', list, ...reencode, '-movflags', '+faststart', joined], { encoding: 'utf8' });
  if (ff.error || ff.status !== 0) throw new RunError(`ffmpeg could not join the parts: ${firstLine((ff.stderr || '').trim().split('\n').pop() || (ff.error && ff.error.message))}`);
  fs.renameSync(joined, out);

  const sidecar = {
    kaleidophone: 'canvas-render/1',
    piece: id,
    song: path.basename(A.song),
    synthetic_song: !!pack.synthetic,
    html: built ? 'built from the piece\'s source with this song' : path.basename(html),
    t0: { requested: t0Asked, snapped: r6(t0) },
    // the song time of this file's first frame: a delivery sheet's silent_start
    silent_start: r6(t0 + from / fps),
    dur,
    fps,
    out_fps: outFps,
    frames: { window: N, from, to, rendered: to - from },
    // t: seconds on this file's clock (what -force_key_frames and a delivery sheet's cut times use); song_t: song time
    keys: keys.filter(k => k >= from && k < to).map(k => ({ frame: k, file_frame: k - from, t: r6((k - from) / fps), song_t: r6(t0 + k / fps) })),
    size: { w, h },
    workers: parts.length,
    stateful: !!drv.stateful,
    warmup: drv.stateful ? (drv.warmup || 0) : null,
    mode: opts.mode, card: opts.card, flags, seed: opts.seed ?? null,
    encode: { codec: 'libx264', crf, tune, preset: 'medium', pix_fmt: 'yuv420p', capture: `jpeg q${q}` },
    tools: { 'kaleidophone-canvas': toolVersion(), chromium, ffmpeg: ffmpegVersion, node: process.version },
  };
  fs.writeFileSync(out + '.json', JSON.stringify(sidecar, null, 2) + '\n');
  const el = (Date.now() - T) / 1000;
  console.log(`DONE ${out}  ${total} frames (t0 ${t0.toFixed(3)}, ${dur}s @ ${fps} fps${outFps !== fps ? ` -> ${outFps}` : ''}${keys.length ? `, keyframes ${keys.join(',')}` : ''}) in ${el.toFixed(0)}s (${(total / el).toFixed(1)} fps)  + ${path.basename(out)}.json`);
});
