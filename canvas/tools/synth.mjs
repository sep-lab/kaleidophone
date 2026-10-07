#!/usr/bin/env node
// synth.mjs -- synthetic song packs: the grid and the shape of a song, none of its sound.
//
//   node tools/synth.mjs <piece> [...]            -> out/songs/<piece>.songpack.json from pieces/<piece>/synthetic.json
//   node tools/synth.mjs --all
//   node tools/synth.mjs --twin real.songpack.json --sections 0,32.26,42.26 [--bpm 120 --downbeat 0.255] > synthetic.json
//   node tools/synth.mjs --twin real.songpack.json --piece <id> [--sections ...]
//        re-measure a piece's twin in place: its grid, its section boundaries and everything written
//        by hand (patterns, voc windows, events, chords, beatGrid, keys, alias, quantize) stay; its levels are replaced
//
// Why this exists: a real song pack is derived from unreleased audio, so it never enters the
// repository (docs/decisions/0003, 0007). But a piece is a function of (time, envelope), and to
// run it -- in CI, on the gallery page, on a stranger's machine -- it needs an envelope. A synthetic
// pack keeps what the piece is choreographed to (tempo, first downbeat, section boundaries, and how
// each section's envelopes are distributed) and generates everything else.
//
// The spec (pieces/<id>/synthetic.json):
//   bpm, downbeat, dur, seed   the grid, the length, and the seed every generated detail comes from
//   beatGrid {bpm, downbeat}   optional: the beat list a driver sees, when it runs on its own grid
//   keys, quantize             which envelopes to write; bytes (0..255) instead of 0..1, like the toolkit-era packs
//   sections [{from, kick, snare, hats, crash, <envelope>: level}]
//       kick 'all' | '1-3' | 'none' (default 'all'); snare, hats true | false (default true);
//       crash true | false (default: every section after the first that has a kick or a snare opens on one).
//       A level is a number -- the section's mean -- or [mean, p95, max], the section's distribution,
//       which the generator reproduces: the section's biggest hit reaches the max, 5 % of its frames sit
//       at or above the p95, the rest average out to the mean. A mean alone gets the peaks real sections
//       with that mean have (defaultPeaks). Envelopes: bass lowmid mid high air rms flux bflux hflux cent
//       voc. `energy` is the rms mean's old name; a band a section leaves out falls back to it.
//   voc [[from, to, amp]]      vocal-ish syllables, 4-7 a second, into `voc` and the mid band
//   events {name: {key: [[from, to, rate_hz, strength]]}}   onsets on the song's 16th grid, humanised by at
//                              most 20 ms; above the grid's rate some steps add a 32nd, below it some rest.
//                              A fifth item, a list of pitches, gives every onset in the window a third
//                              column, [t, s, pitch], drawn from that list: made up, never the song's notes
//                              (see synthEvents)
//   alias {name: envelope}     also write an envelope under the name a piece reads it by: {"vstem": "voc"}
//                              writes the twin's voc again as "vstem" (a vocal envelope taken from a stem);
//                              --twin then measures that envelope's levels from the real pack's "vstem"
//   chords {track, progression, every}   a chord progression on the grid, for a piece that moves on chord
//                              changes: events.chords.<track> = [[t, 1, "Am"], ...], one chord on every bar
//                              line ("every": "bar", the default; "beat"; or a number of bars), cycling
//                              through "progression" from the first downbeat. Made up, like the drums:
//                              never the song's own harmony (see chordEvents)
//   stems true                 also write stems.drums / .bass / .vocals / .other, from what made each frame
//                              of each band, normalised like a real pack's stems (see stemsOf)
//
// What gets played: kicks (and the odd syncopated one), snares on 2 and 4 with ghost notes, hats on
// the 8ths with accented off-beats, pickups, drop-outs and an open hat into the bar, a crash on section
// starts, bass notes and chords that move on the bar, phrase-long swells. Then every envelope is mapped,
// section by section, onto its level (levelMap). The map keeps order: the biggest hit stays the biggest.
// The drums it played are in the pack too, as MIDI: events.midi.kick / .snare / .hat / .crash; and with
// "chords", the chord changes, events.chords.<track>. Neither touches the envelopes: a spec without
// "chords" makes the same pack, byte for byte, as before there were any.
//
// `--twin` measures a real pack per section -- [mean, p95, max] of each envelope, rounded to 0.05 -- and
// that spec is the only thing that crosses from private to public: coarse numbers, nothing per hit.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { CANVAS, parseArgs, die, loadPiece, listPieces } from './lib/common.mjs';

const BANDS = ['bass', 'lowmid', 'mid', 'high', 'air'];
// what a level can be given for, and what --twin measures (in this order)
export const ENVELOPES = [...BANDS, 'rms', 'flux', 'bflux', 'hflux', 'cent', 'voc'];
// songpack/1's envelopes (src/kaleidophone/audio/envelope.py) -- a pack carries these unless `keys` trims it
const PACK_KEYS = [...BANDS, 'rms', 'rmsdb', 'flux', 'bflux', 'hflux', 'cent', 'voc'];
// songpack/1 lets the three flux envelopes run to 1.5 (envelope.py, _FLUX_CEILING), so the biggest hit
// in a song stands out from an ordinary strong one instead of both clipping at 1
export const FLUX_CEILING = 1.5;
const ceilingOf = k => (k === 'flux' || k === 'bflux' || k === 'hflux') ? FLUX_CEILING : 1;
const CENTROID_HZ = 8000; // envelope.py's _CENTROID_SCALE: a centroid stored in Hz reads as cent = Hz / 8000
const TWIN_STEP = 0.05;   // what --twin rounds to: the shape, not the sound

