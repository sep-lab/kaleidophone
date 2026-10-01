"""
Session in: the artist's DAW session -- its MIDI -- on the master's clock.

    kaleidophone envelope Song.wav --midi Song.mid [--midi-offset S] -o song.songpack.json

A song pack's hits are guessed from the mixed master: flux peaks in a band
where the kick, the bass and a synth's attack all land in the same bins. The
session knows exactly when every note was played, how hard, and on which
track. This module reads that -- a Standard MIDI File, which every DAW and an
MPC export -- into seconds, finds where it sits on the bounce, and names the
chords. audio/envelope.py writes the result into the pack: `midi`,
`events.midi`, `events.chords` and the beat grid.

The reader is our own rather than mido or pretty_midi because what a pack
needs from a MIDI file -- notes, the tempo map, the time signatures, the track
names -- is a few hundred lines of a spec that stopped moving in 1996, and the
package keeps its dependencies to what it can't do without (pyproject.toml).

Decisions that are not obvious from the code:

- Time. Ticks become seconds through the tempo map: tempo events (0x51) from
  every track, the last one at a tick winning, and 120 BPM before the first,
  as the spec says. A file with an SMPTE division counts real time and
  ignores tempo for timing; its tempo events still say where the beats are.
- Beats are quarter notes, because that is what MIDI's tempo counts and what
  every DAW's tempo display shows, counted from each bar line: one 3/8 bar in a
  4/4 song doesn't leave every later bar line half a beat off the beats. Bars
  follow the time signatures (0x58, 4/4 until the first); one that arrives
  mid-bar starts a new bar there. So a 6/8 bar is three beats long, and a 7/8
  bar three and a half, its last beat an eighth.
- Pulses are the felt beat (pulse_length), which in 6/8 is not the quarter:
  the time signature's metronome byte (MIDI clocks per click, 24 a quarter)
  when it divides the bar into whole clicks -- except 24 itself, the default
  writers put there whatever the meter (inferred: mido's default, while the
  spec's own 6/8 example says 36, a dotted quarter) -- else the dotted
  quarter of 6/8, 9/8 and 12/8 (three of the denominator's notes, for an
  8th or shorter and a numerator of 6, 9, 12, ...), else the denominator's
  note: a quarter in 4/4, an eighth in 7/8, a half in 2/2.
- Notes pair first in, first out, per channel and pitch: of two overlapping
  notes on one pitch, the first note-off ends the first note. Nothing in the
  file says which off belongs to which on, and FIFO is the usual reading. A
  note that is never turned off ends where its track does. A note-on with
  velocity 0 is a note-off.
- The sustain pedal holds what it holds: a note released while its track's
  channel has CC64 at 64 or more sounds on until the pedal comes up -- or the
  same key is struck again, as a piano's damper falls back -- so a pedalled
  arpeggio of short notes is the chord it sounds like, in its durations and
  in chord_events. A pedal still down at the end of the track lets go there.
- Running status survives meta and sysex events, which the spec says cancel
  it: a reader that keeps it reads every file a strict one reads, and the few
  writers that rely on it too.
- A format-0 file (one track holding every channel) is split by channel, so
  the drums on channel 10 and the keys on channel 1 come back as two tracks,
  as they were in the session.
- Anything this reader can't make sense of -- a truncated file, a length
  running past the end of its chunk, a data byte with no status before it --
  is refused with what is wrong and where (MidiError), never guessed past: a
  note list read from half a file would drive a picture wrong without a word.
- So is what no song holds but a corrupt file can ask for: a tempo outside
  MIN_BPM-MAX_BPM (a tempo of 1 microsecond a quarter note is 60 million BPM,
  and its grid doesn't fit in memory), a file over MAX_MIDI_BYTES, and a grid
  of more than MAX_GRID bars, beats or pulses inside the song.

Alignment (align): a DAW's MIDI export starts at the session's start; the
bounce may not -- pre-roll, a trimmed head, a bounce from bar 5. The offset is
found by cross-correlating the notes as an onset train (velocity-weighted,
drum-like tracks weighted up, a chord counted once) against the master's onset
envelope over +-30 s, normalised once by both signals' whole energy, the peak
refined below a frame. Only the notes that can reach the song at some lag in
the window are in the train: a note far past the song's end could never
line up, and would only make the train -- and the FFT -- longer. How sure it
is: the peak's correlation and its margin over the best distinct runner-up (a
song that repeats itself bar for bar has a runner-up a bar away that scores
the same).

Chords (chord_events): the pitch-class set sounding at each onset cluster of a
polyphonic track, a new event only when the set changes and holds for an 8th
note or more, so a passing chord doesn't count. Named by pitch class, written
over the lowest note when that isn't the root (chord_name): any inversion is
the same chord over its bass (C/E, G7/B), and a chord over a bass note that
isn't one of its own is that chord over the bass -- F/G, C/B -- not the one
chord the whole set happens to spell (Fadd9, Cmaj7). Where two names fit one
set (Dsus4 and Gsus2, C6 and Am7) the one rooted on the bass note wins.
"""

from __future__ import annotations

import errno
import heapq
import math
import os
import re
import struct
import unicodedata
from collections import Counter, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

# 120 BPM: the tempo before the first tempo event (SMF 1.0, "Set Tempo").
DEFAULT_TEMPO_US = 500_000
# The four SMPTE division rates, as the header's negative high byte gives them.
# -29 is 30 drop-frame, which runs at 30000/1001 frames per second.
SMPTE_RATES = {24: 24.0, 25: 25.0, 29: 30000.0 / 1001.0, 30: 30.0}
DRUM_CHANNEL = 9  # MIDI channel 10, General MIDI's percussion channel (0-based)
SUSTAIN_PEDAL = 64  # the damper pedal's controller; at 64 or more it is down

# What no song holds and a corrupt file can ask for. A tempo event can say
# anything from 1 microsecond a quarter note (60 million BPM) to 16.8 s (3.6
# BPM); a song's tempo map lives far inside 10-1000 BPM. A song's MIDI is
# kilobytes. And a grid of more bars, beats or pulses than this inside the
# song is a bar of 1/64 at a tempo no one plays, not music.
MIN_BPM, MAX_BPM = 10.0, 1000.0
MAX_MIDI_BYTES = 64 << 20
MAX_GRID = 100_000

# Alignment. Drums carry the song's timing and their MIDI notes are hits, so
# they count double; a chord's notes within 20 ms of each other are one onset.
DRUM_WEIGHT = 2.0
ONSET_CLUSTER = 0.020
ALIGN_SEARCH = 30.0  # seconds either way
# A runner-up must be a distinct alignment, not the peak's own shoulder.
_RUNNER_UP_EXCLUSION = 0.05
# Below either, the offset is a guess (see align() for how they were set).
ALIGN_MIN_R = 0.25
ALIGN_MIN_MARGIN = 0.05

# Chords: onsets within 30 ms are one chord (a humanised or strummed voicing),
# and a note still sounding 30 ms into the next cluster is held into it.
CHORD_CLUSTER = 0.030
# A track is harmonic when at least this share of its onset clusters sound a
# chord (three or more pitch classes, or a power chord's fifth).
POLYPHONIC_SHARE = 0.2

