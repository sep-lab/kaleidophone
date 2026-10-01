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
//        [--variant ending=lamp]   a piece with "variants": the option to draw on an axis (default: piece.json's)
//        [--endings ending]        the window's body once, then every option of this axis after it (below)
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
// --endings <axis> writes, with one encoder setting for all of them, instead of <out>:
//   <out stem>.body.mp4           the window up to the axis's join (its first frame at or after "at"), default option
//   <out stem>.<axis>-<opt>.mp4   one per option: from the join to the window's end, starting on a keyframe
//   <out stem>.variants.json      the manifest: the files, their frames, the join and the stream they share
// each with its sidecar. Nothing is moved into place until every file checks out (ffprobe): the
// frames and keyframes planned, the same stream parameters in all of them, and body + each ending
// joined by the concat demuxer with no gap -- what `kaleidophone deliver` does with them. The body is
// shared, so every option must draw the frame before the join exactly as the body did, or the run stops.
// The manifest is written last, and a set's old one is removed before rendering starts: whatever a
// failed run leaves, it never leaves a manifest beside parts that aren't its own.
//
// Work in progress -- the encodes, the joins -- goes in a folder made for the run next to <out>
// (<out stem>.parts-XXXXXX), removed when it ends; a failed run leaves no half-written video.
//
// The piece is built from its source with THIS song pack before it's opened (never dist/, which
// the gallery fills with synthetic twins). Stateless pieces are split into contiguous chunks, one
// browser page per worker, and joined with the concat demuxer (segment-then-concat: the answer
// every one of these releases re-derived). Stateful pieces render in one worker, in order, and any
// window -- a resumed one, and every part of --endings, included -- replays its history from the
// warm-up first. A piece with "variants" is always encoded in separate stretches either side of a
// join inside the window, so the whole window rendered with the defaults is, frame for frame, the
// body and the default ending of --endings joined.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import {
  UsageError, RunError, main, onCleanup, parseArgs, helpText, firstLine, loadPiece, loadDriver, loadSong,
  launch, openPiece, assertPageOk, buildForRun, requireFfmpeg, requireFfprobe, ffmpegSink, dataUrlToBuffer,
  keyTimesToFrames, toolVersion, pieceVariants, resolveVariant, withVariant, planRender, concatList,
  probeVideo, probeConcat, streamDifference, timelineProblems, variantsManifest,
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
    variant: { type: 'list', repeat: true, arg: 'axis=option', help: 'a piece with "variants": the option to draw on that axis (default: piece.json\'s)' },
    endings: { type: 'string', arg: 'axis', help: 'the body once and every option of this axis after it, as <out stem>.body.mp4 + .<axis>-<option>.mp4 + .variants.json' },
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
const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');

