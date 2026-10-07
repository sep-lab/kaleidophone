// tools/golden.mjs without a browser: the PNG decoder its hashes stand on, the pixel hash, the golden
// file format and which stills a piece gets. The frames themselves are compared on CI (golden.mjs --check).
import test from 'node:test';
import assert from 'node:assert/strict';
import zlib from 'node:zlib';

delete process.env.KALEIDOPHONE_PIECES;
const { decodePng, pixelHash, formatGolden, parseGolden, parseStill, stillName, defaultStills, frozenPieces, isTemplate, FRAMES, COVERS, COVER_W } = await import('../tools/golden.mjs');
const { loadPiece, loadSong } = await import('../tools/lib/common.mjs');
const { synthFor } = await import('../tools/synth.mjs');

// ---------------------------------------------------------------- a small PNG encoder, every filter
const CRC = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc32 = buf => { let c = 0xffffffff; for (const b of buf) c = CRC[(c ^ b) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
function chunk(kind, body) {
  const len = Buffer.alloc(4), crc = Buffer.alloc(4), kb = Buffer.from(kind, 'latin1');
  len.writeUInt32BE(body.length); crc.writeUInt32BE(crc32(Buffer.concat([kb, body])));
  return Buffer.concat([len, kb, body, crc]);
}
const paeth = (a, b, c) => { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); return pa <= pb && pa <= pc ? a : pb <= pc ? b : c; };
// pixels: w*h*channels bytes; filter(y) picks row y's filter (0..4)
function encodePng(w, h, channels, pixels, filter = () => 0) {
  const type = { 1: 0, 2: 4, 3: 2, 4: 6 }[channels], stride = w * channels, raw = Buffer.alloc(h * (stride + 1));
  for (let y = 0; y < h; y++) {
    const f = filter(y);
    raw[y * (stride + 1)] = f;
    for (let x = 0; x < stride; x++) {
      const v = pixels[y * stride + x], a = x >= channels ? pixels[y * stride + x - channels] : 0;
      const b = y ? pixels[(y - 1) * stride + x] : 0, c = x >= channels && y ? pixels[(y - 1) * stride + x - channels] : 0;
      const p = [0, a, b, (a + b) >> 1, paeth(a, b, c)][f];
      raw[y * (stride + 1) + 1 + x] = (v - p) & 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = type;
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))]);
}
const W = 7, H = 6;
const rgba = Buffer.from(Array.from({ length: W * H * 4 }, (_, i) => (i * 37 + (i >> 2) * 11) & 255));

test('decodePng: every row filter, back to the exact pixels', () => {
  for (const filter of [() => 0, () => 1, () => 2, () => 3, () => 4, y => y % 5]) {
    const { w, h, rgba: got } = decodePng(encodePng(W, H, 4, rgba, filter));
    assert.equal(w, W); assert.equal(h, H);
    assert.deepEqual(got, rgba);
  }
});

test('decodePng: grey, grey + alpha and RGB come out as the same RGBA', () => {
  const opaque = Buffer.from(rgba); for (let i = 3; i < opaque.length; i += 4) opaque[i] = 255;
  const rgb = Buffer.from(Array.from({ length: W * H * 3 }, (_, i) => opaque[Math.floor(i / 3) * 4 + i % 3]));
  assert.deepEqual(decodePng(encodePng(W, H, 3, rgb, y => y % 5)).rgba, opaque);
  const grey = Buffer.from(Array.from({ length: W * H }, (_, i) => (i * 13) & 255));
  const ga = Buffer.from(Array.from({ length: W * H * 2 }, (_, i) => (i % 2 ? 200 : grey[i >> 1])));
  const want = (g, a) => Buffer.from(Array.from({ length: W * H * 4 }, (_, i) => (i % 4 === 3 ? a(i >> 2) : g[i >> 2])));
  assert.deepEqual(decodePng(encodePng(W, H, 1, grey, () => 4)).rgba, want(grey, () => 255));
  assert.deepEqual(decodePng(encodePng(W, H, 2, ga, () => 1)).rgba, want(grey, () => 200));
});

test('decodePng refuses what it can\'t read, rather than hashing garbage', () => {
  assert.throws(() => decodePng(Buffer.from('not a png at all')), /not a PNG/);
  const png = encodePng(W, H, 4, rgba);
  const sixteen = Buffer.from(png); sixteen[8 + 8 + 8] = 16; // IHDR bit depth
  assert.throws(() => decodePng(sixteen), /16-bit/);
});