// mulberry32: small, fast, and the same numbers on every machine
function rng(seed) {
  let a = seed >>> 0;
  return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
// one independent stream per part (drums, bassline, each voc window, ...), so editing one part of a
// spec doesn't reshuffle every other generated detail
function stream(seed, name) {
  let h = (0x811c9dc5 ^ (seed >>> 0)) >>> 0;
  for (const c of String(name)) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  return rng(h);
}
const clamp = (v, a = 0, b = 1) => v < a ? a : v > b ? b : v;
// the first frame at or after t: a section owns its frames from here on, and so does its crash
export const firstFrame = (t, fps) => Math.max(0, Math.ceil(t * fps - 1e-6));

function sectionAt(sections, t) {
  for (let i = sections.length - 1; i >= 0; i--) if (t >= sections[i].from) return i;
  return 0;
}
const drumsIn = sec => (sec.kick ?? 'all') !== 'none' || sec.snare !== false;

// ------------------------------------------------------------------------------------------ levels
// a level: a number (the mean) or [mean, p95, max]
function levelOf(sec, k) {
  let v = sec[k];
  if (v == null && k === 'rms') v = sec.energy;
  if (v == null) return null;
  const [mean, p95, max] = Array.isArray(v) ? v : [v];
  return { mean, p95, max };
}

// The peaks for a level given as a mean alone: about where real sections with that mean have them.
// Fitted by hand to the per-section band and rms statistics of the four released songs' packs
// (mean 0.05 -> p95 0.2, max 0.8; 0.2 -> 0.64 / 0.91; 0.45 -> 0.82 / 0.96; 0.8 -> 0.97 / 0.99).
export function defaultPeaks(mean) {
  const m = clamp(mean);
  const p95 = Math.min(1, m + (1 - m) * Math.min(0.85, 0.45 + 0.5 * m) * Math.min(1, m / 0.15));
  return { mean: m, p95, max: p95 + 0.75 * (1 - p95) * Math.min(1, m / 0.05) };
}
function complete(lv) {
  const d = defaultPeaks(lv.mean), p95 = lv.p95 ?? d.p95;
  return { mean: lv.mean, p95, max: lv.max ?? Math.max(p95, d.max) };
}

// The map that carries a section's raw values onto its level, keeping their order. The top 5 % of
// frames rise in a straight line from the p95 to the max; the rest rise from a floor picked so the
// section averages out to its mean -- bent into a curve when even a floor of zero would leave it too
// loud (a sparse kick: mostly nothing, then a hit).
export function levelMap(values, level, ceil = 1) {
  const s = Float64Array.from(values).sort(), n = s.length;
  const M = clamp(level.mean, 0, ceil), P = clamp(level.p95, 0, ceil), X = clamp(level.max, P, ceil);
  if (!n || !(s[n - 1] - s[0] > 1e-12)) return () => M;   // nothing to shape: a flat section sits at its mean
  const r0 = s[0], r1 = s[n - 1];
  let r95 = s[Math.round(0.95 * (n - 1))], nb = 0;
  while (nb < n && s[nb] < r95) nb++;
  if (!nb) {   // most frames tie at the bottom: they are the body, everything above them the top
    while (nb < n && s[nb] <= r0) nb++;
    const L = clamp((M * n - (n - nb) * (P + X) / 2) / nb, 0, P), T = s[nb];
    return x => x <= r0 ? L : clamp(P + (X - P) * (x - T) / (r1 - T || 1), 0, ceil);
  }
  const top = x => r1 > r95 ? P + (X - P) * (x - r95) / (r1 - r95) : X;
  let sumTop = 0; for (let i = nb; i < n; i++) sumTop += top(s[i]);
  const want = (M * n - sumTop) / nb, span = r95 - r0;      // what the body has to average
  // the body's shape, from 512 evenly spaced ranks (plenty for a mean)
  const m = Math.min(nb, 512), u = new Float64Array(m);
  for (let k = 0; k < m; k++) u[k] = (s[Math.floor((k + 0.5) * nb / m)] - r0) / span;
  let ub = 0; for (let k = 0; k < m; k++) ub += u[k] / m;
  const meanPow = e => { let a = 0; for (let k = 0; k < m; k++) a += Math.pow(u[k], e); return P * a / m; };
  let L = ub < 1 ? (want - P * ub) / (1 - ub) : P, g = 1;
  if (L < 0) {
    L = 0;
    let lo = 1, hi = 2;
    while (meanPow(hi) > want && hi < 512) { lo = hi; hi *= 2; }
    for (let it = 0; it < 24; it++) { const mid = (lo + hi) / 2; if (meanPow(mid) > want) lo = mid; else hi = mid; }
    g = (lo + hi) / 2;
  } else if (L > P) L = P;
  return x => x >= r95 ? clamp(top(x), 0, ceil) : L + (P - L) * (g === 1 ? Math.max(0, (x - r0) / span) : Math.pow(Math.max(0, (x - r0) / span), g));
}

// every frame of `raw`, mapped section by section onto its level. `fallback(sec)` gives the level of
// a section that has none (null: leave that section's raw values as they are). A section's map takes
// over on its first frame -- at the boundary, not before it: a drop is not anticipated (the old
// generator faded levels in over the half second before each boundary).
function shapeTrack(raw, sections, key, fps, fallback) {
  const n = raw.length, out = new Float64Array(n), ceil = ceilingOf(key);
  const starts = sections.map((s, i) => i === 0 ? 0 : Math.min(n, firstFrame(s.from, fps)));
  const ends = starts.map((_, i) => i + 1 < starts.length ? starts[i + 1] : n);
  const maps = sections.map((s, i) => {
    const lv = levelOf(s, key) ?? fallback(s);
    return lv && ends[i] > starts[i] ? levelMap(raw.subarray(starts[i], ends[i]), complete(lv), ceil) : null;
  });
  for (let i = 0; i < sections.length; i++) {
    const f = maps[i] || (x => x);
    for (let j = starts[i]; j < ends[i]; j++) out[j] = clamp(f(raw[j]), 0, ceil);
  }
  return out;
}

// the flux envelopes' level when a section gives none: songpack/1's numbers (the one release analysed
// with it, rounded) -- with drums a mean near 0.15, a p95 near 0.45 and the section's biggest onset at
// the ceiling; without them far less, and less again in a quiet section
function defaultFlux(key, sec, rmsMean) {
  const on = key === 'bflux' ? (sec.kick ?? 'all') !== 'none' : key === 'hflux' ? (sec.snare !== false || sec.hats !== false) : (drumsIn(sec) || sec.hats !== false);
  if (on) return key === 'bflux' ? { mean: 0.25, p95: 0.7, max: FLUX_CEILING } : { mean: 0.15, p95: 0.45, max: FLUX_CEILING };
  const q = clamp(rmsMean / 0.3);
  return key === 'bflux' ? { mean: 0.1 * q, p95: 0.3 * q, max: 0.8 * q } : { mean: 0.08 * q, p95: 0.2 * q, max: 0.5 * q };
}

// ------------------------------------------------------------------------------------------- the band
// The drum hits, as [time, velocity] lists. Every step draws the same random numbers whatever the
// pattern, so switching one section's kick off doesn't reshuffle the hats of every later section.
export function drumEvents(spec) {
  const sections = sectionsOf(spec), fps = spec.fps || 100, R = stream(spec.seed ?? 7, 'drums');
  const six = 60 / spec.bpm / 4, t0 = spec.downbeat ?? 0;
  const ev = { kick: [], snare: [], hat: [], open: [], crash: [] };
  for (let s = 0, t = t0; t < spec.dur; s++, t = t0 + s * six) {
    const sec = sections[sectionAt(sections, t)], step = s % 16, beat = step >> 2, sub = step & 3;
    const kick = sec.kick ?? 'all', snare = sec.snare !== false, hats = sec.hats !== false;
    const r = [R(), R(), R(), R()];
    if (sub === 0 && (kick === 'all' || (kick === '1-3' && beat % 2 === 0))) ev.kick.push([t, Math.min(1, 0.8 + 0.2 * r[0] + (step === 0 ? 0.08 : 0))]);
    else if (kick !== 'none' && step === 10 && r[0] < 0.2) ev.kick.push([t, 0.5 + 0.25 * r[1]]);        // the odd syncopated kick
    if (snare && sub === 0 && beat % 2 === 1) ev.snare.push([t, 0.85 + 0.15 * r[1]]);
    else if (snare && (step === 6 || step === 15) && r[1] < 0.12) ev.snare.push([t, 0.25 + 0.2 * r[2]]); // ghost notes
    if (hats) {
      if (step === 14 && r[2] < 0.3) ev.open.push([t, 0.85 + 0.15 * r[3]]);                                // an open hat into the next bar
      else if (sub % 2 === 0) { if (r[2] > 0.04) ev.hat.push([t, (sub === 2 ? 0.95 : 0.7) * (0.85 + 0.3 * r[3])]); } // off-beats lean, the odd drop-out
      else if (r[2] < 0.08) ev.hat.push([t, 0.45 * (0.85 + 0.3 * r[3])]);                                  // a 16th pickup
    }
  }
  sections.forEach((sec, i) => { if (sec.crash ?? (i > 0 && drumsIn(sec))) ev.crash.push([firstFrame(sec.from, fps) / fps, 1]); });
  return ev;
}

// The drums as the Session engine writes a MIDI part, one track per drum: events.midi.<track> =
// [[t, velocity 0..1, duration, pitch], ...] sorted by time. General MIDI's drum notes: kick 36, snare 38,
// closed hat 42 and open hat 46 (both in `hat`), crash 49. Every hit lasts 0.05 s; times are rounded to
// 0.1 ms, like the pack's beats.
export const MIDI_DRUMS = { kick: 36, snare: 38, hat: 42, open: 46, crash: 49 };
export function drumMidi(ev) {
  const note = (pitch, dur = 0.05) => ([t, v]) => [+t.toFixed(4), +Math.min(1, v).toFixed(3), dur, pitch];
  const hat = [...ev.hat.map(note(MIDI_DRUMS.hat)), ...ev.open.map(note(MIDI_DRUMS.open))].sort((a, b) => a[0] - b[0]);
  return { kick: ev.kick.map(note(MIDI_DRUMS.kick)), snare: ev.snare.map(note(MIDI_DRUMS.snare)), hat, crash: ev.crash.map(note(MIDI_DRUMS.crash)) };
}

// The chord changes, as a Session writes a chord track: { <track>: [[t, 1, "Am"], ...] }, sorted by time.
// spec.chords = { track (default "keys"), progression: ["Am", "F", "C", "G"], every: "bar" | "beat" | bars }:
// a chord on every bar line of the song's grid (or beat, or every n bars) inside [0, dur), going round the
// progression from the first downbeat -- a bar line before it plays the end of the progression, a pickup
// into chord 1. Times are rounded to 0.1 ms, like the drums. It draws no random numbers and touches no
// envelope. A progression is something to choreograph to (the template's droste turns on each change),
// made up for the twin like its drums: never the real song's harmony, which says something about the sound.
export function chordEvents(spec) {
  const c = spec.chords, bad = msg => new Error(`a spec's "chords" ${msg}`);
  if (!c || typeof c !== 'object' || Array.isArray(c)) throw bad('must be {"track": "keys", "progression": ["Am", "F", ...], "every": "bar"}');
  const track = c.track ?? 'keys', prog = c.progression, every = c.every ?? 'bar';
  if (typeof track !== 'string' || !/^[A-Za-z0-9_-]+$/.test(track)) throw bad(`"track" must be a name of letters, digits, - and _ (it is a key: events.chords.<track>), got ${JSON.stringify(track)}`);
  if (!Array.isArray(prog) || !prog.length || !prog.every(x => typeof x === 'string' && x.trim())) throw bad(`"progression" must be a non-empty list of chord names, got ${JSON.stringify(prog)}`);
  const beat = 60 / spec.bpm, bar = 4 * beat;
  const P = every === 'bar' ? bar : every === 'beat' ? beat : typeof every === 'number' && every > 0 && Number.isFinite(every) ? every * bar : null;
  if (!P) throw bad(`"every" must be "bar", "beat" or a number of bars, got ${JSON.stringify(every)}`);
  const t0 = spec.downbeat ?? 0, n = prog.length, out = [];
  for (let k = Math.ceil(-t0 / P - 1e-9); t0 + k * P < spec.dur - 1e-9; k++) out.push([+(t0 + k * P).toFixed(4), 1, prog[((k % n) + n) % n]]);
  return { [track]: out };
}

// one decaying hit per event: flat for `hold` seconds, then exponential decay `decay`; it peaks on the
// frame nearest its onset, the way an analysed pack's attack does
function hits(n, fps, list, hold, decay) {
  const out = new Float64Array(n);
  for (const [t, v] of list) {
    const i0 = Math.round(t * fps);
    for (let i = Math.max(0, i0); i < n; i++) {
      const dt = (i - i0) / fps, e = dt < hold ? 1 : Math.exp(-(dt - hold) / decay);
      if (e < 1e-3) break;
      out[i] += v * e;
    }
  }
  return out;
}
// a level that changes every `len` seconds (a bass note, a chord, a phrase's swell) and glides there
function steps(n, fps, t0, len, lo, hi, glide, R) {
  const out = new Float64Array(n), a = 1 - Math.exp(-1 / (fps * glide));
  let k = null, target = 0, v = null;
  for (let i = 0; i < n; i++) {
    const kk = Math.floor((i / fps - t0) / len);
    if (kk !== k) { k = kk; target = lo + (hi - lo) * R(); }
    v = v === null ? target : v + (target - v) * a;
    out[i] = v;
  }
  return out;
}
// slow noise, about +-0.1
function wander(n, R) { const out = new Float64Array(n); let v = 0; for (let i = 0; i < n; i++) { v = v * 0.985 + (R() - 0.5) * 0.03; out[i] = v; } return out; }

// vocal-ish activity: syllables at 4-7 a second inside the given windows
function syllables(spec, n, fps) {
  const voc = new Float64Array(n);
  for (const [a, b, amp = 0.8] of spec.voc || []) {
    const R = stream(spec.seed ?? 7, `voc:${a}`);
    for (let t = a; t < b;) {
      const per = 1 / (4 + 3 * R()), len = Math.min(per * (0.55 + 0.3 * R()), b - t), v = amp * (0.6 + 0.4 * R());
      for (let i = Math.max(0, Math.floor(t * fps)); i < Math.min(n, Math.ceil((t + len) * fps)); i++) {
        const u = (i / fps - t) / len; voc[i] = Math.max(voc[i], v * Math.sin(Math.PI * clamp(u)));
      }
      t += per;
    }
  }
  return voc;
}

function sectionsOf(spec) {
  const s = spec.sections && spec.sections.length ? spec.sections : [{ from: 0, energy: 0.5 }];
  return s.map(x => ({ ...x, from: +x.from }));
}

// ----------------------------------------------------------------------------------------- the pack
export function synthesize(spec) {
  if (!(spec.bpm > 0) || !(spec.dur > 0)) throw new Error('a synthetic spec needs bpm and dur');
  const fps = spec.fps || 100, dur = spec.dur, n = Math.ceil(dur * fps) + 1, seed = spec.seed ?? 7;
  const period = 60 / spec.bpm, bar = 4 * period, t0 = spec.downbeat ?? 0;
  const sections = sectionsOf(spec);
  const ev = drumEvents(spec);

  // the raw band: beds that move on the bar, hits on the grid, a swell per phrase
  const phrase = steps(n, fps, t0, 4 * bar, 0.8, 1.1, 0.6, stream(seed, 'phrase'));
  const bassline = steps(n, fps, t0, bar / 2, 0.35, 1, 0.03, stream(seed, 'bassline'));
  const chords = steps(n, fps, t0, bar, 0.5, 1, 0.08, stream(seed, 'chords'));
  const wob = Object.fromEntries(BANDS.map(b => [b, wander(n, stream(seed, `wander:${b}`))]));
  const kB = hits(n, fps, ev.kick, 0.05, 0.16), kL = hits(n, fps, ev.kick, 0.01, 0.05), kM = hits(n, fps, ev.kick, 0, 0.012);
  const sL = hits(n, fps, ev.snare, 0.005, 0.05), sM = hits(n, fps, ev.snare, 0.01, 0.09), sH = hits(n, fps, ev.snare, 0.005, 0.07), sA = hits(n, fps, ev.snare, 0, 0.04);
  const hH = hits(n, fps, ev.hat, 0, 0.02), hA = hits(n, fps, ev.hat, 0, 0.035);
  const oH = hits(n, fps, ev.open, 0.01, 0.12), oA = hits(n, fps, ev.open, 0.02, 0.18);
  const cM = hits(n, fps, ev.crash, 0.01, 0.25), cH = hits(n, fps, ev.crash, 0.02, 0.8), cA = hits(n, fps, ev.crash, 0.03, 1.2);
  const syl = syllables(spec, n, fps);
  const raw = Object.fromEntries(BANDS.map(b => [b, new Float64Array(n)]));
  for (let i = 0; i < n; i++) {
    const g = phrase[i];
    raw.bass[i] = g * (0.5 * bassline[i] * (1 + wob.bass[i]) + kB[i]);
    raw.lowmid[i] = g * (0.5 * chords[i] * (1 + wob.lowmid[i]) + 0.45 * kL[i] + 0.55 * sL[i]);
    raw.mid[i] = g * (0.55 * chords[i] * (1 + wob.mid[i]) + 0.12 * kM[i] + 0.8 * sM[i] + 0.25 * cM[i]) + 0.6 * syl[i];
    raw.high[i] = g * (0.2 * (1 + wob.high[i]) + 0.75 * sH[i] + 0.35 * hH[i] + 0.55 * oH[i] + cH[i]);
    raw.air[i] = g * (0.15 * (1 + wob.air[i]) + 0.3 * sA[i] + 0.85 * hA[i] + 0.8 * oA[i] + cA[i]);
  }

  // every band onto its level, section by section; a band a section leaves out follows its rms mean
  const rmsMean = sec => levelOf(sec, 'rms')?.mean ?? 0.4;
  const Y = {};
  for (const b of BANDS) Y[b] = shapeTrack(raw[b], sections, b, fps, sec => ({ mean: rmsMean(sec) }));
  // voc: the syllables, over a faint bed so a section with a level but no syllables still moves
  const vocLevels = sections.some(s => s.voc != null);
  const vocRaw = vocLevels ? Float64Array.from(syl, (v, i) => v + 0.08 * (0.5 + wob.mid[i])) : syl;
  const voc = vocLevels ? shapeTrack(vocRaw, sections, 'voc', fps, () => null) : syl;

  // derived: rms, flux (positive change, all bands), bass flux, high flux, centroid -- then each onto its level
  // A real mix is never still, so its flux never rests at zero between the hits: a faint, lightly
  // smoothed noise floor under the onsets gives each section's body something to spread over.
  const rms0 = new Float64Array(n), fl0 = new Float64Array(n), bf0 = new Float64Array(n), hf0 = new Float64Array(n), ce0 = new Float64Array(n);
  const Rf = stream(seed, 'flux-floor'), floor = [0, 0, 0];
  for (let i = 0; i < n; i++) {
    rms0[i] = 0.32 * Y.bass[i] + 0.22 * Y.lowmid[i] + 0.3 * Y.mid[i] + 0.12 * Y.high[i] + 0.04 * Y.air[i];
    for (let k = 0; k < 3; k++) floor[k] = 0.5 * floor[k] + 0.01 * Rf();
    if (i) {
      const d = b => Math.max(0, Y[b][i] - Y[b][i - 1]);
      fl0[i] = d('bass') + d('lowmid') + d('mid') + d('high') + d('air') + floor[0]; bf0[i] = d('bass') + floor[1]; hf0[i] = d('high') + d('air') + floor[2];
    }
    ce0[i] = clamp((0.2 * Y.mid[i] + 0.5 * Y.high[i] + 0.9 * Y.air[i]) / (Y.bass[i] + Y.mid[i] + Y.high[i] + Y.air[i] + 1e-6));
  }
  const bandMean = sec => ({ mean: 0.32 * (levelOf(sec, 'bass')?.mean ?? 0.4) + 0.22 * (levelOf(sec, 'lowmid')?.mean ?? 0.4) + 0.3 * (levelOf(sec, 'mid')?.mean ?? 0.4) + 0.12 * (levelOf(sec, 'high')?.mean ?? 0.4) + 0.04 * (levelOf(sec, 'air')?.mean ?? 0.4) });
  const rms = shapeTrack(rms0, sections, 'rms', fps, bandMean);
  const flux = shapeTrack(fl0, sections, 'flux', fps, sec => defaultFlux('flux', sec, rmsMean(sec)));
  const bflux = shapeTrack(bf0, sections, 'bflux', fps, sec => defaultFlux('bflux', sec, rmsMean(sec)));
  const hflux = shapeTrack(hf0, sections, 'hflux', fps, sec => defaultFlux('hflux', sec, rmsMean(sec)));
  const cent = shapeTrack(ce0, sections, 'cent', fps, () => null);
  const rmsdb = Float64Array.from(rms, v => -60 + 54 * v);   // a plausible dB scale for a synthetic song

  // the grid, as songpack/1 writes it: every beat in [0, dur), and the loudest minute
  const bg = spec.beatGrid || { bpm: spec.bpm, downbeat: t0 }, bp = 60 / bg.bpm, beats = [];
  const beat0 = bg.downbeat - Math.floor(bg.downbeat / bp + 1e-9) * bp;
  for (let k = 0, t = beat0; t < dur; k++, t = beat0 + k * bp) beats.push(+t.toFixed(4));
  const arrays = { ...Y, rms, rmsdb, flux, bflux, hflux, cent, voc };
  const pack = {
    kaleidophone: 'songpack/1', synthetic: true, fps, dur: +dur.toFixed(3),
    bpm: +bg.bpm.toFixed(3), beat0: +beat0.toFixed(4), period: +bp.toFixed(6), beats, downbeat: +(+bg.downbeat).toFixed(4),
    loudest: loudest(rmsdb, bg.downbeat, 4 * bp, dur, fps),
  };
  const q = spec.quantize; // e.g. 255 for the toolkit-era packs that stored bytes
  if (q) pack.quantize = q;
  const store = k => Array.from(arrays[k], k === 'rmsdb' ? v => Math.round(v * 10) / 10 : q ? v => Math.round(clamp(v) * q) : v => Math.round(v * 1000) / 1000);
  for (const k of spec.keys || PACK_KEYS) if (arrays[k]) pack[k] = store(k);
  for (const [k, src] of aliasesOf(spec, pack)) pack[k] = pack[src];
  if (spec.events && spec.events.midi) throw new Error('a spec\'s "events" can\'t have a group named "midi": events.midi is the drums the twin plays');
  if (spec.events && spec.events.chords) throw new Error('a spec\'s "events" can\'t have a group named "chords": events.chords is the chord progression (the spec\'s "chords")');
  pack.events = { ...(spec.events ? synthEvents(spec) : {}), midi: drumMidi(ev), ...(spec.chords != null ? { chords: chordEvents(spec) } : {}) };
  if (spec.stems) {
    // the same parts the raw bands were summed from, kept apart
    const P = Object.fromEntries(STEMS.map(s => [s, {}]));
    for (const s of STEMS) for (const b of BANDS) P[s][b] = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const g = phrase[i], D = P.drums, O = P.other;
      D.bass[i] = g * kB[i]; D.lowmid[i] = g * (0.45 * kL[i] + 0.55 * sL[i]); D.mid[i] = g * (0.12 * kM[i] + 0.8 * sM[i] + 0.25 * cM[i]);
      D.high[i] = g * (0.75 * sH[i] + 0.35 * hH[i] + 0.55 * oH[i] + cH[i]); D.air[i] = g * (0.3 * sA[i] + 0.85 * hA[i] + 0.8 * oA[i] + cA[i]);
      P.bass.bass[i] = g * 0.5 * bassline[i] * (1 + wob.bass[i]);
      O.lowmid[i] = g * 0.5 * chords[i] * (1 + wob.lowmid[i]); O.mid[i] = g * 0.55 * chords[i] * (1 + wob.mid[i]);
      O.high[i] = g * 0.2 * (1 + wob.high[i]); O.air[i] = g * 0.15 * (1 + wob.air[i]);
      P.vocals.mid[i] = 0.6 * syl[i];
    }
    const S = stemsOf(P, Y, rms, rmsdb, flux, bflux, hflux);
    pack.stems = {};
    for (const s of STEMS) {
      pack.stems[s] = {};
      for (const k of (spec.keys || PACK_KEYS).filter(k => k !== 'voc')) {
        pack.stems[s][k] = Array.from(S[s][k], k === 'rmsdb' ? v => Math.round(v * 10) / 10 : q ? v => Math.round(clamp(v) * q) : v => Math.round(v * 1000) / 1000);
      }
    }
  }
  return pack;
}

