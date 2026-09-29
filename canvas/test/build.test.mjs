import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { buildPiece, BuildError, reservedNames, reservedText, LIB_ORDER } from '../tools/build.mjs';
import { synthFor } from '../tools/synth.mjs';
import { CANVAS } from './helpers.mjs';

const pieces = fs.readdirSync(path.join(CANVAS, 'pieces')).filter(d => fs.existsSync(path.join(CANVAS, 'pieces', d, 'piece.json')));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-build-'));

const scripts = html => [...html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m => ({ attrs: m[1] || '', js: m[2] }));

// Anything that would make a built piece reach the network. XML namespace names are identifiers
// that happen to look like URLs (createElementNS), and the font credits quote their projects'
// URLs in a comment; neither is ever requested.
const NETWORK = [
  [/\bfetch\s*\(/, 'fetch('], [/\bXMLHttpRequest\b/, 'XMLHttpRequest'], [/\bWebSocket\b/, 'WebSocket'],
  [/\bEventSource\b/, 'EventSource'], [/\bsendBeacon\b/, 'sendBeacon'], [/\bimportScripts\b/, 'importScripts'],
  [/@import\b/i, '@import'], [/url\(\s*['"]?\s*(?:https?:)?\/\//i, 'url(http'], [/\/\/cdn\b/i, '//cdn'],
  [/\b(?:src|href|srcset|poster|action|data)\s*=\s*['"]?\s*(?:https?:)?\/\//i, 'src/href=http'],
  [/\bimport\s*\(\s*['"`](?:https?:)?\/\//i, 'import(http'],
];
const XML_NAMESPACES = ['http://www.w3.org/2000/svg', 'http://www.w3.org/1999/xlink', 'http://www.w3.org/1999/xhtml',
  'http://www.w3.org/1998/Math/MathML', 'http://www.w3.org/XML/1998/namespace', 'http://www.w3.org/2000/xmlns/'];
const FONT_CREDIT = /\/\*! font: [^*]*\*\//g;

for (const id of pieces) {
  test(`${id}: builds into one self-contained HTML file`, () => {
    const out = buildPiece(id, { song: synthFor(id), out: path.join(tmp, `${id}.html`), quiet: true });
    const html = fs.readFileSync(out, 'utf8');
    assert.ok(html.startsWith('<!'), 'a whole document');
    assert.ok(!html.includes('/*__JS__*/') && !html.includes('/*__FONTS__*/'), 'every placeholder filled');
    // nothing is fetched at runtime: no scripts, stylesheets or fonts from the network
    assert.ok(!/<script[^>]+src=/i.test(html), 'no external scripts');
    assert.ok(!/<link[^>]+href=/i.test(html), 'no external stylesheets');
    assert.ok(!/url\(\s*['"]?https?:/i.test(html), 'no remote fonts or images');
    // and nothing personal: no home-directory paths
    assert.ok(!/\/Users\/[^/\s<]+\/|\/home\/[^/\s<]+\//.test(html), 'no absolute home paths');
    const spec = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'piece.json'), 'utf8'));
    for (const f of spec.fonts || []) assert.ok(html.includes(`font-family:'${f.family}';font-weight:${f.weight};src:url(data:font/woff2;base64,`), `${f.family} ${f.weight} inlined`);
    for (const name of Object.keys(spec.bake || {})) assert.ok(html.includes(`const ${name} = `), `${name} baked`);
  });

  test(`${id}: its script compiles as one script, the way Chromium will parse it`, () => {
    const html = fs.readFileSync(buildPiece(id, { song: synthFor(id), out: path.join(tmp, `${id}.vm.html`), quiet: true }), 'utf8');
    const S = scripts(html);
    assert.ok(S.length >= 1, 'an inline script');
    for (const [i, s] of S.entries()) assert.doesNotThrow(() => new vm.Script(s.js, { filename: `${id}.html <script> #${i + 1}` }));
  });

  test(`${id}: nothing in it can reach the network`, () => {
    const html = fs.readFileSync(buildPiece(id, { song: synthFor(id), out: path.join(tmp, `${id}.net.html`), quiet: true }), 'utf8');
    for (const [re, what] of NETWORK) assert.ok(!re.test(html), `${what}: ${(html.match(re) || [])[0]}`);
    const urls = html.replace(FONT_CREDIT, '').match(/\bhttps?:\/\/[^\s'"`<>)\\]+/gi) || [];
    const stray = urls.filter(u => !XML_NAMESPACES.some(ns => u.startsWith(ns)));
    assert.deepEqual(stray, [], 'no URL outside the font credits but XML namespace names');
  });

  test(`${id}: every inlined font carries its credit`, () => {
    const spec = JSON.parse(fs.readFileSync(path.join(CANVAS, 'pieces', id, 'piece.json'), 'utf8'));
    const html = fs.readFileSync(buildPiece(id, { song: synthFor(id), out: path.join(tmp, `${id}.fonts.html`), quiet: true }), 'utf8');
    const credits = html.match(FONT_CREDIT) || [];
    assert.equal(credits.length, (spec.fonts || []).length);
    for (const f of spec.fonts || []) {
      const c = credits.find(x => x.startsWith(`/*! font: ${f.family} ${f.weight} | `));
      assert.ok(c, `${f.family} ${f.weight} credited`);
      assert.match(c, /\| (OFL-1\.1|Apache-2\.0) \| Copyright /, c);
    }
  });
}

test('a lib the piece asks for is inlined ahead of its own modules', () => {
  const out = buildPiece('template', { song: synthFor('template'), out: path.join(tmp, 'template.html'), quiet: true });
  const html = fs.readFileSync(out, 'utf8');
  const order = ['// ---- lib/core.js', '// ---- lib/live.js', '// ---- lib/ink.js', '// ---- lib/rig.js', '// ---- main.js'].map(m => html.indexOf(m));
  assert.ok(order.every(i => i > 0), 'all modules present');
  assert.deepEqual([...order].sort((a, b) => a - b), order, 'in order');
});

// ---------------------------------------------------------------- the one-scope rules
// A piece folder outside pieces/, for the cases that must fail.
function fixture(name, lib, main) {
  const dir = path.join(tmp, 'fixtures', name);
  fs.mkdirSync(path.join(dir, 'src'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'piece.json'), JSON.stringify({ title: name, template: 'template.html', src: 'src', lib }));
  fs.writeFileSync(path.join(dir, 'template.html'), '<!doctype html>\n<html><body><canvas id="c"></canvas>\n<script>\n/*__JS__*/\n</script></body></html>\n');
  fs.writeFileSync(path.join(dir, 'src', 'main.js'), main);
  return dir;
}
const build = (name, lib, main) => buildPiece(name, { dir: fixture(name, lib, main), out: path.join(tmp, `${name}.html`), quiet: true });
const fails = re => err => err instanceof BuildError && re.test(err.message);

test('the fixture itself builds: the lib in order, names of its own', () => {
  assert.doesNotThrow(() => build('fine', ['core', 'live', 'ink'], 'const G = makeGrid({ bpm: 120 });\nconst mySeed = 42;\n'));
});

test('a copy of the template that declares `const seed` fails the build, naming the lib file that owns it', () => {
  assert.throws(() => build('seed', ['core', 'live', 'ink'], 'const G = makeGrid({ bpm: 120 });\nconst seed = 42;\n'),
    fails(/main\.js:2 declares "seed", which lib\/ink\.js:\d+ \(let seed = .*\) already declares .*Identifier 'seed' has already been declared.*--reserved/));
});

test('a piece function with a lib function\'s name fails the build: it would replace the lib\'s silently', () => {
  assert.throws(() => build('override', ['core', 'live', 'ink'], 'function stroke(p) { return p; }\nvar rect = 1;\nfunction mine() {}\n'),
    fails(/"stroke" \(main\.js:1; lib\/ink\.js\), "rect" \(main\.js:2; lib\/ink\.js\)/));
});

test('the lib loads in dependency order, or the build says which comes first', () => {
  assert.throws(() => build('order', ['ink', 'core', 'live'], 'const a = 1;\n'),
    fails(/"lib" is \["ink","core","live"\]: core must come before ink \(ink\.js needs core\.js, live\.js\)/));
  assert.throws(() => build('order2', ['core', 'recursion', 'live'], 'const a = 1;\n'), fails(/live must come before recursion/));
  assert.throws(() => build('order3', ['core', 'live', 'viewfinder', 'ink'], 'const a = 1;\n'), fails(/ink must come before viewfinder -- the lib loads in the order core -> live -> ink/));
  assert.throws(() => build('missing', ['core', 'ink'], 'const a = 1;\n'), fails(/has ink without live -- ink\.js needs core\.js, live\.js/));
  assert.throws(() => build('twice', ['core', 'core'], 'const a = 1;\n'), fails(/lists core twice/));
  assert.throws(() => build('nolib', ['core', 'nope'], 'const a = 1;\n'), fails(/canvas\/lib\/nope\.js does not exist/));
  assert.deepEqual(LIB_ORDER, ['core', 'live', 'ink', 'rig', 'recursion', 'viewfinder']);
});

test('a syntax error is reported in the piece\'s own file and line', () => {
  assert.throws(() => build('syntax', ['core'], 'const a = 1;\nconst b = ;\n'), fails(/syntax: main\.js:2: Unexpected token/));
});

test('--reserved: each lib file\'s top-level names, no name declared by two files', () => {
  const R = reservedNames();
  assert.deepEqual(Object.keys(R).slice(0, LIB_ORDER.length), LIB_ORDER.map(n => `${n}.js`));
  for (const [f, names] of [['core.js', ['TAU', 'clamp', 'makeGrid']], ['live.js', ['ctx', 'W', 'H', 'S', 'Q']], ['ink.js', ['seed', 'stroke', 'rect', 'C', 'J']]]) {
    for (const n of names) assert.ok(R[f].includes(n), `${f} declares ${n}`);
  }
  assert.ok(!R['core.js'].includes('boot') && !R['core.js'].includes('i'), 'only top-level declarations');
  const all = Object.values(R).flat();
  assert.equal(new Set(all).size, all.length, 'two lib files declare the same name: the later one silently replaces the other');
});

test('canvas/README.md lists the reserved names exactly as `node tools/build.mjs --reserved` prints them', () => {
  const readme = fs.readFileSync(path.join(CANVAS, 'README.md'), 'utf8');
  const m = /<!-- reserved names[^\n]*-->\n```text\n([\s\S]*?)```/.exec(readme);
  assert.ok(m, 'the README has the generated block under "Reserved names"');
  assert.equal(m[1].trim(), reservedText(),
    'canvas/README.md\'s reserved names are out of date: paste the output of `node tools/build.mjs --reserved` into the block under "Reserved names"');
});