await main(async () => {
  const A = parseArgs(process.argv.slice(2), SPEC);
  if (A.help) { console.log(helpText(SPEC)); return; }
  const id = A._[0];
  const piece = loadPiece(id);
  const drv = await loadDriver(piece);
  const R = piece.spec.render || {};
  need(A.song, `--song is required: the song pack to render from (usage: ${SPEC.usage})`);
  const pack = loadSong(A.song);
  const variants = pieceVariants(piece);

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
  const endings = A.endings ?? null;
  need(endings === null || (A.from === undefined && A.to === undefined), '--endings renders the whole window, a body and every ending: --from / --to split one file, not a set');
  const from = A.from ?? 0, to = A.to ?? N;
  need(from >= 0 && from < N, `--from ${from} is outside the window's frames 0..${N - 1} (${dur} s at ${fps} fps)`);
  need(to > from && to <= N, `--to ${to} must be after --from ${from} and at most ${N}, the window's frame count (${dur} s at ${fps} fps)`);
  const crf = A.crf ?? +(R.crf ?? 18), tune = A.tune ?? R.tune ?? 'animation', q = A.q ?? 0.92;
  need(crf >= 0 && crf <= 51, `--crf must be 0..51 (got ${crf})`);
  need(q > 0 && q <= 1, `--q is a JPEG quality, 0..1 (got ${q})`);
  const flags = A.flags ?? {};
  need(flags && typeof flags === 'object' && !Array.isArray(flags), '--flags must be a JSON object, e.g. \'{"noSpots":true}\'');
  need(!Object.hasOwn(flags, 'variant'), '--flags can\'t set "variant": choose an option with --variant axis=option');
  const { choice, given } = resolveVariant(id, variants, A.variant || []);
  need(endings === null || !Object.hasOwn(given, endings), `--endings ${endings} renders every option of ${endings}: leave ${endings} out of --variant`);
  need(endings === null || outFps === fps, '--endings needs the render and output frame rates to match: its files are joined by stream copy, and a frame-rate change re-encodes');
  const requested = A.workers ?? 2;
  need(requested >= 1, `--workers must be at least 1 (got ${requested})`);
  const keysGiven = (A.keys || []).length || (A['key-times'] || []).length;
  need(!keysGiven || outFps === fps, '--keys / --key-times need the render and output frame rates to match (a frame-rate change re-encodes)');
  for (const k of A.keys || []) need(k >= 0 && k < N, `--keys ${k} is outside the window's frames 0..${N - 1}`);
  const pngFrames = new Set(A['png-frames'] || []);
  for (const k of pngFrames) need(k >= from && k < to, `--png-frames ${k} is outside the frames being rendered (${from}..${to - 1})`);
  const out = path.resolve(A.out || `${id}_silent.mp4`);
  const ext = path.extname(out) || '.mp4', stem = out.slice(0, out.length - path.extname(out).length);
  const fileOf = p => p.name ? `${stem}.${p.name}${ext}` : out;
  const manifestFile = `${stem}.variants.json`;

  const opts = { t0, dur, fps, w, h, card: !!A.card, mode: A.mode || 'reel', flags, seed: A.seed ?? R.seed, snap: A.snap ?? true, variant: choice };
  if (drv.plan) {
    let planned;
    try { planned = drv.plan(pack, opts); } catch (e) { throw new RunError(`${id}: its driver could not plan the window from this song pack: ${firstLine(e.message)}`); }
    if (planned && planned.t0 !== undefined && Math.abs(planned.t0 - t0) > 1e-9) {
      console.log(`t0 snapped to the nearest beat: ${t0} -> ${planned.t0.toFixed(3)}  (use THIS value for the audio -ss; it is silent_start in ${path.basename(endings ? manifestFile : out)}${endings ? '' : '.json'})`);
      t0 = planned.t0; opts.t0 = t0;
    }
  }
  // keyframes: frames of the window, from --keys and from --key-times (song seconds, on this window's grid)
  const keys = [...new Set([...(A.keys || []), ...keyTimesToFrames(A['key-times'] || [], { t0, fps, frames: N })])].sort((a, b) => a - b);
  let workers = requested;
  if (drv.stateful && requested > 1 && endings === null) {
    if (A.workers > 1) console.log(`${id} is stateful: rendering in one worker (every frame depends on the ones before it)`);
    workers = 1;
  }
  // the files, the pages that draw them, and the join (--endings)
  const plan = planRender({ id, variants, choice, endings, t0, fps, frames: N, from, to, workers, stateful: !!drv.stateful, keys });
  const lanes = Math.min(workers, plan.runs.length);
  if (drv.stateful && endings !== null) {
    console.log(`${id} is stateful: each of its ${plan.parts.length} files renders in one worker, in order, from its warm-up${lanes > 1 ? ` (${lanes} at a time)` : ''}`);
  }
  for (const f of [...plan.parts.map(fileOf), ...(endings ? [manifestFile] : [])]) {
    need(!fs.existsSync(f) || fs.statSync(f).isFile(), endings ? `${path.basename(f)} would be written over a directory (${path.dirname(f)}): give --out another name` : `--out ${A.out} is a directory: give a file name`);
  }

  // ---- then the machinery: ffmpeg first (no point starting Chromium without it), the build, the browser
  const ffmpegVersion = requireFfmpeg();
  if (endings) requireFfprobe();
  const { file: html, built } = await buildForRun(piece, A.song, A.html);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  // A set rendered again loses its old manifest now, before anything is rendered: a run that fails from
  // here on can't leave it beside new parts. A manifest means a whole set; parts without one are leftovers.
  if (endings) fs.rmSync(manifestFile, { force: true });
  // The encodes and joins go in a folder of this run's own, made next to the output (moving a finished
  // file into place is then a rename on the same disk) and removed when the run ends, however it ends.
  // Nothing else is deleted: a folder of yours that happens to share its name is never touched.
  const tmp = fs.mkdtempSync(path.join(path.dirname(out), `${path.basename(stem)}.parts-`));
  onCleanup(() => fs.rmSync(tmp, { recursive: true, force: true }));
  const browser = await launch();
  onCleanup(() => browser.close());
  const sinks = [];
  onCleanup(() => sinks.forEach(s => s.kill()));
  const allowPageErrors = !!A['allow-page-errors'];
  const T = Date.now(), total = plan.runs.reduce((n, r) => n + r.b - r.a, 0);
  let done = 0, failed = false;
  const encodeFile = (p, e) => path.join(tmp, `${p.name ? p.name + '.' : ''}part${String(e.k).padStart(2, '0')}.mp4`);
  const framesDir = p => fileOf(p).replace(/\.mp4$/, '') + '_frames';
  const probes = new Map(); // part -> sha256 of the lossless frame just before the join (--endings)

  // A page drawing the frames of part p, with p's choice. A driver of its own for every page: a
  // stateful driver keeps its schedule on `this` (plan()).
  async function openRun(p) {
    const label = p.name ? `${p.name}: ` : '';
    const d = await loadDriver(piece);
    const ro = { ...opts, variant: p.variant };
    if (d.plan) {
      try { d.plan(pack, { ...ro, snap: false }); } catch (e) { throw new RunError(`${id}: its driver could not plan the window from this song pack: ${firstLine(e.message)}`); }
    }
    const page = await openPiece(browser, html, d.query({ w, h, seed: opts.seed }), { width: Math.min(w, 1080), height: Math.min(h, 1920) }, { allowPageErrors });
    await d.init(page, pack, ro);
    assertPageOk(page, `${id}: init`);
    const draw = async i => {
      const t = t0 + i / fps;
      try { await d.draw(page, withVariant(d.frame(t, pack, ro), p.variant)); } catch (e) {
        throw new RunError(`${id}: ${label}frame ${i} (t ${t.toFixed(3)} s) failed: ${firstLine(e.message)}`);
      }
      assertPageOk(page, `${id}: ${label}frame ${i} (t ${t.toFixed(3)} s)`);
    };
    const png = async () => dataUrlToBuffer(await page.evaluate(sel => document.querySelector(sel).toDataURL('image/png'), d.canvasSelector));
    return { d, page, draw, png };
  }

  // --endings, stateless: every option must draw the frame before the join as the default does. Each
  // draws it on a fresh page of its own (like for like), before anything is rendered.
  const notTheBody = p => new RunError(`${id}: ${p.name} draws frame ${plan.join.frame - 1} (song time ${(t0 + (plan.join.frame - 1) / fps).toFixed(3)} s) differently from the body, before ${endings} starts at ${plan.join.at} s -- ` +
    `every option must draw the same frames before "at": move ${endings}'s "at" in piece.json back to where the options start to differ`);
  if (endings && !drv.stateful) {
    const before = async p => {
      const { page, draw, png } = await openRun(p);
      await draw(plan.join.frame - 1);
      const h = sha256(await png());
      await page.close();
      return h;
    };
    const ends = plan.parts.filter(p => p.role === 'ending'), ref = await before(ends.find(p => p.default));
    for (const p of ends.filter(q => !q.default)) if (await before(p) !== ref) throw notTheBody(p);
  }

  async function work(run) {
    const p = plan.parts[run.part];
    const { d, page, draw, png } = await openRun(p);
    // a stateful piece has no frame N without the frames before it: replay them (from the warm-up,
    // or from the window's first frame) without writing, so a resumed window matches a whole one and
    // an ending continues the body
    if (d.stateful) {
      const wn = Math.round((d.warmup || 0) * fps);
      for (let i = -wn; i < run.a && !failed; i++) {
        await draw(i);
        if (i === run.probe) probes.set(p.name, sha256(await png()));
      }
    }
    for (const k of run.encodes) {
      const e = p.encodes[k];
      // forced keyframes are in frame numbers of the whole window; each encode counts from its own 0
      const sink = ffmpegSink(encodeFile(p, e), { fps, crf, tune, keyframes: e.keys });
      sinks.push(sink);
      for (let i = e.a; i < e.b && !failed; i++) {
        await draw(i);
        const jpg = await page.evaluate(([sel, qq]) => document.querySelector(sel).toDataURL('image/jpeg', qq), [d.canvasSelector, q]);
        await sink.write(dataUrlToBuffer(jpg));
        if (pngFrames.has(i) || i === run.probe) {
          const buf = await png();
          if (i === run.probe) probes.set(p.name, sha256(buf));
          if (pngFrames.has(i)) {
            const dir = framesDir(p); fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(path.join(dir, `frame_${String(i).padStart(5, '0')}.png`), buf);
          }
        }
        if (++done % 120 === 0) { const el = (Date.now() - T) / 1000; console.log(`${done}/${total} frames  ${(done / el).toFixed(1)} fps  eta ${((total - done) / (done / el)).toFixed(0)}s`); }
      }
      await sink.end();
    }
    await page.close();
  }

  // `lanes` pages at a time, each taking the next run
  let next = 0;
  const lane = async () => { while (next < plan.runs.length && !failed) await work(plan.runs[next++]); };
  await Promise.all(Array.from({ length: lanes }, () => lane().catch(e => { failed = true; throw e; })));
  const chromium = browser.version();
  await browser.close();

  // join each file's encodes into a file next to the output: <out> is either the previous render or
  // this complete one, never half of one
  const reencode = outFps !== fps
    // e.g. a piece drawn on twos at 12 fps delivered at 24: ffmpeg duplicates every frame (re-encode once)
    ? ['-r', String(outFps), '-c:v', 'libx264', '-preset', 'medium', '-tune', tune, '-crf', String(crf), '-pix_fmt', 'yuv420p']
    : ['-c', 'copy'];
  const joinedOf = {};
  for (const p of plan.parts) {
    const list = path.join(tmp, p.name ? `${p.name}.list.txt` : 'list.txt');
    fs.writeFileSync(list, concatList(p.encodes.map(e => encodeFile(p, e))));
    const joined = path.join(tmp, (p.name ? `${p.name}.joined` : 'joined') + ext);
    const ff = spawnSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', list, ...reencode, '-movflags', '+faststart', joined], { encoding: 'utf8' });
    if (ff.error || ff.status !== 0) throw new RunError(`ffmpeg could not join the parts${p.name ? ` of ${p.name}` : ''}: ${firstLine((ff.stderr || '').trim().split('\n').pop() || (ff.error && ff.error.message))}`);
    joinedOf[p.name] = joined;
  }

  const encode = { codec: 'libx264', crf, tune, preset: 'medium', pix_fmt: 'yuv420p', capture: `jpeg q${q}` };
  const tools = { 'kaleidophone-canvas': toolVersion(), chromium, ffmpeg: ffmpegVersion, node: process.version };
  const sidecar = p => ({
    kaleidophone: 'canvas-render/1',
    piece: id,
    song: path.basename(A.song),
    synthetic_song: !!pack.synthetic,
    html: built ? 'built from the piece\'s source with this song' : path.basename(html),
    t0: { requested: t0Asked, snapped: r6(t0) },
    // the song time of this file's first frame: a delivery sheet's silent_start
    silent_start: r6(t0 + p.from / fps),
    dur,
    fps,
    out_fps: outFps,
    frames: { window: N, from: p.from, to: p.to, rendered: p.to - p.from },
    // t: seconds on this file's clock (what -force_key_frames and a delivery sheet's cut times use); song_t: song time
    keys: p.keys.map(k => ({ frame: k, file_frame: k - p.from, t: r6((k - p.from) / fps), song_t: r6(t0 + k / fps) })),
    size: { w, h },
    workers: plan.runs.filter(r => plan.parts[r.part] === p).length,
    stateful: !!drv.stateful,
    warmup: drv.stateful ? (drv.warmup || 0) : null,
    mode: opts.mode, card: opts.card, flags, seed: opts.seed ?? null,
    // a piece with "variants": the option drawn on every axis, and the joins inside this file (the
    // encoder starts again at each, on a keyframe)
    ...(variants ? {
      variant: p.variant,
      joins: p.joins.map(j => ({ axis: j.axis, at: j.at, frame: j.frame, file_frame: j.file_frame, t: r6(j.file_frame / fps), song_t: r6(t0 + j.frame / fps) })),
    } : {}),
    ...(p.role !== 'window' ? {
      part: { role: p.role, axis: plan.join.axis, option: p.option ?? null, join_frame: plan.join.frame, manifest: path.basename(manifestFile) },
    } : {}),
    encode,
    tools,
  });
  const el = () => (Date.now() - T) / 1000;

  if (!endings) {
    const [p] = plan.parts;
    fs.renameSync(joinedOf[p.name], out);
    fs.writeFileSync(out + '.json', JSON.stringify(sidecar(p), null, 2) + '\n');
    const tag = variants ? `, ${Object.entries(choice).map(([a, o]) => `${a}=${o}`).join(' ')}` : '';
    console.log(`DONE ${out}  ${total} frames (t0 ${t0.toFixed(3)}, ${dur}s @ ${fps} fps${outFps !== fps ? ` -> ${outFps}` : ''}${tag}${keys.length ? `, keyframes ${keys.join(',')}` : ''}) in ${el().toFixed(0)}s (${(total / el()).toFixed(1)} fps)  + ${path.basename(out)}.json`);
    return;
  }

  // ---- --endings: check the set as the delivery will use it, then move it into place
  const J = plan.join.frame, body = plan.parts.find(p => p.role === 'body'), ends = plan.parts.filter(p => p.role === 'ending');
  const name = p => path.basename(fileOf(p));
  // 1. one body for every option: a stateful ending's replay drew the frame before the join as the body did
  if (drv.stateful) for (const p of ends) if (probes.get(p.name) !== probes.get('body')) throw notTheBody(p);
  // 2. every file: the frames planned, a keyframe first and at every forced key
  const probed = {};
  for (const p of plan.parts) {
    const v = probeVideo(joinedOf[p.name]);
    const bad = timelineProblems(v.packets, { frames: p.frames, fps, timeBase: v.params.time_base, keys: [0, ...p.keys.map(k => k - p.from)] });
    if (bad.length) throw new RunError(`${name(p)}: ${bad[0]}`);
    probed[p.name] = v;
  }
  // 3. one stream: what the concat demuxer needs to join them with -c copy
  for (const p of ends) {
    const diff = streamDifference(probed.body.params, probed[p.name].params);
    if (diff) throw new RunError(`${name(p)} can't be joined to ${name(body)} by stream copy: its ${diff[0]} is ${diff[2]}, the body's ${diff[1]}`);
  }
  // 4. the joins themselves, as `kaleidophone deliver` makes them: every frame once, one frame apart
  const joined = {};
  for (const p of ends) {
    const c = probeConcat([joinedOf.body, joinedOf[p.name]], path.join(tmp, `${p.name}.join.txt`));
    const bad = timelineProblems(c.packets, { frames: N, fps, timeBase: c.time_base, keys: [0, J] });
    if (bad.length) throw new RunError(`${name(body)} + ${name(p)}, joined by the concat demuxer: ${bad[0]}`);
    joined[p.name] = { frames: c.packets.length, gapless: true, keyframe_at_join: true };
  }
  // into place: the videos, their sidecars, and the manifest last -- a manifest means a whole set
  const files = {};
  for (const p of plan.parts) {
    fs.renameSync(joinedOf[p.name], fileOf(p));
    fs.writeFileSync(fileOf(p) + '.json', JSON.stringify(sidecar(p), null, 2) + '\n');
    files[p.name] = { file: name(p), sidecar: `${name(p)}.json` };
  }
  const manifest = variantsManifest({
    piece: id, song: path.basename(A.song), synthetic: pack.synthetic, axis: { name: endings, spec: variants[endings] },
    t0, dur, fps, size: { w, h }, plan, files, stream: probed.body.params, joined, encode, tools,
  });
  fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + '\n');
  console.log(`DONE ${manifestFile}  body ${J} frames + ${ends.length} endings x ${N - J} frames (${endings} from ${plan.join.at} s = frame ${J}; t0 ${t0.toFixed(3)}, ${dur}s @ ${fps} fps) in ${el().toFixed(0)}s (${(total / el()).toFixed(1)} fps)`);
  for (const p of plan.parts) {
    console.log(`  ${name(p)}  ${p.frames} frames${p.role === 'body' ? `, song ${r6(t0)}-${r6(t0 + J / fps)} s` : `, joins at frame ${J}${p.default ? ' (default)' : ''}`}  + ${name(p)}.json`);
  }
});