// Stems, as the Session engine writes them for real ones (docs/CONFIG-SCHEMA.md): per stem, the master's
// envelopes (the spec's `keys`, voc aside), each normalised on its own like the master's -- its own 5th
// percentile -> 0 and 99.5th -> 1, the fluxes divided by their 99.5th and clipped at 1.5 -- with digital
// silence left out of the percentiles and reading 0. Where they come from: the generator knows what made
// every frame (the drums' hits, the bassline, the chords and the bed under them, the syllables), so before
// it is normalised a stem's band is the master's band times that stem's share of it -- loud where the master
// is loud and that part is playing, silent where the part doesn't play (no voc windows: a silent vocals
// stem). rms the same way, by the weighted bands the master's rms is made of; rmsdb the master's plus the
// share in dB; the fluxes by each stem's share of the frame's rise; cent each stem's own centroid.
export const STEMS = ['drums', 'bass', 'vocals', 'other'];
const RMS_W = { bass: 0.32, lowmid: 0.22, mid: 0.3, high: 0.12, air: 0.04 };   // how the master's rms weighs the bands
function stemsOf(parts, Y, rms, rmsdb, flux, bflux, hflux) {
  const n = rms.length, out = {};
  for (const s of STEMS) {
    out[s] = {};
    for (const k of [...BANDS, 'rms', 'rmsdb', 'flux', 'bflux', 'hflux', 'cent']) out[s][k] = new Float64Array(n);
  }
  for (const b of BANDS) for (let i = 0; i < n; i++) {
    let tot = 0; for (const s of STEMS) tot += parts[s][b][i];
    if (tot > 0) for (const s of STEMS) out[s][b][i] = Y[b][i] * parts[s][b][i] / tot;
  }
  const w = {}, up = {}, upB = {}, upH = {};
  for (let i = 0; i < n; i++) {
    let W = 0, U = 0, UB = 0, UH = 0;
    for (const s of STEMS) {
      const B = out[s], d = b => (i ? Math.max(0, B[b][i] - B[b][i - 1]) : 0);
      w[s] = 0; for (const b of BANDS) w[s] += RMS_W[b] * B[b][i];
      up[s] = d('bass') + d('lowmid') + d('mid') + d('high') + d('air'); upB[s] = d('bass'); upH[s] = d('high') + d('air');
      W += w[s]; U += up[s]; UB += upB[s]; UH += upH[s];
    }
    for (const s of STEMS) {
      const B = out[s], share = W > 0 ? w[s] / W : 0, den = B.bass[i] + B.mid[i] + B.high[i] + B.air[i];
      B.rms[i] = rms[i] * share;
      B.rmsdb[i] = share > 0 ? Math.max(-100, rmsdb[i] + 20 * Math.log10(share)) : -100;
      B.flux[i] = U > 1e-12 ? flux[i] * up[s] / U : flux[i] * share;      // a frame with no rise: shared like the level
      B.bflux[i] = UB > 1e-12 ? bflux[i] * upB[s] / UB : bflux[i] * share;
      B.hflux[i] = UH > 1e-12 ? hflux[i] * upH[s] / UH : hflux[i] * share;
      B.cent[i] = den > 1e-6 ? clamp((0.2 * B.mid[i] + 0.5 * B.high[i] + 0.9 * B.air[i]) / (den + 1e-6)) : 0;
    }
  }
  for (const s of STEMS) {
    for (const k of [...BANDS, 'rms']) stemNormalise(out[s][k], false);
    for (const k of ['flux', 'bflux', 'hflux']) stemNormalise(out[s][k], true);
  }
  return out;
}
// in place: the sounding frames' 5th percentile -> 0 and 99.5th -> 1 (a flux: its 99.5th -> 1, up to 1.5); 0 stays 0
function stemNormalise(a, isFlux) {
  const on = Float64Array.from(a.filter(v => v > 0)).sort(), n = on.length;
  if (!n) return a;
  const at = q => on[Math.min(n - 1, Math.round(q * (n - 1)))], lo = isFlux ? 0 : at(0.05), hi = at(0.995);
  for (let i = 0; i < a.length; i++) {
    if (!(a[i] > 0)) { a[i] = 0; continue; }
    a[i] = hi - lo > 1e-12 ? clamp((a[i] - lo) / (hi - lo), 0, isFlux ? FLUX_CEILING : 1) : 1;
  }
  return a;
}