_DRUM_WORDS = re.compile(
    r"\b(drums?|drummer|kit|kick|bd|snare|sd|hats?|hihats?|hi hats?|hh|claps?|perc|percussion|"
    r"rim|rimshot|toms?|cymbals?|crash|ride|shaker|tamb|tambourine|conga|bongo|cowbell|clave)\b"
)

# (suffix, intervals above the root). Order is the preference where two names
# fit one pitch-class set and neither is rooted on the bass: Am7 over C6,
# Dsus4 over Gsus2. "7", "m7" and "maj7" come again voiced without their
# fifth, and the last five are extensions a keys part plays rooted (a 6/9,
# m11, maj7#11 and 7#9, the last with and without its fifth).
_QUALITIES: tuple[tuple[str, frozenset[int]], ...] = tuple(
    (suffix, frozenset(intervals))
    for suffix, intervals in (
        ("", (0, 4, 7)),
        ("m", (0, 3, 7)),
        ("7", (0, 4, 7, 10)),
        ("m7", (0, 3, 7, 10)),
        ("maj7", (0, 4, 7, 11)),
        ("sus4", (0, 5, 7)),
        ("sus2", (0, 2, 7)),
        ("5", (0, 7)),
        ("dim", (0, 3, 6)),
        ("aug", (0, 4, 8)),
        ("m7b5", (0, 3, 6, 10)),
        ("dim7", (0, 3, 6, 9)),
        ("mMaj7", (0, 3, 7, 11)),
        ("7sus4", (0, 5, 7, 10)),
        ("6", (0, 4, 7, 9)),
        ("m6", (0, 3, 7, 9)),
        ("add9", (0, 2, 4, 7)),
        ("madd9", (0, 2, 3, 7)),
        ("9", (0, 2, 4, 7, 10)),
        ("m9", (0, 2, 3, 7, 10)),
        ("maj9", (0, 2, 4, 7, 11)),
        ("7", (0, 4, 10)),
        ("m7", (0, 3, 10)),
        ("maj7", (0, 4, 11)),
        ("6/9", (0, 2, 4, 7, 9)),
        ("m11", (0, 2, 3, 5, 7, 10)),
        ("maj7#11", (0, 4, 6, 7, 11)),
        ("7#9", (0, 3, 4, 7, 10)),
        ("7#9", (0, 3, 4, 10)),
    )
)
_SHARPS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLATS = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
# No key signature: the spellings a chord chart uses most.
_PLAIN = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
# A sharp key's sharps, in the order its signature adds them: F# C# G# D# A#.
_SHARP_ORDER = (6, 1, 8, 3, 10)


class MidiError(ValueError):
    """A file this reader can't use as a Standard MIDI File, and why."""


# --------------------------------------------------------------------------
# what a file holds
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Note:
    """One note, in seconds on the MIDI file's own clock (tick 0 is 0 s)."""

    t: float
    dur: float
    pitch: int  # MIDI note number, 60 = middle C
    velocity: int  # 1..127
    channel: int  # 0..15 (MIDI channels 1..16)


@dataclass(frozen=True)
class Track:
    """A track with notes. `name` is the DAW's (meta 0x03, else 0x04), None
    when it has none; `label` is the name or the fallback the pack lists it
    under (`track-<n>`, n its 1-based place among the file's tracks, or
    `channel-<n>` for a split format-0 file); `slug` is its key in
    `events.midi`, unique within the file."""

    name: str | None
    number: int
    label: str
    slug: str
    notes: tuple[Note, ...]
    drum_like: bool


@dataclass(frozen=True)
class TempoMap:
    """Piecewise-constant tempo: from `seconds[k]` (quarter note `quarters[k]`)
    on, the tempo is `bpm[k]` quarter notes a minute. Both ends extrapolate --
    before the first entry at its tempo, after the last at its own -- so a
    grid extends into pre-roll and past the session's last event."""

    seconds: np.ndarray
    quarters: np.ndarray
    bpm: np.ndarray

    def seconds_at(self, quarters) -> np.ndarray:
        q = np.asarray(quarters, dtype=np.float64)
        k = np.clip(np.searchsorted(self.quarters, q, side="right") - 1, 0, len(self.bpm) - 1)
        return self.seconds[k] + (q - self.quarters[k]) * 60.0 / self.bpm[k]

    def quarters_at(self, seconds) -> np.ndarray:
        s = np.asarray(seconds, dtype=np.float64)
        k = np.clip(np.searchsorted(self.seconds, s, side="right") - 1, 0, len(self.bpm) - 1)
        return self.quarters[k] + (s - self.seconds[k]) * self.bpm[k] / 60.0

    def bpm_at(self, seconds: float) -> float:
        k = int(np.clip(np.searchsorted(self.seconds, seconds, side="right") - 1, 0, len(self.bpm) - 1))
        return float(self.bpm[k])


@dataclass(frozen=True)
class MidiFile:
    """A Standard MIDI File, read into seconds.

    `tracks` are the tracks with notes, in file order. `meter` is the time
    signatures as (quarter-note position, numerator, denominator), the first at
    0 (4/4 when the file has none -- `has_meter` says which), and `pulses` the
    felt beat of each, in quarter notes (pulse_length). `key_signature` is the
    first key signature's sharps (> 0) or flats (< 0), None without one.
    `end` is the last event of any track, in seconds. `name` is the file's
    basename when it was read from a path.
    """

    format: int
    ppq: int | None
    smpte: tuple[float, int] | None
    tracks: tuple[Track, ...]
    tempo: TempoMap
    meter: tuple[tuple[float, int, int], ...]
    has_meter: bool
    key_signature: int | None
    end: float
    unclosed: int = 0
    name: str | None = None
    pulses: tuple[float, ...] = ()

    @property
    def notes(self) -> int:
        return sum(len(track.notes) for track in self.tracks)


@dataclass
class _RawTrack:
    number: int
    name: str | None = None
    instrument: str | None = None
    notes: list[tuple[int, int, int, int, int]] = field(default_factory=list)  # start, end, pitch, vel, ch
    tempos: list[tuple[int, int]] = field(default_factory=list)  # tick, microseconds per quarter
    # tick, numerator, denominator, MIDI clocks per metronome click (None if the event has no such byte)
    meters: list[tuple[int, int, int, int | None]] = field(default_factory=list)
    keys: list[tuple[int, int]] = field(default_factory=list)  # tick, sharps
    end_tick: int = 0
    unclosed: int = 0


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------
def read_midi(path: str) -> MidiFile:
    """Read a Standard MIDI File (format 0 or 1) from `path`. Its first four
    bytes are checked before the rest is read, and a file over MAX_MIDI_BYTES
    isn't read at all: a song's MIDI is kilobytes."""
    if not os.path.exists(path):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        head = fh.read(4)
        if head != b"MThd":
            raise _not_a_midi_file(head, name)
        size = os.fstat(fh.fileno()).st_size
        if size > MAX_MIDI_BYTES:
            raise MidiError(
                f"{name}: {size / 2**20:.0f} MB, and a song's MIDI is kilobytes (this reads at most "
                f"{MAX_MIDI_BYTES >> 20} MB) -- is it the session's MIDI export?"
            )
        data = head + fh.read()
    return parse_midi(data, name=name)


