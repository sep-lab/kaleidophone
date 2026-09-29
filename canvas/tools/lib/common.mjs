// Shared plumbing for the canvas tools: arguments, errors, pieces, song packs, the browser, the ffmpeg sink.
//
// Nothing in here knows what any particular piece draws. A piece is a folder under
// canvas/pieces/<id>/ with a piece.json (what to build) and a driver.mjs (how the harness
// talks to it); see canvas/README.md, "The piece contract".
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const CANVAS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const PIECES = path.join(CANVAS, 'pieces');
export const DIST = path.join(CANVAS, 'dist');
// where render.mjs and still.mjs build the piece they are about to open (never dist/: see buildForRun)
export const BUILD = path.join(CANVAS, 'out', 'build');

// ---------------------------------------------------------------- errors and exit codes
// Two kinds of failure, two exit codes. 2: the command asked for something that can't be done
// (an unknown flag, a frame range outside the window) -- one line, before anything starts.
// 1: something went wrong while running (Chromium, ffmpeg, the piece threw, a build check).
export class UsageError extends Error {
  constructor(msg) { super(msg); this.name = 'UsageError'; this.exitCode = 2; }
}
export class RunError extends Error {
  constructor(msg) { super(msg); this.name = 'RunError'; this.exitCode = 1; }
}

export function die(msg, code = 1) {
  console.error(`kaleidophone-canvas: ${msg}`);
  process.exit(code);
}

export const firstLine = s => String(s ?? '').split('\n').find(l => l.trim()) || String(s ?? '');

// Cleanups run on success, on failure and on Ctrl-C: temp builds, _parts/, Chromium, ffmpeg.
const CLEANUPS = [];
export function onCleanup(fn) { CLEANUPS.push(fn); return fn; }
async function runCleanups() {
  while (CLEANUPS.length) {
    const fn = CLEANUPS.pop();
    try { await fn(); } catch { /* best effort: the run's own error is the one to report */ }
  }
}

// Run a tool's body: a UsageError/RunError prints one line and exits 2/1; anything else is a
// bug in the tools and keeps its stack. Cleanups run either way, then the process exits (so a
// stray Chromium or ffmpeg handle can't keep it alive).
export async function main(fn) {
  let code = 0, stopping = false;
  const interrupted = async () => {
    if (stopping) return;
    stopping = true;
    console.error('kaleidophone-canvas: interrupted -- cleaning up');
    await Promise.race([runCleanups(), new Promise(r => setTimeout(r, 10000))]);
    process.exit(130);
  };
  process.once('SIGINT', interrupted);
  process.once('SIGTERM', interrupted);
  try {
    await fn();
  } catch (e) {
    // an interrupt makes the work fail (its browser and ffmpeg are being shut): that's not news
    if (stopping) return new Promise(() => { /* the signal handler exits */ });
    code = (e && e.exitCode) || 1;
    console.error(`kaleidophone-canvas: ${e && e.exitCode ? e.message : (e && e.stack) || e}`);
  }
  if (stopping) return new Promise(() => { /* the signal handler exits */ });
  await runCleanups();
  process.exit(code);
}