// the loudest 60 s, starting on the bar line nearest it (envelope.py's `_loudest_window`: a default
// reel that opens where a phrase does). Bar lines run both ways from the downbeat, 4 beats of the
// pack's own grid apart, so a loud stretch before bar 1 still snaps to a bar.
function loudest(rmsdb, downbeat, bar, dur, fps) {
  const width = 60 * fps;
  if (dur <= 60 || rmsdb.length <= width) return { start: 0, len: +dur.toFixed(3) };
  const c = new Float64Array(rmsdb.length + 1);
  for (let i = 0; i < rmsdb.length; i++) c[i + 1] = c[i] + Math.pow(10, rmsdb[i] / 10);
  let best = -Infinity, bi = 0;
  for (let i = 0; i + width <= rmsdb.length; i++) if (c[i + width] - c[i] > best) { best = c[i + width] - c[i]; bi = i; }
  const latest = dur - 60;
  let start = bi / fps;
  if (bar > 0) {
    const first = Math.ceil((0 - downbeat) / bar - 1e-9), last = Math.floor((latest - downbeat) / bar + 1e-9);
    if (first <= last) start = downbeat + Math.min(Math.max(Math.round((start - downbeat) / bar), first), last) * bar;
  }
  return { start: +clamp(start, 0, latest).toFixed(3), len: 60 };
}

