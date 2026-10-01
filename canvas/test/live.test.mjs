// lib/live.js's live mode, simulated: core.js + live.js in a node vm against a recording Web
// Audio mock and a recording 2D context, on a virtual clock. No browser, no audio device --
// what is checked is what gets scheduled, connected and drawn, and when.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { CANVAS } from './helpers.mjs';

const LIB = ['core', 'live'].map(n => fs.readFileSync(path.join(CANVAS, 'lib', `${n}.js`), 'utf8')).join('\n');
const SR = 48000, FFT = 2048, BIN = SR / FFT;                     // 23.4375 Hz per analyser bin

// ---------------------------------------------------------------- a recording Web Audio
function webAudio(clock, { outputLatency = 0, baseLatency = 0, spectrum = null, samples = null } = {}) {
  const made = { osc: [], src: [], analyser: [], ac: null };
  class Param {
    constructor(owner, v) { this.owner = owner; this.value = v; this.events = []; }
    setValueAtTime(v, t) { this.events.push(['set', v, t]); return this; }
    linearRampToValueAtTime(v, t) { this.events.push(['linear', v, t]); return this; }
    exponentialRampToValueAtTime(v, t) { this.events.push(['exp', v, t]); return this; }
    cancelScheduledValues(t) { this.events.push(['cancel', t]); return this; }
  }
  class Node {
    constructor(ac) { this.ac = ac; this.outs = new Set(); }
    connect(d) { this.outs.add(d instanceof Param ? d.owner : d); return d; }
    disconnect() { this.outs.clear(); }
  }
  class Source extends Node {
    start(t = 0) { this.startAt = Math.max(t, clock.now); }
    stop(t = 0) { this.stopAt = Math.max(t, clock.now); }
  }
  class Osc extends Source { constructor(ac) { super(ac); this.frequency = new Param(this, 440); made.osc.push(this); } }
  class BufferSource extends Source { constructor(ac) { super(ac); this.buffer = null; this.loop = false; made.src.push(this); } }
  class Gain extends Node { constructor(ac) { super(ac); this.gain = new Param(this, 1); } }
  class Biquad extends Node { constructor(ac) { super(ac); this.type = 'lowpass'; this.frequency = new Param(this, 350); } }
  class Analyser extends Node {
    constructor(ac) { super(ac); this.fftSize = 2048; this.smoothingTimeConstant = 0.8; made.analyser.push(this); }
    get frequencyBinCount() { return this.fftSize / 2; }
    getFloatFrequencyData(a) { const m = spectrum && spectrum(this, clock.now); for (let i = 0; i < a.length; i++) a[i] = m ? 20 * Math.log10(m[i]) : -Infinity; }
    getFloatTimeDomainData(a) { const s = samples && samples(this, clock.now); for (let i = 0; i < a.length; i++) a[i] = s ? s[i] : 0; }
  }
  class AudioBuffer_ {
    constructor(chans, sr) { this.chans = chans; this.sampleRate = sr; this.numberOfChannels = chans.length; this.length = chans[0].length; this.duration = this.length / sr; }
    getChannelData(c) { return this.chans[c]; }
  }
  class AudioContext {
    constructor() { this.sampleRate = SR; this.state = 'running'; this.destination = new Node(this); this.outputLatency = outputLatency; this.baseLatency = baseLatency; made.ac = this; }
    get currentTime() { return clock.now; }
    resume() { return Promise.resolve(); }
    createGain() { return new Gain(this); }
    createOscillator() { return new Osc(this); }
    createBiquadFilter() { return new Biquad(this); }
    createBufferSource() { return new BufferSource(this); }
    createAnalyser() { return new Analyser(this); }
    createChannelSplitter() { return new Node(this); }
    createBuffer(n, len, sr) { return new AudioBuffer_(Array.from({ length: n }, () => new Float32Array(Math.round(len))), sr); }
    decodeAudioData(ab) { return Promise.resolve(ab.decoded); }
  }
  const reaches = (n, target, seen = new Set()) => n === target || (!seen.has(n) && (seen.add(n), [...n.outs].some(o => reaches(o, target, seen))));
  return { AudioContext, AudioBuffer_, made, reaches };
}

// ---------------------------------------------------------------- a page on a virtual clock
const PIECE = extra => `boot({ bpm: 120, dur: 16, idleT: 1.5, ${extra || ''}
  draw(t, env) { ctx.fillStyle = '#101010'; ctx.fillRect(0, 0, W, H); ctx.fillStyle = '#e0d8c8'; ctx.fillRect(100, 100 + 400 * env.bass, 200, 200);
                 __draws.push({ at: __clock.now, t, env: { ...env } }); },
  cover(name) { ctx.fillStyle = '#222'; ctx.fillRect(0, 0, PXW, PXH); } });`;