def _not_a_midi_file(head: bytes, label: str) -> MidiError:
    hint = ""
    if head[:4] == b"RIFF":
        hint = " (it is a RIFF file -- an .rmi or a WAV?); export a Standard MIDI File (.mid) from the DAW"
    return MidiError(f"{label}: not a Standard MIDI File: it doesn't start with an 'MThd' header{hint}")


def parse_midi(data: bytes, *, name: str | None = None) -> MidiFile:
    """Parse the bytes of a Standard MIDI File. Pure: no file is touched."""
    label = name or "the MIDI file"

    def fail(problem: str) -> MidiError:
        return MidiError(f"{label}: {problem}")

    if data[:4] != b"MThd":
        raise _not_a_midi_file(data[:4], label)
    if len(data) < 14:
        raise fail(f"the header is cut short ({len(data)} bytes) -- the file is truncated")
    header_len = int.from_bytes(data[4:8], "big")
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if header_len < 6:
        raise fail(f"its header says it is {header_len} bytes long; a MIDI header is at least 6 -- corrupt")
    if fmt == 2:
        raise fail(
            "format 2 (independent sequences, each with its own tempo) isn't supported -- "
            "export it as format 1 (one track per part) or format 0"
        )
    if fmt > 2:
        raise fail(f"unknown MIDI file format {fmt} (0, 1 and 2 exist) -- corrupt, or not MIDI")
    if ntracks == 0:
        raise fail("its header lists no tracks")

    ppq: int | None = None
    smpte: tuple[float, int] | None = None
    if division & 0x8000:
        rate, per_frame = 256 - (division >> 8), division & 0xFF
        if rate not in SMPTE_RATES or per_frame == 0:
            raise fail(f"an SMPTE division of {rate} fps x {per_frame} ticks per frame isn't one MIDI allows")
        smpte = (SMPTE_RATES[rate], per_frame)
    elif division == 0:
        raise fail("a division of 0 ticks per quarter note -- corrupt")
    else:
        ppq = division

    raws: list[_RawTrack] = []
    pos = 8 + header_len
    while len(raws) < ntracks:
        if pos + 8 > len(data):
            raise fail(
                f"the header promises {ntracks} tracks and the file ends after {len(raws)} -- truncated"
            )
        kind = data[pos : pos + 4]
        length = int.from_bytes(data[pos + 4 : pos + 8], "big")
        if not all(0x20 < b < 0x7F for b in kind):
            raise fail(f"byte {pos}: garbage where track {len(raws) + 1} should begin -- corrupt")
        start = pos + 8
        if start + length > len(data):
            raise fail(
                f"track {len(raws) + 1} says it is {length} bytes long and the file has "
                f"{len(data) - start} left -- truncated"
            )
        if kind == b"MTrk":
            raws.append(_parse_track(data, start, start + length, len(raws) + 1, label))
        # Any other chunk type is an "alien" chunk: the spec says to skip it.
        pos = start + length

    return _assemble(raws, fmt, ppq, smpte, name)


def _parse_track(data: bytes, start: int, end: int, number: int, label: str) -> _RawTrack:
    raw = _RawTrack(number=number)
    where = f"{label}: track {number}"
    truncated = MidiError(
        f"{where} is cut short in the middle of an event -- the file is truncated or corrupt"
    )
    open_notes: dict[tuple[int, int], deque[tuple[int, int]]] = {}
    # Notes released while the pedal is down, by channel and pitch: (on tick,
    # velocity), still sounding until the pedal comes up or the key is struck again.
    pedalled: dict[int, dict[int, list[tuple[int, int]]]] = {}
    pedal_down = [False] * 16
    pos, tick, running = start, 0, None
    while pos < end:
        delta, pos = _read_vlq(data, pos, end, truncated, where)
        tick += delta
        if pos >= end:
            raise truncated
        status = data[pos]
        if status == 0xFF:  # meta event: type, length, data
            if pos + 2 > end:
                raise truncated
            kind = data[pos + 1]
            length, pos = _read_vlq(data, pos + 2, end, truncated, where)
            if pos + length > end:
                raise truncated
            body = data[pos : pos + length]
            pos += length
            if kind == 0x2F:  # end of track
                break
            _meta(raw, kind, body, tick, where)
            continue
        if status in (0xF0, 0xF7):  # sysex, or an escape: a length and bytes to skip
            length, pos = _read_vlq(data, pos + 1, end, truncated, where)
            if pos + length > end:
                raise truncated
            pos += length
            continue
        if status >= 0xF0:
            raise MidiError(
                f"{where}: byte {pos} is 0x{status:02X}, a status that never appears in a MIDI file -- corrupt"
            )
        if status & 0x80:
            running = status
            pos += 1
        elif running is None:
            raise MidiError(
                f"{where}: byte {pos} is a data byte with no status before it -- corrupt, or not MIDI"
            )
        kind, channel = running & 0xF0, running & 0x0F
        size = 1 if kind in (0xC0, 0xD0) else 2
        if pos + size > end:
            raise truncated
        args = data[pos : pos + size]
        pos += size
        if any(b & 0x80 for b in args):
            raise MidiError(f"{where}: a status byte where event data belongs (byte {pos - size}) -- corrupt")
        if kind == 0x90 and args[1] > 0:
            # A key struck again while the pedal still holds it: the held note ends here.
            held = pedalled.get(channel, {}).pop(args[0], ())
            raw.notes.extend((on, tick, args[0], velocity, channel) for on, velocity in held)
            open_notes.setdefault((channel, args[0]), deque()).append((tick, args[1]))
        elif kind in (0x80, 0x90):  # note-off, or note-on at velocity 0
            queue = open_notes.get((channel, args[0]))
            if queue:
                on, velocity = queue.popleft()
                if pedal_down[channel]:
                    pedalled.setdefault(channel, {}).setdefault(args[0], []).append((on, velocity))
                else:
                    raw.notes.append((on, tick, args[0], velocity, channel))
        elif kind == 0xB0 and args[0] == SUSTAIN_PEDAL:
            down = args[1] >= 64
            if pedal_down[channel] and not down:
                _release(raw, pedalled.pop(channel, {}), tick, channel)
            pedal_down[channel] = down
    raw.end_tick = tick
    for channel, held in pedalled.items():
        _release(raw, held, tick, channel)
    for (channel, pitch), queue in open_notes.items():
        for on, velocity in queue:
            raw.notes.append((on, tick, pitch, velocity, channel))
            raw.unclosed += 1
    return raw


def _release(raw: _RawTrack, held: dict[int, list[tuple[int, int]]], tick: int, channel: int) -> None:
    """End every note the pedal was holding on `channel` at `tick`."""
    for pitch, notes in held.items():
        raw.notes.extend((on, tick, pitch, velocity, channel) for on, velocity in notes)