// spec.alias = { name: envelope } -> [[name, envelope], ...], each envelope one the pack has just stored
function aliasesOf(spec, pack) {
  const a = spec.alias;
  if (a == null) return [];
  const bad = msg => new Error(`a spec's "alias" ${msg}`);
  if (typeof a !== 'object' || Array.isArray(a)) throw bad('must be {"name": "envelope"}, e.g. {"vstem": "voc"}');
  return Object.entries(a).map(([k, src]) => {
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(k)) throw bad(`names a key ${JSON.stringify(k)}: use letters, digits and _ (it is a top-level key of the pack)`);
    if (k in pack || k === 'events' || k === 'stems' || ENVELOPES.includes(k)) throw bad(`can't name "${k}": the pack has a key of that name already`);
    if (!ENVELOPES.includes(src)) throw bad(`"${k}" must name an envelope (${ENVELOPES.join(', ')}), got ${JSON.stringify(src)}`);
    if (!Array.isArray(pack[src])) throw bad(`"${k}" names "${src}", which the spec's "keys" leave out of the pack`);
    return [k, src];
  });
}

// events: { name: { key: [[from, to, rate_hz, strength, pitches?]] } } -> { name: { key: [[t, s], ...] } }
// Onsets sit on the song's 16th grid, humanised by at most 20 ms (triangular). A window whose rate is
// above the grid's adds a 32nd to some steps and one below it rests on some, so it averages `rate`;
// its first step always sounds. A window with a list of pitches gives each of its onsets one, drawn from
// the list, as a third column: [t, s, pitch]. The pitches come from a stream of their own, so the onsets
// are the same with or without them -- and the list is made up for the twin, like its drums and chords:
// never the song's own notes. (A piece that reads a pitch, ⛈️'s CQT bin, would otherwise read undefined.)
function synthEvents(spec) {
  const out = {}, six = 60 / spec.bpm / 4, t0 = spec.downbeat ?? 0;
  for (const [name, groups] of Object.entries(spec.events)) {
    out[name] = {};
    for (const [key, wins] of Object.entries(groups)) {
      const R = stream(spec.seed ?? 7, `events:${name}:${key}`), Rp = stream(spec.seed ?? 7, `events:${name}:${key}:pitch`), L = [];
      for (const [a, b, rate = 6, s = 0.9, pitches] of wins) {
        if (pitches !== undefined && !(Array.isArray(pitches) && pitches.length && pitches.every(Number.isFinite))) {
          throw new Error(`a spec's events.${name}.${key} window [${a}, ${b}, ...]: its pitches must be a non-empty list of numbers, got ${JSON.stringify(pitches)}`);
        }
        const pitch = pitches ? () => pitches[Math.floor(Rp() * pitches.length)] : null;
        // 19.5 ms, so an onset is still within 20 ms of its step once rounded to the ms; kept inside the window
        const push = t => L.push([+clamp(t + (R() + R() - 1) * 0.0195, a, b - 0.001).toFixed(3), +(s * (0.65 + 0.7 * R())).toFixed(2), ...(pitch ? [pitch()] : [])]);
        const per = rate * six;   // onsets per 16th
        for (let k = Math.ceil((a - t0) / six - 1e-9), first = true; t0 + k * six < b; k++, first = false) {
          const g = t0 + k * six;
          if (first || R() < per) push(g);
          if (per > 1 && R() < per - 1 && g + six / 2 < b) push(g + six / 2);
        }
      }
      out[name][key] = L;
    }
  }
  return out;
}