function page({ search = '', piece = PIECE(), audio = {}, fps = 60, lib = LIB, exports = [] } = {}) {
  const clock = { now: 0 }, timers = [], rafs = [], ctxLog = [], draws = [], on = {}, onCanvas = {}, warns = [];
  let tid = 0;
  const wa = webAudio(clock, audio);
  const ctx2d = new Proxy({}, {
    get: (t, k) => (...a) => { ctxLog.push([k, ...a]); },
    set: (t, k, v) => { ctxLog.push(['=' + String(k), v]); return true; },
  });
  const canvas = { style: {}, width: 0, height: 0, getContext: () => ctx2d, addEventListener: (ty, f) => { onCanvas[ty] = f; } };
  const g = {
    console: { log: console.log, error: console.error, warn: (...a) => warns.push(a.join(' ')) }, Math, Promise, Float32Array, Float64Array, Map, URLSearchParams, Array, Object,
    location: { search },
    document: { getElementById: id => (id === 'c' ? canvas : null), fonts: { load: () => Promise.resolve(), ready: Promise.resolve() } },
    innerWidth: 540, innerHeight: 960, addEventListener: (ty, f) => { on[ty] = f; },
    requestAnimationFrame: f => { rafs.push(f); return rafs.length; },
    setTimeout: (f, ms = 0) => { timers.push({ id: ++tid, at: clock.now + ms / 1000, f }); return tid; },
    clearTimeout: id => { const i = timers.findIndex(x => x.id === id); if (i >= 0) timers.splice(i, 1); },
    AudioContext: wa.AudioContext, __draws: draws, __clock: clock,
  };
  g.window = g;
  vm.createContext(g);
  vm.runInContext(`${lib}\n${piece}\n;globalThis.__lib = { livePrescan, liveFFT, liveVocPower, liveVocContrast, SAFE_FRAME, ${exports.join(', ')} };`, g);
  const flush = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setImmediate(r)); };
  const P = {
    g, clock, wa, ctxLog, draws, warns, lib: g.__lib,
    async run(until) {                                            // the clock, timers and animation frames, to `until` s
      await flush();
      const dt = 1 / fps;
      while (clock.now < until - 1e-9) {
        clock.now = Math.min(until, clock.now + dt);
        for (;;) {
          timers.sort((a, b) => a.at - b.at || a.id - b.id);
          if (!timers.length || timers[0].at > clock.now + 1e-12) break;
          timers.shift().f(); await flush();
        }
        for (const f of rafs.splice(0)) f(clock.now * 1000);
      }
      await flush();
    },
    click() { onCanvas.click({}); },
    async drop(buffer) {                                          // the clock keeps running while the track is scanned
      let done = false;
      on.drop({ preventDefault() { }, dataTransfer: { files: [{ arrayBuffer: async () => ({ decoded: buffer }) }] } }).then(() => { done = true; });
      await flush();
      while (!done) await P.run(clock.now + 1 / fps);
    },
    buffer: (chans, sr = SR) => new wa.AudioBuffer_(chans, sr),
  };
  return P;
}
// kicks are the oscillators with a pitch sweep; snares and hats are noise through a high-pass
const kicks = P => P.wa.made.osc.filter(o => o.frequency.events.length).map(o => o.frequency.events[0][2]);
const hitsThrough = (P, hz) => P.wa.made.src.filter(s => [...s.outs].some(f => f.frequency && f.frequency.value === hz)).map(s => s.startAt);
const near = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol;

// ---------------------------------------------------------------- the fallback's beat
test('live fallback: a kick on every beat for 30 s (it used to stop after the first)', async () => {
  const P = page({ piece: PIECE('downbeat: 0,') });
  await P.run(0.5); P.click(); await P.run(30.5);
  const k = kicks(P);
  assert.ok(k.length >= 60, `${k.length} kicks in 30 s at 120 BPM`);
  assert.ok(near(k[0], 0.6, 0.02) && k[k.length - 1] >= 30.4, `from ${k[0]} to ${k[k.length - 1]}`);
  k.slice(1).forEach((t, i) => assert.ok(near(t - k[i], 0.5), `kick ${i + 1} ${(t - k[i]).toFixed(3)} s after the last`));
  const snares = hitsThrough(P, 1400);                              // on 2 and 4: half-way between kicks
  assert.ok(snares.length >= 29 && snares.every(t => near((t - k[0]) % 1, 0.5)));
});

test('live fallback: half-time below 90 BPM -- kick on 1 and 3, snare on 2 and 4', async () => {
  for (const [bpm, beatsPerKick] of [[80, 2], [89, 2], [90, 1], [128, 1]]) {
    const P = page({ piece: PIECE().replace('bpm: 120', `bpm: ${bpm}`) });
    P.click(); await P.run(20);
    const beat = 60 / bpm, k = kicks(P), s = hitsThrough(P, 1400);
    k.slice(1).forEach((t, i) => assert.ok(near(t - k[i], beatsPerKick * beat), `${bpm} BPM: kicks ${beatsPerKick} beat(s) apart`));
    assert.ok(s.length > 5 && s.every(t => near(((t - k[0]) / beat) % 2, 1, 1e-6)), `${bpm} BPM: snare on 2 and 4`);
  }
});

