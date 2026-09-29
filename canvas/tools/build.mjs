#!/usr/bin/env node
// build.mjs -- assemble a piece into ONE self-contained HTML file.
//
//   node tools/build.mjs <piece-id> [--song pack.json] [--out file.html]
//   node tools/build.mjs --all            (bakes each piece's synthetic twin: tools/synth.mjs)
//   node tools/build.mjs --reserved       the lib's top-level names, per file: a piece must not declare them
//
// A piece is written as small modules (pieces/<id>/src/*.js, concatenated in name order) plus
// a template.html. The build inlines the modules, base64-inlines the fonts (from npm packages,
// pinned in package.json -- no font binaries live in git) with a credit comment each, and bakes
// in whatever the piece's piece.json lists under "bake" from a song pack (e.g. vocal onsets that
// the live mode needs).
//
// Everything lands in ONE <script>, so the lib's top-level names and the piece's share a scope.
// The build compiles the assembled script (node's V8 is the browser's parser) and refuses what
// Chromium would refuse later -- a name declared twice, a lib loaded before what it needs -- or
// would silently get wrong: a piece function that replaces a lib function of the same name.
//
// The output has no external requests at all: open it from disk, click, or drop the track on it.
// Nothing here is a bundler and nothing needs to be: vanilla JS in one <script>, on purpose.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { pathToFileURL } from 'node:url';
import { DIST, CANVAS, RunError, UsageError, main, parseArgs, helpText, loadPiece, listPieces, loadSong } from './lib/common.mjs';
import { songPath, synthFor } from './synth.mjs';

export class BuildError extends RunError {
  constructor(msg) { super(msg); this.name = 'BuildError'; }
}

// ---------------------------------------------------------------- the lib: order and names
// The order the lib loads in, and what each file needs loaded before it. A file's top level runs
// when the script loads, so a lib listed ahead of its dependency dies on the spot ("Cannot access
// 'TAU' before initialization"). A lib file not listed here declares its needs in its header:
// "Needs: core.js, live.js".
export const LIB_DEPS = {
  core: [],
  live: ['core'],
  ink: ['core', 'live'],
  rig: ['core', 'live', 'ink'],
  recursion: ['core', 'live'],
  viewfinder: ['core'],
};
export const LIB_ORDER = Object.keys(LIB_DEPS);
const LIB_DIR = path.join(CANVAS, 'lib');

function libNeeds(name, src) {
  const m = /Needs:([^\n]*)/.exec(src || '');
  const declared = m ? [...m[1].matchAll(/([\w-]+)\.js/g)].map(x => x[1]) : [];
  return [...new Set([...(LIB_DEPS[name] || []), ...declared])].filter(n => n !== name);
}

export function checkLibOrder(id, list, sources = {}) {
  const order = LIB_ORDER.join(' -> ');
  const seen = [];
  for (const name of list) {
    if (seen.includes(name)) throw new BuildError(`${id}: piece.json "lib" lists ${name} twice`);
    const needs = libNeeds(name, sources[name]);
    for (const need of needs) {
      if (seen.includes(need)) continue;
      throw new BuildError(list.includes(need)
        ? `${id}: piece.json "lib" is ${JSON.stringify(list)}: ${need} must come before ${name} (${name}.js needs ${needs.map(n => n + '.js').join(', ')}) -- the lib loads in the order ${order}`
        : `${id}: piece.json "lib" has ${name} without ${need} -- ${name}.js needs ${needs.map(n => n + '.js').join(', ')} listed before it (the lib loads in the order ${order})`);
    }
    const oi = LIB_ORDER.indexOf(name);
    const later = seen.find(p => oi >= 0 && LIB_ORDER.indexOf(p) > oi);
    if (later) throw new BuildError(`${id}: piece.json "lib" is ${JSON.stringify(list)}: ${name} must come before ${later} -- the lib loads in the order ${order}`);
    seen.push(name);
  }
  return list;
}

// Which top-level names does a script declare? V8 answers exactly: appending `let a, b, c;` to a
// script fails with "Identifier 'x' has already been declared" for the first of them the script
// already declares (const, let, var, function or class alike). Drop that one and ask again.
const KEYWORDS = new Set(('break case catch class const continue debugger default delete do else enum export extends false ' +
  'finally for function if import in instanceof new null return super switch this throw true try typeof var void while ' +
  'with yield let static implements interface package private protected public await eval arguments').split(' '));
const NAMES = new Map();

