#!/usr/bin/env node
// golden.mjs -- golden frames: what each frozen piece draws, held to the pixel.
//
//   node tools/golden.mjs --check [piece...] [--strict] [--dir folder]
//   node tools/golden.mjs --update [piece...] [--force] [--dir folder]
//
// A frozen piece (every piece but the templates: AGENTS.md) is guarded twice. test/contract.test.mjs
// holds its page to the bytes the release shipped; this holds what that page draws: 6 frames and 2
// covers per piece, from its synthetic twin, each kept as the sha256 of the still's decoded RGBA pixels
// (not of the PNG: an encoder may change where the pixels don't) in test/golden/<piece>.sha256.
//
// Exact pixels only repeat on one machine image. Chromium's software rasteriser differs between Linux
// and macOS, and a piece that falls back on a system font (HAMECHI MANZOR DARE's credit line is
// ui-monospace) changes with the fonts installed: canvas/README.md, "Verified against what shipped".
// So the hashes are recorded on CI's ubuntu-24.04 with its fonts pinned (.github/actions/canvas-env),
// every file says what it was recorded on, and:
//
//   --check    builds each piece as the release ships it, checks the page's sha256 against the one the
//              frames were drawn from (anywhere), then renders the stills the file lists and compares
//              them. On a machine other than the one the file names, the frames can't match: it says
//              so and skips them -- unless --strict (CI), where a different machine is itself a failure.
//   --update   renders and rewrites the files. Use the golden-update job (Actions -> CI -> Run workflow,
//              with golden_update), which uploads them for a reviewed PR to commit. Anywhere but Linux it
//              refuses without --force: hashes from another machine would only ever match that machine.
//   --dir      read and write the files in another folder (a local experiment; default test/golden).
//
// The stills land in canvas/out/golden/<piece>/ (git ignores canvas/out/), so a failed check can be
// looked at; CI uploads them.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { CANVAS, PIECES, RunError, UsageError, main, onCleanup, parseArgs, helpText, firstLine, listPieces, loadPiece, launch, loadSong } from './lib/common.mjs';
import { buildPiece, retitle } from './build.mjs';
import { synthFor } from './synth.mjs';

export const GOLDEN = path.join(CANVAS, 'test', 'golden');
const STILLS = path.join(CANVAS, 'out', 'golden');
export const FRAMES = 6, COVERS = 2, COVER_W = 1200;
const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');

// ---------------------------------------------------------------- which pieces
// Every piece but the templates is frozen: a template is versioned, and grows with the lib.
export const isTemplate = spec => ((spec && spec.gallery) || {}).role === 'template';
export function frozenPieces() { return listPieces().filter(id => !isTemplate(loadPiece(id).spec)); }

// ---------------------------------------------------------------- the page, as it ships
// Built from the piece's synthetic twin and retitled "TITLE — artist", exactly as the gallery and the
// release zip ship it: the page test/contract.test.mjs holds to the release's sha256.
export function releasePage(id, out) {
  const file = buildPiece(id, { song: synthFor(id), out, quiet: true });
  const html = retitle(fs.readFileSync(file, 'utf8'), loadPiece(id).spec);
  fs.writeFileSync(file, html);
  return { file, sha256: sha256(Buffer.from(html)), bytes: Buffer.byteLength(html) };
}