def _read_vlq(data: bytes, pos: int, end: int, truncated: MidiError, where: str) -> tuple[int, int]:
    """A variable-length quantity: 7 bits a byte, at most 4 bytes."""
    value = 0
    for _ in range(4):
        if pos >= end:
            raise truncated
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise MidiError(f"{where}: a time or length longer than MIDI's 4 bytes (byte {pos - 4}) -- corrupt")


def _meta(raw: _RawTrack, kind: int, body: bytes, tick: int, where: str) -> None:
    if kind == 0x03 and raw.name is None:
        raw.name = _text(body)
    elif kind == 0x04 and raw.instrument is None:
        raw.instrument = _text(body)
    elif kind == 0x51:
        if len(body) != 3:
            raise MidiError(f"{where}: a tempo event {len(body)} bytes long (it is always 3) -- corrupt")
        microseconds = int.from_bytes(body, "big")
        if microseconds == 0:
            raise MidiError(f"{where}: a tempo of 0 microseconds per quarter note -- corrupt")
        bpm = 60e6 / microseconds
        if not MIN_BPM <= bpm <= MAX_BPM:
            raise MidiError(
                f"{where}: a tempo of {bpm:.7g} BPM ({microseconds} microseconds per quarter note), outside the "
                f"{MIN_BPM:g}-{MAX_BPM:g} BPM a song's tempo map holds -- corrupt"
            )
        raw.tempos.append((tick, microseconds))
    elif kind == 0x58:
        if len(body) < 2 or body[0] == 0 or body[1] > 6:
            shown = f"{body[0]}/2^{body[1]}" if len(body) >= 2 else f"{len(body)} bytes"
            raise MidiError(f"{where}: a time signature MIDI can't mean ({shown}) -- corrupt")
        raw.meters.append((tick, body[0], 1 << body[1], body[2] if len(body) >= 3 else None))
    elif kind == 0x59 and body:
        raw.keys.append((tick, body[0] - 256 if body[0] > 127 else body[0]))


def _text(body: bytes) -> str | None:
    """A meta event's text. The spec says ASCII; DAWs write UTF-8, and a few
    older ones Latin-1."""
    raw = body.replace(b"\x00", b"")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.strip() or None


def _assemble(
    raws: list[_RawTrack], fmt: int, ppq: int | None, smpte: tuple[float, int] | None, name: str | None
) -> MidiFile:
    tempos: dict[int, int] = {}
    meters: dict[int, tuple[int, int, int | None]] = {}
    keys: list[tuple[int, int]] = []
    for raw in raws:  # later tracks override earlier ones at the same tick
        for tick, microseconds in raw.tempos:
            tempos[tick] = microseconds
        for tick, num, den, clocks in raw.meters:
            meters[tick] = (num, den, clocks)
        keys.extend(raw.keys)
    tempo = _tempo_map(tempos, ppq, smpte)
    tick_rate = None if smpte is None else smpte[0] * smpte[1]

    def to_seconds(ticks) -> np.ndarray:
        ticks = np.asarray(ticks, dtype=np.float64)
        return tempo.seconds_at(ticks / ppq) if ppq else ticks / tick_rate

    def to_quarters(tick: int) -> float:
        return tick / ppq if ppq else float(tempo.quarters_at(tick / tick_rate))

    meter = [(to_quarters(tick), meters[tick][0], meters[tick][1]) for tick in sorted(meters)]
    pulses = [pulse_length(*meters[tick]) for tick in sorted(meters)]
    if not meter or meter[0][0] > 0.0:
        meter.insert(0, (0.0, 4, 4))
        pulses.insert(0, 1.0)
    key_signature = min(keys, key=lambda k: k[0])[1] if keys else None  # the earliest; file order breaks ties

    parts: list[tuple[str | None, int, str | None, list[tuple[int, int, int, int, int]]]] = []
    for raw in raws:
        if not raw.notes:
            continue
        channels = sorted({note[4] for note in raw.notes})
        if fmt == 0 and len(channels) > 1:
            for channel in channels:
                parts.append(
                    (None, channel + 1, f"channel-{channel + 1}", [n for n in raw.notes if n[4] == channel])
                )
        else:
            parts.append((raw.name or raw.instrument, raw.number, None, raw.notes))

    tracks = []
    used: dict[str, int] = {}
    for track_name, number, fallback, notes in parts:
        notes = sorted(notes)
        starts = to_seconds([n[0] for n in notes])
        ends = to_seconds([n[1] for n in notes])
        label = track_name or fallback or f"track-{number}"
        slug = _unique(slugify(track_name or "") or fallback or f"track-{number}", used)
        tracks.append(
            Track(
                name=track_name,
                number=number,
                label=label,
                slug=slug,
                notes=tuple(
                    sorted(
                        (
                            Note(t=float(s), dur=float(e - s), pitch=n[2], velocity=n[3], channel=n[4])
                            for n, s, e in zip(notes, starts, ends)
                        ),
                        key=lambda note: (note.t, note.pitch),
                    )
                ),
                drum_like=any(n[4] == DRUM_CHANNEL for n in notes) or _drum_named(track_name),
            )
        )
    last_tick = max(raw.end_tick for raw in raws)
    return MidiFile(
        format=fmt,
        ppq=ppq,
        smpte=smpte,
        tracks=tuple(tracks),
        tempo=tempo,
        meter=tuple(meter),
        has_meter=bool(meters),
        key_signature=key_signature,
        end=float(to_seconds(last_tick)),
        unclosed=sum(raw.unclosed for raw in raws),
        name=name,
        pulses=tuple(pulses),
    )


def _tempo_map(tempos: dict[int, int], ppq: int | None, smpte: tuple[float, int] | None) -> TempoMap:
    ticks = sorted(tempos)
    if not ticks or ticks[0] > 0:
        ticks.insert(0, 0)
        tempos = {**tempos, 0: DEFAULT_TEMPO_US}
    micro = np.array([tempos[t] for t in ticks], dtype=np.float64)
    bpm = 60e6 / micro
    tick_arr = np.array(ticks, dtype=np.float64)
    if ppq:
        quarters = tick_arr / ppq
        seconds = np.concatenate([[0.0], np.cumsum(np.diff(tick_arr) * micro[:-1] / (ppq * 1e6))])
    else:
        seconds = tick_arr / (smpte[0] * smpte[1])
        quarters = np.concatenate([[0.0], np.cumsum(np.diff(seconds) * bpm[:-1] / 60.0)])
    return TempoMap(seconds=seconds, quarters=quarters, bpm=bpm)