export function declaredAmong(code, candidates) {
  const found = [];
  let rest = [...new Set(candidates)].filter(w => !KEYWORDS.has(w));
  while (rest.length) {
    try {
      new vm.Script(`${code}\n;let ${rest.join(', ')};`);
      break;
    } catch (e) {
      const m = /Identifier '([^']+)' has already been declared/.exec(e.message);
      if (!m || !rest.includes(m[1])) break; // the code itself doesn't compile on its own: nothing to report here
      found.push(m[1]);
      rest = rest.filter(w => w !== m[1]);
    }
  }
  return found;
}

export function topLevelNames(code) {
  if (!NAMES.has(code)) NAMES.set(code, declaredAmong(code, code.match(/[A-Za-z_$][\w$]*/g) || []));
  return NAMES.get(code);
}

function libFiles() {
  const extra = fs.readdirSync(LIB_DIR).filter(f => f.endsWith('.js')).map(f => f.slice(0, -3)).filter(n => !LIB_ORDER.includes(n)).sort();
  return [...LIB_ORDER.filter(n => fs.existsSync(path.join(LIB_DIR, `${n}.js`))), ...extra];
}

// { 'core.js': [names in the order the file declares them], ... } -- what `--reserved` prints and
// the README lists.
export function reservedNames() {
  const out = {};
  for (const n of libFiles()) {
    const src = fs.readFileSync(path.join(LIB_DIR, `${n}.js`), 'utf8');
    const at = name => (declLine(src, name) || { line: Infinity }).line;
    out[`${n}.js`] = topLevelNames(src).map((name, i) => [at(name), i, name]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(x => x[2]);
  }
  return out;
}

export function reservedText() {
  const R = reservedNames();
  const total = new Set(Object.values(R).flat()).size;
  return [`${total} top-level names in canvas/lib, by file (a piece that lists the file in "lib" must not declare them):`,
    ...Object.entries(R).map(([f, names]) => `${f} (${names.length}): ${names.join(' ')}`)].join('\n');
}

// the line a top-level declaration of `name` sits on, if a plain search finds it (for messages only)
function declLine(src, name) {
  const n = name.replace(/\$/g, '\\$');
  const re = new RegExp(`^(?:(?:const|let|var)\\b[^\\n]*?[\\s,{\\[]${n}\\s*(?:[=,;})\\]]|$)|(?:async\\s+)?function\\s*\\*?\\s*${n}\\s*\\(|class\\s+${n}\\b)`);
  const lines = src.split('\n');
  const i = lines.findIndex(l => re.test(l));
  return i < 0 ? null : { line: i + 1, text: lines[i].trim().slice(0, 60) };
}

// Compile the assembled script as Chromium will parse it; on a SyntaxError, say where it is in the
// piece's own files, and for a double declaration, which file declared the name first.
function compileCheck(id, chunks) {
  const js = chunks.map(c => c.code).join('\n');
  let start = 1;
  for (const c of chunks) { c.start = start; start += c.code.split('\n').length; }
  try {
    new vm.Script(js, { filename: `${id}.js` });
    return js;
  } catch (e) {
    if (!(e instanceof SyntaxError)) throw e;
    const line = +((/:(\d+)$/.exec(String(e.stack).split('\n')[0]) || [])[1]) || 0;
    const ci = chunks.findLastIndex(c => c.start <= line);
    const at = ci >= 0 ? chunks[ci] : null;
    const where = at ? `${at.name}:${line - at.start + 1 - at.header}` : `line ${line} of the assembled script`;
    const dup = /Identifier '([^']+)' has already been declared/.exec(e.message);
    const first = dup && chunks.slice(0, Math.max(0, ci)).find(c => declaredAmong(c.src, [dup[1]]).length);
    if (first) {
      const name = dup[1], fl = declLine(first.src, name);
      const reserved = first.lib ? ' The lib\'s top-level names are reserved: rename yours (node tools/build.mjs --reserved lists them).' : '';
      throw new BuildError(`${id}: ${where} declares "${name}", which ${first.name}${fl ? `:${fl.line} (${fl.text})` : ''} already declares -- ` +
        `all of a piece's JS is one <script>, so Chromium would refuse to run it (${e.message}).${reserved}`);
    }
    throw new BuildError(`${id}: ${where}: ${e.message}`);
  }
}

