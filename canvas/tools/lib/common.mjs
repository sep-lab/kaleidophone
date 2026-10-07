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
// KALEIDOPHONE_PIECES: another folder of pieces instead of canvas/pieces -- how the tests render
// throwaway fixture pieces without writing into the repository
export const PIECES = process.env.KALEIDOPHONE_PIECES ? path.resolve(process.env.KALEIDOPHONE_PIECES) : path.join(CANVAS, 'pieces');
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

// Cleanups run on success, on failure and on Ctrl-C: temp builds, the render's private work folder, Chromium, ffmpeg.
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
// spec = { usage: 'one line', positional: [min, max], flags: { name: { type, help, choices, arg, repeat } } }
// types: string | number | int | bool | numbers | ints | list | json | optional (a value, or bare = true)
// repeat: the flag may be given more than once; its values collect into one array, in order
// (`--variant a=x --variant b=y` is `--variant a=x,b=y`)
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
    const v = typed(key, val, f);
    out[key] = f.repeat ? [...(out[key] || []), ...(Array.isArray(v) ? v : [v])] : v;
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
    return [`--${k}${arg ? ' ' + arg : ''}`, (f.help || '') + (f.repeat ? ' (repeatable)' : '')];
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

// ---------------------------------------------------------------- variants
// piece.json "variants": {"<axis>": {"at": 14, "options": ["a", "b"], "default": "a", "note": "..."}}.
// An axis is one choice the piece can make -- how it ends, say. Every option is drawn from `at`
// (song seconds) on; before it, every option draws the same frames, so one render of the body
// serves every ending (render.mjs --endings). The page gets the choice as p.variant =
// {<axis>: "<option>", ...} in __frame(p), every axis in it; live mode reads ?variant=<axis>:<option>.
export const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SLUG_IS = 'lowercase letters, digits and single hyphens';
const axisRef = axis => SLUG.test(axis) ? `variants.${axis}` : `variants[${JSON.stringify(axis)}]`;

// The piece's "variants", checked; null when it declares none. A problem throws an Error whose
// message is one line naming the piece and the axis (build.mjs reports it as a build error).
export function checkVariants(id, spec) {
  if (!spec || !Object.hasOwn(spec, 'variants')) return null;
  const V = spec.variants;
  const bad = (what, msg) => new Error(`${id}: piece.json ${what}: ${msg}`);
  if (!V || typeof V !== 'object' || Array.isArray(V)) {
    throw bad('"variants"', 'must be an object of axes, e.g. {"ending": {"at": 14, "options": ["a", "b"], "default": "a"}}');
  }
  const axes = Object.keys(V);
  if (!axes.length) throw bad('"variants"', 'declares no axes (remove it, or declare one)');
  const dur = spec.grid && Number.isFinite(spec.grid.dur) ? spec.grid.dur : null;
  for (const axis of axes) {
    const a = V[axis], where = axisRef(axis);
    if (!SLUG.test(axis)) throw bad(where, `an axis name must be a slug (${SLUG_IS}): it names files, <out>.<axis>-<option>.mp4`);
    if (!a || typeof a !== 'object' || Array.isArray(a)) throw bad(where, 'must be an object with "at", "options" and "default"');
    const { options, at } = a;
    if (!Array.isArray(options) || !options.length) throw bad(where, '"options" must be a non-empty list of option names');
    for (const o of options) {
      if (typeof o !== 'string' || !SLUG.test(o)) throw bad(where, `option ${JSON.stringify(o)} must be a slug (${SLUG_IS}): it names a file, <out>.${axis}-<option>.mp4`);
    }
    const twice = options.find((o, i) => options.indexOf(o) !== i);
    if (twice) throw bad(where, `option "${twice}" is listed twice`);
    if (!Object.hasOwn(a, 'default')) throw bad(where, `has no "default" (one of ${options.join(', ')})`);
    if (!options.includes(a.default)) throw bad(where, `"default" must be one of its options (${options.join(', ')}), got ${JSON.stringify(a.default)}`);
    if (typeof at !== 'number' || !Number.isFinite(at)) throw bad(where, `"at" must be a number of song seconds, got ${JSON.stringify(at)}`);
    if (at < 0 || (dur !== null && at > dur)) throw bad(where, `"at" ${at} is outside the song (0 to ${dur ?? '...'} s${dur !== null ? ', grid.dur' : ''})`);
    if (a.note !== undefined && typeof a.note !== 'string') throw bad(where, '"note" must be a string');
  }
  return V;
}