test('live fallback: the first kick is the piece\'s beat 1', async () => {
  const P = page({ piece: PIECE('downbeat: 0.7,') });              // bar = 2 s: bar 1 starts at 0.7 s of piece time
  P.click(); await P.run(3);
  const k0 = kicks(P)[0], d = P.draws.find(x => x.at >= k0);       // the frame drawn as the first kick sounds
  assert.ok(near(d.t, 0.7, 1 / 24), `piece time ${d.t.toFixed(3)} at the first kick`);
});

test('live fallback: the pad is an open fifth in just intonation -- nothing beats faster than 0.5 Hz', async () => {
  const P = page();
  P.click(); await P.run(0.2);
  const pad = P.wa.made.osc.filter(o => !o.frequency.events.length).map(o => o.frequency.value);
  assert.deepEqual(pad.map(f => Math.round(f / pad[0] * 100) / 100), [1, 1.5, 2, 3]);
  // two partials a few Hz apart are heard as one beating tone: the roughness a pad must not have
  const maxBeat = oscs => {
    const parts = oscs.flatMap((f, i) => Array.from({ length: Math.floor(1000 / f) }, (_, h) => [i, f * (h + 1)]));
    let m = 0;
    for (const [i, a] of parts) for (const [j, b] of parts) if (i < j && Math.abs(a - b) < 20) m = Math.max(m, Math.abs(a - b));
    return m;
  };
  assert.ok(maxBeat(pad) < 0.5, `slowest shimmer ${maxBeat(pad).toFixed(2)} Hz`);
  const before = [[1, -0.003], [1.5, 0.002], [2, 0.004], [2.52, -0.002]].map(([m, d]) => 110 * m * (1 + d));   // the 0.2 voicing
  assert.ok(maxBeat(before) > 4, `the equal-tempered third beat at ${maxBeat(before).toFixed(1)} Hz`);
});

test('dropping a track stops the pad: a fade, its oscillators stopped, its output and scheduled hits off the bus', async () => {
  const P = page();
  P.click(); await P.run(12);
  const padOscs = P.wa.made.osc.filter(o => !o.frequency.events.length);
  const tone = new Float32Array(SR * 4);
  await P.drop(P.buffer([tone, tone]));
  const dropAt = P.clock.now;
  await P.run(16);
  const ac = P.wa.made.ac, audible = n => P.wa.reaches(n, ac.destination);
  assert.ok(padOscs.every(o => o.stopAt <= dropAt + 0.1), 'pad oscillators stopped');
  assert.ok(padOscs.every(o => !audible(o)), 'and off the bus');
  const lp = [...padOscs[0].outs][0], g = [...lp.outs][0], padOut = [...g.outs][0];   // osc -> lowpass -> gain -> the pad's output
  assert.deepEqual(padOut.gain.events.slice(-1)[0].slice(0, 2), ['linear', 0], 'faded, not cut');
  assert.equal(padOut.outs.size, 0, 'the pad output is disconnected');
  const late = kicks(P).filter(t => t > dropAt + 0.4);
  assert.equal(late.length, 0, 'no kick scheduled after the drop');
  const stillSounding = [...P.wa.made.osc, ...P.wa.made.src].filter(s => audible(s) && !(s.stopAt <= dropAt + 0.1) && s.buffer !== P.wa.made.src.at(-1).buffer);
  assert.deepEqual(stillSounding, [], 'nothing but the track reaches the speakers');
  assert.ok(P.wa.made.src.at(-1).loop && audible(P.wa.made.src.at(-1)), 'the track loops, and is heard');
});

// ---------------------------------------------------------------- the pre-scan and the envelope
test('liveFFT is a DFT', () => {
  const { liveFFT } = page().lib, n = 64, re = new Float64Array(n), im = new Float64Array(n);
  for (let i = 0; i < n; i++) { re[i] = Math.sin(i * 1.7) + 0.3 * Math.cos(i * i); im[i] = Math.cos(i * 0.61); }
  const x = [Float64Array.from(re), Float64Array.from(im)];
  liveFFT(re, im);
  for (let k = 0; k < n; k++) {
    let r = 0, m = 0;
    for (let j = 0; j < n; j++) { const a = -2 * Math.PI * k * j / n; r += x[0][j] * Math.cos(a) - x[1][j] * Math.sin(a); m += x[0][j] * Math.sin(a) + x[1][j] * Math.cos(a); }
    assert.ok(near(re[k], r, 1e-9) && near(im[k], m, 1e-9), `bin ${k}`);
  }
});

// A sine at a bin centre, through Web Audio's analyser (Blackman window, |FFT| / fftSize), lands in
// five bins: 0.21 A in its own (a0 / 2), 0.125 A either side (a1 / 4), 0.02 A two away (a2 / 4).
const blackmanLine = (bin, A) => { const m = new Float32Array(FFT / 2); [[0, 0.21], [1, 0.125], [2, 0.02]].forEach(([d, v]) => { m[bin - d] = m[bin + d] = v * A; }); return m; };
const sine = (bin, amp, secs) => { const x = new Float32Array(SR * secs); for (let i = 0; i < x.length; i++) x[i] = amp(i / SR) * Math.sin(2 * Math.PI * bin * BIN * i / SR); return x; };

