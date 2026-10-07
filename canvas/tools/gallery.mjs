#!/usr/bin/env node
// gallery.mjs -- the public gallery: every piece, rendered from its SYNTHETIC twin, as an animated WebP,
// a poster and a cover, plus the live pieces themselves, as a static site.
//
//   node tools/gallery.mjs --out ../site [--only should-i,minus] [--w 360] [--fps 12]
//                          [--site-url https://sep-lab.github.io/kaleidophone/] [--keep]
//
// Nothing this writes is committed. CI runs it on every push to main and publishes the result
// with GitHub Pages (.github/workflows/pages.yml), so the README can show the work while the
// repository still holds no media at all (docs/decisions/0003, 0007).
//
// What each piece shows comes from its piece.json "gallery" entry (canvas/README.md, "The gallery
// entry"). The site it writes:
//   index.html               the page; its link-preview tags point at gallery/og.jpg (absolute, --site-url)
//   gallery/<id>.webp        the clip; <id>.jpg is its poster (the reduced-motion fallback), <id>-cover.jpg a cover
//   gallery/og.jpg           the link preview: the works' posters side by side, 1200x630
//   gallery/manifest.json    what was built, in page order
//   pieces/<id>.html         the live pieces, titled "TITLE — artist" (in this copy only; sources and dist/ keep theirs)
//   fonts/, licenses/        the page's Vazirmatn, and the license of every font the site ships
// --keep leaves the intermediate MP4s and cover PNGs in a temp folder and prints where.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { CANVAS, DIST, parseArgs, die, listPieces, loadPiece } from './lib/common.mjs';
import { buildPiece, retitle } from './build.mjs';
import { synthFor } from './synth.mjs';