export function songPath(id) { return path.join(CANVAS, 'out', 'songs', `${id}.songpack.json`); }

export function synthFor(id) {
  const piece = loadPiece(id);
  const specFile = path.join(piece.dir, 'synthetic.json');
  if (!fs.existsSync(specFile)) die(`${id} has no synthetic.json`);
  const pack = synthesize(JSON.parse(fs.readFileSync(specFile, 'utf8')));
  const f = songPath(id);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, JSON.stringify(pack));
  return f;
}

// ------------------------------------------------------------------------------------------- --twin
// mean, p95 and max of some frames (the p95 by nearest rank, as the generator reads it)
export function distribution(values) {
  const s = Float64Array.from(values).sort(), n = s.length;
  if (!n) return { mean: 0, p95: 0, max: 0 };
  let m = 0; for (const v of s) m += v;
  return { mean: m / n, p95: s[Math.round(0.95 * (n - 1))], max: s[n - 1] };
}

// A real pack's envelopes as 0..1 (flux up to 1.5), whatever era it comes from: toolkit packs stored
// bytes, and some store the centroid in Hz. With `alias` ({"vstem": "voc"}, a spec's), an envelope is read
// from the key the piece reads it by, when the pack has that key.
export function readEnvelopes(P, { alias } = {}) {
  const fps = P.fps || P.sr || P.sr_env || 100, env = {};
  const peak = a => { let m = -Infinity; for (const v of a) if (v > m) m = v; return m; };
  const bytes = P.quantize === 255 || peak(P.rms.slice(0, 4000)) > 1.5;
  const has = k => Array.isArray(P[k]) && P[k].length > 0;
  for (const k of ENVELOPES) {
    const from = Object.keys(alias || {}).find(n => alias[n] === k && has(n));
    const a = P[from ?? k]; if (!Array.isArray(a) || !a.length) continue;
    const scale = bytes ? 255 : k === 'cent' && peak(a) > 1.5 ? CENTROID_HZ : 1;
    env[k] = Float64Array.from(a, v => clamp(v / scale, 0, ceilingOf(k)));
  }
  return { fps, dur: P.dur || P.duration || P.rms.length / fps, env };
}