// ---------------------------------------------------------------- arguments
// parseArgs()                       -> { _: [positional...], flag: value|true } -- permissive: any
//                                      flag, values are strings (the gallery and synth use this)
// parseArgs(argv, spec) / (spec)   -> strict: only the flags the tool declares, typed, else a
//                                      UsageError naming the valid ones.
// Both accept --flag value, --flag=value and a bare --flag (true).
//
// spec = { usage: 'one line', positional: [min, max], flags: { name: { type, help, choices, arg } } }
// types: string | number | int | bool | numbers | ints | list | json | optional (a value, or bare = true)
export function parseArgs(argv = process.argv.slice(2), spec) {
  if (argv && !Array.isArray(argv)) { spec = argv; argv = process.argv.slice(2); }
  const out = { _: [] };
  const flags = spec && spec.flags ? { help: { type: 'bool', help: 'print this help' }, ...spec.flags } : null;
  for (let i = 0; i < argv.length; i++) {
    const a = String(argv[i]);
    if (a === '--') { out._.push(...argv.slice(i + 1).map(String)); break; }
    if (!a.startsWith('--')) {
      if (flags && a === '-h') { out.help = true; continue; }
      if (flags && /^-[^\d.]/.test(a)) throw new UsageError(`unknown option ${a}. ${validFlags(flags)}`);
      out._.push(a);
      continue;
    }
    const eq = a.indexOf('=');
    const key = eq > 2 ? a.slice(2, eq) : a.slice(2);
    let val = eq > 2 ? a.slice(eq + 1) : undefined;
    if (!flags) { // permissive: exactly the old behaviour, plus --key=value
      if (val !== undefined) out[key] = val;
      else {
        const next = argv[i + 1];
        if (next === undefined || String(next).startsWith('--')) out[key] = true;
        else { out[key] = String(next); i++; }
      }
      continue;
    }
    const f = Object.hasOwn(flags, key) ? flags[key] : null;
    if (!f) throw new UsageError(`unknown flag --${key}${suggest(key, Object.keys(flags))}. ${validFlags(flags)}`);
    const type = f.type || 'string';
    if (type === 'bool') {
      if (val === undefined && /^(true|false)$/.test(argv[i + 1] ?? '')) val = argv[++i];
      if (val === undefined || /^(true|1|yes)$/i.test(val)) out[key] = true;
      else if (/^(false|0|no)$/i.test(val)) out[key] = false;
      else throw new UsageError(`--${key} is a switch: give it alone, or =true / =false (got "${val}")`);
      continue;
    }
    if (val === undefined) {
      const next = argv[i + 1];
      if (next !== undefined && !String(next).startsWith('--')) { val = String(next); i++; }
      else if (type === 'optional') { out[key] = true; continue; }
      else throw new UsageError(`--${key} needs a value${f.arg ? ` (${f.arg})` : ''}`);
    }
    out[key] = typed(key, val, f);
  }
  if (flags && spec.positional && !out.help) {
    const [min, max] = spec.positional;
    if (out._.length < min) throw new UsageError(`usage: ${spec.usage}`);
    if (out._.length > max) throw new UsageError(`unexpected argument${out._.length - max > 1 ? 's' : ''} ${out._.slice(max).map(x => `"${x}"`).join(' ')} (usage: ${spec.usage})`);
  }
  return out;
}

function typed(key, val, f) {
  const type = f.type || 'string';
  const bad = what => new UsageError(`--${key} expects ${what}, got "${val}"`);
  const num = (s, int) => {
    const t = String(s).trim();
    const n = t === '' ? NaN : Number(t);
    if (!Number.isFinite(n) || (int && !Number.isInteger(n))) throw bad(int ? 'a whole number' : 'a number');
    return n;
  };
  const list = () => {
    const parts = String(val).split(',').map(s => s.trim());
    if (!parts.length || parts.some(s => s === '')) throw bad('a comma-separated list with no empty items');
    return parts;
  };
  if (val === '') throw new UsageError(`--${key} needs a value${f.arg ? ` (${f.arg})` : ''}`);
  let v;
  switch (type) {
    case 'string': case 'optional': v = val; break;
    case 'number': v = num(val, false); break;
    case 'int': v = num(val, true); break;
    case 'numbers': v = list().map(s => num(s, false)); break;
    case 'ints': v = list().map(s => num(s, true)); break;
    case 'list': v = list(); break;
    case 'json':
      try { v = JSON.parse(val); } catch (e) { throw new UsageError(`--${key} is not valid JSON (${e.message})`); }
      break;
    default: throw new Error(`parseArgs: unknown type "${type}" for --${key}`);
  }
  if (f.choices && !(Array.isArray(v) ? v : [v]).every(x => f.choices.includes(x))) {
    throw new UsageError(`--${key} must be one of ${f.choices.join(', ')} (got "${val}")`);
  }
  return v;
}

function validFlags(flags) { return `Valid flags: ${Object.keys(flags).map(k => '--' + k).join(' ')}`; }