test('the pre-scan is the AnalyserNode, offline: a bin-centred sine reads the spec\'s Blackman line', async () => {
  const { livePrescan } = page().lib;
  const x = sine(4, () => 0.5, 6);                                  // 93.75 Hz: the bass band
  const s = await livePrescan([x, x], SR, { pause: () => null });
  assert.ok(near(s.ref.bass, 0.5 * 0.5, 1e-4), `bass ${s.ref.bass}: 0.5 A summed over the line`);
  assert.ok(near(s.ref.rms, 0.5 / Math.SQRT2, 1e-4), `rms ${s.ref.rms}`);
  assert.ok(s.ref.mid < 1e-3 * s.ref.bass && s.ref.air < 1e-3 * s.ref.bass, 'nothing leaks into other bands (the onset, under -60 dB)');
  assert.equal(s.frames, 6 * 24);
});

// A track with a quiet intro (-20 dB) and a loud drop. The mock analyser returns the analytic
// spectrum of what the track plays at the centre of its window (the last fftSize samples), so
// what is tested is the scaling and the timing, not the FFT.
function introAndDrop(P, { secs = 20, drop = 10 } = {}) {
  const amp = t => (t < drop ? 0.05 : 0.5), x = sine(4, amp, secs);
  return {
    buffer: P.buffer([x, x]),
    spectrum: (an, now) => {
      const src = P.wa.made.src.at(-1), centre = now - FFT / 2 / SR;
      if (!src || !src.loop || centre < src.startAt || an !== P.wa.made.analyser[0]) return null;
      return blackmanLine(4, amp((centre - src.startAt) % secs));
    },
  };
}

test('a dropped track is scaled by its own loud passages: its quiet intro reads quiet from the first frame', async () => {
  let T;
  const P = page({ audio: { spectrum: (...a) => T.spectrum(...a) } });
  T = introAndDrop(P);
  await P.run(1); await P.drop(T.buffer); const t0 = P.wa.made.src.at(-1).startAt;
  await P.run(t0 + 16);
  const at = t => P.draws.filter(d => d.t > t - 1 && d.t < t + 1).map(d => d.env.bass);
  const intro = at(5), loud = at(14), mean = a => a.reduce((s, v) => s + v, 0) / a.length;
  assert.ok(Math.abs(mean(intro) - 0.1) < 0.01, `intro ${mean(intro).toFixed(3)}: -20 dB under the drop`);
  assert.ok(Math.abs(mean(loud) - 1) < 0.01, `drop ${mean(loud).toFixed(3)}`);
  // what the 0.2 auto-gain made of the same frames: a running maximum from 1e-3, -6 dB a minute
  let agc = 1e-3;
  const before = [...Array(240)].map(() => { agc = Math.max(agc * 0.9995, 0.025); return Math.min(1, 0.025 / agc); });
  assert.ok(before.every(v => v === 1), 'the old gain read the whole intro at 1.0, as loud as the drop');
});

test('the picture waits for the sound: frame and envelope run outputLatency + baseLatency behind the clock', async () => {
  const drawn = async audio => {
    let T;
    const P = page({ audio: { ...audio, spectrum: (...a) => T.spectrum(...a) } });
    T = introAndDrop(P);
    await P.run(1); await P.drop(T.buffer); const t0 = P.wa.made.src.at(-1).startAt;
    await P.run(t0 + 11);
    const lat = (audio.outputLatency || 0) + (audio.baseLatency || 0), ds = P.draws.filter(d => d.at - lat > t0);
    const i = ds.findIndex(x => x.env.bass > 0.5), a = ds[i - 1], b = ds[i], u = (0.5 - a.env.bass) / (b.env.bass - a.env.bass);
    // where the drawn envelope crosses half-way up the drop: in piece time, and on the clock after the drop played
    return { ds, t0, lat, t: a.t + u * (b.t - a.t), late: a.at + u * (b.at - a.at) - (t0 + 10) };
  };
  const frame = 1 / 24, bt = await drawn({ outputLatency: 0.2, baseLatency: 0.01 }), wired = await drawn({});
  assert.ok(bt.ds.every(d => near(d.t, d.at - bt.lat - bt.t0, 1e-9)), 'every frame drawn is the song position being heard');
  assert.ok(near(bt.t, 10, frame), `the drop lands on its own frame: piece time ${bt.t.toFixed(3)}`);
  assert.ok(near(bt.late, 0.21, frame), `...drawn ${bt.late.toFixed(3)} s after it plays on a 0.21 s output: as it is heard`);
  assert.ok(wired.late < frame + 0.03, `on a wired output, ${wired.late.toFixed(3)} s: an analysis frame and half a window`);
});