// A piece function or var with a lib function's name compiles, and replaces the lib's for every
// caller -- the lib's own included. Refuse it, naming each clash and the lib file it clashes with.
function overrideCheck(id, libChunks, modChunks) {
  if (!libChunks.length) return;
  const owner = new Map();
  for (const c of libChunks) for (const n of topLevelNames(c.src)) if (!owner.has(n)) owner.set(n, c.name);
  const clashes = [];
  for (const m of modChunks) {
    for (const n of declaredAmong(m.src, [...owner.keys()])) {
      const l = declLine(m.src, n);
      clashes.push(`"${n}" (${m.name}${l ? ':' + l.line : ''}; ${owner.get(n)})`);
    }
  }
  if (clashes.length) {
    throw new BuildError(`${id}: declares ${clashes.length === 1 ? 'a name' : 'names'} the lib already declares at the top level: ${clashes.join(', ')}. ` +
      'In one <script> the later declaration replaces the lib\'s for every caller, the lib\'s own included -- rename yours (node tools/build.mjs --reserved lists every reserved name).');
  }
}

// ---------------------------------------------------------------- fonts
// Each inlined font carries its credit: family, weight, licence, the copyright line from its
// package, and the package itself. OFL-1.1 and Apache-2.0 both ask for the notice to travel with
// the font; the licence texts are published with the gallery.
function readJson(f) { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } }

export function fontCredit(f) {
  const segs = f.file.split('/');
  const pkgName = segs[0].startsWith('@') ? segs.slice(0, 2).join('/') : segs[0];
  const dir = path.join(CANVAS, 'node_modules', pkgName);
  const pj = readJson(path.join(dir, 'package.json')) || {};
  const meta = readJson(path.join(dir, 'metadata.json')); // @fontsource packages
  let license = (meta && meta.license && meta.license.type) || pj.license || 'see the package';
  let copyright = meta && meta.license && meta.license.attribution
    ? meta.license.attribution.split(/\s+\S+\.(?:ttf|otf|woff2?):\s*/)[0].trim() : null;
  let text = '';
  for (const lf of ['OFL.txt', 'LICENSE', 'LICENSE.txt', 'LICENSE.md', 'OFL', 'COPYRIGHT.txt']) {
    if (!fs.existsSync(path.join(dir, lf))) continue;
    text = fs.readFileSync(path.join(dir, lf), 'utf8');
    if (!copyright) copyright = (text.split('\n').find(l => /^\s*Copyright\b/i.test(l)) || '').trim() || null;
    break;
  }
  if (/^OFL$/i.test(license) && /Version 1\.1/.test(text)) license = 'OFL-1.1';
  const credit = [`${f.family} ${f.weight}`, license, copyright || 'copyright: see the package', `${pj.name || pkgName} ${pj.version || ''}`.trim()];
  return `/*! font: ${credit.join(' | ').replace(/\*\//g, '* /')} */`;
}

// ---------------------------------------------------------------- the build
function get(obj, dotted) { return dotted.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj); }

function readPiece(id, dir) {
  const file = path.join(dir, 'piece.json');
  if (!fs.existsSync(file)) throw new BuildError(`${id}: no piece.json in ${dir}`);
  return { id, dir, spec: JSON.parse(fs.readFileSync(file, 'utf8')) };
}

