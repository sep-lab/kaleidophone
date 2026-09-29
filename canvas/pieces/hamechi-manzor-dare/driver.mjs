// HAMECHI MANZOR DARE is the one STATEFUL piece: the swarm, the fire, the feedback trails and
// the mask state machine all carry over from frame to frame, and it draws from a seeded RNG.
// So a window is rendered in one worker, in order, starting WARMUP seconds early (frames that
// are drawn but not written, so trails and fire are alive on frame 0), and the harness -- not
// the piece -- decides when masks go on and off, so a render is repeatable:
//   calm 8-beat phrases wear a mask, the loudest phrases and the single biggest hit go raw.
// This is the canvas toolkit's generalized harness, written right after the release. It is NOT
// frame-identical to the delivered reel, whose one-off harness wasn't kept (measured: same mask at
// frame 60, 28.3 dB PSNR; by frame 450 the mask schedule has diverged) -- see
// docs/case-studies/hamechi-manzor-dare.md.
const WARMUP = 3.0;

function beatsOf(pack) {
  if (pack.beats && pack.beats.length) return pack.beats;
  // flux peaks: mean + 1.6 sd over the last 0.72 s, above 0.10, 0.28 s refractory
  const N = pack.rms.length, flux = pack.flux.map(v => v / 255), beats = []; let last = -9;
  for (let i = 0; i < N; i++) {
    const win = flux.slice(Math.max(0, i - 72), i + 1);
    const mean = win.reduce((s, x) => s + x, 0) / win.length;
    const sd = Math.sqrt(win.reduce((s, x) => s + (x - mean) ** 2, 0) / win.length);
    const t = i / 100;
    if (flux[i] > mean + 1.6 * sd && flux[i] > 0.10 && t - last > 0.28) { beats.push(t); last = t; }
  }
  return beats;
}

export default {
  stateful: true,
  warmup: WARMUP,
  query({ w, h, seed }) { return { render: 1, w, h, seed: seed ?? 7 }; },
  coverQuery({ size }) { return { cover: 1, size }; },

  // Called once per window, before any frame: snap t0, schedule masks and cards.
  plan(pack, { t0, dur, fps, mode = 'reel', snap = true }) {
    const N = pack.rms.length;
    const at = (arr, t) => arr[Math.max(0, Math.min(N - 1, Math.round(t * 100)))] / 255;
    const beats = beatsOf(pack);
    const T0 = snap ? beats.reduce((p, c) => Math.abs(c - t0) < Math.abs(p - t0) ? c : p, beats[0]) : t0;
    const inWin = beats.filter(b => b >= T0 - WARMUP && b <= T0 + dur + 0.5);
    const winBeats = beats.filter(b => b >= T0 && b <= T0 + dur);
    const phrases = [];
    for (let i = 0; i < winBeats.length; i += 8) {
      const s = winBeats[i], e = winBeats[Math.min(i + 8, winBeats.length - 1)];
      let acc = 0, c = 0; for (let t = s; t < e; t += 0.05) { acc += at(pack.rms, t); c++; }
      phrases.push({ s, e, rms: c ? acc / c : 0 });
    }
    const nMask = Math.max(3, Math.round(phrases.length * 0.5));
    const maskSet = new Set([...phrases].sort((a, b) => a.rms - b.rms).slice(0, nMask).map(p => p.s));
    let bigBeat = winBeats[0] || T0, bigV = 0;
    for (const b of winBeats) { const v = pack.flux[Math.round(b * 100)] || 0; if (v > bigV) { bigV = v; bigBeat = b; } }
    this._p = { N, at, T0, dur, fps, mode, inWin, phrases, maskSet, bigBeat, bi: 0 };
    return { t0: T0 };
  },

  frame(t, pack, opts) {
    const P = this._p, dt = 1 / P.fps, shape = (v, g) => Math.min(1, Math.pow(v, g));
    let beat = false;
    while (P.bi < P.inWin.length && P.inWin[P.bi] <= t) { beat = true; P.bi++; }
    let forceMaskOn = false, forceMaskOff = false;
    if (beat) {
      for (const ph of P.phrases) if (Math.abs(ph.s - t) < dt) (P.maskSet.has(ph.s) ? forceMaskOn = true : forceMaskOff = true);
      if (Math.abs(P.bigBeat - t) < dt) { forceMaskOff = true; forceMaskOn = false; }
    }
    const rel = t - P.T0;
    let titleCard = 0, endCard = 0;
    if (P.mode === 'reel') { if (rel < 1.6) titleCard = 1; else if (rel < 2.4) titleCard = Math.max(0, 1 - (rel - 1.6) / 0.8); }
    if (rel > P.dur - 1.4 && rel <= P.dur) endCard = Math.min(1, (rel - (P.dur - 1.4)) / 0.9);
    if (P.mode === 'none') { titleCard = 0; endCard = 0; }
    return {
      dt, beat, noAutoMask: true, forceMaskOn, forceMaskOff, titleCard, endCard,
      bass: shape(P.at(pack.bass, t), 1.25), mid: shape(P.at(pack.mid, t), 1.1),
      high: shape(P.at(pack.high, t), 1.1), rms: shape(P.at(pack.rms, t), 1.0),
    };
  },

  async cover(page, name) { await page.evaluate(v => window.__cover(v), name); },
};