// checkVariants for the render and still tools: a piece.json that can't be right stops the run.
export function pieceVariants(piece) {
  try { return checkVariants(piece.id, piece.spec); } catch (e) { throw new RunError(e.message); }
}

// --variant axis=option,... -> { choice: every axis -> its option (the default unless given),
// given: only the axes asked for }. choice is null for a piece without variants.
export function resolveVariant(id, variants, asked = []) {
  if (!variants) {
    if (asked.length) throw new UsageError(`${id} declares no variants in piece.json: there is nothing for --variant to choose`);
    return { choice: null, given: {} };
  }
  const axes = Object.keys(variants), given = {};
  const eg = `${axes[0]}=${variants[axes[0]].options.at(-1)}`;
  for (const item of asked) {
    const m = /^([^=]*)=([^=]*)$/.exec(String(item));
    if (!m || !m[1] || !m[2]) throw new UsageError(`--variant takes axis=option, e.g. --variant ${eg} (got "${item}")`);
    const [, axis, option] = m;
    if (!Object.hasOwn(variants, axis)) throw new UsageError(`${id} has no variant axis "${axis}" (axes: ${axes.join(', ')})`);
    const options = variants[axis].options;
    if (!options.includes(option)) throw new UsageError(`${id}: "${option}" is not an option of ${axis} (options: ${options.join(', ')})`);
    if (Object.hasOwn(given, axis) && given[axis] !== option) throw new UsageError(`--variant gives ${axis} twice (${given[axis]}, ${option}): pick one`);
    given[axis] = option;
  }
  return { choice: Object.fromEntries(axes.map(a => [a, Object.hasOwn(given, a) ? given[a] : variants[a].default])), given };
}

// "ending-lamp", "ending-lamp.palette-dark": the axes asked for, in the piece's order, as file names use them
export function variantTag(variants, given) {
  return variants ? Object.keys(variants).filter(a => Object.hasOwn(given, a)).map(a => `${a}-${given[a]}`).join('.') : '';
}

// A driver's frame with the choice on it. The harness adds p.variant itself, so it reaches the page
// through any driver whose draw() passes p on (the default one does), whatever its frame() returns.
export function withVariant(p, variant) {
  return variant && p && typeof p === 'object' ? { ...p, variant } : p;
}

// The window frame a variant starts on: the first frame at or after `at` (frame i is song time
// t0 + i / fps). Before it, the frames are the body's.
export function joinFrame(at, { t0, fps }) {
  return Math.ceil((at - t0) * fps - 1e-6);
}

// Window frames [from, to) as separate encodes: cut at every join strictly inside (the encoder
// starts again there, so the frames on each side are exactly a body's and an ending's), then each
// stretch split among the workers as planParts splits it. With no join inside, this is planParts.
export function planEncodes(from, to, workers, keys = [], joins = []) {
  const cuts = [...new Set(joins)].filter(j => j > from && j < to).sort((a, b) => a - b);
  const bounds = [from, ...cuts, to], out = [];
  for (let s = 0; s + 1 < bounds.length; s++) {
    for (const p of planParts(bounds[s], bounds[s + 1], workers, keys)) out.push({ ...p, k: out.length });
  }
  return out;
}

