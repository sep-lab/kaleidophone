// The frozen-piece contract: every shipped piece builds, from its synthetic twin, into exactly the page
// its release shipped, byte for byte, as the gallery and the release zip ship it (titled "TITLE — artist":
// tools/build.mjs retitle). The artist site vendors those pages by sha256 and refuses drift, so lib work,
// a build change or a font bump that moves one byte of a frozen page breaks a published contract; this
// fails first. Golden frames (tools/golden.mjs) hold what the pages draw; this holds the pages and what
// they are built from. The template is versioned, not frozen: it grows with the lib.
//
// A frozen page changes only for a real bug, fixed with a measured before/after (AGENTS.md): then its new
// sha256 goes in FROZEN with the release that ships it, and the PR says why.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { CANVAS } from './helpers.mjs';

// The contract is about this repository's pieces: KALEIDOPHONE_PIECES (private pieces) must not stand in
// for them, and the tools read it when they load.
delete process.env.KALEIDOPHONE_PIECES;
const { releasePage, frozenPieces, parseGolden, GOLDEN, FRAMES, COVERS } = await import('../tools/golden.mjs');
const { synthesize } = await import('../tools/synth.mjs');

const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-contract-'));
const RELEASE_ZIP = 'gh release download v0.4.0 -R sep-lab/kaleidophone -p \'kaleidophone-pieces-0.4.0.zip\'';

// Each frozen piece's page as its release shipped it: the size and sha256 of <piece>.html in
// kaleidophone-pieces-<release>.zip on that GitHub release (the same bytes the artist site vendors).
const FROZEN = {
  'hamechi-manzor-dare': { release: '0.4.0', bytes: 241040, sha256: 'b60aa672468aed4529fd2c91480083b4f8dd52431e6edcc8fd5df5aaa65d723b' },
  minus: { release: '0.4.0', bytes: 49008, sha256: 'f707602f55c60c07b091f08e3db473ed85f510f01fefe57872b59059cb143b94' },
  'same-as-you': { release: '0.4.0', bytes: 116311, sha256: 'af5900ac1527b2e4262bc73f5d97978a813394cb4d7b71668313f80a6d194faf' },
  'should-i': { release: '0.4.0', bytes: 245036, sha256: '65a8204150efd1a4584730681c289c3aa2fa9ced39343fe58c28a48b1ef1a727' },
  // ---- W1 (v0.5.0): Setareh (lane L3) and STORM (lane L4) land frozen, and each adds its line HERE, the
  // page after the scrub, built from its twin and retitled:
  //   node -e "import('./tools/golden.mjs').then(g => console.log(g.releasePage('<id>', '/tmp/<id>.html')))"
  //   '<id>': { release: '0.5.0', bytes: <bytes>, sha256: '<sha256>' },
  // and, in the same PR: its twin in TWINS below, "libVersion": "0.4.0" in its piece.json (the lib it was
  // built with), and its golden frames (the golden-update job: canvas/README.md, "Frozen pieces").
  storm: { release: '0.5.0', bytes: 185542, sha256: '7670b46d13167eda7036fe3a44c6c6c0ffe93b4e1a5f679d93b75abeb397013a' },
  // ---- end of the W1 additions
};

// Each frozen piece's twin: its synthetic.json as committed, and the pack tools/synth.mjs makes from it
// (as JSON, the way synthFor writes it). The pages bake from the pack (SHOULD I ?'s stutter windows) and
// every golden frame is drawn from it, so a generator change that moves a twin moves what they all see.
const TWINS = {
  'hamechi-manzor-dare': { spec: '076fc84c0cedbdabc205f9f4bb776a608fc1f28ce90991533fb3ce959430c352', pack: '06c2e4f33a314328026c26290b8af2c62ced272a2af8eead377a5a5e0c44ea44' },
  minus: { spec: '7aa0ca89b97fde1b0e4bd3394f9c742acb4290f769e1fb3a555bb97083e0c655', pack: 'c0c393e42634089802a115ae957b537dcfa8ba2ad71181089000d92cf13041dc' },
  'same-as-you': { spec: '9a58e241d90893b346a383097a265822c3ab57e10ea9dd69b68578a81a5d9d2c', pack: '24029df7e0b21ef6ebc8919738545442cdf5a8b65d170796a1bed333e562d843' },
  'should-i': { spec: '6f131dca27b81f13d90e988ba59835b15d9c337aca966de72933f3a0203edb07', pack: 'c573da10cc4ed0f16cc4dd2c2da3b687a2f2eb0efc54bd285733b97b95b4a7bd' },
  // ---- W1: Setareh's (L3) and STORM's (L4) twins go here, in the same form
  storm: { spec: '6c848fe22ac0523ba41cb2da8e2ab7f3785c5d2699615c5ff8b8a7b2212a56c9', pack: '5084e08150bc3fd38acab86f548e92be5785ae77babc78629a2b937de091071a' },
};

