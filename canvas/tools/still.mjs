#!/usr/bin/env node
// still.mjs -- lossless PNG stills: QA frames at chosen times, or the piece's covers.
//
//   node tools/still.mjs <piece> --song pack.json --t 12.5,30,60 [--w 540 --h 960] [--out dir] [--qa]
//                                  [--flags '{"noSpots":true}'] [--card --t0 51] [--html file.html]
//   node tools/still.mjs <piece> --song pack.json --cover main,drift [--size 3000] [--out dir]
//   node tools/still.mjs <piece> --song pack.json --cover all
//
// --qa draws every declared body<->furniture contact on the frame and prints the worst one
// (pieces built on the rig v2 contact log; see docs/TECHNIQUES.md, "contact QA").
// PNG, not JPEG: stills are for judging, and covers are deliverables.
//
// Like render.mjs, the piece is built from its source with THIS song pack first (--html to open
// another file), and a page error or a request for anything but a local file fails the run
// (--allow-page-errors to keep going). A stateful piece has no "frame at t" without its history,
// so each of its stills gets a fresh page that warms up into t: `--t 60,70` gives the same t=70
// as `--t 70` alone.
import fs from 'node:fs';
import path from 'node:path';
import {
  UsageError, RunError, main, onCleanup, parseArgs, helpText, firstLine, loadPiece, loadDriver, loadSong,
  launch, openPiece, assertPageOk, buildForRun,
} from './lib/common.mjs';

const SPEC = {
  usage: 'node tools/still.mjs <piece> --song pack.json (--t t1,t2,... | --cover name,...|all) [flags]',
  positional: [1, 1],
  flags: {
    song: { type: 'string', arg: 'pack.json', help: 'the song pack that drives the piece (required)' },
    t: { type: 'numbers', arg: 's,s,...', help: 'stills at these song times (seconds)' },
    cover: { type: 'optional', arg: 'name,...|all', help: 'the piece\'s covers instead (bare --cover = all)' },
    size: { type: 'int', arg: 'px', help: 'cover width (height keeps the cover\'s aspect; default: piece.json)' },
    w: { type: 'int', arg: 'px', help: 'still width (default 540)' },
    h: { type: 'int', arg: 'px', help: 'still height (default: 16:9 portrait of --w)' },
    out: { type: 'string', arg: 'dir', help: 'where the PNGs go (default <piece>_stills)' },
    prefix: { type: 'string', help: 'file name prefix for --t stills (default: the piece id)' },
    qa: { type: 'bool', help: 'draw the rig\'s contact log on the frame and print the worst contact' },
    flags: { type: 'json', arg: '{...}', help: 'extra per-frame flags, as JSON' },
    card: { type: 'bool', help: 'the piece\'s signature card (with --t0: the window it opens)' },
    t0: { type: 'number', arg: 's', help: 'the window start the card belongs to (default 0)' },
    fps: { type: 'number', help: 'frame rate the piece is timed at (default: piece.json, else 24)' },
    mode: { type: 'string', choices: ['reel', 'story', 'none'], help: 'stateful pieces: which cards to draw (default none)' },
    seed: { type: 'number', help: 'the piece\'s seed (default: the driver\'s)' },
    html: { type: 'string', arg: 'file.html', help: 'open this HTML instead of building the piece now' },
    'allow-page-errors': { type: 'bool', help: 'keep going when the page throws or requests anything but a local file' },
  },
};

const need = (ok, msg) => { if (!ok) throw new UsageError(msg); };

