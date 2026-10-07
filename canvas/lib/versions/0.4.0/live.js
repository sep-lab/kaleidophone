'use strict';
/* ============================================================================
   kaleidophone canvas lib -- live.js
   The stage (one canvas, a 1080x1920 virtual frame) and the three modes every
   piece has, off the URL query:

     live    (no query)          click -> a procedural pad and beat at the piece's
                                 tempo, or drop the track on it -> an AnalyserNode
                                 drives it. Never silent, never the same twice.
     render  ?render=1&w=&h=     deterministic: window.__init(songPack) once, then
                                 window.__frame({ t, bass, mid, ... }) per frame.
                                 Driven by tools/render.mjs; the audio is muxed later.
     cover   ?cover=1&size=N     window.__cover(name, arg) -> one still.
     ?qa=1, in any mode, draws the 9:16 safe frame over the finished frame.

   One draw function serves all three; only the driver changes. That is why one
   file gives the live piece, the videos and the covers (docs/TECHNIQUES.md #19).

   Usage, at the end of the piece's last module:
     boot({ bpm: 100, dur: 24, draw(t, env, flags) {...}, cover(name, arg) {...},
            fonts: ['700 30px "Space Mono"'], hint: 'TITLE · click · or drop the wav' });
   Optional: downbeat (s; the fallback's first kick is the piece's beat 1), root (Hz;
   the fallback pad, default 110), idleT (s; the frame shown before a click), variants
   (the piece's variant axes, as in piece.json: flags.variant, below).

   The song's events (MIDI notes, chords, onsets) are in EV, for core.js's ev* functions:
   evList(EV, 'midi.snare'). Render and cover mode: the song pack's. Live: the fallback's
   own kicks, snares and hats as it schedules them; a dropped track has none.

   The live envelope against a song pack's (what render mode reads):
   - Bands, rms, fluxes and cent are measured on the analyser's mono downmix -- the
     pack's mid signal -- with the pack's band edges (bass 20-150 Hz, lowmid -400,
     mid -2000, high -6000, air -16000; bflux under 150 Hz, hflux 2000-16000).
   - Scale. A dropped track is pre-scanned once through this same analysis
     (livePrescan), and each band is divided by its own 99.5th percentile -- the
     pack's 1.0 -- and clipped at 1: its loud passages read 1 from the first frame,
     its quiet intro reads quiet. The pack maps dB between its 5th and 99.5th
     percentiles, live is linear magnitude: a passage 20 dB down reads 0.1 live and
     more in a pack. The fallback has no pre-scan: a running maximum per band,
     decaying 6 dB a minute. Fluxes are linear-magnitude differences here and
     log-magnitude in a pack: the same hits, different heights.
   - voc is the pack's: how far the 250-3500 Hz band's centre, (L+R)/2, stands out
     from its sides, (L-R)/2, in dB, clipped at +-30 and mapped between the track's
     own 5th and 99.5th percentiles. Mono and dual-mono tracks and the fallback have
     none: voc is 0, as a mono file's pack has no voc.
   - Time. What the analyser measures now is heard outputLatency + baseLatency later
     (~0.2 s on Bluetooth), so the frame drawn and its envelope both run that far
     behind the audio clock: the picture waits for the sound.
   ============================================================================ */
const Q = new URLSearchParams(typeof location !== 'undefined' ? location.search : '');
const MODE = Q.get('render') === '1' ? 'render' : Q.get('cover') === '1' ? 'cover' : 'live';
const QA = Q.get('qa') === '1';

