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

function page({ search = '', piece = PIECE(), audio = {}, fps = 60 } = {}) {
  const clock = { now: 0 }, timers = [], rafs = [], ctxLog = [], draws = [], on = {}, onCanvas = {};
  let tid = 0;
  const wa = webAudio(clock, audio);
  const ctx2d = new Proxy({}, {
    get: (t, k) => (...a) => { ctxLog.push([k, ...a]); },
    set: (t, k, v) => { ctxLog.push(['=' + String(k), v]); return true; },
  });
  const canvas = { style: {}, width: 0, height: 0, getContext: () => ctx2d, addEventListener: (ty, f) => { onCanvas[ty] = f; } };
  const g = {
    console, Math, Promise, Float32Array, Float64Array, Map, URLSearchParams, Array, Object,
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
  vm.runInContext(`${LIB}\n${piece}\n;globalThis.__lib = { livePrescan, liveFFT, liveVocPower, liveVocContrast, SAFE_FRAME };`, g);
  const flush = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setImmediate(r)); };
  const P = {
    g, clock, wa, ctxLog, draws, lib: g.__lib,
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
    assert.ok(overlay.some(c => c[0] === 'strokeRect' && c.slice(1).join() === '54,220,972,1260'), `${mode}: ...then the safe frame x 54-1026, y 220-1480`);
    assert.ok(overlay.some(c => c[0] === 'setLineDash' && c[1].length) && overlay.some(c => c[0] === 'fillText' && /9:16 SAFE/.test(c[1])), `${mode}: dashed and labelled`);
    assert.deepEqual([overlay[0][0], overlay.at(-1)[0]], ['save', 'restore'], `${mode}: and leaves the context as it found it`);
  }
});