await main(async () => {
  const A = parseArgs(process.argv.slice(2), SPEC);
  if (A.help) { console.log(helpText(SPEC)); return; }
  const id = A._[0];
  const piece = loadPiece(id);
  const drv = await loadDriver(piece);
  need(A.song, `--song is required: the song pack to draw from (usage: ${SPEC.usage})`);
  const pack = loadSong(A.song);
  const flags = A.flags ?? {};
  need(flags && typeof flags === 'object' && !Array.isArray(flags), '--flags must be a JSON object, e.g. \'{"noSpots":true}\'');
  need(A.cover || A.t, 'give --t t1,t2,... or --cover name,...|all');
  need(!(A.cover && A.t), 'give --t or --cover, not both');
  const allowPageErrors = !!A['allow-page-errors'];

  let covers, cw, ch, times, w, h, opts;
  if (A.cover) {
    const C = piece.spec.covers;
    need(C, `${id} has no "covers" in piece.json`);
    const all = C.variants.map(v => v.name);
    const names = A.cover === true || A.cover === 'all' ? all : String(A.cover).split(',').map(s => s.trim());
    for (const n of names) need(all.includes(n), `${id}: no cover "${n}" (have: ${all.join(', ')})`);
    covers = names.map(n => C.variants.find(v => v.name === n));
    need(A.size === undefined || A.size > 0, `--size must be positive (got ${A.size})`);
    [cw, ch] = A.size ? [A.size, Math.round(A.size * C.size[1] / C.size[0])] : C.size;
  } else {
    times = A.t;
    for (const t of times) need(t >= 0, `--t ${t}: song time can't be negative`);
    w = A.w ?? 540; h = A.h ?? Math.round(w * 16 / 9);
    need(w > 0 && h > 0, `--w and --h must be positive (got ${w}x${h})`);
    const fps = A.fps ?? +((piece.spec.render || {}).fps || 24);
    need(fps > 0, `--fps must be positive (got ${fps})`);
    need((A.t0 ?? 0) >= 0, `--t0 is song time and can't be negative (got ${A.t0})`);
    opts = { t0: A.t0 ?? 0, dur: 1, fps, w, h, card: !!A.card, mode: A.mode || 'none', flags };
  }
  const outDir = path.resolve(A.out || `${id}_stills`);
  need(!fs.existsSync(outDir) || fs.statSync(outDir).isDirectory(), `--out ${A.out} is a file: give a folder`);

  const { file: html } = await buildForRun(piece, A.song, A.html);
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await launch();
  onCleanup(() => browser.close());

  async function png(page, file) {
    const d = await page.evaluate(sel => document.querySelector(sel).toDataURL('image/png'), drv.canvasSelector);
    fs.writeFileSync(file, Buffer.from(d.slice(d.indexOf(',') + 1), 'base64'));
    return file;
  }
  const guard = async (what, fn) => {
    try { return await fn(); } catch (e) {
      if (e instanceof RunError || e instanceof UsageError) throw e;
      throw new RunError(`${id}: ${what} failed: ${firstLine(e.message)}`);
    }
  };

  if (covers) {
    const C = piece.spec.covers;
    for (const variant of covers) {
      const name = variant.name;
      const query = C.mode === 'cover' && drv.coverQuery ? drv.coverQuery({ size: cw }) : drv.query({ w: cw, h: ch, seed: A.seed });
      const page = await openPiece(browser, html, query, { width: 1080, height: 1920 }, { allowPageErrors });
      await guard(`cover "${name}"`, async () => {
        await drv.init(page, pack, {});
        const T = Date.now();
        await drv.cover(page, name, variant, pack, variant);
        assertPageOk(page, `${id}: cover "${name}"`);
        const f = await png(page, path.join(outDir, `${id}_cover_${name}_${cw}.png`));
        console.log(`${path.relative(process.cwd(), f)}  ${Date.now() - T} ms`);
      });
      await page.close();
    }
  } else {
    const query = { ...drv.query({ w, h, seed: A.seed }), ...(A.qa ? { qa: 1 } : {}) };
    const viewport = { width: Math.min(w, 1080), height: Math.min(h, 1920) };
    const open = async () => {
      const page = await openPiece(browser, html, query, viewport, { allowPageErrors });
      await guard('init', () => drv.init(page, pack, opts));
      assertPageOk(page, `${id}: init`);
      return page;
    };
    // stateless: one page draws every t. Stateful: a fresh page per t (see the header).
    let page = drv.stateful ? null : await open();
    for (const t of times) {
      let res;
      if (drv.stateful) {
        page = await open();
        // a stateful piece has no "frame at t" without its history: warm up into it
        const o = { ...opts, t0: t, dur: 0.05 };
        if (drv.plan) drv.plan(pack, { ...o, snap: false });
        const wn = Math.round((drv.warmup || 3) * o.fps);
        for (let i = -wn; i <= 0; i++) res = await guard(`t ${t}`, () => drv.draw(page, drv.frame(t + i / o.fps, pack, o)));
      } else {
        res = await guard(`t ${t}`, () => drv.draw(page, drv.frame(t, pack, opts)));
      }
      assertPageOk(page, `${id}: t ${t}`);
      const f = await png(page, path.join(outDir, `${A.prefix || id}_${t.toFixed(3)}.png`));
      const qa = res && res.contacts ? res.contacts : null;
      console.log(`${path.relative(process.cwd(), f)}${qa ? '  contacts ' + JSON.stringify(qa) : ''}`);
      if (drv.stateful) { await page.close(); page = null; }
    }
    if (page) await page.close();
  }
  await browser.close();
});