def slugify(name: str) -> str:
    """A track name as a key: lowercase, a-z, 0-9 and '-', accents folded
    ("Bajo Eléctrico" -> "bajo-electrico"); '' when nothing is left."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def _unique(slug: str, used: dict[str, int]) -> str:
    """`slug`, or `slug-2`, `slug-3`, ... -- the first not yet handed out.
    `used` holds every key handed out, each mapped to the last suffix tried for
    it as a slug, so ten thousand tracks of one name don't each count up from 2
    again: every suffix below that one is taken, and none is ever freed."""
    n = used.get(slug, 1)
    candidate = slug if n == 1 else f"{slug}-{n}"
    while candidate in used:
        n += 1
        candidate = f"{slug}-{n}"
    used[slug] = n
    used.setdefault(candidate, 1)
    return candidate


def _drum_named(name: str | None) -> bool:
    return bool(name) and bool(_DRUM_WORDS.search(re.sub(r"[_\-.]+", " ", name.lower())))


# --------------------------------------------------------------------------
# bars and beats
# --------------------------------------------------------------------------
def pulse_length(num: int, den: int, clocks: int | None = None) -> float:
    """The felt beat of a num/den bar, in quarter notes -- what a conductor
    beats and a dancer steps to (see the module docstring for the rule).
    `clocks` is the time signature's metronome byte, MIDI clocks per click (24
    a quarter note). 4/4 -> 1, 6/8 and 12/8 -> 1.5 (the dotted quarter), 2/2
    -> 2, 3/8 and 7/8 -> 0.5; 6/8 clicking every 12 clocks -> 0.5, 4/4 every
    48 -> 2. A click shorter than a 16th (6 clocks) is no felt beat and is
    ignored, as is one that doesn't divide the bar."""
    if clocks and clocks != 24 and clocks >= 6:
        clicks = num * 96.0 / den / clocks  # a bar is num * 96 / den MIDI clocks
        if clicks >= 1.0 and abs(clicks - round(clicks)) < 1e-9:
            return clocks / 24.0
    if den >= 8 and num > 3 and num % 3 == 0:
        return 12.0 / den  # three of the denominator's notes: a dotted quarter in x/8
    return 4.0 / den


def bar_lines(
    midi: MidiFile,
    q_to: float,
    *,
    q_from: float = 0.0,
    meter: Sequence[tuple[float, int, int]] | None = None,
    anchor: float = 0.0,
) -> list[tuple[float, int, int, int]]:
    """(quarter-note position, bar number, numerator, denominator) of every bar
    that overlaps [q_from, q_to] -- so the first is the bar q_from falls in.
    Bar 1 starts at `anchor`, tick 0 unless told otherwise (a clip that opens
    on a pickup); each bar is as long as its time signature says (a 6/8 bar is
    3 quarter notes), and a signature that arrives mid-bar starts a new bar
    there. Before bar 1 -- pre-roll, a pickup -- bars are extrapolated at bar
    1's signature and numbered 0, -1, ... `meter` replaces the file's time
    signatures (for a file that has none)."""
    return [bar[:4] for bar in _bars(midi, q_to, q_from, meter, anchor)]


def _bars(
    midi: MidiFile,
    q_to: float,
    q_from: float,
    meter: Sequence[tuple[float, int, int]] | None,
    anchor: float,
) -> list[tuple[float, int, int, int, float, float]]:
    """bar_lines(), each bar with its length and its pulse in quarter notes."""
    if meter:
        meter, pulses = list(meter), [pulse_length(num, den) for _, num, den in meter]
    else:
        meter, pulses = list(midi.meter), list(midi.pulses) or [pulse_length(n, d) for _, n, d in midi.meter]
    if q_from < anchor - 1e6:
        raise ValueError(
            f"a grid starting {anchor - q_from:.0f} quarter notes before the MIDI's bar 1 -- check the offset"
        )
    i = 0
    while i + 1 < len(meter) and meter[i + 1][0] <= anchor + 1e-9:
        i += 1
    head = (meter[i][1], meter[i][2], pulses[i])  # bar 1's signature, extrapolated back from it
    after: list[tuple[float, int, int, int, float, float]] = []
    before: list[tuple[float, int, int, int, float, float]] = []

    def keep(into: list, bar: tuple[float, int, int, int, float, float]) -> None:
        into.append(bar)
        if len(after) + len(before) > MAX_GRID:
            raise ValueError(
                f"the MIDI's grid has more than {MAX_GRID} bars inside the song ({bar[2]}/{bar[3]} bars) -- "
                f"a time signature or tempo no song has: is the file corrupt?"
            )

    q, number = anchor, 1
    while q <= q_to + 1e-9:
        while i + 1 < len(meter) and meter[i + 1][0] <= q + 1e-9:
            i += 1
        num, den = meter[i][1], meter[i][2]
        length = num * 4.0 / den
        upcoming = meter[i + 1][0] if i + 1 < len(meter) else math.inf
        # Whole bars that end before the song starts, with no signature among
        # them, are counted rather than walked: a bounce from an hour into a
        # session starts thousands of bars in.
        skip = math.floor((min(q_from, upcoming) - q) / length + 1e-9) - 1
        if skip > 0:
            q, number = q + skip * length, number + skip
            continue
        following = min(q + length, upcoming)
        if following > q_from + 1e-9:
            keep(after, (q, number, num, den, following - q, pulses[i]))
        q, number = following, number + 1
    num, den, pulse = head
    length = num * 4.0 / den
    q, number = anchor - length, 0
    if q > q_to:  # the song ends before bar 1: skip the bars after it, too
        skip = math.ceil((q - q_to) / length - 1e-9)
        q, number = q - skip * length, number - skip
    while q + length > q_from + 1e-9:
        keep(before, (q, number, num, den, length, pulse))
        q, number = q - length, number - 1
    return before[::-1] + after