// The whole render, planned before anything starts: the files (parts) and the page runs that draw them.
//   no --endings  one file, window frames [from, to), cut at every join inside it
//   --endings X   a body, frames [0, J) with X's default, and one ending per option of X, frames
//                 [J, N): J is X's join frame. Other axes keep the given choice, cut at their joins.
// Runs: a stateless piece draws each encode on a page of its own, `workers` at a time -- exactly the
// frames it encodes, as a whole-window render's pages do; a stateful one draws each part on one page,
// in order, replaying from its warm-up first. `probe` (stateful --endings) marks the frame before the
// join, captured losslessly by the body and by every ending's replay, so the tool can check that each
// ending continues the same body. (A stateless piece's options are checked on pages of their own.)
export function planRender({ id = 'piece', variants = null, choice = null, endings = null, t0 = 0, fps, frames, from = 0, to = frames, workers = 1, stateful = false, keys = [] }) {
  const W = stateful ? 1 : Math.max(1, Math.floor(workers) || 1);
  const axes = variants ? Object.keys(variants) : [];
  const joinOf = axis => ({ axis, at: variants[axis].at, frame: joinFrame(variants[axis].at, { t0, fps }) });
  const part = (name, role, a, b, variant, joins, extra = {}) => {
    const inside = joins.filter(j => j.frame > a && j.frame < b);
    return {
      name, role, ...extra, from: a, to: b, frames: b - a, variant,
      joins: inside.map(j => ({ ...j, file_frame: j.frame - a })),
      keys: keys.filter(k => k >= a && k < b),
      encodes: planEncodes(a, b, W, keys, inside.map(j => j.frame)),
    };
  };
  let parts, join = null;
  if (!endings) {
    parts = [part(null, 'window', from, to, choice, axes.map(joinOf))];
  } else {
    if (!variants) throw new UsageError(`${id} declares no variants in piece.json: there are no endings to render`);
    if (!Object.hasOwn(variants, endings)) throw new UsageError(`${id} has no variant axis "${endings}" (axes: ${axes.join(', ')})`);
    const spec = variants[endings], J = joinFrame(spec.at, { t0, fps });
    const s = n => +(t0 + n / fps).toFixed(6);
    if (!(J > 0 && J < frames)) {
      throw new UsageError(`--endings ${endings}: ${endings} starts at ${spec.at} s, outside this window (song time ${s(0)} to ${s(frames)} s): ` +
        (spec.at <= 0 ? `an axis that changes the whole piece has no body -- render each option with --variant ${endings}=<option>`
          : `give a window that starts before ${spec.at} s and ends after it`));
    }
    join = { axis: endings, at: spec.at, frame: J, song_t: s(J) };
    const others = axes.filter(a => a !== endings).map(joinOf);
    parts = [
      part('body', 'body', 0, J, { ...choice, [endings]: spec.default }, others),
      ...spec.options.map(o => part(`${endings}-${o}`, 'ending', J, frames, { ...choice, [endings]: o }, others,
        { axis: endings, option: o, default: o === spec.default })),
    ];
  }
  const runs = [];
  parts.forEach((p, i) => {
    const encodes = stateful ? [p.encodes.map(e => e.k)] : p.encodes.map(e => [e.k]);
    for (const ks of encodes) {
      const a = p.encodes[ks[0]].a, b = p.encodes[ks.at(-1)].b;
      const probe = join && stateful && ((p.role === 'body' && b === join.frame) || (p.role === 'ending' && a === join.frame)) ? join.frame - 1 : null;
      runs.push({ part: i, a, b, encodes: ks, probe });
    }
  });
  return { join, parts, runs };
}

// ---------------------------------------------------------------- joining by stream copy
// What two files must share for the concat demuxer to join them with -c copy: `kaleidophone
// deliver` stream-copies a body and an ending into one film, so every part of an --endings render
// is probed and must agree on all of these (the extradata is the H.264 SPS/PPS every frame decodes with).
export const JOIN_PARAMS = ['codec_name', 'codec_tag_string', 'profile', 'level', 'pix_fmt', 'width', 'height',
  'sample_aspect_ratio', 'r_frame_rate', 'time_base', 'has_b_frames', 'refs', 'field_order', 'chroma_location',
  'color_range', 'color_space', 'color_transfer', 'color_primaries', 'bits_per_raw_sample', 'extradata_hash'];