// ---------------------------------------------------------------- pixels
// The RGBA pixels of a PNG, for hashing: 8-bit, not interlaced (what Chromium's canvas.toDataURL writes),
// grey, grey + alpha, RGB or RGBA, all widened to RGBA so the encoder's choice of colour type can't
// change the hash.
export function decodePng(buf) {
  const SIG = '89504e470d0a1a0a';
  if (buf.subarray(0, 8).toString('hex') !== SIG) throw new RunError('not a PNG');
  let w = 0, h = 0, depth = 0, type = -1, interlace = 0;
  const idat = [];
  for (let o = 8; o + 8 <= buf.length;) {
    const len = buf.readUInt32BE(o), kind = buf.toString('latin1', o + 4, o + 8), body = buf.subarray(o + 8, o + 8 + len);
    if (kind === 'IHDR') { w = body.readUInt32BE(0); h = body.readUInt32BE(4); depth = body[8]; type = body[9]; interlace = body[12]; }
    else if (kind === 'IDAT') idat.push(body);
    else if (kind === 'IEND') break;
    o += 12 + len;
  }
  const channels = { 0: 1, 2: 3, 4: 2, 6: 4 }[type];
  if (!channels || depth !== 8 || interlace) throw new RunError(`a PNG this decoder doesn't read (colour type ${type}, ${depth}-bit${interlace ? ', interlaced' : ''})`);
  const raw = zlib.inflateSync(Buffer.concat(idat)), stride = w * channels;
  if (raw.length !== h * (stride + 1)) throw new RunError(`a truncated PNG (${raw.length} bytes of pixels, expected ${h * (stride + 1)})`);
  const px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], row = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)), at = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? px[at + x - channels] : 0, b = y ? px[at - stride + x] : 0, c = x >= channels && y ? px[at - stride + x - channels] : 0;
      let p;
      if (f === 0) p = 0;
      else if (f === 1) p = a;
      else if (f === 2) p = b;
      else if (f === 3) p = (a + b) >> 1;
      else if (f === 4) { const q = a + b - c, pa = Math.abs(q - a), pb = Math.abs(q - b), pc = Math.abs(q - c); p = pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      else throw new RunError(`a PNG with an unknown row filter (${f}) on row ${y}`);
      px[at + x] = (row[x] + p) & 255;
    }
  }
  if (channels === 4) return { w, h, rgba: px };
  const rgba = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    const j = i * channels, k = i * 4, grey = channels <= 2;
    rgba[k] = px[j]; rgba[k + 1] = px[grey ? j : j + 1]; rgba[k + 2] = px[grey ? j : j + 2];
    rgba[k + 3] = channels === 2 ? px[j + 1] : 255;
  }
  return { w, h, rgba };
}

// sha256 over "rgba8 WxH\n" and the pixels: a still's hash depends on its size and its pixels, nothing else
export function pixelHash(png) {
  const { w, h, rgba } = decodePng(png);
  return crypto.createHash('sha256').update(`rgba8 ${w}x${h}\n`).update(rgba).digest('hex');
}

// ---------------------------------------------------------------- the files
// test/golden/<piece>.sha256: a few "# key value" lines, then "<sha256>  <still>.png" per still. A still's
// name says what it is, in still.mjs's own naming: <piece>_<t>.png (a frame at song time t, seconds) or
// <piece>_cover_<name>_<width>.png.
const HEAD = id => [
  `# kaleidophone golden frames: ${id}, from its synthetic twin. Each line is the sha256 of one still's decoded`,
  '# RGBA pixels (canvas/tools/golden.mjs), drawn from the page with the "html" sha256 below: the page as the',
  '# release zip ships it. Recorded by the golden-update job on the machine named in "env"; never edit by hand.',
];

export function stillName(id, s) { return s.cover ? `${id}_cover_${s.cover}_${s.w}.png` : `${id}_${s.t.toFixed(3)}.png`; }

export function parseStill(id, name) {
  const esc = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const c = new RegExp(`^${esc}_cover_([\\w-]+)_(\\d+)\\.png$`).exec(name);
  if (c) return { cover: c[1], w: +c[2] };
  const f = new RegExp(`^${esc}_(\\d+\\.\\d{3})\\.png$`).exec(name);
  if (f) return { t: +f[1] };
  return null;
}

export function formatGolden({ id, html, env, size, stills }) {
  return [...HEAD(id), `# html ${html}`, `# env ${env}`, `# size ${size.w}x${size.h}`,
    ...stills.map(s => `${s.sha256}  ${stillName(id, s)}`)].join('\n') + '\n';
}