def _ticks(
    tempo: TempoMap,
    offset: float,
    dur: float,
    bars: list[tuple[float, int, int, int, float, float]],
    steps: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    """(master seconds, bar number) of every step from each bar line on --
    `steps[k]` quarter notes apart in bar k, the bar's last step cut short by
    the next bar line -- that falls inside [0, dur)."""
    counts = np.array([math.ceil(bar[4] / step - 1e-9) for bar, step in zip(bars, steps)], dtype=np.int64)
    total = int(counts.sum())
    if total > MAX_GRID:
        raise ValueError(
            f"the MIDI's grid has more than {MAX_GRID} beats inside the song -- a time signature or tempo no song "
            f"has: is the file corrupt?"
        )
    first = np.repeat(np.cumsum(counts) - counts, counts)
    q = np.repeat([bar[0] for bar in bars], counts) + (np.arange(total) - first) * np.repeat(steps, counts)
    numbers = np.repeat(np.array([bar[1] for bar in bars], dtype=np.int64), counts)
    t = tempo.seconds_at(q) + offset
    inside = (t >= -EDGE) & (t < dur)
    return np.maximum(t[inside], 0.0), numbers[inside]


@dataclass(frozen=True)
class SessionGrid:
    """The session's grid on the master's timeline (master time = MIDI time +
    `offset`), for the song's [0, dur).

    `beats` are every quarter note, counted from each bar line; `beat_bars`
    the session's bar number each beat falls in; `pulses` every felt beat
    (pulse_length), also from each bar line, and `pulses_per_bar` how many
    there are in the bar the downbeat opens; `bars` every bar line as (s, bar
    number, num, den); `downbeat` bar 1 -- the first bar line at or after 0,
    or the one given -- and `downbeat_bar` its number in the session; `bpm` the
    tempo there. `tempo_map` and `time_signatures` start with what is in
    effect at 0 s and list every change inside the song."""

    beats: np.ndarray
    beat_bars: np.ndarray
    bars: list[tuple[float, int, int, int]]
    downbeat: float
    downbeat_bar: int
    bpm: float
    tempo_map: list[tuple[float, float]]
    time_signatures: list[tuple[float, int, int]]
    pulses: np.ndarray = field(default_factory=lambda: np.zeros(0))
    pulses_per_bar: int = 4


# Grid points this close before 0 s are at 0 s: an alignment a fraction of a
# millisecond early must not push bar 1 a whole bar later.
EDGE = 0.001


def session_grid(
    midi: MidiFile,
    offset: float,
    dur: float,
    *,
    meter: Sequence[tuple[float, int, int]] | None = None,
    downbeat: float | None = None,
) -> SessionGrid:
    """The grid of `midi` placed at `offset` on a song of `dur` seconds.

    `downbeat` (s, master time) is bar 1 when the MIDI's tick 0 isn't -- a clip
    exported from a pickup: the bar lines follow the MIDI's meter from there,
    and the bars before it are pickup bars, numbered 0, -1, ..."""
    tempo = midi.tempo
    q_lo = float(tempo.quarters_at(-offset - EDGE))
    q_hi = float(tempo.quarters_at(dur - offset))
    anchor = 0.0 if downbeat is None else float(tempo.quarters_at(downbeat - offset))
    full = _bars(midi, q_hi, q_lo, meter, anchor)
    lines = [bar[:4] for bar in full]
    starts = np.array([line[0] for line in lines])

    beats, beat_bars = _ticks(tempo, offset, dur, full, [1.0] * len(full))
    pulses, _ = _ticks(tempo, offset, dur, full, [bar[5] for bar in full])

    bars = []
    for q, number, num, den in lines:
        t = float(tempo.seconds_at(q)) + offset
        if -EDGE <= t < dur:
            bars.append((max(t, 0.0), number, num, den))
    real = [bar for bar in bars if bar[1] >= 1]
    if not real:
        raise ValueError(
            f"the MIDI's bars don't reach into the song at an offset of {offset:+.3f} s (its bar 1 would be at "
            f"{offset:.3f} s of a {dur:.2f} s song) -- check --midi-offset"
        )
    bar1, bar1_number = real[0][0], real[0][1]
    _, _, bar1_num, bar1_den, _, bar1_pulse = next(bar for bar in full if bar[1] == bar1_number)

    tempo_map = [(0.0, tempo.bpm_at(-offset))]
    for s, bpm in zip(tempo.seconds + offset, tempo.bpm):
        if 0.0 < s < dur and abs(bpm - tempo_map[-1][1]) > 1e-6:
            tempo_map.append((float(s), float(bpm)))
    # The signature in effect at 0 s is the one of the bar 0 s falls in.
    q_zero = float(tempo.quarters_at(-offset))
    head = lines[int(np.clip(np.searchsorted(starts, q_zero + 1e-9, side="right") - 1, 0, len(lines) - 1))]
    signatures = [(0.0, head[2], head[3])]
    for t, _, num, den in bars:
        if t > 0.0 and (num, den) != signatures[-1][1:]:
            signatures.append((t, num, den))
    return SessionGrid(
        beats=beats,
        beat_bars=beat_bars,
        bars=bars,
        downbeat=float(bar1),
        downbeat_bar=int(bar1_number),
        bpm=tempo.bpm_at(bar1 - offset),
        tempo_map=tempo_map,
        time_signatures=signatures,
        pulses=pulses,
        pulses_per_bar=round(bar1_num * 4.0 / bar1_den / bar1_pulse),
    )


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Alignment:
    """Where the MIDI sits on the master: master time = MIDI time + `offset`.

    `r` is the normalised correlation of the MIDI's onsets with the master's
    there (-1..1; None with no notes to correlate), `margin` how far it beats
    the best distinct other alignment, found at `runner_up` seconds. `source`
    is "auto" or "given"; a given offset has no runner-up.
    """

    offset: float
    r: float | None
    margin: float | None = None
    runner_up: float | None = None
    source: str = "auto"

    @property
    def sure(self) -> bool:
        """Whether the found offset clears ALIGN_MIN_R and ALIGN_MIN_MARGIN."""
        return (
            self.r is not None
            and self.r >= ALIGN_MIN_R
            and (self.margin is None or self.margin >= ALIGN_MIN_MARGIN)
        )


def onset_impulses(
    tracks: Iterable[Track], *, drum_weight: float = DRUM_WEIGHT, cluster: float = ONSET_CLUSTER
) -> tuple[np.ndarray, np.ndarray]:
    """(times, weights) of every onset: velocity / 127, doubled on drum-like
    tracks, and a track's notes within `cluster` seconds of each other counted
    once at its loudest -- a six-note chord is one attack, not six."""
    times: list[float] = []
    weights: list[float] = []
    for track in tracks:
        scale = drum_weight if track.drum_like else 1.0
        opened = -math.inf
        for note in track.notes:
            weight = note.velocity / 127.0 * scale
            if note.t - opened <= cluster:
                weights[-1] = max(weights[-1], weight)
                continue
            opened = note.t
            times.append(note.t)
            weights.append(weight)
    order = np.argsort(times, kind="stable")
    return np.asarray(times, dtype=np.float64)[order], np.asarray(weights, dtype=np.float64)[order]


def align(
    times: np.ndarray,
    weights: np.ndarray,
    onset: np.ndarray,
    *,
    fps: int = 100,
    search: float = ALIGN_SEARCH,
    center: float = 0.0,
) -> Alignment:
    """Where MIDI onsets at `times` (s, weighted) best fit `onset`, an onset
    envelope at `fps` frames per second (audio/envelope.py's onset_strength),
    within +-`search` s of an offset of `center` s.

    Only the onsets that can land in the song at some offset in that window
    count (reachable): a note further away than that lines up with nothing
    anywhere in it, and would only make the train longer -- one stray note
    20 years down a 70-byte file would make it 400 GiB. They become an
    impulse train at `fps` over the window, each split between the two frames
    around it and smoothed by the same 3-frame box as the audio's envelope.
    Their Pearson correlation is computed for every whole-frame lag at once
    (one FFT), normalised once by both signals' whole energy, so a lag that
    pushes notes off the end of the song is penalised for every note it
    pushes, and the best lag is refined below a frame: the train is
    re-rendered at 0.05-frame steps across the peak and a parabola fitted
    through the best three. The runner-up is the best other local maximum
    more than 50 ms away -- the distinct alignment most likely to be the
    right one if this isn't.
    """
    times, weights = reachable(times, weights, len(onset) / fps, center, search)
    audio = _centred(onset)
    if times.size == 0 or not np.any(weights > 0):
        raise ValueError("the MIDI has no notes to line up with the audio")
    if audio is None:
        raise ValueError("the audio has no onsets to line the MIDI up with -- is it silent?")
    # Train frame 0 is master time center - search; a residual lag d (frames)
    # puts a note at master frame position + d - reach.
    reach = round(search * fps)
    positions = (times + center) * fps + reach
    length, start = _train_length(len(onset), reach), round(center * fps) + reach
    residuals = np.arange(-reach, reach + 1)
    r = _ncc_lags(_train(positions, weights, length, start), audio, residuals - reach)
    best = int(np.argmax(r))

    steps = np.arange(-20, 21) * 0.05
    fine = np.array(
        [_ncc_at(positions, weights, audio, residuals[best] + d - reach, length, start) for d in steps]
    )
    k = int(np.argmax(fine))
    shift = _parabola(fine, k) if 0 < k < len(fine) - 1 else 0.0
    offset = center + (residuals[best] + steps[k] + shift * 0.05) / fps
    peak = float(fine[k])

    exclusion = round(_RUNNER_UP_EXCLUSION * fps)
    interior = np.zeros(len(r), dtype=bool)
    interior[1:-1] = (r[1:-1] >= r[:-2]) & (r[1:-1] >= r[2:])
    interior &= np.abs(residuals - residuals[best]) > exclusion
    if np.any(interior):
        j = int(np.argmax(np.where(interior, r, -np.inf)))
        runner, margin = float(center + residuals[j] / fps), peak - float(r[j])
    else:
        runner, margin = None, None
    return Alignment(offset=float(offset), r=peak, margin=margin, runner_up=runner, source="auto")


def correlation_at(
    times: np.ndarray,
    weights: np.ndarray,
    onset: np.ndarray,
    offset: float,
    *,
    fps: int = 100,
    search: float = ALIGN_SEARCH,
) -> float | None:
    """The correlation align() gives the MIDI at `offset` seconds, over the
    notes that can reach the song within +-`search` of it; None with no notes,
    or no onsets in the audio, and 0.0 when no note comes near the song."""
    times = np.asarray(times, dtype=np.float64)
    audio = _centred(onset)
    if times.size == 0 or audio is None:
        return None
    times, weights = reachable(times, weights, len(onset) / fps, offset, search)
    if times.size == 0:
        return 0.0
    reach = round(search * fps)
    positions = (times + offset) * fps + reach
    return _ncc_at(positions, weights, audio, -reach, _train_length(len(onset), reach), round(offset * fps) + reach)


def reachable(
    times: np.ndarray, weights: np.ndarray, dur: float, center: float, search: float
) -> tuple[np.ndarray, np.ndarray]:
    """The onsets that land inside a `dur`-second song at some offset within
    +-`search` of `center`: MIDI time t with t + center in [-search, dur + search]."""
    times = np.asarray(times, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    keep = (times + center >= -search) & (times + center <= dur + search)
    return times[keep], weights[keep]


def _train_length(frames: int, reach: int) -> int:
    """Frames an impulse train needs to cover a `frames`-long song and `reach`
    frames either side, plus room for the smoothing -- the song's length, not
    the notes', decides it."""
    return frames + 2 * reach + 4


# The correlation is normalised once, by both signals' whole energy, not per
# lag over the overlap: normalised per lag, a groove shifted by a few bars
# scores exactly as well as the right alignment over the part that still
# overlaps, and nothing counts the notes it pushed off the end of the song.
# Measured on a synthetic 32-bar groove, the margin over the runner-up was
# 0.02-0.08 that way.
def _centred(values) -> tuple[np.ndarray, float] | None:
    """(values minus their mean, the norm of that); None if flat."""
    x = np.asarray(values, dtype=np.float64)
    x = x - x.mean() if x.size else x
    norm = float(np.sqrt(np.dot(x, x))) if x.size else 0.0
    return (x, norm) if norm > 1e-12 else None


def _train(
    positions: np.ndarray, weights: np.ndarray, length: int, start: int, shift: float = 0.0
) -> tuple[np.ndarray, float] | None:
    """The onsets at `positions` (+ `shift`) as a rendered train, centred and
    normalised over the notes' own span -- from the MIDI's 0 s (frame
    `start`) to its last onset -- and zero either side of it: the frames the
    window adds there are room to move in, and counted, they would water r
    down by how wide the search is. None if the train is flat."""
    end = min(length, math.floor(float(positions.max())) + 4)
    start = min(max(0, start), end - 1)
    centred = _centred(_render(positions + shift, weights, length)[start:end])
    if centred is None:
        return None
    train = np.zeros(length)
    train[start:end] = centred[0]
    return train, centred[1]


def _render(positions: np.ndarray, weights: np.ndarray, length: int) -> np.ndarray:
    """Impulses at fractional frame positions, each split linearly between
    the two frames around it, then smoothed by a 3-frame box -- the audio's
    onset envelope gets the same box (envelope.onset_strength)."""
    train = np.zeros(length + 2)
    base = np.floor(positions).astype(np.int64)
    frac = positions - base
    for index, share in ((base + 1, 1.0 - frac), (base + 2, frac)):  # +1: room for a frame at -1
        keep = (index >= 0) & (index < length + 2)
        np.add.at(train, index[keep], (weights * share)[keep])
    return np.convolve(train[1 : length + 1], np.ones(3) / 3.0, mode="same")


def _ncc_lags(
    train: tuple[np.ndarray, float], audio: tuple[np.ndarray, float], lags: np.ndarray
) -> np.ndarray:
    """Normalised cross-correlation of a centred train moved by each of `lags`
    frames against the centred audio envelope: one FFT for every lag."""
    (m, m_norm), (a, a_norm) = train, audio
    size = 1 << (len(a) + len(m)).bit_length()
    cross = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(m, size)), size)
    # A lag the two can't overlap at would otherwise wrap around the FFT.
    overlap = (lags > -len(m)) & (lags < len(a))
    return np.where(overlap, cross[lags % size], 0.0) / (m_norm * a_norm)