test('voc is the pack\'s: the vocal band\'s centre over its sides, on the track\'s own range; none for mono or dual mono', async () => {
  const { livePrescan, liveVocPower, liveVocContrast } = page().lib;
  // 0-8 s a voice in the centre (750 Hz, L = R) over a quiet wide part (1500 Hz, L = -R); 8-16 s the reverse
  const n = SR * 16, L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR, v = (t < 8 ? 0.3 : 0.03) * Math.sin(2 * Math.PI * 32 * BIN * t), w = (t < 8 ? 0.03 : 0.3) * Math.sin(2 * Math.PI * 64 * BIN * t);
    L[i] = v + w; R[i] = v - w;
  }
  const s = await livePrescan([L, R], SR, { pause: () => null });
  assert.ok(near(s.voc.lo, -20, 0.5) && near(s.voc.hi, 20, 0.5), `range ${s.voc.lo.toFixed(2)}..${s.voc.hi.toFixed(2)} dB`);
  const norm = c => Math.min(1, Math.max(0, (c - s.voc.lo) / (s.voc.hi - s.voc.lo)));
  const c = (v, w) => liveVocContrast(...liveVocPower(blackmanLine(32, v), blackmanLine(64, w), SR));   // centre: the voice; sides: the wide part
  assert.ok(norm(c(0.3, 0.03)) > 0.95 && norm(c(0.03, 0.3)) < 0.05, 'a centred voice is 1, a wide part 0');
  assert.equal(liveVocContrast(...liveVocPower(new Float32Array(1024), new Float32Array(1024), SR)), null, 'silence has no voc');
  assert.equal((await livePrescan([L, L], SR, { pause: () => null })).voc, null, 'dual mono has none');
  assert.equal((await livePrescan([L], SR, { pause: () => null })).voc, null, 'mono has none');
});

// ---------------------------------------------------------------- ?qa=1
test('?qa=1 draws the 9:16 safe frame after the piece, in every mode; without it nothing drawn changes', async () => {
  const pieceCalls = [['=fillStyle', '#101010'], ['fillRect', 0, 0, 1080, 1920], ['=fillStyle', '#e0d8c8'], ['fillRect', 100, 300, 200, 200]];
  const coverCalls = [['=fillStyle', '#222'], ['fillRect', 0, 0, 600, 600]];
  const drawn = async (search, act) => { const P = page({ search }); await P.run(0.1); await act(P); return P.ctxLog.slice(); };
  const modes = {
    render: ['?render=1&w=540&h=960', P => P.g.__frame({ t: 2, bass: 0.5 }), pieceCalls],
    cover: ['?cover=1&size=600', P => P.g.__cover('title'), coverCalls],
    live: ['', async P => { await P.run(0.2); }, pieceCalls.map(c => (c[0] === 'fillRect' && c[1] === 100 ? ['fillRect', 100, 100, 200, 200] : c))],
  };
  for (const [mode, [search, act, own]] of Object.entries(modes)) {
    const off = await drawn(search, act), on = await drawn(search + (search ? '&' : '?') + 'qa=1', act);
    assert.deepEqual(off, own, `${mode}: without qa, only the piece draws`);
    assert.deepEqual(on.slice(0, off.length), off, `${mode}: with qa, the piece draws the same...`);
    const overlay = on.slice(off.length);
    assert.ok(overlay.some(c => c[0] === 'strokeRect' && c.slice(1).join() === '65,269,875,979'), `${mode}: ...then the safe frame x 65-940, y 269-1248`);
    assert.ok(overlay.some(c => c[0] === 'setLineDash' && c[1].length) && overlay.some(c => c[0] === 'fillText' && c[1] === '9:16 SAFE  x 65-940  y 269-1248'), `${mode}: dashed and labelled`);
    assert.ok(overlay.some(c => c[0] === 'fillText' && c[1] === 'Reels / TikTok / Shorts UI below: caption, buttons'), `${mode}: naming whose interface is under it`);
    assert.deepEqual([overlay[0][0], overlay.at(-1)[0]], ['save', 'restore'], `${mode}: and leaves the context as it found it`);
  }
});