const cv = document.getElementById('c');
let ctx = cv.getContext('2d', { alpha: false });
const MAINCTX = ctx;
function withCtx(c2, fn) { const o = ctx; ctx = c2; try { return fn(); } finally { ctx = o; } }
const W = 1080, H = 1920;                    // the virtual frame: draw everything in these units
let S = 1, PXW = 1080, PXH = 1920;
function setSize(pw, ph) { PXW = pw; PXH = ph; cv.width = pw; cv.height = ph; S = pw / W; }
function base() { ctx.setTransform(S, 0, 0, S, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none'; }
// A square cover is a crop of the portrait composition, drawn at portrait stroke scale:
// keep the 1080-wide virtual space and slide it up so the band that matters is in frame.
function coverCrop(topFraction) { ctx.setTransform(S, 0, 0, S, 0, -topFraction * H * S); }

const ENV_KEYS = ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent', 'voc'];
function envFrom(p) { const e = {}; for (const k of ENV_KEYS) e[k] = +(p && p[k]) || 0; return e; }

// ---------------------------------------------------------------- the song's events: EV
// Pack-shaped ({ events }), so one call reads it and a song pack alike: evList(EV, 'midi.kick').
//   render, cover  the events of the pack window.__init was given
//   live           what is playing: the procedural fallback's own kicks, snares and hats, pushed into
//                  EV.events.midi.kick / .snare / .hat as it schedules them -- [t, velocity, 0.05, pitch]
//                  in the piece's time, this loop's only, the way a synthetic twin has its drums. A dropped
//                  track has no MIDI: those lists stay empty (react to its envelope there: env.bflux, hflux).
// Look a list up in draw, every frame (evList is two property reads): __init replaces the whole tree.
const EV = { events: {} };

// ---------------------------------------------------------------- variants
// A piece's alternatives -- three endings, say -- are its variants: piece.json "variants": {axis: {at,
// options, default, note}}, and the same axes given to boot({ variants }) so the page can check what it
// is asked for. draw(t, env, flags) then always gets flags.variant = {axis: option}, every declared axis
// in it (its default where none was asked for):
//   render  from the harness: --variant ending=lamp -> window.__frame({ ..., variant: { ending: 'lamp' } })
//   live    from the URL: ?variant=ending:lamp[,axis:option]
// An axis or option the piece doesn't declare stops a render (the page throws, naming what it has); live,
// it warns on the console and plays the default. A page that declares none passes on what it is given.
function variantParse(s) {                  // "ending:lamp,palette:night" -> { ending: 'lamp', palette: 'night' }
  const out = {};
  for (const part of String(s || '').split(',')) {
    const i = part.indexOf(':'), axis = part.slice(0, i).trim(), option = part.slice(i + 1).trim();
    if (!part.trim()) continue;
    if (i < 0 || !axis || !option) { console.warn(`live.js: ?variant=${s}: "${part}" is not axis:option -- ignored`); continue; }
    out[axis] = option;
  }
  return out;
}
function variantResolve(declared, asked, strict = false) {
  if (typeof asked === 'string') asked = variantParse(asked);
  asked = asked && typeof asked === 'object' ? asked : {};
  if (!declared) return { ...asked };
  const out = {}, axes = Object.keys(declared);
  const bad = (msg, fallback) => {
    if (strict) throw new Error(`variant: ${msg}`);
    console.warn(`live.js: variant: ${msg}${fallback ? ` -- playing ${fallback}` : ' -- ignored'}`);
  };
  for (const axis of axes) {
    const options = declared[axis].options || [], dflt = declared[axis].default ?? options[0];
    if (!options.includes(dflt)) throw new Error(`variant: the piece declares "${axis}" with no options, or a default that isn't one of them`);
    const want = asked[axis];
    if (want == null) out[axis] = dflt;
    else if (options.includes(want)) out[axis] = want;
    else { bad(`${axis} has no option "${want}" (it has ${options.join(', ')})`, dflt); out[axis] = dflt; }
  }
  for (const axis of Object.keys(asked)) if (!axes.includes(axis)) bad(`this piece has no variant axis "${axis}" (it has ${axes.join(', ') || 'none'})`);
  return out;
}

// ---------------------------------------------------------------- ?qa=1: the 9:16 safe frame
// What each vertical-video player's interface covers of a 1080x1920 frame -- its header, the
// caption and username, the like / comment / share column -- as the margins to keep clear of, in
// stage px: docs/PLATFORMS.md (src/kaleidophone/render/platforms.py; cited, mostly third-party
// measurements of overlays that change -- checked 2026-09-30). The Reels figure is Stories' too.
// npm test checks these against docs/PLATFORMS.md.
const SAFE_MARGINS = {
  Reels: { top: 269, bottom: 672, left: 65, right: 65 },
  TikTok: { top: 130, bottom: 484, left: 44, right: 140 },
  Shorts: { top: 192, bottom: 480, left: 0, right: 108 },
};
// The safe frame is the part none of them covers -- on each side, the widest margin: x 65-940
// (Reels on the left, TikTok's buttons on the right), y 269-1248 (Reels' header and caption).
// Anything that must be read goes inside it; picture and texture can bleed past. Drawn over the
// finished frame, in every mode, only with ?qa=1: a QA still shows at once whether a title or a
// face sits under the UI. Stage units, so on a square cover only its top part is in frame.
const SAFE_FRAME = (() => {
  const m = Object.values(SAFE_MARGINS), most = side => Math.max(...m.map(a => a[side]));
  return { x0: most('left'), y0: most('top'), x1: W - most('right'), y1: H - most('bottom') };
})();
function drawSafeFrame() {
  withCtx(MAINCTX, () => {
    const { x0, y0, x1, y1 } = SAFE_FRAME, ink = '#2fe3ff', shade = 'rgba(0,0,0,0.75)';
    ctx.save(); base();
    ctx.lineWidth = 2; ctx.setLineDash([18, 12]);                  // a dark line under a light one: reads on paper and on black
    ctx.strokeStyle = shade; ctx.strokeRect(x0 + 2, y0 + 2, x1 - x0, y1 - y0);
    ctx.strokeStyle = ink; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    ctx.setLineDash([]); ctx.font = '600 22px ui-monospace, Menlo, Consolas, monospace'; ctx.lineWidth = 5; ctx.lineJoin = 'round';
    const label = (s, x, y, baseline) => {
      ctx.textBaseline = baseline; ctx.strokeStyle = shade; ctx.strokeText(s, x, y); ctx.fillStyle = ink; ctx.fillText(s, x, y);
    };
    label(`9:16 SAFE  x ${x0}-${x1}  y ${y0}-${y1}`, x0 + 6, y0 - 8, 'bottom');
    label(`${Object.keys(SAFE_MARGINS).join(' / ')} UI below: caption, buttons`, x0 + 6, y1 + 8, 'top');
    ctx.restore();
  });
}
// the overlay goes on after the piece has drawn -- also when its draw returns a promise
function afterDraw(r) {
  if (!QA) return r;
  if (r && typeof r.then === 'function') return r.then(v => { drawSafeFrame(); return v; });
  drawSafeFrame(); return r;
}

function boot(o) {
  const fontsReady = () => Promise.all((o.fonts || []).map(f => document.fonts.load(f))).then(() => document.fonts.ready);
  const init = pack => { envInit(pack); EV.events = (pack && pack.events) || {}; if (o.init) o.init(pack); };
  // the harness's flags, with the variant checked against the piece's and completed with its defaults
  const flagsOf = p => (o.variants || (p && p.variant != null)) ? { ...p, variant: variantResolve(o.variants, p && p.variant, true) } : p;

  if (MODE === 'render') {
    setSize(+Q.get('w') || 1080, +Q.get('h') || 1920);
    window.__init = init;
    window.__frame = p => { const e = envFrom(p); ENV.now = e; return afterDraw(o.draw(p.t, e, flagsOf(p)) || null); };
    window.__ready = false;
    fontsReady().then(() => { window.__ready = true; });
    return;
  }
  if (MODE === 'cover') {
    const n = +Q.get('size') || 3000;
    setSize(+Q.get('w') || n, +Q.get('h') || n);
    window.__init = init;
    window.__cover = (name, arg = {}) => afterDraw(o.cover ? o.cover(name, arg) : o.draw(+arg.t || 0, envFrom(arg), flagsOf(arg)));
    window.__ready = false;
    fontsReady().then(() => { window.__ready = true; });
    return;
  }
  liveMode(o, fontsReady);
}

// ---------------------------------------------------------------- the live analysis
// The song pack's band edges: src/kaleidophone/audio/envelope.py, BANDS / FLUX_BANDS / VOCAL_BAND.
const LIVE_FPS = 24;                          // the analysis runs at the drawing rate
const LIVE_FFT = 2048, LIVE_SMOOTH = 0.55;    // the AnalyserNode's fftSize and smoothingTimeConstant
const LIVE_GAIN_KEYS = ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux'];
// voc: the band, the contrast clip (dB), the whole-track side-to-mid under which a file is dual
// mono (dB), and the silence floor in the analyser's units (~ the pack's -100 dB mean square)
const LIVE_VOC = { lo: 250, hi: 3500, limit: 30, dualMono: -60, floor: 1.5e-11 };

// One frame of the analysis, from a smoothed magnitude spectrum (bins 0..n-1 of a 2n-point
// transform at `sr`), the previous frame's (or null) and the frame's RMS. The live analyser and
// the pre-scan both measure through here, so a pre-scanned 1.0 means the same thing live.
function liveMeasure(mag, prev, rms, sr) {
  const n = mag.length, hz = sr / 2 / n, bin = f => Math.min(n, Math.max(1, Math.ceil(f / hz)));   // the first bin at or above f
  const b20 = bin(20), b150 = bin(150), b400 = bin(400), b2k = bin(2000), b6k = bin(6000), b16k = bin(16000);
  const sum = (a, b) => { let s = 0; for (let i = a; i < b; i++) s += mag[i]; return s; };
  let num = 0, den = 0, flux = 0, bflux = 0, hflux = 0;
  for (let i = 1; i < n; i++) { num += mag[i] * i; den += mag[i]; }
  if (prev) for (let i = b20; i < b16k; i++) { const d = mag[i] - prev[i]; if (d > 0) { flux += d; if (i < b150) bflux += d; else if (i >= b2k) hflux += d; } }
  return { bass: sum(b20, b150), lowmid: sum(b150, b400), mid: sum(b400, b2k), high: sum(b2k, b6k), air: sum(b6k, b16k),
    rms, flux, bflux, hflux, cent: den > 0 ? num * hz / den / 8000 : 0 };
}
// power in the vocal band of the centre and of the sides: [mid, side]
function liveVocPower(mMid, mSide, sr) {
  const n = mMid.length, hz = sr / 2 / n, a = Math.ceil(LIVE_VOC.lo / hz), b = Math.min(n, Math.ceil(LIVE_VOC.hi / hz));
  let pm = 0, ps = 0;
  for (let i = a; i < b; i++) { pm += mMid[i] * mMid[i]; ps += mSide[i] * mSide[i]; }
  return [pm, ps];
}
// the pack's voc before it is normalised: centre over sides in dB, clipped -- null in silence
function liveVocContrast(pm, ps) {
  return pm > LIVE_VOC.floor ? clamp(10 * Math.log10(pm / Math.max(ps, 1e-30)), -LIVE_VOC.limit, LIVE_VOC.limit) : null;
}
// numpy's default percentile: linear between the two nearest ranks
function livePercentile(a, q) {
  const s = Float64Array.from(a).sort(), n = s.length;
  if (!n) return 0;
  const x = q / 100 * (n - 1), i = Math.floor(x);
  return i + 1 < n ? s[i] + (s[i + 1] - s[i]) * (x - i) : s[n - 1];
}

// In-place radix-2 complex FFT, X[k] = sum x[n] e^(-2 pi i k n / N); N a power of two.
const LIVE_FFT_TABLES = new Map();
function liveFFT(re, im) {
  const n = re.length, h = n >> 1;
  let T = LIVE_FFT_TABLES.get(n);
  if (!T) {                                                         // twiddles e^(-2 pi i k / n) and the bit reversal, once per size
    T = { c: new Float64Array(h), s: new Float64Array(h), rev: new Uint32Array(n) };
    for (let k = 0; k < h; k++) { T.c[k] = Math.cos(2 * Math.PI * k / n); T.s[k] = -Math.sin(2 * Math.PI * k / n); }
    for (let i = 1, j = 0; i < n; i++) { let bit = h; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit; T.rev[i] = j; }
    LIVE_FFT_TABLES.set(n, T);
  }
  const { c, s, rev } = T;
  for (let i = 1; i < n; i++) { const j = rev[i]; if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; } }
  for (let len = 2; len <= n; len <<= 1) {
    const half = len >> 1, step = n / len;
    for (let k = 0, t = 0; k < half; k++, t += step) {
      const wr = c[t], wi = s[t];
      for (let a = k; a < n; a += len) {
        const b = a + half, xr = re[b] * wr - im[b] * wi, xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
      }
    }
  }
}

// The pre-scan: the whole dropped track through the live analysis, before it plays. It is
// Web Audio's AnalyserNode, offline (spec: "FFT Windowing and Smoothing over Time"): the last
// fftSize samples of the mono downmix at each analysis tick, Blackman-windowed (alpha 0.16),
// |FFT| / fftSize, then per bin X = tau * X_previous + (1 - tau) * |FFT| / fftSize. The side
// signal rides in the imaginary part of the same transform, so voc costs nothing extra.
// Returns { ref: each band's 99.5th percentile, voc: { lo, hi } or null, frames }.
async function livePrescan(chans, sr, { fps = LIVE_FPS, N = LIVE_FFT, tau = LIVE_SMOOTH, chunk = 240,
  pause = () => new Promise(r => setTimeout(r, 0)) } = {}) {
  const L = chans[0], R = chans.length > 1 ? chans[1] : null, len = L.length, h = N >> 1;
  const win = new Float64Array(N);
  for (let i = 0; i < N; i++) win[i] = 0.42 - 0.5 * Math.cos(2 * Math.PI * i / N) + 0.08 * Math.cos(4 * Math.PI * i / N);
  const re = new Float64Array(N), im = new Float64Array(N);
  const sm = new Float64Array(h), smS = new Float64Array(h), prev = new Float64Array(h);
  const frames = Math.max(1, Math.floor(len / sr * fps));
  const vals = {}; for (const k of LIVE_GAIN_KEYS) vals[k] = new Float64Array(frames);
  const voc = []; let pmSum = 0, psSum = 0;
  for (let j = 0; j < frames; j++) {
    if (j && j % chunk === 0) await pause();                        // keep the page responsive
    const end = Math.round(j / fps * sr);                           // the window ends at the clock
    let s2 = 0;
    for (let i = 0; i < N; i++) {
      const x = end - N + i, l = x >= 0 && x < len ? L[x] : 0, r = R ? (x >= 0 && x < len ? R[x] : 0) : l;
      const m = 0.5 * (l + r);
      s2 += m * m; re[i] = m * win[i]; im[i] = 0.5 * (l - r) * win[i];
    }
    liveFFT(re, im);
    const g = (1 - tau) / (2 * N);                                  // the halves of one complex FFT: mid and side
    for (let k = 0; k < h; k++) {
      const a = re[k], b = im[k], k2 = k ? N - k : 0, c = re[k2], d = im[k2];
      sm[k] = tau * sm[k] + g * Math.sqrt((a + c) * (a + c) + (b - d) * (b - d));
      smS[k] = tau * smS[k] + g * Math.sqrt((a - c) * (a - c) + (b + d) * (b + d));
    }
    const m = liveMeasure(sm, j ? prev : null, Math.sqrt(s2 / N), sr);
    for (const k of LIVE_GAIN_KEYS) vals[k][j] = m[k];
    if (R) {
      const [pm, ps] = liveVocPower(sm, smS, sr), c = liveVocContrast(pm, ps);
      pmSum += pm; psSum += ps; if (c !== null) voc.push(c);
    }
    prev.set(sm);
  }
  const ref = {};
  for (const k of LIVE_GAIN_KEYS) ref[k] = livePercentile(vals[k], 99.5);
  let vr = null;                                                    // mono, dual mono, a flat contrast: no voc
  if (R && voc.length && 10 * Math.log10(Math.max(psSum, 1e-30) / Math.max(pmSum, 1e-30)) > LIVE_VOC.dualMono) {
    const lo = livePercentile(voc, 5), hi = livePercentile(voc, 99.5);
    if (hi - lo > 1e-9) vr = { lo, hi };
  }
  return { ref, voc: vr, frames };
}

// ---------------------------------------------------------------- live
function liveMode(o, fontsReady) {
  setSize(1080, 1920);
  const fit = () => { const r = Math.min(innerWidth / 1080, innerHeight / 1920); cv.style.width = (1080 * r) + 'px'; cv.style.height = (1920 * r) + 'px'; };
  fit(); addEventListener('resize', fit);
  const hint = document.getElementById('hint');
  const beat = 60 / (o.bpm || 100), bar = 4 * beat, loopLen = () => (buf ? buf.duration : (o.dur || 60));
  let ac = null, bus = null, an = null, anMid = null, anSide = null, buf = null, src = null, pad = null;
  let t0 = 0, running = false, last = -1, lastTick = -1, scale = null;
  const env = envFrom(null), agc = {};
  // ?variant=ending:lamp -- checked against the piece's axes: a mistyped one warns and plays the default
  const variant = variantResolve(o.variants, variantParse(Q.get('variant')), false);

  // The fallback's hits as MIDI events, the way a synthetic twin has its drums: [u, velocity, 0.05, pitch],
  // u in the piece's time unwrapped (seconds since its 0, counting on across loops). Each frame, EV gets
  // this loop's, in loop time; earlier loops' are dropped.
  const HITS = { kick: [], snare: [], hat: [] }, HIT = { kick: [0.9, 36], snare: [0.9, 38], hat: [0.8, 42] };
  let hitsLoop = null, hitsNew = false;
  EV.events = { midi: { kick: [], snare: [], hat: [] } };
  function liveHit(track, at) { HITS[track].push([at - t0, HIT[track][0], 0.05, HIT[track][1]]); hitsNew = true; }
  function clearHits() { for (const k in HITS) HITS[k].length = 0; hitsNew = true; }
  function liveEvents(u) {
    const L = loopLen(), k = u > 0 ? Math.floor(u / L) : 0, off = k * L;
    if (!hitsNew && k === hitsLoop) return;
    hitsNew = false; hitsLoop = k;
    for (const track in HITS) {
      const H = HITS[track], out = EV.events.midi[track];
      while (H.length && H[0][0] < off - 1e-6) H.shift();
      out.length = 0;                                                // in place: a list looked up earlier stays live
      for (const e of H) if (e[0] - off < L - 1e-6) out.push([e[0] - off, e[1], e[2], e[3]]);
    }
  }

  function audio() {
    if (ac) return;
    ac = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = () => { const a = ac.createAnalyser(); a.fftSize = LIVE_FFT; a.smoothingTimeConstant = LIVE_SMOOTH; return a; };
    bus = ac.createGain(); an = analyser(); bus.connect(an); an.connect(ac.destination);   // everything heard goes through `bus`
    // voc: the centre (L+R)/2 and the sides (L-R)/2 of the same signal, each on its own analyser
    const split = ac.createChannelSplitter(2), mid = ac.createGain(), side = ac.createGain(), inv = ac.createGain(), mute = ac.createGain();
    mid.gain.value = 0.5; side.gain.value = 0.5; inv.gain.value = -1; mute.gain.value = 0;
    bus.connect(split); split.connect(mid, 0); split.connect(mid, 1); split.connect(side, 0); split.connect(inv, 1); inv.connect(side);
    anMid = analyser(); anSide = analyser(); mid.connect(anMid); side.connect(anSide);
    anMid.connect(mute); anSide.connect(mute); mute.connect(ac.destination);            // pulled every block, never heard
  }

  // Each analysed frame is kept, keyed by the audio time at the centre of its window; the
  // picture draws the one being heard now, `latency()` behind the clock (the ring holds 4 s).
  const n2 = LIVE_FFT / 2, db = new Float32Array(n2), td = new Float32Array(LIVE_FFT);
  const magM = new Float32Array(n2), magS = new Float32Array(n2);
  let mag = new Float32Array(n2), prev = new Float32Array(n2), havePrev = false;
  const RING = 96, ringT = new Float64Array(RING), ringE = new Array(RING);
  let ringN = 0;
  const latency = () => clamp((ac.outputLatency || 0) + (ac.baseLatency || 0), 0, 1);
  const toMag = (a, out) => { a.getFloatFrequencyData(db); for (let i = 0; i < n2; i++) out[i] = Math.pow(10, db[i] / 20); return out; };
  function resetAnalysis() {
    ringN = 0; havePrev = false; lastTick = -1;
    for (const k of LIVE_GAIN_KEYS) agc[k] = 1e-3;
  }
  function analyse() {
    toMag(an, mag); an.getFloatTimeDomainData(td);
    let s2 = 0; for (let i = 0; i < td.length; i++) s2 += td[i] * td[i];
    const raw = liveMeasure(mag, havePrev ? prev : null, Math.sqrt(s2 / td.length), ac.sampleRate);
    const t = prev; prev = mag; mag = t; havePrev = true;
    const e = {};
    for (const k of LIVE_GAIN_KEYS) {
      // a pre-scanned track: its own 99.5th percentile is 1.0; the fallback: a slow running maximum
      const ref = scale ? scale.ref[k] : (agc[k] = Math.max(agc[k] * 0.9995, raw[k]));
      e[k] = ref > 0 ? clamp(raw[k] / ref) : 0;
    }
    e.cent = clamp(raw.cent); e.voc = 0;
    if (scale && scale.voc) {
      const c = liveVocContrast(...liveVocPower(toMag(anMid, magM), toMag(anSide, magS), ac.sampleRate));
      if (c !== null) e.voc = clamp((c - scale.voc.lo) / (scale.voc.hi - scale.voc.lo));
    }
    ringT[ringN % RING] = ac.currentTime - LIVE_FFT / 2 / ac.sampleRate; ringE[ringN % RING] = e; ringN++;
  }
  // the frame analysed at audio time `at`: linear between the two either side of it
  function recall(at) {
    const n = Math.min(ringN, RING);
    for (let j = ringN - 1; j >= ringN - n; j--) {
      const a = j % RING;
      if (ringT[a] > at) continue;
      if (j === ringN - 1) return ringE[a];
      const b = (j + 1) % RING, u = (at - ringT[a]) / (ringT[b] - ringT[a] || 1), r = {};
      for (const k in ringE[a]) r[k] = ringE[a][k] + (ringE[b][k] - ringE[a][k]) * u;
      return r;
    }
    return n ? ringE[(ringN - n) % RING] : null;
  }

  // The fallback, so clicking the piece without a file still plays it properly. A soft pad on an
  // open fifth in just intonation -- root, fifth, octave, twelfth: every partial falls on the
  // root's own harmonics, so nothing beats against it, and it is neither major nor minor (an
  // equal-tempered major third beat at ~4 Hz against the root's 5th harmonic). A kick on every
  // beat, or on 1 and 3 below 90 BPM (half-time); a noise snare on 2 and 4; hats on the 8ths;
  // scheduled ahead of the clock, and each hit into EV as it is scheduled. All of it goes through
  // one output, so a dropped track stops it.
  const PAD_LEVEL = 0.45, PAD_FADE = 0.04;
  function procedural() {
    audio(); if (ac.state === 'suspended') ac.resume();
    const out = ac.createGain(); out.gain.value = PAD_LEVEL; out.connect(bus);
    const root = o.root || 110, oscs = [];
    for (const [m, d] of [[1, 0], [3 / 2, 0.00025], [2, -0.0002], [3, 0.00015]]) {   // < 1/2 cent apart: partials under 1 kHz drift < 0.3 Hz
      const osc = ac.createOscillator(), g = ac.createGain(), lp = ac.createBiquadFilter();
      osc.type = 'sawtooth'; osc.frequency.value = root * m * (1 + d); lp.type = 'lowpass'; lp.frequency.value = 650; g.gain.value = 0.035;
      osc.connect(lp).connect(g).connect(out); osc.start(); oscs.push(osc);
    }
    const nb = ac.createBuffer(1, ac.sampleRate * 0.3, ac.sampleRate), nd = nb.getChannelData(0), R = mulberry32(11);
    for (let i = 0; i < nd.length; i++) nd[i] = (R() * 2 - 1) * Math.exp(-i / (ac.sampleRate * 0.05));
    const halfTime = (o.bpm || 100) < 90;
    let next = ac.currentTime + 0.1, k = 0;
    t0 = next - (((o.downbeat || 0) % bar) + bar) % bar;           // the first kick is the piece's beat 1
    const p = pad = { out, oscs, timer: 0 };
    resetAnalysis(); clearHits(); running = true;
    (function tick() {
      if (pad !== p) return;                                        // a track was dropped
      while (next < ac.currentTime + 0.4) {
        if (!halfTime || k % 2 === 0) {
          const osc = ac.createOscillator(), g = ac.createGain();
          osc.frequency.setValueAtTime(110, next); osc.frequency.exponentialRampToValueAtTime(42, next + 0.22);
          g.gain.setValueAtTime(0.9, next); g.gain.exponentialRampToValueAtTime(0.001, next + 0.35);
          osc.connect(g).connect(out); osc.start(next); osc.stop(next + 0.4);
          liveHit('kick', next);
        }
        for (const [off, hp, gain] of (k % 2 ? [[0, 1400, 0.45], [beat / 2, 7000, 0.12]] : [[beat / 2, 7000, 0.12]])) {
          const s = ac.createBufferSource(), f = ac.createBiquadFilter(), g2 = ac.createGain();
          s.buffer = nb; f.type = 'highpass'; f.frequency.value = hp; g2.gain.value = gain; s.connect(f).connect(g2).connect(out); s.start(next + off);
          liveHit(hp === 1400 ? 'snare' : 'hat', next + off);
        }
        next += beat; k++;
      }
      p.timer = setTimeout(tick, 150);
    })();
  }
  // a 40 ms fade (no click), then the pad's oscillators stop and its output -- which the hits
  // already scheduled go through too -- comes off the bus
  function stopPad() {
    const p = pad;
    if (!p) return;
    pad = null; clearTimeout(p.timer);
    const now = ac.currentTime, g = p.out.gain;
    g.cancelScheduledValues(now); g.setValueAtTime(PAD_LEVEL, now); g.linearRampToValueAtTime(0, now + PAD_FADE);
    for (const osc of p.oscs) osc.stop(now + PAD_FADE + 0.01);
    setTimeout(() => p.out.disconnect(), (PAD_FADE + 0.06) * 1000);
  }
  function play() {
    audio(); if (ac.state === 'suspended') ac.resume();
    stopPad(); clearHits();                                         // a dropped track has no MIDI: EV's lists go empty
    if (src) { try { src.stop(); } catch (_) { /* already stopped */ } src.disconnect(); }
    src = ac.createBufferSource(); src.buffer = buf; src.loop = true; src.connect(bus);
    t0 = ac.currentTime + 0.05; src.start(t0); resetAnalysis(); running = true;
  }
  function frame() {
    requestAnimationFrame(frame);
    let t = o.idleT || 0.1, heard = 0, u = 0;
    if (running) {
      const tick = Math.floor(ac.currentTime * LIVE_FPS);
      if (tick !== lastTick) { lastTick = tick; analyse(); }        // at the analysis rate, whatever the display's
      heard = ac.currentTime - latency();
      u = heard - t0; t = u > 0 ? u % loopLen() : 0;
    }
    const fi = Math.floor(t * LIVE_FPS); if (fi === last) return; last = fi;
    if (running) { const e = recall(heard); if (e) Object.assign(env, e); ENV.now = env; liveEvents(u); }
    o.draw(t, env, { live: true, variant });
    if (QA) drawSafeFrame();
  }
  cv.addEventListener('click', () => { if (hint) hint.classList.add('off'); if (buf) play(); else if (!running) procedural(); });
  addEventListener('dragover', e => e.preventDefault());
  addEventListener('drop', async e => {
    e.preventDefault(); const f = e.dataTransfer.files[0]; if (!f) return;
    audio(); const b = await ac.decodeAudioData(await f.arrayBuffer());
    const chans = []; for (let c = 0; c < Math.min(2, b.numberOfChannels); c++) chans.push(b.getChannelData(c));
    // the track's own loud passages set its scale; if the scan fails, the running maximum does
    try { scale = await livePrescan(chans, b.sampleRate); } catch (err) { scale = null; console.warn('live.js: pre-scan failed, using auto-gain', err); }
    buf = b; if (hint) hint.classList.add('off'); play();
  });
  fontsReady().then(() => requestAnimationFrame(frame));
}