// Measure a real pack per section and write its twin's spec: [mean, p95, max] of each envelope the
// piece reads (and rms), rounded to 0.05. With `base` (the piece's current spec) everything written by
// hand survives -- per-section patterns, the voc windows, events and chords, beatGrid, keys, quantize, the
// comment -- and so do its grid and its section boundaries unless new ones are given.
export function twin(P, { sections, bpm, downbeat, base } = {}) {
  const B = base || {}, { fps, dur, env } = readEnvelopes(P, { alias: B.alias });
  const cuts = (sections || (B.sections || []).map(s => +s.from)).slice().sort((a, b) => a - b);
  if (!cuts.length || cuts[0] > 0) cuts.unshift(0);
  const keys = ENVELOPES.filter(k => env[k] && (!B.keys || k === 'rms' || B.keys.includes(k)));
  const r = v => Math.round(v / TWIN_STEP) * TWIN_STEP;
  const round = v => +r(v).toFixed(2);
  const bySec = new Map((B.sections || []).map(s => [+s.from, s]));
  const secs = cuts.map((from, i) => {
    const to = i + 1 < cuts.length ? cuts[i + 1] : dur, sec = { from };
    for (const [k, v] of Object.entries(bySec.get(from) || {})) if (k !== 'from' && k !== 'energy' && !ENVELOPES.includes(k)) sec[k] = v;
    // a frame centred just before a boundary already hears the next section's first hit (the analysis
    // window is ~43 ms wide), so a section is measured up to 25 ms short of its end
    const a = firstFrame(from, fps), b = Math.max(a + 1, firstFrame(to - (i + 1 < cuts.length ? 0.025 : 0), fps));
    for (const k of keys) { const d = distribution(env[k].subarray(a, Math.min(b, env[k].length))); sec[k] = [round(d.mean), round(d.p95), round(d.max)]; }
    return sec;
  });
  const measured = { seed: 7, fps: 100, dur: +dur.toFixed(3), bpm: +(P.bpm || 120).toFixed(3), downbeat: +(P.downbeat ?? P.beat0 ?? P.t0 ?? P.beat_phase_s ?? 0) };
  const spec = {};
  for (const k of ['_comment', 'seed', 'fps', 'dur', 'bpm', 'downbeat', 'beatGrid', 'keys', 'alias', 'quantize', 'voc', 'events', 'chords', 'stems']) {
    const v = k in B ? B[k] : measured[k];
    if (v !== undefined) spec[k] = v;
  }
  for (const k of Object.keys(B)) if (!(k in spec) && k !== 'sections') spec[k] = B[k];
  if (bpm != null) spec.bpm = bpm;
  if (downbeat != null) spec.downbeat = downbeat;
  spec.sections = secs;
  return spec;
}