export function parseGolden(id, text, where = `test/golden/${id}.sha256`) {
  const g = { id, html: null, env: null, size: null, stills: [] };
  for (const [i, line] of text.split('\n').entries()) {
    if (!line.trim()) continue;
    const bad = why => { throw new RunError(`${where}:${i + 1}: ${why}`); };
    let m;
    if ((m = /^# html ([0-9a-f]{64})$/.exec(line))) g.html = m[1];
    else if ((m = /^# env (.+)$/.exec(line))) g.env = m[1];
    else if ((m = /^# size (\d+)x(\d+)$/.exec(line))) g.size = { w: +m[1], h: +m[2] };
    else if (line.startsWith('#')) continue;
    else if ((m = /^([0-9a-f]{64}) {2}(\S+)$/.exec(line))) {
      const s = parseStill(id, m[2]) || bad(`"${m[2]}" is not a still of ${id} (${id}_<t>.png or ${id}_cover_<name>_<width>.png)`);
      if (g.stills.some(x => stillName(id, x) === m[2])) bad(`${m[2]} is listed twice`);
      g.stills.push({ ...s, sha256: m[1] });
    } else bad(`not a "<sha256>  <still>.png" line: ${JSON.stringify(line.slice(0, 80))}`);
  }
  if (!g.html || !g.env || !g.size) throw new RunError(`${where} is missing its ${['html', 'env', 'size'].filter(k => !g[k]).join(', ')} line`);
  return g;
}

// What a new piece's goldens are: the moment its gallery poster shows and five more dividing its twin
// in six (each on the piece's frame grid, to the millisecond), plus its gallery cover and the next one.
// An existing file keeps its own list: --update re-renders it, never re-picks it.
export function defaultStills(id, spec, pack) {
  const fps = +((spec.render || {}).fps || 24), g = spec.gallery || {};
  const dur = pack.dur || pack.rms.length / pack.fps;
  const onGrid = t => +(Math.round(t * fps) / fps).toFixed(3);
  const gdur = g.dur ?? 6, poster = g.t0 !== undefined ? onGrid(g.t0 + (g.poster ?? Math.min(gdur * 0.6, gdur - 1 / (g.fps || 12)))) : null;
  const spread = n => Array.from({ length: n }, (_, k) => onGrid(dur * (k + 1) / (n + 1)));
  // the poster, then five points dividing the song in six (a second spread only if one of those is the poster)
  const times = [...new Set([poster, ...spread(FRAMES - 1), ...spread(FRAMES + 1)].filter(t => t !== null && t < dur))]
    .slice(0, FRAMES).sort((a, b) => a - b);
  const names = (spec.covers?.variants || []).map(v => v.name);
  const covers = [...new Set([g.cover, ...names].filter(n => n && names.includes(n)))].slice(0, COVERS);
  return [...times.map(t => ({ t })), ...covers.map(cover => ({ cover, w: COVER_W }))];
}

// ---------------------------------------------------------------- the machine
const UNAVAILABLE = 'unavailable';
// What a still's pixels depend on besides the piece: the OS and CPU family, the Chromium build, and the
// system font a piece's "monospace" falls back to (with its package version where dpkg can say).
export async function environment() {
  let chromium;
  try {
    const browser = await launch();
    chromium = browser.version();
    await browser.close();
  } catch (e) {
    chromium = `${UNAVAILABLE} (${firstLine(e.message).slice(0, 80)})`;
  }
  const fc = spawnSync('fc-match', ['-f', '%{family[0]}', 'monospace'], { encoding: 'utf8' });
  const dpkg = spawnSync('dpkg-query', ['-W', '-f=${Version}', 'fonts-dejavu-core'], { encoding: 'utf8' });
  return [`${process.platform}-${process.arch}`, `chromium ${chromium}`,
    `monospace ${fc.status === 0 && fc.stdout.trim() ? fc.stdout.trim() : 'unknown (no fc-match)'}`,
    ...(dpkg.status === 0 && dpkg.stdout.trim() ? [`fonts-dejavu-core ${dpkg.stdout.trim()}`] : [])].join(' | ');
}

// The CPU, which isn't part of "env": Chromium's software rasteriser picks code paths by CPU, so what
// it draws can depend on it. Vendor and vector width where Linux says, else the model.
export function cpu() {
  const model = (os.cpus()[0] || {}).model || 'unknown';
  try {
    const info = fs.readFileSync('/proc/cpuinfo', 'utf8');
    const vendor = (/^vendor_id\s*:\s*(\S+)/m.exec(info) || [])[1] || '?';
    const flags = new Set(((/^flags\s*:(.*)$/m.exec(info) || [])[1] || '').trim().split(/\s+/));
    return `${vendor}/${flags.has('avx512f') ? 'avx512' : flags.has('avx2') ? 'avx2' : 'pre-avx2'} (${model.trim()})`;
  } catch { return model; }
}

// ---------------------------------------------------------------- rendering
const node = process.execPath;
function still(args) {
  try {
    execFileSync(node, [path.join(CANVAS, 'tools', 'still.mjs'), ...args], { cwd: CANVAS, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) {
    throw new RunError(`still.mjs ${args[0]} failed: ${firstLine(String(e.stderr || e.message).trim().split('\n').pop())}`);
  }
}

// Render a piece's stills from `html` with still.mjs (the tool every QA still comes from) into
// out/golden/<id>/, and hash them.
export function renderStills(id, html, song, stills, size) {
  const dir = path.join(STILLS, id);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const times = stills.filter(s => !s.cover), covers = stills.filter(s => s.cover);
  if (times.length) still([id, '--song', song, '--html', html, '--t', times.map(s => s.t.toFixed(3)).join(','), '--w', String(size.w), '--h', String(size.h), '--out', dir]);
  for (const w of [...new Set(covers.map(s => s.w))]) {
    still([id, '--song', song, '--html', html, '--cover', covers.filter(s => s.w === w).map(s => s.cover).join(','), '--size', String(w), '--out', dir]);
  }
  return stills.map(s => {
    const f = path.join(dir, stillName(id, s));
    if (!fs.existsSync(f)) throw new RunError(`${id}: still.mjs wrote no ${path.basename(f)}`);
    return { ...s, sha256: pixelHash(fs.readFileSync(f)), file: f };
  });
}

// ---------------------------------------------------------------- the command
const SPEC = {
  usage: 'node tools/golden.mjs --check [piece...] [--strict]  |  --update [piece...] [--force]',
  positional: [0, Infinity],
  flags: {
    check: { type: 'bool', help: 'render each frozen piece\'s stills and compare them with test/golden/<piece>.sha256' },
    update: { type: 'bool', help: 'render them and rewrite the files (the golden-update job does this on CI)' },
    strict: { type: 'bool', help: '--check: a machine other than the one the files were recorded on fails instead of skipping (CI)' },
    force: { type: 'bool', help: '--update: write hashes anywhere but Linux too (they only match the machine that made them)' },
    dir: { type: 'string', arg: 'folder', help: 'the golden files\' folder (default canvas/test/golden)' },
  },
};

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await main(async () => {
    const A = parseArgs(process.argv.slice(2), SPEC);
    if (A.help) { console.log(helpText(SPEC)); return; }
    if (!!A.check === !!A.update) throw new UsageError(`give --check or --update (usage: ${SPEC.usage})`);
    if (process.env.KALEIDOPHONE_PIECES) throw new UsageError(`golden frames are this repository's frozen pieces, but KALEIDOPHONE_PIECES points the tools at ${PIECES}: unset it`);
    if (A.strict && !A.check) throw new UsageError('--strict is for --check');
    if (A.force && !A.update) throw new UsageError('--force is for --update');
    const dir = A.dir ? path.resolve(A.dir) : GOLDEN;
    const frozen = frozenPieces();
    for (const id of A._) {
      if (!listPieces().includes(id)) throw new UsageError(`no piece "${id}" (frozen pieces: ${frozen.join(', ')})`);
      if (!frozen.includes(id)) throw new UsageError(`${id} is a template: it is versioned, not frozen, and has no golden frames`);
    }
    const ids = A._.length ? A._ : frozen;
    const fileOf = id => path.join(dir, `${id}.sha256`);
    const shown = f => (path.relative(process.cwd(), f).startsWith('..') ? f : path.relative(process.cwd(), f));
    // golden frames of a piece that is gone, or a template now: --check refuses them, --update (all) removes them
    const stray = !A._.length && fs.existsSync(dir)
      ? fs.readdirSync(dir).filter(f => f.endsWith('.sha256')).map(f => f.slice(0, -7)).filter(id => !frozen.includes(id)) : [];
    if (A.check && stray.length) throw new RunError(`${shown(dir)} has golden frames for ${stray.join(', ')}, which ${stray.length > 1 ? 'are' : 'is'} not a frozen piece here: remove ${stray.length > 1 ? 'them' : 'it'} or put the piece back`);
    const env = await environment();
    console.log(`on ${env} | cpu ${cpu()}`);
    const chromium = env.split(' | ')[1];
    if ((A.update || A.strict) && chromium.startsWith(`chromium ${UNAVAILABLE}`)) {
      throw new RunError(`Chromium didn't start, so no frame can be drawn: ${chromium.slice(9)}. Install it (\`npx playwright-core install chromium\` in canvas/) or set KALEIDOPHONE_CHROMIUM`);
    }
    if (A.update && process.platform !== 'linux' && !A.force) {
      throw new UsageError(`golden frames are recorded on Linux CI (this is ${env.split(' | ')[0]}): run the golden-update job (Actions -> CI -> Run workflow, golden_update) and commit what it uploads. --force writes hashes that only this machine will match`);
    }
    const work = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-golden-'));
    onCleanup(() => fs.rmSync(work, { recursive: true, force: true }));
    const problems = [];
    let skipped = 0;
    for (const id of ids) {
      const T = Date.now();
      const old = fs.existsSync(fileOf(id)) ? parseGolden(id, fs.readFileSync(fileOf(id), 'utf8'), shown(fileOf(id))) : null;
      if (A.check && !old) {
        problems.push(`${id}: no golden frames (${shown(fileOf(id))}) -- a frozen piece needs them: run the golden-update job and commit what it uploads`);
        continue;
      }
      const page = releasePage(id, path.join(work, `${id}.html`));
      const song = synthFor(id);
      const spec = loadPiece(id).spec;
      const size = old ? old.size : { w: +((spec.render || {}).w || 1080), h: +((spec.render || {}).h || 1920) };
      if (A.update) {
        const stills = renderStills(id, page.file, song, old ? old.stills : defaultStills(id, spec, loadSong(song)), size);
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(fileOf(id), formatGolden({ id, html: page.sha256, env, size, stills }));
        console.log(`${id}: ${stills.length} stills -> ${shown(fileOf(id))}  (${((Date.now() - T) / 1000).toFixed(1)} s)`);
        continue;
      }
      if (page.sha256 !== old.html) {
        problems.push(`${id}: its page is no longer the one its golden frames were drawn from (sha256 ${page.sha256.slice(0, 12)}…, the frames: ${old.html.slice(0, 12)}…) -- ` +
          'a frozen piece\'s build changed; test/contract.test.mjs says how');
        continue;
      }
      if (old.env !== env) {
        if (A.strict) {
          problems.push(`${id}: its golden frames were recorded on "${old.env}", and this is "${env}". If nothing else changed, the CI image did: ` +
            'run the golden-update job and review what it uploads');
        } else {
          console.log(`${id}: page ok (sha256 ${page.sha256.slice(0, 12)}…); frames not compared: they were recorded on "${old.env}", this is "${env}" (CI compares them)`);
          skipped++;
        }
        continue;
      }
      const got = renderStills(id, page.file, song, old.stills, old.size);
      let differ = 0;
      got.forEach((s, i) => {
        if (s.sha256 === old.stills[i].sha256) return;
        differ++;
        problems.push(`${id}: ${stillName(id, s)} draws different pixels (sha256 ${s.sha256.slice(0, 12)}…, golden ${old.stills[i].sha256.slice(0, 12)}…) -- ${shown(s.file)}`);
      });
      console.log(`${id}: ${differ ? `${differ} of ${got.length} stills differ` : `${got.length} stills match`}  (${((Date.now() - T) / 1000).toFixed(1)} s)`);
    }
    if (A.update) {
      for (const id of stray) { fs.rmSync(fileOf(id)); console.log(`${id}: no longer a frozen piece -- removed ${shown(fileOf(id))}`); }
    }
    if (problems.length) {
      // the CPU isn't part of "env" (it would fail runs whose pixels match), but Skia picks its code paths by
      // CPU: name it, so a mismatch on a runner of another kind can be told from a change to a piece
      throw new RunError(`golden frames: ${problems.length} problem${problems.length > 1 ? 's' : ''}\n  ${problems.join('\n  ')}\n` +
        `This run: ${env} | cpu ${cpu()}.\n` +
        'A frozen piece must draw exactly what it shipped drawing. If the change is meant (a new CI image, a measured fix), regenerate with the golden-update job and say why in the PR.');
    }
    if (A.check) {
      const compared = ids.length - skipped;
      console.log(`golden frames: ${ids.length} page${ids.length > 1 ? 's' : ''} as shipped; ${compared ? `frames of ${compared} compared, all match` : 'no frames compared here'}` +
        `${skipped ? ` (${skipped} recorded on another machine: CI compares them)` : ''}`);
    }
  });
}