function suggest(key, names) {
  let best = null, bestD = Infinity;
  for (const n of names) {
    const d = n.startsWith(key) || key.startsWith(n) ? Math.abs(n.length - key.length) * 0.5 : editDistance(key, n);
    if (d < bestD) { best = n; bestD = d; }
  }
  return best && bestD <= Math.max(1, Math.floor(key.length / 3)) ? ` (did you mean --${best}?)` : '';
}

function editDistance(a, b) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

export function helpText(spec) {
  const flags = { ...spec.flags, help: { type: 'bool', help: 'print this help' } };
  const rows = Object.entries(flags).map(([k, f]) => {
    const t = f.type || 'string';
    const arg = f.arg || (t === 'bool' ? '' : t === 'optional' ? '[value]' : t === 'numbers' || t === 'ints' || t === 'list' ? 'a,b,...' : t === 'json' ? '{...}' : t === 'number' || t === 'int' ? 'n' : 'value');
    return [`--${k}${arg ? ' ' + arg : ''}`, f.help || ''];
  });
  const w = Math.max(...rows.map(r => r[0].length));
  return `usage: ${spec.usage}\n\n` + rows.map(([a, h]) => `  ${a.padEnd(w)}  ${h}`).join('\n') + '\n\nFlags take --flag value or --flag=value.';
}

// ---------------------------------------------------------------- pieces
export function listPieces() {
  return fs.readdirSync(PIECES).filter(d => fs.existsSync(path.join(PIECES, d, 'piece.json'))).sort();
}