// buildPiece(id, { song | pack, out, dir, quiet }) -> the file written. Throws BuildError.
//   song   a song pack file to bake from (or pack: the pack itself, already loaded)
//   out    the HTML to write (default dist/<id>.html)
//   dir    build the piece in this folder instead of pieces/<id> (tests)
export function buildPiece(id, { song, pack, out, dir, quiet = false } = {}) {
  const piece = dir ? readPiece(id, dir) : loadPiece(id);
  const s = piece.spec;
  const tplFile = path.join(piece.dir, s.template || 'template.html');
  if (!fs.existsSync(tplFile)) throw new BuildError(`${id}: no template (${path.relative(process.cwd(), tplFile)})`);
  let html = fs.readFileSync(tplFile, 'utf8');

  const srcDir = path.join(piece.dir, s.src || 'src');
  const files = fs.existsSync(srcDir) ? fs.readdirSync(srcDir).filter(f => f.endsWith('.js')).sort() : [];
  if (!files.length) throw new BuildError(`${id}: no modules in ${path.relative(process.cwd(), srcDir)}`);
  // canvas/lib modules the piece asks for go first, in dependency order (core before live before ink...)
  const libList = s.lib || [];
  const libSrc = {};
  for (const name of libList) {
    const f = path.join(LIB_DIR, `${name}.js`);
    if (!fs.existsSync(f)) throw new BuildError(`${id}: piece.json asks for lib "${name}", but canvas/lib/${name}.js does not exist (the lib: ${libFiles().join(', ')})`);
    libSrc[name] = fs.readFileSync(f, 'utf8');
  }
  checkLibOrder(id, libList, libSrc);
  const libs = libList.map(name => ({ name: `lib/${name}.js`, lib: true, header: 1, src: libSrc[name], code: `// ---- lib/${name}.js\n` + libSrc[name] }));
  const mods = files.map(f => {
    const body = fs.readFileSync(path.join(srcDir, f), 'utf8');
    const header = s.moduleHeader || libs.length ? 1 : 0;
    return { name: f, lib: false, header, src: body, code: header ? `// ---- ${f}\n${body}` : body };
  });

  // Values baked in from the song pack: `const NAME = <json>;` lines ahead of the modules.
  const bakes = [];
  const P = pack || (song ? loadSong(song) : null);
  for (const [name, dotted] of Object.entries(s.bake || {})) {
    const v = P ? get(P, dotted) : undefined;
    if (v === undefined) {
      if (P) console.warn(`${id}: song pack has no "${dotted}" -- ${name} is left undefined (the piece falls back)`);
      continue;
    }
    bakes.push({ name: `(baked ${name})`, lib: false, header: 0, src: `const ${name} = ${JSON.stringify(v)};`, code: `const ${name} = ${JSON.stringify(v)};` });
  }
  // = [bakes..., libs..., modules...].join('\n'): byte for byte what the shipped builds were
  const js = compileCheck(id, [...bakes, ...libs, ...mods]);
  overrideCheck(id, libs, mods);

  const fonts = (s.fonts || []).map(f => {
    const file = path.join(CANVAS, 'node_modules', f.file);
    if (!fs.existsSync(file)) throw new BuildError(`font file missing: node_modules/${f.file} -- run \`npm ci\` in canvas/ first`);
    const b64 = fs.readFileSync(file).toString('base64');
    return `${fontCredit(f)}@font-face{font-family:'${f.family}';font-weight:${f.weight};src:url(data:font/woff2;base64,${b64}) format('woff2');}`;
  });

  if (!html.includes('/*__JS__*/')) throw new BuildError(`${tplFile} has no /*__JS__*/ placeholder`);
  // split/join rather than String.replace: the payload may contain "$&"-style sequences.
  html = html.split('/*__JS__*/').join(js);
  html = html.split('/*__FONTS__*/').join(fonts.join(s.fontJoiner ?? ''));

  const dst = out || path.join(DIST, `${id}.html`);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, html);
  if (!quiet) console.log(`built ${path.relative(process.cwd(), dst)}  ${Math.round(html.length / 1024)} KB  (${libs.length ? `lib ${libList.join('+')} + ` : ''}${files.length} modules${bakes.length ? `, baked ${bakes.map(b => b.name.slice(7, -1)).join(', ')}` : ''})`);
  return dst;
}

// ---------------------------------------------------------------- the command
const SPEC = {
  usage: 'node tools/build.mjs <piece>... [--song pack.json] [--out file.html]  |  --all  |  --reserved',
  positional: [0, Infinity],
  flags: {
    all: { type: 'bool', help: 'every piece, each baked with its synthetic twin (tools/synth.mjs)' },
    song: { type: 'string', arg: 'pack.json', help: 'bake from this song pack' },
    out: { type: 'string', arg: 'file.html', help: 'where to write it (one piece only; default dist/<piece>.html)' },
    synthetic: { type: 'bool', help: 'with no --song, bake the piece\'s synthetic twin' },
    reserved: { type: 'bool', help: 'print the lib\'s top-level names, per file: a piece that uses the lib must not declare them' },
  },
};

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await main(async () => {
    const A = parseArgs(process.argv.slice(2), SPEC);
    if (A.help) { console.log(helpText(SPEC)); return; }
    if (A.reserved) { console.log(reservedText()); return; }
    if (A.all && A._.length) throw new UsageError('give piece ids or --all, not both');
    const ids = A.all ? listPieces() : A._;
    if (!ids.length) throw new UsageError(`usage: ${SPEC.usage}`);
    if (A.out && ids.length > 1) throw new UsageError('--out names one file: build one piece with it');
    for (const id of ids) {
      let song = A.song;
      if (!song && (A.synthetic || A.all)) {
        // no song given: bake from the piece's synthetic twin (generated on demand, never committed)
        song = fs.existsSync(songPath(id)) ? songPath(id) : synthFor(id);
      }
      buildPiece(id, { song, out: A.out });
    }
  });
}