def _ncc_at(
    positions: np.ndarray,
    weights: np.ndarray,
    audio: tuple[np.ndarray, float],
    lag: float,
    length: int,
    start: int,
) -> float:
    """_ncc_lags at one lag of any fraction: the train is rendered at the
    lag's fraction, so the whole-frame shift left over is exact, and at a
    whole-frame lag the two agree. The train covers the song and the search
    either side of it (_train_length), so at any lag searched it overlaps
    the whole song."""
    whole = math.floor(lag)
    train = _train(positions, weights, length, start, lag - whole)
    a, a_norm = audio
    if train is None:
        return 0.0
    m, m_norm = train
    j0, j1 = max(0, -whole), min(len(m), len(a) - whole)
    return float(np.dot(m[j0:j1], a[j0 + whole : j1 + whole])) / (m_norm * a_norm)


def _parabola(values: np.ndarray, k: int) -> float:
    """The vertex of the parabola through values[k-1..k+1], in steps from k."""
    left, mid, right = values[k - 1], values[k], values[k + 1]
    denom = left - 2.0 * mid + right
    return float(0.5 * (left - right) / denom) if denom < 0 else 0.0


# --------------------------------------------------------------------------
# chords
# --------------------------------------------------------------------------
def chord_name(pitches: Iterable[int], *, key_signature: int | None = None) -> str | None:
    """The chord `pitches` (MIDI note numbers) spell: "C", "Am", "G7",
    "Dsus4", "E5" -- over the lowest note when that isn't the root: "C/E",
    "G7/B", "F/G". "?" for a chord the table doesn't name; None for what isn't
    a chord -- one pitch class, or two that aren't a fifth.

    The lowest note is the bass, and decides in turn. A chord the whole set
    spells rooted on it is named plainly: {C, E, G, A} over a C is C6, and {D,
    G, A} over a D Dsus4. Otherwise, if the notes above the bass spell a
    chord of three or more pitch classes, it is that chord over the bass:
    F-A-C over a G is F/G, not Fadd9, and C-E-G over a B is C/B, not Cmaj7 --
    the chart's reading of a bass walking under a held chord. Not over a bass
    with its own third and fifth in the set, though: that bass is the root of
    what is stacked on it (C-E-G-B-D-F# is a Cmaj7#11 the table may lack, not
    Em9/C). Then the whole set's chord over the bass, an inversion: E-G-C is
    C/E, E-G-B-C Cmaj7/E, A-D-G Dsus4/A (sus4 preferred to Gsus2). Notes are spelled for the key signature: in a flat
    key with flats; in a sharp key with its own sharps (F# in G major) and
    the chart's usual spelling for the rest (Bb in G major, not A#); without
    one, C# Eb F# Ab Bb.
    """
    notes = sorted(set(pitches))
    classes = frozenset(p % 12 for p in notes)
    if len(classes) < 2 or (len(classes) == 2 and _interval(classes) not in (5, 7)):
        return None
    spell = _speller(key_signature)
    bass = notes[0] % 12
    whole = _quality(classes, bass)
    if whole is not None and whole[0] == bass:
        return spell(bass) + whole[1]
    above_bass = {(p - bass) % 12 for p in classes}
    own_triad = (3 in above_bass or 4 in above_bass) and 7 in above_bass
    upper = frozenset(p % 12 for p in notes[1:])
    above = _quality(upper, notes[1] % 12) if len(upper) >= 3 and not own_triad else None
    if above is not None:
        return f"{spell(above[0])}{above[1]}/{spell(bass)}"
    if whole is not None:
        return f"{spell(whole[0])}{whole[1]}/{spell(bass)}"
    return "?"


