// ---------------------------------------------------------------- the HUD: the game's clock and its weather
// Not data about the song: the game has a clock whether or not anyone is listening (a second
// is a minute), and the weather icon is the weather -- which is the title. Drawn after the
// dither, in game pixels, inside the platforms' safe frame.
const DIG = {
  '0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111', '4': '101101111001001',
  '5': '111100111001111', '6': '111100111101111', '7': '111001001001001', '8': '111101111101111', '9': '111101111001111',
};
const LET = {     // 5 x 7
  S: '01111100001000001110000010000111110', E: '11111100001000011110100001000011111', P: '11110100011000111110100001000010000',
  T: '11111001000010000100001000010000100', H: '10001100011000111111100011000110001', C: '01111100001000010000100001000001111',
  O: '01110100011000110001100011000101110', N: '10001110011010110011100011000110001', ' ': '00000000000000000000000000000000000',
};
function glyph(g, bits, w, h, x, y, s, col, shadow) {
  for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) if (bits[r * w + c] === '1') {
    if (shadow) { g.fillStyle = shadow; g.fillRect(x + c * s + s, y + r * s + s, s, s); }
  }
  g.fillStyle = col;
  for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) if (bits[r * w + c] === '1') g.fillRect(x + c * s, y + r * s, s, s);
}
function textW(str, s) { let w = 0; for (const ch of str) w += (ch === ':' ? 1 : 3) * s + s; return w - s; }
function digits(g, str, x, y, s, col, shadow) {
  for (const ch of str) {
    if (ch === ':') { for (const r of [1, 3]) { g.fillStyle = shadow; g.fillRect(x + s, y + r * s + s, s, s); g.fillStyle = col; g.fillRect(x, y + r * s, s, s); } x += 2 * s; continue; }
    glyph(g, DIG[ch], 3, 5, x, y, s, col, shadow); x += 4 * s;
  }
}
function letters(g, str, x, y, s, col, shadow, track = 1) {
  for (const ch of str) { glyph(g, LET[ch] || LET[' '], 5, 7, x, y, s, col, shadow); x += (5 + track) * s; }
}
const lettersW = (str, s, track = 1) => str.length * (5 + track) * s - track * s;
function lettersOutlined(g, str, x, y, s, col, track = 1) {
  for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [1, 1]]) letters(g, str, x + dx, y + dy, s, 'rgba(6,8,16,0.9)', null, track);
  letters(g, str, x, y, s, col, null, track);
}
// the weather icon, 16 x 14: a cloud, its bolt, its rain
const ICON = [
  '.......aaaa.....',
  '....aa.aaaaaa...',
  '..aaaaaaaaaaaa..',
  '.aaaaaaaaaaaaaa.',
  'aaaaaaaaaaaaaaaa',
  'bbbbbbbbbbbbbbbb',
  '.bbbbbbbbbbbbbb.',
  '......yyyy..r...',
  '.r...yyyy..r..r.',
  'r...yyyyyyy..r..',
  '.......yyy......',
  '.r....yyy...r...',
  'r.....yy...r..r.',
  '......y.........',
];
const ICOL = { a: [226, 230, 240], b: [150, 160, 186], y: [255, 212, 64], r: [110, 170, 255] };
function icon(g, x, y, s, alpha = 1) {
  g.globalAlpha = alpha;
  // a hard one-pixel shadow at HUD size; big, a thin dark rim all round instead
  const o = s >= 4 ? Math.max(1, Math.round(s / 6)) : s;
  ICON.forEach((row, r) => [...row].forEach((ch, c) => {
    if (ch === '.') return;
    g.fillStyle = s >= 4 ? 'rgba(4,6,14,0.7)' : 'rgba(0,0,0,0.6)';
    if (s >= 4) g.fillRect(x + c * s - o, y + r * s - o, s + 2 * o, s + 2 * o);
    else g.fillRect(x + c * s + s, y + r * s + s, s, s);
  }));
  ICON.forEach((row, r) => [...row].forEach((ch, c) => { if (ch !== '.') { g.fillStyle = css(ICOL[ch]); g.fillRect(x + c * s, y + r * s, s, s); } }));
  g.globalAlpha = 1;
}
function clockStr(t) {
  const m = Math.floor(gameMin(t)), hh = Math.floor(m / 60) % 24, mm = m % 60;
  return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0');
}
// The signature card (#16), as the game would do it: each vertical cut opens on the weather
// icon, big, in the middle of the frame (the platform's first frame, so the reel's cover); then it
// flies up into the HUD's corner and the clock starts.
const CARD = 1.9;
function drawHUD(g, t, cardT0) {
  const s = 2, str = clockStr(t), w = textW(str, s);
  const x1 = Math.round(BW * 940 / 1080) - 2, y0 = Math.round(BH * 269 / 1920) + 4;   // inside the safe frame's top right
  const hx = x1 - w - 16 - 5, hy = y0 - 3;
  const u = cardT0 == null ? 1 : (t - cardT0) / CARD;
  if (u < 1) {
    const big = Math.max(4, Math.floor(BW / 34)), fly = easeInOut(clamp((u - 0.5) / 0.42));
    const sc = Math.max(1, Math.round(lerp(big, 1, fly)));
    // the centre travels smoothly from mid-frame to the HUD slot; the corner follows from this step's size
    const mx = lerp(BW / 2, hx + 8, fly), my = lerp(BH / 2 - BH * 0.04, hy + 7, fly);
    const cx = mx - 8 * sc, cy = my - 7 * sc;
    if (fly < 0.3) { g.fillStyle = `rgba(4,6,14,${(0.65 * (1 - fly / 0.3)).toFixed(3)})`; g.fillRect(0, 0, BW, BH); }
    icon(g, Math.round(cx), Math.round(cy + (fly ? 0 : Math.sin(t * 5) * 1.5)), sc);
    if (u > 0.92) digits(g, str, x1 - w, y0, s, '#f2f2ea', 'rgba(0,0,0,0.75)');
    return;
  }
  const blink = t >= SONG.stop + 0.2 ? (Math.floor((t - SONG.stop) * 1.6) % 2 === 0) : true;
  if (blink) digits(g, str, x1 - w, y0, s, '#f2f2ea', 'rgba(0,0,0,0.75)');
  icon(g, hx, hy, 1);
}