export function requireFfprobe() {
  const r = spawnSync('ffprobe', ['-hide_banner', '-version'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) {
    throw new RunError(`ffprobe is not on PATH${r.error ? ` (${r.error.code || r.error.message})` : ''} -- --endings checks every file it writes with it. ` +
      'It comes with ffmpeg (macOS: brew install ffmpeg; Debian/Ubuntu: sudo apt-get install ffmpeg).');
  }
}

// the concat demuxer's list: one quoted file per line
export function concatList(files) {
  return files.map(p => `file '${String(p).replace(/'/g, "'\\''")}'`).join('\n') + '\n';
}

function ffprobeJson(args, what) {
  const r = spawnSync('ffprobe', ['-v', 'error', ...args, '-of', 'json'], { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  if (r.error || r.status !== 0) {
    throw new RunError(`ffprobe could not read ${what}: ${firstLine((r.stderr || '').trim().split('\n').pop() || (r.error && r.error.message))}`);
  }
  try { return JSON.parse(r.stdout); } catch { throw new RunError(`ffprobe's answer about ${what} is not JSON`); }
}

// One file's video stream: the parameters a join needs, and its packets' pts and key flags (in file order).
export function probeVideo(file) {
  const j = ffprobeJson(['-select_streams', 'v:0', '-show_entries', 'stream:packet=pts,flags', '-show_data_hash', 'sha256', file], path.basename(file));
  const s = (j.streams || [])[0];
  if (!s) throw new RunError(`${path.basename(file)} has no video stream`);
  return { params: Object.fromEntries(JOIN_PARAMS.map(k => [k, s[k] ?? null])), packets: (j.packets || []).map(p => ({ pts: +p.pts, key: /^K/.test(p.flags || '') })) };
}

// The packets of `files` joined in order by the concat demuxer, as `-c copy` writes them (nothing is written).
export function probeConcat(files, listFile) {
  fs.writeFileSync(listFile, concatList(files));
  const j = ffprobeJson(['-f', 'concat', '-safe', '0', '-i', listFile, '-select_streams', 'v:0', '-show_entries', 'stream=time_base:packet=pts,flags'], `${files.map(f => path.basename(f)).join(' + ')} joined`);
  const s = (j.streams || [])[0] || {};
  return { time_base: s.time_base || null, packets: (j.packets || []).map(p => ({ pts: +p.pts, key: /^K/.test(p.flags || '') })) };
}

// The first parameter two probed files disagree on, or null: [name, a, b].
export function streamDifference(a, b) {
  for (const k of JOIN_PARAMS) if ((a[k] ?? null) !== (b[k] ?? null)) return [k, a[k] ?? null, b[k] ?? null];
  return null;
}

// Problems with a timeline of packets (in presentation order once sorted): `frames` of them, the
// first at pts 0 and each one frame after the last -- no gap, no repeat -- and keyframes at `keys`
// (frame numbers). [] when there are none.
export function timelineProblems(packets, { frames, fps, timeBase, keys = [] }) {
  const out = [];
  const [num, den] = String(timeBase).split('/').map(Number);
  const step = den / (num * fps), exact = Math.abs(step - Math.round(step)) < 1e-9;
  const pts = packets.map(p => p.pts).sort((x, y) => x - y);
  if (pts.length !== frames) out.push(`${pts.length} frames, expected ${frames}`);
  if (pts.length && pts[0] !== 0) out.push(`the first frame is at pts ${pts[0]}, not 0`);
  for (let i = 1; i < pts.length; i++) {
    const d = pts[i] - pts[i - 1];
    if (exact ? d !== Math.round(step) : Math.abs(d - step) > 1) {
      out.push(`${d > step ? 'a gap' : d === 0 ? 'a repeated timestamp' : 'frames too close'} between frames ${i - 1} and ${i} (pts ${pts[i - 1]} -> ${pts[i]}, one frame is ${+step.toFixed(3)})`);
      break;
    }
  }
  const keyPts = new Set(packets.filter(p => p.key).map(p => p.pts));
  for (const k of keys) if (!keyPts.has(pts[k])) out.push(`frame ${k} is not a keyframe`);
  return out;
}

// The --endings manifest, <out>.variants.json: what was rendered, what joins to what, and the
// stream every file shares -- what `kaleidophone deliver` reads (a cut's `endings:`). File names
// only, never paths: the files sit next to it. t0, at and silent_start are song seconds; `at` is the
// join on the frame grid, t0 + join.frame / fps (piece.json's own value, if it was between two
// frames, is join.declared_at).
export function variantsManifest({ piece, song, synthetic, axis, t0, dur, fps, size, plan, files, stream, joined, encode, tools }) {
  const spec = axis.spec, J = plan.join.frame;
  const body = plan.parts.find(p => p.role === 'body'), endings = plan.parts.filter(p => p.role === 'ending');
  const N = endings[0].to;
  const r6 = x => +x.toFixed(6);
  const entry = p => ({ file: files[p.name].file, sidecar: files[p.name].sidecar, frames: p.frames, variant: p.variant });
  return {
    kaleidophone: 'canvas-variants/1',
    piece,
    axis: axis.name,
    // the window: its first frame's song time (snapped, for a stateful piece), its length, its rate
    t0: r6(t0),
    dur,
    fps,
    // where the body ends and every ending begins
    at: r6(t0 + J / fps),
    options: spec.options,
    default: spec.default,
    note: spec.note ?? null,
    song,
    synthetic_song: !!synthetic,
    // the song time of the body's first frame: silent_start for the joined film
    silent_start: r6(t0),
    size,
    // the ending's first frame: J frames into the joined film (t on its clock)
    join: { frame: J, t: r6(J / fps), declared_at: spec.at },
    frames: { window: N, body: J, ending: N - J },
    body: entry(body),
    endings: endings.map(p => ({ option: p.option, default: !!p.default, ...entry(p), joined: joined[p.name] })),
    stream,
    encode,
    tools,
  };
}

// ---------------------------------------------------------------- the browser
export function chromiumPath() {
  // Explicit override first; then the cloud sandbox's preinstalled Chromium (never run
  // `playwright install` there); otherwise let playwright-core find its own download.
  if (process.env.KALEIDOPHONE_CHROMIUM) return process.env.KALEIDOPHONE_CHROMIUM;
  for (const p of ['/opt/pw-browsers/chromium']) if (fs.existsSync(p)) return p;
  return undefined;
}

// KALEIDOPHONE_CHROMIUM_ARGS: more Chromium switches for every browser the tools start, space-separated.
// tools/golden.mjs sets --disable-skia-runtime-opts through it, so its stills don't depend on the CPU.
export function chromiumArgs(extra = []) {
  return [...extra, ...(process.env.KALEIDOPHONE_CHROMIUM_ARGS || '').split(/\s+/).filter(Boolean)];
}

export async function launch(extraArgs = []) {
  const { chromium } = await import('playwright-core');
  const executablePath = chromiumPath();
  try {
    return await chromium.launch({
      executablePath,
      // main() handles Ctrl-C / SIGTERM: it closes the browser itself once the run's files are
      // cleaned up (Playwright's own handlers would exit first and leave the work folder behind)
      handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
      // no proxy, and no host resolves: a piece is one self-contained file, and a render must never
      // reach the network (openPiece also aborts, and fails the run on, any request that isn't
      // file:/data:/blob:)
      args: ['--allow-file-access-from-files', '--disable-gpu', '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND', ...chromiumArgs(extraArgs)],
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
  // p.variant (a piece with "variants") arrives here from the harness: a driver of its own that
  // replaces draw() must pass it on to the page
  async draw(page, p) { return await page.evaluate(q => window.__frame(q), p); },
  async cover(page, name, arg, pack) {
    // default cover = one frame at arg.t, with the flags in arg
    const t = +(arg && arg.t) || 0;
    await page.evaluate(q => window.__frame(q), { ...this.frame(t, pack, { flags: arg || {} }), t });
  },
};