export function loadPiece(id) {
  const dir = path.join(PIECES, id);
  const file = path.join(dir, 'piece.json');
  if (!fs.existsSync(file)) die(`no piece "${id}" (expected ${path.relative(process.cwd(), file)}). Pieces: ${listPieces().join(', ')}`, 2);
  let spec;
  try { spec = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { die(`${path.relative(process.cwd(), file)} is not valid JSON (${firstLine(e.message)})`); }
  return { id, dir, spec };
}

export async function loadDriver(piece) {
  const p = path.join(piece.dir, 'driver.mjs');
  const mod = fs.existsSync(p) ? await import(pathToFileURL(p).href) : {};
  return { ...DEFAULT_DRIVER, ...(mod.default || {}) };
}

export function toolVersion() {
  return JSON.parse(fs.readFileSync(path.join(CANVAS, 'package.json'), 'utf8')).version;
}

// ---------------------------------------------------------------- song packs
// A song pack is the analysed song, as JSON: 100 Hz envelope arrays (bass, mid, rms, ...),
// the grid (bpm, first downbeat, duration), beats, and any piece-specific events.
// Real song packs are private (they are derived from unreleased audio) -- the repository
// only ever holds synthetic ones, generated by tools/synth.mjs. See docs/decisions/0007.
export function loadSong(file) {
  if (!file || file === true) die('no song pack given (--song path/to/songpack.json). For a synthetic one: node tools/synth.mjs <piece>', 2);
  if (!fs.existsSync(file)) die(`song pack not found: ${file}`, 2);
  let pack;
  try { pack = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { die(`song pack ${path.basename(file)} is not valid JSON (${firstLine(e.message)})`, 2); }
  if (!pack || typeof pack !== 'object' || Array.isArray(pack)) die(`song pack ${path.basename(file)} is not a song pack (expected a JSON object)`, 2);
  pack.fps = pack.fps || pack.sr || pack.sr_env || 100;
  if (!(pack.fps > 0)) die(`song pack ${path.basename(file)} has no usable frame rate (fps ${pack.fps})`, 2);
  return pack;
}

// Linear interpolation between 100 Hz frames, i = floor(t*fps). Inside the song this is exactly
// what the SAME AS YOU / ( - ) harnesses did -- the released films were verified against it, so
// that expression stays bit-for-bit. Outside the song it holds the first / last frame: it used
// to carry the edge slope on, to values far outside 0..1 a few minutes past the end.
export function sampleLinear(pack, keys, t) {
  const o = {};
  for (const k of keys) {
    const a = pack[k];
    if (!a || !a.length) { o[k] = 0; continue; }
    const n = a.length;
    const x = t * pack.fps;
    if (x < 0 || n < 2) { o[k] = a[0]; continue; }
    if (x > n - 1) { o[k] = a[n - 1]; continue; }
    const i = Math.max(0, Math.min(n - 2, Math.floor(t * pack.fps)));
    const f = t * pack.fps - i;
    o[k] = a[i] + (a[i + 1] - a[i]) * f;
  }
  return o;
}

// ---------------------------------------------------------------- windows, workers, keyframes
// Split window frames [from, to) into contiguous parts, one per worker -- never more workers
// than frames. Forced keyframes are window frame numbers; each part's ffmpeg counts from 0.
export function planParts(from, to, workers, keys = []) {
  const n = to - from;
  if (!(Number.isInteger(from) && Number.isInteger(to) && n >= 1)) throw new RangeError(`planParts: empty or invalid range [${from}, ${to})`);
  const W = Math.max(1, Math.min(Math.floor(workers) || 1, n));
  const parts = [];
  for (let k = 0; k < W; k++) {
    const a = from + Math.floor(k * n / W), b = from + Math.floor((k + 1) * n / W);
    parts.push({ k, a, b, keys: keys.filter(kf => kf >= a && kf < b).map(kf => kf - a) });
  }
  return parts;
}

// --key-times: song seconds -> window frame numbers. A time must sit on this window's frame grid
// (within 0.01 frame, as `kaleidophone deliver` checks its cut times) and inside the window.
export function keyTimesToFrames(times, { t0, fps, frames, tolerance = 0.01 }) {
  return times.map(s => {
    const x = (s - t0) * fps, k = Math.round(x);
    const at = n => (t0 + n / fps).toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
    if (k < 0 || k >= frames) {
      throw new UsageError(`--key-times ${s} is outside this render (song time ${at(0)} to ${at(frames)} s; key times are song time, not the render's clock)`);
    }
    if (Math.abs(x - k) > tolerance) {
      throw new UsageError(`--key-times ${s} isn't on the ${fps} fps frame grid of a render from t0 ${at(0)} (nearest frames: ${at(Math.floor(x))} / ${at(Math.ceil(x))} s)`);
    }
    return k;
  });
}

// ---------------------------------------------------------------- the browser
export function chromiumPath() {
  // Explicit override first; then the cloud sandbox's preinstalled Chromium (never run
  // `playwright install` there); otherwise let playwright-core find its own download.
  if (process.env.KALEIDOPHONE_CHROMIUM) return process.env.KALEIDOPHONE_CHROMIUM;
  for (const p of ['/opt/pw-browsers/chromium']) if (fs.existsSync(p)) return p;
  return undefined;
}

export async function launch(extraArgs = []) {
  const { chromium } = await import('playwright-core');
  const executablePath = chromiumPath();
  try {
    return await chromium.launch({
      executablePath,
      // main() handles Ctrl-C / SIGTERM: it closes the browser itself once the run's files are
      // cleaned up (Playwright's own handlers would exit first and leave _parts/ behind)
      handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
      // no proxy, and no host resolves: a piece is one self-contained file, and a render must never
      // reach the network (openPiece also aborts, and fails the run on, any request that isn't
      // file:/data:/blob:)
      args: ['--allow-file-access-from-files', '--disable-gpu', '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND', ...extraArgs],
    });
  } catch (e) {
    throw new RunError(`could not start Chromium (${firstLine(e.message)}). ` +
      'Set KALEIDOPHONE_CHROMIUM to a Chromium/Chrome binary, or run `npx playwright-core install chromium` once.');
  }
}

// A file name with "?" in it must go through pathToFileURL, or the "?" starts the query string
// (learned the hard way on a piece whose title ends in one).
export function pieceUrl(htmlFile, query) {
  const u = pathToFileURL(path.resolve(htmlFile));
  return u.href + '?' + new URLSearchParams(query).toString();
}

const LOCAL_URL = /^(file|data|blob|about):/i;
const PAGE = new WeakMap();

// Open a built piece in render or cover mode and wait until it says it's ready. Every page error,
// failed request and request that isn't file:/data:/blob: is recorded; unless allowPageErrors,
// the first one fails the run (assertPageOk) -- during loading it fails at once, instead of
// timing out 30 s later on a __ready that a script which never parsed can't set.
export async function openPiece(browser, htmlFile, query, viewport, { allowPageErrors = false } = {}) {
  const page = await browser.newPage({ viewport: viewport || { width: 1080, height: 1920 } });
  const tr = { errors: [], allow: allowPageErrors, onError: null };
  PAGE.set(page, tr);
  const add = msg => {
    tr.errors.push(msg);
    if (tr.allow) console.error(`kaleidophone-canvas: warning: ${msg} (continuing: --allow-page-errors)`);
    else if (tr.onError) tr.onError(msg);
  };
  page.on('pageerror', e => add(`page error: ${firstLine(e.message)}`));
  page.on('console', m => { if (m.type() === 'error') console.error('CONSOLE', m.text()); });
  page.on('request', r => { if (!LOCAL_URL.test(r.url())) add(`network request to ${r.url()} (a piece must not reach the network)`); });
  page.on('requestfailed', r => { if (LOCAL_URL.test(r.url())) add(`request failed: ${r.url()} (${(r.failure() || {}).errorText || 'failed'})`); });
  page.on('crash', () => add('the page crashed (out of memory?)'));
  // blocked even with --allow-page-errors: carrying on never means reaching the network
  await page.route(u => !LOCAL_URL.test(u.href), r => r.abort('blockedbyclient'));
  const failed = new Promise((_, reject) => {
    tr.onError = msg => reject(new RunError(`${path.basename(htmlFile)}: ${msg} (--allow-page-errors to render anyway)`));
  });
  failed.catch(() => { /* raced below; later errors are checked by assertPageOk */ });
  try {
    await Promise.race([page.goto(pieceUrl(htmlFile, query)), failed]);
    // __ready is either `true` or a promise (the paranoia piece awaits its fonts). A piece's cover
    // mode may define only __cover, which loads its own fonts -- then its presence is readiness.
    await Promise.race([page.waitForFunction(() => window.__ready === true || (window.__ready && typeof window.__ready.then === 'function')
      || (window.__ready === undefined && typeof window.__cover === 'function'), null, { timeout: 30000 }), failed]);
    await Promise.race([page.evaluate(() => window.__ready), failed]);
  } catch (e) {
    if (e instanceof RunError) throw e;
    throw new RunError(`${path.basename(htmlFile)} did not get ready: ${firstLine(e.message)}`);
  } finally {
    tr.onError = null;
  }
  assertPageOk(page);
  return page;
}

// Throws on the first page error recorded since the page opened (unless they are allowed).
export function assertPageOk(page, where = '') {
  const tr = PAGE.get(page);
  if (!tr || tr.allow || !tr.errors.length) return;
  throw new RunError(`${where ? where + ': ' : ''}${tr.errors[0]}${tr.errors.length > 1 ? ` (and ${tr.errors.length - 1} more)` : ''} (--allow-page-errors to render anyway)`);
}

// The HTML a render or still opens: built right now from the piece's source with the song pack
// being rendered, into out/build/, and removed when the run ends. Never dist/<piece>.html: the
// gallery and `build --all` overwrite that with the synthetic twin baked in, and a real render
// that picked it up would run with the wrong song's events. --html overrides (golden-frame checks).
export async function buildForRun(piece, song, override) {
  if (override) {
    const f = path.resolve(override);
    if (!fs.existsSync(f) || !fs.statSync(f).isFile()) throw new UsageError(`--html: no such file: ${override}`);
    return { file: f, built: false };
  }
  const { buildPiece } = await import('../build.mjs');
  fs.mkdirSync(BUILD, { recursive: true });
  const file = path.join(BUILD, `${piece.id}.${process.pid}.${Date.now().toString(36)}.html`);
  onCleanup(() => fs.rmSync(file, { force: true }));
  buildPiece(piece.id, { song, out: file, quiet: true });
  return { file, built: true };
}

// Kept for older callers: the dist/ build of a piece, or an explicit file. The render and still
// tools no longer open dist/ (buildForRun above says why).
export function builtHtml(piece, override) {
  const f = override || path.join(DIST, `${piece.id}.html`);
  if (!fs.existsSync(f)) die(`${path.relative(process.cwd(), f)} is not built yet -- run: node tools/build.mjs ${piece.id}`);
  return f;
}

// ---------------------------------------------------------------- ffmpeg
// Fails before anything else starts (Chromium, a build) if there is no ffmpeg; returns its version.
export function requireFfmpeg() {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-version'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) {
    throw new RunError(`ffmpeg is not on PATH${r.error ? ` (${r.error.code || r.error.message})` : ''} -- the render pipes its frames into it. ` +
      'Install it (macOS: brew install ffmpeg; Debian/Ubuntu: sudo apt-get install ffmpeg) and run again.');
  }
  return (/ffmpeg version (\S+)/.exec(r.stdout) || [])[1] || 'unknown';
}

export function ffmpegSink(out, { fps, crf = '18', tune = 'animation', preset = 'medium', keyframes = [] }) {
  // JPEG frames in (toDataURL('image/jpeg') captures 1.7-3.8x faster than PNG at 1080x1920, measured),
  // H.264 out. Keyframes can be forced at planned cut points so the cuts are later made with
  // -c:v copy on the device -- lossless and frame-exact (docs/TECHNIQUES.md, "forced keyframes").
  const fk = keyframes.length ? ['-force_key_frames', 'expr:' + keyframes.map(n => `eq(n,${n})`).join('+')] : [];
  const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(fps), '-i', '-',
    '-c:v', 'libx264', '-preset', preset, '-tune', tune, '-crf', String(crf), '-pix_fmt', 'yuv420p', '-r', String(fps), ...fk,
    '-movflags', '+faststart', out], { stdio: ['pipe', 'ignore', 'pipe'] });
  let stderr = '', failure = null;
  ff.stderr.on('data', d => { stderr = (stderr + d).slice(-4000); });
  const closed = new Promise((resolve, reject) => {
    ff.on('error', e => reject(new RunError(`could not run ffmpeg (${e.code || e.message})`)));
    ff.on('close', (code, signal) => code === 0 ? resolve() : reject(new RunError(
      `ffmpeg ${signal ? `was stopped (${signal})` : `exited ${code}`} writing ${path.basename(out)}${stderr.trim() ? `: ${firstLine(stderr.trim().split('\n').pop())}` : ''}`)));
  });
  closed.catch(e => { failure = e; });
  ff.stdin.on('error', () => { /* EPIPE when ffmpeg has died: reported through `closed` */ });
  return {
    async write(buf) {
      if (failure) throw failure;
      if (!ff.stdin.write(buf)) await Promise.race([new Promise(r => ff.stdin.once('drain', r)), closed]);
    },
    async end() { ff.stdin.end(); await closed; },
    kill() { if (ff.exitCode === null && ff.signalCode === null) ff.kill('SIGKILL'); },
  };
}

export function dataUrlToBuffer(d) { return Buffer.from(d.slice(d.indexOf(',') + 1), 'base64'); }

// ---------------------------------------------------------------- the default driver
// Stateless pieces that take the envelope per frame: __frame({ t, ...env(t), ...flags }).
export const DEFAULT_DRIVER = {
  stateful: false,              // true -> frames are drawn in order, in one worker, replayed from the warm-up
  canvasSelector: 'canvas',
  keys: ['bass', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent'],
  query({ w, h }) { return { render: 1, w, h }; },
  async init(/* page, pack, opts */) { },
  frame(t, pack, opts) { return { t, ...sampleLinear(pack, this.keys, t), ...(opts.flags || {}) }; },
  async draw(page, p) { return await page.evaluate(q => window.__frame(q), p); },
  async cover(page, name, arg, pack) {
    // default cover = one frame at arg.t, with the flags in arg
    const t = +(arg && arg.t) || 0;
    await page.evaluate(q => window.__frame(q), { ...this.frame(t, pack, { flags: arg || {} }), t });
  },
};