// one line per section (and per top-level field), the way the specs are written by hand
export function formatSpec(spec) {
  const c = v => Array.isArray(v) ? `[${v.map(c).join(', ')}]`
    : v && typeof v === 'object' ? `{${Object.entries(v).map(([k, x]) => `${JSON.stringify(k)}: ${c(x)}`).join(', ')}}`
    : JSON.stringify(v);
  const lines = Object.entries(spec).map(([k, v]) => k === 'sections'
    ? `  "sections": [\n${v.map(s => `    ${c(s)}`).join(',\n')}\n  ]`
    : `  ${JSON.stringify(k)}: ${c(v)}`);
  return `{\n${lines.join(',\n')}\n}\n`;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const A = parseArgs();
  if (A.twin) {
    const real = JSON.parse(fs.readFileSync(A.twin, 'utf8'));
    const specFile = A.piece ? path.join(loadPiece(A.piece).dir, 'synthetic.json') : null;
    const base = specFile && fs.existsSync(specFile) ? JSON.parse(fs.readFileSync(specFile, 'utf8')) : null;
    const spec = twin(real, {
      sections: A.sections ? String(A.sections).split(',').map(Number) : undefined,
      bpm: A.bpm != null ? +A.bpm : undefined, downbeat: A.downbeat != null ? +A.downbeat : undefined, base,
    });
    if (specFile) { fs.writeFileSync(specFile, formatSpec(spec)); console.log('wrote', path.relative(process.cwd(), specFile)); }
    else process.stdout.write(formatSpec(spec));
  } else {
    const ids = A.all ? listPieces() : A._;
    if (!ids.length) die('usage: node tools/synth.mjs <piece> | --all | --twin real.json (--piece <id> | --sections 0,32.26,...)');
    for (const id of ids) console.log('wrote', path.relative(process.cwd(), synthFor(id)));
  }
}