// The pinned lib (tools/build.mjs, "the lib pin"): byte copies of the lib as a release had it. A version
// folder is written once and never edited; a piece that pins it builds as that release built it.
const PINNED = {
  '0.4.0': {
    'core.js': 'c24b06d7f537cdd8d5a1a0d4c7c45f917ea2e5db113bc9138ad43a0ea48cd145',
    'live.js': '8a688afcd811b4848f76f3f713b1c6b6ee8971998c75258365976e1ca874a3bc',
  },
};

for (const [id, want] of Object.entries(FROZEN)) {
  test(`${id}: builds into the page v${want.release} shipped, byte for byte`, () => {
    const got = releasePage(id, path.join(tmp, `${id}.html`));
    assert.ok(got.bytes === want.bytes && got.sha256 === want.sha256,
      `${id} now builds into ${got.bytes} B (sha256 ${got.sha256}); v${want.release} shipped ${want.bytes} B (sha256 ${want.sha256}). ` +
      'Something moved a frozen page: its src/, template.html or piece.json ("lib", "libVersion", "fonts", "bake"), a font package, ' +
      `tools/build.mjs, or its twin. Compare: ${RELEASE_ZIP}, then diff its ${id}.html against ${got.file}`);
  });
}

test('every piece is frozen, with its page\'s sha256 above, or a template', () => {
  const frozen = frozenPieces();
  const missing = frozen.filter(id => !FROZEN[id]), gone = Object.keys(FROZEN).filter(id => !frozen.includes(id));
  assert.deepEqual(missing, [], `${missing.join(', ')}: a shipped piece is frozen, so it needs its page's sha256 in FROZEN (the marked spot in this file) -- or, if it is a template, "gallery": {"role": "template"}`);
  assert.deepEqual(gone, [], `${gone.join(', ')}: frozen here, but no longer a piece (or now a template) in canvas/pieces`);
});

for (const [id, want] of Object.entries(TWINS)) {
  test(`${id}: its twin is unchanged, as committed and as tools/synth.mjs makes it`, () => {
    const raw = fs.readFileSync(path.join(CANVAS, 'pieces', id, 'synthetic.json'));
    assert.equal(sha256(raw), want.spec, `pieces/${id}/synthetic.json changed: a frozen piece's twin is what its page bakes and its golden frames are drawn from`);
    assert.equal(sha256(JSON.stringify(synthesize(JSON.parse(raw)))), want.pack,
      `the pack tools/synth.mjs makes from ${id}'s twin changed: a generator change must leave every frozen twin as it was (add what's new behind a key their specs don't set)`);
  });
}

test('every frozen piece has a twin pinned above', () => {
  assert.deepEqual(Object.keys(FROZEN).filter(id => !TWINS[id]), [], 'add the twin\'s two hashes to TWINS');
});

for (const id of Object.keys(FROZEN)) {
  test(`${id}: its golden frames were drawn from this page, ${FRAMES} frames and ${COVERS} covers`, () => {
    const file = path.join(GOLDEN, `${id}.sha256`);
    assert.ok(fs.existsSync(file), `no test/golden/${id}.sha256: run the golden-update job (Actions -> CI -> Run workflow, golden_update) and commit what it uploads`);
    const g = parseGolden(id, fs.readFileSync(file, 'utf8'));
    assert.equal(g.html, FROZEN[id].sha256, `test/golden/${id}.sha256 was drawn from another page than the one ${id} ships: regenerate it with the golden-update job`);
    assert.equal(g.stills.filter(s => !s.cover).length, FRAMES, 'frames');
    assert.equal(g.stills.filter(s => s.cover).length, COVERS, 'covers');
    assert.match(g.env, /^linux-x64 \| /, 'recorded on Linux CI: nowhere else can check them');
  });
}

test('the pinned lib is byte for byte what each release had, and nothing else is pinned', () => {
  const dir = path.join(CANVAS, 'lib', 'versions');
  const versions = fs.readdirSync(dir).filter(v => fs.statSync(path.join(dir, v)).isDirectory()).sort();
  assert.deepEqual(versions, Object.keys(PINNED).sort(), 'a version folder in canvas/lib/versions without its hashes here (or the reverse)');
  for (const [v, files] of Object.entries(PINNED)) {
    const have = fs.readdirSync(path.join(dir, v)).filter(f => f.endsWith('.js')).sort();
    assert.deepEqual(have, Object.keys(files).sort(), `canvas/lib/versions/${v}/`);
    for (const [f, h] of Object.entries(files)) {
      assert.equal(sha256(fs.readFileSync(path.join(dir, v, f))), h, `canvas/lib/versions/${v}/${f} changed: a pinned lib is never edited (fix the lib in canvas/lib/)`);
    }
  }
});