def _quality(classes: frozenset[int], bass: int) -> tuple[int, str] | None:
    """(root, suffix) of the chord a pitch-class set spells, preferring a root
    on `bass`, then _QUALITIES' order, then the root nearest above the bass;
    None if the table has no name for it."""
    best: tuple[int, int, int, str] | None = None  # (not on the bass, priority, root distance, suffix)
    for priority, (suffix, intervals) in enumerate(_QUALITIES):
        if len(intervals) != len(classes):
            continue
        for root in classes:
            if frozenset((p - root) % 12 for p in classes) == intervals:
                candidate = (0 if root == bass else 1, priority, (root - bass) % 12, suffix)
                if best is None or candidate < best:
                    best = candidate
    return None if best is None else ((bass + best[2]) % 12, best[3])


def _speller(key_signature: int | None):
    """Pitch class -> its name for a key signature (sharps > 0, flats < 0)."""
    if key_signature and key_signature < 0:
        return _FLATS.__getitem__
    sharps = set(_SHARP_ORDER[: key_signature or 0])
    return lambda pc: _SHARPS[pc] if pc in sharps else _PLAIN[pc]


def _interval(classes: frozenset[int]) -> int:
    a, b = sorted(classes)
    return b - a


def is_harmonic(track: Track) -> bool:
    """Whether a track plays chords: not drum-like, and at least
    POLYPHONIC_SHARE of its onset clusters sound one (chord_name not None)."""
    if track.drum_like or not track.notes:
        return False
    clusters = _sounding(track.notes)
    chords = sum(1 for _, pitches in clusters if chord_name(pitches) is not None)
    return chords >= 2 and chords >= POLYPHONIC_SHARE * len(clusters)


def chord_events(
    track: Track, tempo: TempoMap, *, key_signature: int | None = None
) -> list[tuple[float, float, str]]:
    """(start s, until s, name) of every chord change in `track`, MIDI time.

    Per onset cluster (notes starting within CHORD_CLUSTER of each other), the
    pitch classes sounding: the cluster's own notes and any earlier note still
    held CHORD_CLUSTER into it, so a pad under a stab counts and a legato
    overlap doesn't. Consecutive clusters with one set are one segment; a
    segment is a change only if it is a chord, differs from the last change,
    and holds for an 8th note (at the tempo there) until the set changes.
    `until` is when the next change starts, or the track's last note ends.
    """
    clusters = _sounding(track.notes)
    if not clusters:
        return []
    segments: list[tuple[float, frozenset[int], list[int]]] = []
    for t, pitches in clusters:
        classes = frozenset(p % 12 for p in pitches)
        if segments and segments[-1][1] == classes:
            continue
        segments.append((t, classes, pitches))
    last_end = max(note.t + note.dur for note in track.notes)
    changes: list[tuple[float, float, str]] = []
    emitted: frozenset[int] | None = None
    for i, (t, classes, pitches) in enumerate(segments):
        name = chord_name(pitches, key_signature=key_signature)
        if name is None or classes == emitted:
            continue
        until = segments[i + 1][0] if i + 1 < len(segments) else last_end
        eighth = float(tempo.seconds_at(tempo.quarters_at(t) + 0.5)) - t
        if until - t < eighth - 1e-9:
            continue
        if changes:
            changes[-1] = (changes[-1][0], t, changes[-1][2])
        changes.append((t, last_end, name))
        emitted = classes
    return changes


def _sounding(notes: Sequence[Note]) -> list[tuple[float, list[int]]]:
    """(cluster start, the pitches sounding there) for every onset cluster:
    its own notes', then each pitch still held into it, once. The held
    pitches are counted as they come and go, so a track of notes never
    turned off -- every one of them held to the end -- costs a pass, not a
    pass per cluster."""
    ordered = sorted(notes, key=lambda n: (n.t, n.pitch))
    held: list[tuple[float, int]] = []  # heap of (end, pitch) of notes begun before the cluster
    holding: Counter[int] = Counter()  # how many of `held` sound each pitch
    clusters: list[tuple[float, list[int]]] = []
    i = 0
    while i < len(ordered):
        start = ordered[i].t
        j = i
        while j < len(ordered) and ordered[j].t - start < CHORD_CLUSTER:
            j += 1
        while held and held[0][0] <= start + CHORD_CLUSTER:
            _, pitch = heapq.heappop(held)
            holding[pitch] -= 1
            if not holding[pitch]:
                del holding[pitch]
        clusters.append((start, [n.pitch for n in ordered[i:j]] + list(holding)))
        for n in ordered[i:j]:
            heapq.heappush(held, (n.t + n.dur, n.pitch))
            holding[n.pitch] += 1
        i = j
    return clusters