// docs/PLATFORMS.md (generated from src/kaleidophone/render/platforms.py): the safe area of every 9:16
// video platform, as {id: {top, bottom, left, right}} in px of 1080x1920
function platformSafeAreas() {
  const md = fs.readFileSync(path.join(CANVAS, '..', 'docs', 'PLATFORMS.md'), 'utf8'), out = {};
  for (const sec of md.split(/^## /m).slice(1)) {
    const id = sec.slice(0, sec.indexOf('\n')).trim();
    const m = /\*\*safe area:\*\* keep clear of top (\d+), bottom (\d+), left (\d+), right (\d+) px/.exec(sec);
    if (m && /\(video\)/.test(sec) && /\*\*size:\*\* 1080x1920 \(9:16/.test(sec)) out[id] = { top: +m[1], bottom: +m[2], left: +m[3], right: +m[4] };
  }
  return out;
}

test('SAFE_FRAME is what every 9:16 video platform in docs/PLATFORMS.md leaves clear: x 65-940, y 269-1248', () => {
  const doc = platformSafeAreas(), { SAFE_FRAME, SAFE_MARGINS } = page({ exports: ['SAFE_MARGINS'] }).lib;
  const plain = x => JSON.parse(JSON.stringify(x)), key = a => `top ${a.top}, bottom ${a.bottom}, left ${a.left}, right ${a.right}`;
  assert.ok(['instagram-reel', 'tiktok', 'youtube-short'].every(id => doc[id]), `docs/PLATFORMS.md has Reels, TikTok and Shorts with safe areas (found: ${Object.keys(doc).join(', ')})`);
  assert.deepEqual(Object.values(plain(SAFE_MARGINS)).map(key).sort(), [...new Set(Object.values(doc).map(key))].sort(),
    'lib/live.js SAFE_MARGINS must be the safe areas docs/PLATFORMS.md gives the 9:16 video platforms: copy them from there');
  const most = side => Math.max(...Object.values(doc).map(a => a[side]));
  assert.deepEqual(plain(SAFE_FRAME), { x0: most('left'), y0: most('top'), x1: 1080 - most('right'), y1: 1920 - most('bottom') }, 'on each side, the widest margin');
  // the numbers docs/CREATIVE-GUIDE.md quotes ("The frame, in numbers"): change both together
  assert.deepEqual(plain(SAFE_FRAME), { x0: 65, y0: 269, x1: 940, y1: 1248 });
});

// ---------------------------------------------------------------- the song's events, live
// A piece that records what EV holds each time it draws.
const EVPIECE = extra => `boot({ bpm: 120, dur: 16, idleT: 1.5, ${extra || ''}
  draw(t, env, flags) {
    const K = evList(EV, 'midi.kick'), S = evList(EV, 'midi.snare'), Hh = evList(EV, 'midi.hat');
    __draws.push({ at: __clock.now, t, flags: JSON.parse(JSON.stringify(flags)), kick: K.map(e => e[0]), snare: S.map(e => e[0]), hat: Hh.map(e => e[0]),
      rows: [K[0], S[0], Hh[0]].map(e => e && e.slice(1)), nth: evNth(K, t), since: evSince(K, t), pulse: evPulse(K, t, 0, 0.1) });
  } });`;
const drawsOf = P => P.draws.map(d => JSON.parse(JSON.stringify(d)));      // out of the vm's realm; Infinity -> null
const onGrid = (xs, step, phase = 0) => xs.every(x => near(((x - phase) / step) - Math.round((x - phase) / step), 0, 1e-6));
const sorted = xs => xs.every((x, i) => !i || x >= xs[i - 1]);

test('live fallback: the kicks, snares and hats it schedules are the piece\'s events, in its own time', async () => {
  for (const [bpm, kickEvery] of [[120, 1], [80, 2]]) {
    const P = page({ piece: EVPIECE('downbeat: 0,').replace('bpm: 120', `bpm: ${bpm}`) });
    await P.run(0.5);
    assert.deepEqual(drawsOf(P).at(-1).kick, [], `${bpm} BPM: nothing before the click`);
    P.click(); await P.run(10);
    const beat = 60 / bpm, k = kicks(P), draws = drawsOf(P), d = draws.at(-1);
    // the audio's kicks, on the piece's clock (downbeat 0: the first kick is its 0) -- every one EV has, and no other
    assert.deepEqual(d.kick.map(x => +x.toFixed(6)), k.map(x => +(x - k[0]).toFixed(6)).filter(x => x < 16), `${bpm} BPM: EV's kicks are the ones heard`);
    assert.ok(onGrid(d.kick, kickEvery * beat) && onGrid(d.snare, 2 * beat, beat) && onGrid(d.hat, beat, beat / 2), `${bpm} BPM: kicks on ${kickEvery === 1 ? 'every beat' : '1 and 3'}, snares on 2 and 4, hats on the "and"s`);
    assert.ok(sorted(d.kick) && sorted(d.snare) && sorted(d.hat));
    assert.ok(draws.some(x => x.kick.length && x.kick.at(-1) > x.t), 'scheduled ahead, like a pack\'s future');
    assert.deepEqual(d.rows, [[0.9, 0.05, 36], [0.9, 0.05, 38], [0.8, 0.05, 42]], 'velocity, duration, General MIDI pitch');
    for (const x of draws.filter(x => x.at > 1.5)) assert.equal(x.nth, Math.floor(x.t / (kickEvery * beat) + 1e-6) + 1, `${bpm} BPM: kicks so far at t ${x.t}`);
    const right = draws.filter(x => x.at > 1 && x.since < 1 / 24), away = draws.filter(x => x.at > 1 && x.since > 0.35);
    assert.ok(right.length > 5 && right.every(x => x.pulse > 0.5) && away.every(x => x.pulse < 0.03), `${bpm} BPM: evPulse jumps on the kicks heard, and only on them`);
  }
});

test('live fallback: EV holds this loop\'s hits, in loop time; a dropped track has no MIDI', async () => {
  const P = page({ piece: EVPIECE('downbeat: 0,') });
  P.click(); await P.run(20);
  const second = drawsOf(P).filter(x => x.at > 17 && x.at < 20);
  assert.ok(second.length > 30);
  for (const d of second) {
    assert.ok(d.kick[0] === 0 || near(d.kick[0], 0, 1e-6), 'the loop starts over at 0');
    assert.ok(d.kick.every(x => x < 16) && d.kick.length <= 32, 'one loop: 8 bars, 32 kicks at most');
    assert.equal(d.nth, Math.floor(d.t / 0.5 + 1e-6) + 1, `counted from this loop's start (t ${d.t})`);
  }
  const tone = new Float32Array(SR * 4);
  await P.drop(P.buffer([tone, tone]));
  const at = P.clock.now;
  await P.run(at + 2);
  const after = drawsOf(P).filter(x => x.at > at);
  assert.ok(after.length > 10 && after.every(x => !x.kick.length && !x.snare.length && !x.hat.length && x.pulse === 0 && x.since === null), 'no events at all');
});

// ---------------------------------------------------------------- variants
const ENDINGS = `variants: { ending: { at: 14, options: ['droste', 'lamp', 'exit'], default: 'droste' } },`;

test('variantParse / variantResolve: axis:option pairs, checked against what the piece declares', () => {
  const P = page({ exports: ['variantParse', 'variantResolve'] }), { variantParse, variantResolve } = P.lib;
  const plain = x => JSON.parse(JSON.stringify(x));
  assert.deepEqual(plain(variantParse('ending:lamp, palette : night')), { ending: 'lamp', palette: 'night' });
  assert.deepEqual(plain(variantParse('')), {}); assert.deepEqual(plain(variantParse(null)), {});
  assert.deepEqual(plain(variantParse('lamp,:x,a:,ending:exit')), { ending: 'exit' });
  assert.equal(P.warns.length, 3, 'each malformed entry warns');
  const D = { ending: { options: ['droste', 'lamp', 'exit'], default: 'droste' } };
  assert.deepEqual(plain(variantResolve(D, undefined)), { ending: 'droste' }, 'the default when nothing is asked');
  assert.deepEqual(plain(variantResolve(D, { ending: 'exit' }, true)), { ending: 'exit' });
  assert.deepEqual(plain(variantResolve(D, 'ending:lamp', true)), { ending: 'lamp' }, 'the URL\'s form too');
  P.warns.length = 0;
  assert.deepEqual(plain(variantResolve(D, { ending: 'lmap' })), { ending: 'droste' });
  assert.match(P.warns[0], /ending has no option "lmap" \(it has droste, lamp, exit\) -- playing droste/);
  assert.deepEqual(plain(variantResolve(D, { palette: 'night' })), { ending: 'droste' });
  assert.match(P.warns[1], /no variant axis "palette" \(it has ending\)/);
  assert.throws(() => variantResolve(D, { ending: 'lmap' }, true), /variant: ending has no option "lmap" \(it has droste, lamp, exit\)$/);
  assert.throws(() => variantResolve(D, { palette: 'night' }, true), /no variant axis "palette"/);
  assert.deepEqual(plain(variantResolve(undefined, { any: 'thing' }, true)), { any: 'thing' }, 'a piece that declares none passes it on');
  assert.deepEqual(plain(variantResolve(undefined, undefined, true)), {});
  assert.deepEqual(plain(variantResolve({ a: { options: ['x', 'y'] } }, {})), { a: 'x' }, 'no default: the first option');
  assert.throws(() => variantResolve({ a: { options: ['x'], default: 'z' } }, {}), /declares "a" with no options, or a default that isn't one/);
});

test('live mode: ?variant=ending:lamp reaches draw; a mistyped one warns and plays the default', async () => {
  const drawn = async search => { const P = page({ search, piece: EVPIECE(ENDINGS) }); await P.run(0.3); return { flags: drawsOf(P).at(-1).flags, warns: P.warns }; };
  const lamp = await drawn('?variant=ending:lamp');
  assert.deepEqual([lamp.flags, lamp.warns.length], [{ live: true, variant: { ending: 'lamp' } }, 0]);
  assert.deepEqual((await drawn('')).flags, { live: true, variant: { ending: 'droste' } });
  const typo = await drawn('?variant=ending:lmap');
  assert.deepEqual(typo.flags.variant, { ending: 'droste' });
  assert.equal(typo.warns.length, 1); assert.match(typo.warns[0], /"lmap" \(it has droste, lamp, exit\) -- playing droste/);
  const P = page({ search: '?variant=ending:lamp' }); await P.run(0.3);              // a piece with no variants: nothing to check against
  assert.equal(P.warns.length, 0);
});

test('render mode: __init fills EV from the pack; p.variant is checked and completed, and an unknown option stops the render', async () => {
  const P = page({ search: '?render=1&w=540&h=960', piece: EVPIECE(ENDINGS) });
  await P.run(0.1);
  P.g.__init({ fps: 100, rms: [0, 1], events: { midi: { kick: [[1, 1, 0.05, 36], [1.5, 0.5, 0.05, 36]] } } });
  P.g.__frame({ t: 1.05, rms: 0.5 });
  let d = drawsOf(P).at(-1);
  assert.deepEqual(d.kick, [1, 1.5]); assert.equal(d.nth, 1); assert.ok(near(d.since, 0.05, 1e-9)); assert.ok(near(d.pulse, Math.exp(-0.5), 1e-9));
  assert.deepEqual(d.flags, { t: 1.05, rms: 0.5, variant: { ending: 'droste' } }, 'the harness\'s flags, with the variant completed');
  P.g.__frame({ t: 2, variant: { ending: 'exit' } });
  assert.deepEqual(drawsOf(P).at(-1).flags.variant, { ending: 'exit' });
  assert.throws(() => P.g.__frame({ t: 2, variant: { ending: 'lmap' } }), /variant: ending has no option "lmap" \(it has droste, lamp, exit\)/);
  assert.throws(() => P.g.__frame({ t: 2, variant: { palette: 'x' } }), /no variant axis "palette"/);
  P.g.__init({ fps: 100, rms: [0, 1] });                                               // a pack without events: empty lists
  P.g.__frame({ t: 1.05 });
  d = drawsOf(P).at(-1);
  assert.deepEqual([d.kick, d.nth, d.since, d.pulse], [[], 0, null, 0]);
  // a piece that declares no variants gets exactly what the harness sent, as before
  const Q = page({ search: '?render=1&w=540&h=960', piece: EVPIECE() });
  await Q.run(0.1);
  Q.g.__frame({ t: 3, card: true });
  assert.deepEqual(drawsOf(Q).at(-1).flags, { t: 3, card: true });
  Q.g.__frame({ t: 3, variant: { ending: 'lamp' } });
  assert.deepEqual(drawsOf(Q).at(-1).flags.variant, { ending: 'lamp' });
});

// ---------------------------------------------------------------- the pieces' variants
const PIECES = path.join(CANVAS, 'pieces');
const NAME = /^[a-z][a-z0-9-]*$/;                                    // safe in ?variant=a:b,c:d and --variant a=b

test('every piece\'s "variants" is valid: axes and options named plainly, a start inside the song, a default among the options', () => {
  let n = 0;
  for (const id of fs.readdirSync(PIECES)) {
    const f = path.join(PIECES, id, 'piece.json');
    if (!fs.existsSync(f)) continue;
    const spec = JSON.parse(fs.readFileSync(f, 'utf8'));
    if (spec.variants === undefined) continue;
    n++;
    assert.ok(spec.variants && typeof spec.variants === 'object' && !Array.isArray(spec.variants) && Object.keys(spec.variants).length, `${id}: "variants" is {axis: {...}}`);
    for (const [axis, v] of Object.entries(spec.variants)) {
      assert.match(axis, NAME, `${id}: axis "${axis}"`);
      assert.ok(typeof v.at === 'number' && v.at >= 0 && v.at < spec.grid.dur, `${id}.${axis}: "at" is song seconds inside the piece (got ${v.at})`);
      assert.ok(Array.isArray(v.options) && v.options.length >= 2 && new Set(v.options).size === v.options.length, `${id}.${axis}: two or more options, each once`);
      for (const o of v.options) assert.match(o, NAME, `${id}.${axis}: option "${o}"`);
      assert.ok(v.options.includes(v.default), `${id}.${axis}: the default "${v.default}" is one of the options`);
      assert.ok(v.note === undefined || (typeof v.note === 'string' && v.note.trim()), `${id}.${axis}: "note" is words`);
    }
  }
  assert.ok(n >= 1, 'the template declares its endings');
});

test('the template: three endings from bar 7, and the page declares the same variants as piece.json', async () => {
  const spec = JSON.parse(fs.readFileSync(path.join(PIECES, 'template', 'piece.json'), 'utf8'));
  assert.deepEqual({ ...spec.variants.ending, note: undefined }, { at: 14, options: ['droste', 'lamp', 'exit'], default: 'droste', note: undefined });
  const lib = [...spec.lib.map(n => path.join(CANVAS, 'lib', `${n}.js`)), ...fs.readdirSync(path.join(PIECES, 'template', 'src')).sort().map(f => path.join(PIECES, 'template', 'src', f))]
    .map(f => fs.readFileSync(f, 'utf8')).join('\n');
  const P = page({ lib, piece: '', exports: ['VARIANTS'], search: '?variant=ending:exit' });   // loads and boots; draws nothing yet
  const onPage = JSON.parse(JSON.stringify(P.lib.VARIANTS));
  for (const [axis, v] of Object.entries(spec.variants)) {
    assert.deepEqual({ at: onPage[axis].at, options: onPage[axis].options, default: onPage[axis].default }, { at: v.at, options: v.options, default: v.default }, `the page's "${axis}" is piece.json's`);
  }
  assert.deepEqual(Object.keys(onPage), Object.keys(spec.variants));
  assert.equal(P.warns.length, 0, 'the page knows ?variant=ending:exit');
});