const A = parseArgs();
const OUT = path.resolve(A.out || path.join(CANVAS, '..', 'site'));
// Link previews need absolute URLs; a fork that publishes elsewhere passes its own --site-url.
const SITE = String(A['site-url'] || 'https://sep-lab.github.io/kaleidophone/').replace(/\/*$/, '/');
const REPO = 'https://github.com/sep-lab/kaleidophone';
const ARTIST = { name: 'Sep The Concept', url: 'https://soundcloud.com/septheconcept' };   // where the songs are
const VAZIR = 'vazirmatn/fonts/webfonts/Vazirmatn-Regular.woff2';   // the page's Persian titles
const GW = +(A.w || 360), GH = Math.round(GW * 16 / 9), GFPS = +(A.fps || 12);
const FIRST_ROW = 4;   // the grid's widest row (4 columns): those clips load eagerly, the rest lazily
const only = A.only ? String(A.only).split(',') : null;
const node = process.execPath;
const run = (args, opts = {}) => execFileSync(node, args, { cwd: CANVAS, stdio: ['ignore', 'pipe', 'inherit'], ...opts }).toString();
const ff = args => execFileSync('ffmpeg', ['-y', '-v', 'error', ...args], { stdio: ['ignore', 'inherit', 'inherit'] });
const kb = f => Math.round(fs.statSync(f).size / 1024);

// Check every entry before rendering anything, then work in page order: "order" first, then by folder.
const entries = listPieces().filter(id => !only || only.includes(id)).map(id => {
  const { spec } = loadPiece(id);
  return spec.gallery ? { id, s: spec, g: checkEntry(id, spec) } : null;
}).filter(Boolean).sort((a, b) => (a.g.order ?? Infinity) - (b.g.order ?? Infinity) || a.id.localeCompare(b.id));

for (const d of ['gallery', 'pieces', 'fonts', 'licenses']) fs.mkdirSync(path.join(OUT, d), { recursive: true });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kp-gallery-'));   // private to this run, so two runs can't collide
process.on('exit', () => { if (A.keep) console.log(`kept the intermediate renders in ${tmp}`); else fs.rmSync(tmp, { recursive: true, force: true }); });

const manifest = [];
for (const { id, s, g } of entries) {
  const song = synthFor(id);
  buildPiece(id, { song });
  // the live piece, retitled "TITLE — artist" in the site's copy only
  const html = fs.readFileSync(path.join(DIST, `${id}.html`), 'utf8');
  if (!/<title>[\s\S]*?<\/title>/i.test(html)) console.warn(`${id}: the built page has no <title> to normalise`);
  fs.writeFileSync(path.join(OUT, 'pieces', `${id}.html`), retitle(html, s));

  // the clip: rendered at the gallery size, silent, then an animated WebP and a poster frame
  const mp4 = path.join(tmp, `${id}.mp4`);
  const extra = [];
  if (g.mode) extra.push('--mode', g.mode);
  if (g.card) extra.push('--card');
  const log = run(['tools/render.mjs', id, '--song', song, '--t0', String(g.t0), '--dur', String(g.dur), '--fps', String(g.fps),
    '--w', String(GW), '--h', String(GH), '--crf', '14', '--workers', '2', '--out', mp4, ...extra]);
  const snap = log.match(/t0 snapped to the nearest beat: (\S+) -> (\S+)/);
  if (snap) console.log(`${id}: t0 ${snap[1]} snapped to the beat at ${snap[2]}; the clip and its poster start there`);
  // Animated WebP, not GIF: boil, grain and fire change every pixel of every frame, which a 256-colour
  // GIF pays for dearly. Measured 2026-09-29 on the four works' clips (360x640, 6 s, synthetic twins):
  // 4.0-16 MB each as a GIF (ffmpeg palettegen + paletteuse), 0.38-1.2 MB as WebP at the "quality" each
  // piece sets -- HAMECHI MANZOR DARE's fire is 2.2 MB at the default q70, hence its q50.
  const webp = path.join(OUT, 'gallery', `${id}.webp`);
  ff(['-i', mp4, '-an', '-c:v', 'libwebp', '-lossless', '0', '-q:v', String(g.quality), '-compression_level', '6', '-loop', '0', webp]);
  const poster = path.join(OUT, 'gallery', `${id}.jpg`);
  ff(['-ss', String(g.poster), '-i', mp4, '-frames:v', '1', '-q:v', '3', poster]);

  // the cover, from the piece's own cover code, downsized for the web
  let cover = null;
  if (g.cover) {
    const size = 1200;
    run(['tools/still.mjs', id, '--song', song, '--cover', g.cover, '--size', String(size), '--out', tmp]);
    const png = path.join(tmp, `${id}_cover_${g.cover}_${size}.png`);
    cover = path.join(OUT, 'gallery', `${id}-cover.jpg`);
    ff(['-i', png, '-vf', 'scale=900:-1:flags=lanczos', '-q:v', '3', cover]);
  }
  console.log(`${id}: webp ${kb(webp)} KB (q${g.quality}), poster ${kb(poster)} KB at ${g.poster} s${cover ? `, cover ${kb(cover)} KB` : ''}`);
  manifest.push({
    id, order: g.order ?? null, title: s.title, titleFa: s.titleFa || null, artist: s.artist, year: s.year, medium: s.medium,
    summary: s.summary, alt: g.alt || s.title, role: g.role || 'piece',
    clip: `gallery/${id}.webp`, poster: `gallery/${id}.jpg`, posterAt: g.poster, cover: cover ? `gallery/${id}-cover.jpg` : null,
    live: `pieces/${id}.html`, listen: g.listen || null, source: `${REPO}/tree/main/canvas/pieces/${id}`,
  });
}

const works = manifest.filter(i => i.role !== 'template');
const og = works.length ? 'gallery/og.jpg' : null;
if (og) {
  ogImage(works, path.join(OUT, og));
  console.log(`og.jpg: ${kb(path.join(OUT, og))} KB (1200x630, posters of ${works.map(w => w.id).join(', ')})`);
}
const vazir = path.join(CANVAS, 'node_modules', VAZIR);
if (!fs.existsSync(vazir)) die(`font file missing: node_modules/${VAZIR} -- run \`npm ci\` in canvas/ first`);
fs.copyFileSync(vazir, path.join(OUT, 'fonts', path.basename(VAZIR)));
const fonts = shipLicenses([...entries.flatMap(e => e.s.fonts || []), { family: 'Vazirmatn', file: VAZIR }]);
fs.writeFileSync(path.join(OUT, 'gallery', 'manifest.json'), JSON.stringify(manifest, null, 2));
fs.writeFileSync(path.join(OUT, 'index.html'), page(manifest, { fonts, og }));
fs.writeFileSync(path.join(OUT, '.nojekyll'), '');
const rel = path.relative(process.cwd(), OUT);
console.log(`gallery: ${manifest.length} pieces -> ${rel.startsWith('..') ? OUT : rel || '.'}/index.html`);

// ---------------------------------------------------------------- the "gallery" entry
function checkEntry(id, s) {
  const g = s.gallery;
  const bad = msg => die(`${id}: piece.json "gallery": ${msg}`);
  const KNOWN = ['t0', 'dur', 'fps', 'mode', 'card', 'cover', 'role', 'poster', 'alt', 'quality', 'order', 'listen'];
  for (const k of Object.keys(g)) if (!KNOWN.includes(k)) console.warn(`${id}: piece.json "gallery" has an unknown key "${k}" (known: ${KNOWN.join(', ')})`);
  const num = (k, lo, hi, dflt) => {
    const v = g[k] ?? dflt;
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi) bad(`"${k}" must be a number from ${lo} to ${+hi.toFixed(3)} (got ${JSON.stringify(g[k])})`);
    return v;
  };
  if (g.t0 === undefined) bad('"t0" is required: where in the song the clip starts, in seconds');
  const t0 = num('t0', 0, 1e5);
  const dur = num('dur', 0.5, 600, 6), fps = num('fps', 1, 60, GFPS);
  const poster = num('poster', 0, dur - 1 / fps, +Math.min(dur * 0.6, dur - 1 / fps).toFixed(3));
  const quality = num('quality', 0, 100, 70);
  if (g.order !== undefined) num('order', -1e6, 1e6);
  for (const k of ['alt', 'listen', 'cover', 'mode', 'role']) if (g[k] !== undefined && (typeof g[k] !== 'string' || !g[k].trim())) bad(`"${k}" must be a non-empty string`);
  if (g.card !== undefined && typeof g.card !== 'boolean') bad('"card" must be true or false');
  if (g.role !== undefined && !['piece', 'template'].includes(g.role)) bad(`"role" is "piece" (the default) or "template", not "${g.role}"`);
  if (g.listen !== undefined && !/^https:\/\/[^\s"<>]+$/.test(g.listen)) bad(`"listen" must be an https:// URL (got ${JSON.stringify(g.listen)})`);
  if (g.cover !== undefined && !(s.covers?.variants || []).some(v => v.name === g.cover)) bad(`"cover": no cover "${g.cover}" in "covers"`);
  if (g.alt === undefined) console.warn(`${id}: no "gallery.alt" -- the clip's alt text falls back to the title; describe what the clip shows`);
  return { ...g, t0, dur, fps, poster, quality };
}

// ---------------------------------------------------------------- the link preview
// The works' posters side by side on the page's black, each cropped (centred) to fill its tile:
// 1200x630 is what Open Graph and Twitter's large card expect.
function ogImage(items, file) {
  const W = 1200, H = 630, gap = 8, n = items.length;
  const tw = Math.floor((W - gap * (n - 1)) / n);
  const tiles = items.map((_, k) => `[${k}:v]scale=${tw}:${H}:force_original_aspect_ratio=increase,crop=${tw}:${H},setsar=1` +
    (k < n - 1 ? `,pad=${tw + gap}:${H}:0:0:color=0x0d0c0a` : '') + `[t${k}]`);
  const row = n > 1 ? items.map((_, k) => `[t${k}]`).join('') + `hstack=inputs=${n}` : '[t0]null';
  ff([...items.flatMap(i => ['-i', path.join(OUT, i.poster)]), '-filter_complex',
    [...tiles, `${row},pad=${W}:${H}:(ow-iw)/2:0:color=0x0d0c0a[og]`].join(';'), '-map', '[og]', '-frames:v', '1', '-q:v', '3', file]);
}

// ---------------------------------------------------------------- font licenses
// Every font the site ships -- inlined in the pieces, plus the page's own Vazirmatn -- goes out with
// its license: the text from the npm package the build inlined it from, headed by the attribution
// that package records when the text itself doesn't carry one.
function shipLicenses(fonts) {
  const byPkg = new Map();
  for (const f of fonts) {
    const seg = f.file.split('/'), pkg = seg[0].startsWith('@') ? seg.slice(0, 2).join('/') : seg[0];
    if (!byPkg.has(pkg)) byPkg.set(pkg, new Set());
    byPkg.get(pkg).add(f.family);
  }
  const shipped = [];
  for (const [pkg, families] of byPkg) {
    const dir = path.join(CANVAS, 'node_modules', pkg);
    const read = f => (fs.existsSync(path.join(dir, f)) ? fs.readFileSync(path.join(dir, f), 'utf8') : null);
    const meta = JSON.parse(read('package.json') || die(`node_modules/${pkg} is missing -- run \`npm ci\` in canvas/ first`));
    const lic = JSON.parse(read('metadata.json') || '{}').license || {};   // @fontsource packages record type + attribution here
    const text = ['LICENSE', 'LICENSE.txt', 'LICENSE.md', 'OFL.txt'].map(read).find(t => t !== null) ?? die(`node_modules/${pkg} has no license text`);
    let spdx = lic.type || meta.license || 'see the text';
    if (spdx === 'OFL' && /Open Font License,? Version 1\.1/i.test(text)) spdx = 'OFL-1.1';
    const name = [...families].sort().join(', ');
    const head = [`${name}: a font shipped in these pages, from the npm package ${pkg} ${meta.version} (${spdx}).`];
    if (lic.attribution && !text.includes(lic.attribution.slice(0, 60))) head.push(lic.attribution);
    const href = `licenses/${pkg.split('/').pop()}.txt`;
    fs.writeFileSync(path.join(OUT, href), `${head.join('\n')}\n\n${text}`);
    shipped.push({ name, spdx, href });
  }
  return shipped.sort((a, b) => a.name.localeCompare(b.name));
}

// "54 techniques", counted from docs/TECHNIQUES.md so the link can't go stale
function techniquesLabel() {
  try {
    const n = (fs.readFileSync(path.join(CANVAS, '..', 'docs', 'TECHNIQUES.md'), 'utf8').match(/^#{2,4} \d+\. /gm) || []).length;
    return n ? `${n} techniques` : 'the techniques';
  } catch { return 'the techniques'; }
}

// ---------------------------------------------------------------- the page
function esc(x) { return String(x ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function page(items, { fonts, og }) {
  const works = items.filter(i => i.role !== 'template'), tpl = items.find(i => i.role === 'template');
  const title = `kaleidophone gallery — ${ARTIST.name}`;
  const description = `Song-driven canvas pieces by ${ARTIST.name}: each one plays live, renders its own music video deterministically, and draws its own covers.`;
  const count = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'][works.length] ?? String(works.length);
  const years = [...new Set(works.map(w => w.year))].sort();
  const artist = `<a href="${ARTIST.url}">${ARTIST.name}</a>`;
  // the preview shows one poster per work: describe it with the first sentence of each alt
  const ogAlt = `One frame from each piece, side by side, left to right. ${works.map(w => w.alt.split(/(?<=\.)\s+/)[0]).join(' ')}`;
  const clip = (i, eager) => `
      <a class="clip" href="${esc(i.live)}" title="Open the live piece: click to play, or drop a track on it">
        <picture>
          <source srcset="${esc(i.poster)}" media="(prefers-reduced-motion: reduce)">
          <img src="${esc(i.clip)}" alt="${esc(i.alt)}" width="${GW}" height="${GH}"${eager ? '' : ' loading="lazy"'} decoding="async">
        </picture>
      </a>`;
  const card = (i, k) => `
    <article class="work">${clip(i, k < FIRST_ROW)}
      <h2>${esc(i.title)}${i.titleFa ? ` <span class="fa" lang="fa" dir="rtl">${esc(i.titleFa)}</span>` : ''}</h2>
      <p class="medium">${esc(i.medium)}</p>
      <p class="summary">${esc(i.summary)}</p>
      <p class="links">${[
        `<a href="${esc(i.live)}">play it live</a>`,
        i.listen && `<a href="${esc(i.listen)}">listen</a>`,
        `<a href="${esc(i.source)}">source</a>`,
        i.cover && `<a href="${esc(i.cover)}">cover</a>`,
      ].filter(Boolean).join(' · ')}</p>
    </article>`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<meta name="color-scheme" content="dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%230d0c0a'/%3E%3Ccircle cx='8' cy='8' r='4' fill='%23c9301c'/%3E%3C/svg%3E">
<link rel="canonical" href="${esc(SITE)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="kaleidophone">
<meta property="og:url" content="${esc(SITE)}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${esc(description)}">
${og ? `<meta property="og:image" content="${esc(SITE + og)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(ogAlt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="${esc(SITE + og)}">
<meta name="twitter:image:alt" content="${esc(ogAlt)}">` : '<meta name="twitter:card" content="summary">'}
${items.some(i => i.titleFa) ? `<link rel="preload" href="fonts/${path.basename(VAZIR)}" as="font" type="font/woff2" crossorigin>\n` : ''}<style>
  @font-face{font-family:Vazirmatn;font-weight:400;font-display:swap;src:url(fonts/${path.basename(VAZIR)}) format('woff2')}
  :root{--paper:#ede6d6;--soft:#cbc3b2;--dim:#8f887c;--line:#2b2723;--bg:#0d0c0a;--red:#c9301c}
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--paper);font:15px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header,main,footer{max-width:1240px;margin:0 auto;padding:0 16px}
  header{padding-top:56px;padding-bottom:28px}
  h1{font-size:clamp(28px,6vw,54px);letter-spacing:.14em;margin:0 0 12px;font-weight:700}
  h1 span{color:var(--red)}
  header p{color:var(--dim);max-width:760px;margin:0}
  a{color:var(--paper)} a:hover,a:focus-visible{color:var(--red)}
  .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:26px;padding:28px 0;border-top:1px solid var(--line)}
  @media (max-width:1100px){.grid{gap:20px}}
  @media (max-width:960px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .work{display:flex;flex-direction:column;min-width:0}
  .clip{display:block;border-radius:6px;overflow:hidden;background:#000;outline:1px solid var(--line)}
  .clip img{display:block;width:100%;height:auto;aspect-ratio:9/16;object-fit:cover}
  .clip:hover,.clip:focus-visible{outline:1px solid var(--red)}
  h2{margin:16px 0 4px;font-size:17px;letter-spacing:.08em;line-height:1.3}
  .fa{display:block;font-family:Vazirmatn,Tahoma,sans-serif;font-weight:400;font-size:16px;color:var(--dim);letter-spacing:0;margin-top:2px}
  .medium{color:var(--dim);font-size:11px;line-height:1.5;letter-spacing:.06em;text-transform:uppercase;margin:.3em 0 .6em}
  .summary{color:var(--soft);font-size:13px;margin:.4em 0}
  .links{margin-top:auto;padding-top:.6em;font-size:13px}
  .start{display:grid;grid-template-columns:minmax(0,260px) minmax(0,1fr);gap:28px;padding:28px 0;border-top:1px solid var(--line)}
  .start>div{min-width:0}
  .start h2{margin-top:0}
  .start pre{background:#16140f;border:1px solid var(--line);border-radius:6px;padding:14px;overflow-x:auto;font-size:13px;color:var(--soft)}
  .start pre:focus-visible{outline:1px solid var(--red)}
  @media (max-width:720px){.start{grid-template-columns:minmax(0,1fr)}.start .clip{max-width:260px}}
  @media (max-width:560px){
    header{padding-top:36px}
    .grid{gap:24px 14px}
    .start .clip{max-width:calc(50% - 7px)}
    h2{font-size:14px;letter-spacing:.06em;margin-top:12px}
    .fa{font-size:14px}
    .medium{font-size:10px;letter-spacing:.04em}
    .summary,.links,.start pre{font-size:12px}
  }
  footer{color:var(--dim);font-size:13px;padding-bottom:64px}
  footer::before{content:"";display:block;border-top:1px solid var(--line);margin-bottom:24px}
  footer p{margin:0 0 .8em;max-width:860px}
</style>
</head>
<body>
<header>
  <h1>KALEIDOPHONE<span>.</span></h1>
  <p>Music videos written as code. Each piece below is one HTML file that plays live (click it, or drop a track on it),
  renders its own film frame by frame, and draws its own covers.${works.length ? ` ${count} song${works.length === 1 ? '' : 's'} by ${artist}, ${years.join(', ')}.` : ''}</p>
</header>
<main>
  <section class="grid" aria-label="Pieces">
${works.map(card).join('\n')}
  </section>
${tpl ? `  <section class="start" aria-label="Start a piece">
    <div>${clip(tpl, false)}</div>
    <div>
      <h2>Start a piece from this</h2>
      <p class="summary">${esc(tpl.summary)}</p>
      <pre tabindex="0">git clone ${REPO}
cd kaleidophone/canvas &amp;&amp; npm ci
cp -r pieces/template pieces/my-piece
node tools/synth.mjs my-piece
node tools/build.mjs my-piece --song out/songs/my-piece.songpack.json</pre>
      <p class="links"><a href="${esc(tpl.live)}">play the template live</a> · <a href="${REPO}/blob/main/canvas/README.md">the canvas engine</a> · <a href="${REPO}/blob/main/docs/TECHNIQUES.md">${techniquesLabel()}</a></p>
    </div>
  </section>` : ''}
</main>
<footer>
  <p>Every clip on this page is rendered in CI from a <em>synthetic</em> song: the real tempo and structure, none of the audio.
  The real songs, stems and lyrics are not in the repository and never will be. To hear the songs: ${artist} on SoundCloud.</p>
  <p>Source and docs: <a href="${REPO}">github.com/sep-lab/kaleidophone</a> (<a href="${REPO}/blob/main/LICENSE">Apache-2.0</a>).
  Fonts in these pages, with their licenses: ${fonts.map(f => `<a href="${esc(f.href)}">${esc(f.name)}</a> (${esc(f.spdx)})`).join(', ')}.</p>
</footer>
</body>
</html>
`;
}
