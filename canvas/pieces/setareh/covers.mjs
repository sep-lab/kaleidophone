// covers.mjs -- every cover variant of SETAREH in every format, from one build, in one browser session.
//   node pieces/setareh/covers.mjs <built.html> <pack.json> <outdir> [names] [formats]
// names default to all six (night, dawn, before, rays, close, written); formats to sq, reel, feed:
//   sq    3000x3000, streaming and the feed's square        reel  1080x1920, the whole 9:16 frame
//   feed  1080x1350, the 4:5 feed
// Each format is composed on its own (60_covers.js coverView), not cropped from the square. tools/still.mjs
// draws only the square: it doesn't pass the format on. PNG out; the delivered covers were these, saved as
// JPEG 4:4:4 at 300 dpi. Browser, page-error and no-network handling are the tools': tools/lib/common.mjs.
import fs from 'node:fs';
import path from 'node:path';
import { RunError, main, launch, openPiece, assertPageOk, loadSong, dataUrlToBuffer, onCleanup } from '../../tools/lib/common.mjs';

const SIZE = { sq: [3000, 3000], reel: [1080, 1920], feed: [1080, 1350] };
const NAMES = 'night,dawn,before,rays,close,written';

await main(async () => {
  const [html, packFile, out, names = NAMES, fmts = 'sq,reel,feed'] = process.argv.slice(2);
  if (!html || !packFile || !out) throw new RunError('usage: node pieces/setareh/covers.mjs <built.html> <pack.json> <outdir> [names] [formats]');
  for (const f of fmts.split(',')) if (!SIZE[f]) throw new RunError(`unknown format "${f}" (have: ${Object.keys(SIZE).join(', ')})`);
  const pack = loadSong(packFile);
  fs.mkdirSync(out, { recursive: true });
  const browser = await launch();
  onCleanup(() => browser.close());
  for (const fmt of fmts.split(',')) {
    const [w, h] = SIZE[fmt];
    const page = await openPiece(browser, html, { cover: 1, size: w, w, h }, { width: Math.min(w, 1080), height: Math.min(h, 1920) });
    await page.evaluate(p => window.__init(p), pack);
    for (const name of names.split(',')) {
      const T = Date.now();
      await page.evaluate(([n, f]) => window.__cover(n, { fmt: f }), [name, fmt]);
      assertPageOk(page, `cover "${name}" (${fmt})`);
      const d = await page.evaluate(() => document.getElementById('c').toDataURL('image/png'));
      const f = path.join(out, `SETAREH_cover_${name}_${fmt}_${w}x${h}.png`);
      fs.writeFileSync(f, dataUrlToBuffer(d));
      console.log(path.basename(f), Date.now() - T, 'ms');
    }
    await page.close();
  }
  await browser.close();
});