test('pixelHash: the same pixels hash the same however they were encoded; one changed pixel does not', () => {
  const a = pixelHash(encodePng(W, H, 4, rgba, () => 0)), b = pixelHash(encodePng(W, H, 4, rgba, y => y % 5));
  assert.equal(a, b, 'filters and compression are the encoder\'s business, not the picture\'s');
  const one = Buffer.from(rgba); one[4 * (3 * W + 4)] ^= 1;   // one channel of one pixel, by one step
  assert.notEqual(pixelHash(encodePng(W, H, 4, one)), a, 'a 1-pixel change is a different hash');
  assert.notEqual(pixelHash(encodePng(H, W, 4, rgba)), a, 'the same bytes at another size are a different still');
  assert.match(a, /^[0-9a-f]{64}$/);
});

// ---------------------------------------------------------------- the files
const golden = {
  id: 'minus', html: 'a'.repeat(64), env: 'linux-x64 | chromium 141.0.7390.37 | monospace DejaVu Sans Mono | fonts-dejavu-core 2.37-8', size: { w: 1080, h: 1920 },
  stills: [{ t: 29.583, sha256: 'b'.repeat(64) }, { t: 131.5, sha256: 'c'.repeat(64) }, { cover: 'plates', w: 1200, sha256: 'd'.repeat(64) }],
};

test('a golden file reads back as it was written: "<sha256>  <still>.png" under a few "# key" lines', () => {
  const text = formatGolden(golden);
  assert.match(text, /^# kaleidophone golden frames: minus/);
  assert.ok(text.includes('\nbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  minus_29.583.png\n'));
  assert.ok(text.includes('  minus_131.500.png\n') && text.includes('  minus_cover_plates_1200.png\n'));
  const back = parseGolden('minus', text);
  assert.deepEqual({ ...back, id: 'minus' }, golden);
});

test('a still\'s name says what it is, in still.mjs\'s own naming', () => {
  assert.equal(stillName('should-i', { t: 61.25 }), 'should-i_61.250.png');
  assert.equal(stillName('should-i', { cover: 'crossed-out', w: 1200 }), 'should-i_cover_crossed-out_1200.png');
  assert.deepEqual(parseStill('should-i', 'should-i_cover_crossed-out_1200.png'), { cover: 'crossed-out', w: 1200 });
  assert.deepEqual(parseStill('should-i', 'should-i_61.250.png'), { t: 61.25 });
  assert.equal(parseStill('should-i', 'minus_61.250.png'), null, 'another piece\'s still');
  assert.equal(parseStill('should-i', 'should-i_61.25.png'), null, 'times to the millisecond, as still.mjs names them');
});

test('a golden file that isn\'t one is refused, naming the line', () => {
  const text = formatGolden(golden);
  assert.throws(() => parseGolden('minus', text.replace('# html ', '# HTML ')), /missing its html line/);
  assert.throws(() => parseGolden('minus', text + 'eeee  minus_1.000.png\n'), /minus\.sha256:\d+: not a "<sha256>  <still>\.png" line/);
  assert.throws(() => parseGolden('minus', `${text}${'e'.repeat(64)}  same-as-you_1.000.png\n`), /is not a still of minus/);
  assert.throws(() => parseGolden('minus', `${text}${'e'.repeat(64)}  minus_29.583.png\n`), /listed twice/);
});

// ---------------------------------------------------------------- which pieces, which stills
test('the frozen pieces are every piece but the templates', () => {
  const frozen = frozenPieces();
  assert.ok(frozen.includes('minus') && frozen.includes('hamechi-manzor-dare'));
  assert.ok(!frozen.includes('template'));
  assert.ok(isTemplate(loadPiece('template').spec) && !isTemplate(loadPiece('minus').spec));
});

test(`a new piece's stills: its gallery poster and ${FRAMES - 1} more through the song, on its frame grid, and ${COVERS} covers`, () => {
  for (const id of frozenPieces()) {
    const spec = loadPiece(id).spec, pack = loadSong(synthFor(id)), fps = spec.render.fps;
    const stills = defaultStills(id, spec, pack), times = stills.filter(s => !s.cover).map(s => s.t);
    assert.equal(times.length, FRAMES, id);
    assert.deepEqual([...times].sort((a, b) => a - b), times, `${id}: in order`);
    assert.ok(times.every(t => t > 0 && t < pack.dur), `${id}: inside the song`);
    assert.ok(times.every(t => Math.abs(Math.round(t * fps) / fps - t) < 5e-4), `${id}: on the ${fps} fps grid, to the millisecond`);
    const poster = spec.gallery.poster ?? Math.min(spec.gallery.dur * 0.6, spec.gallery.dur - 1 / (spec.gallery.fps || 12));
    assert.ok(times.includes(+(Math.round((spec.gallery.t0 + poster) * fps) / fps).toFixed(3)), `${id}: the gallery poster's moment`);
    const covers = stills.filter(s => s.cover);
    assert.equal(covers.length, COVERS, id);
    assert.equal(covers[0].cover, spec.gallery.cover, `${id}: the gallery's cover first`);
    assert.ok(covers.every(c => c.w === COVER_W));
    assert.deepEqual(defaultStills(id, spec, pack), stills, `${id}: the same every time`);
  }
});
