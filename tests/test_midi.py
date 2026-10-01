"""audio/midi.py: the Standard MIDI File reader, the session's grid on the
master, the alignment and the chords.

Every MIDI file here is written byte by byte by the helpers below -- no file
from a DAW, no recording, nothing from a real session (AGENTS.md). The
alignment is tested on onset envelopes built from impulses; the same thing
end to end, on audio rendered from a MIDI file, is tests/test_envelope.py's.

What is pinned is what a reader gets wrong quietly: running status, a note-on
at velocity 0, two notes on one pitch at once, tempo changes and SMPTE time,
a 3/4 bar between 4/4 ones, and a truncated file read as a shorter song
instead of refused. Then what the 0.4 review found, each with the reviewers'
own case: one 3/8 bar moving every later bar line off the beats, 6/8's pulse
counted in quarters, a pedalled piano read as single notes, a tempo of 1
microsecond and a note 17 years down a 70-byte file asking for more memory
than exists, ten thousand tracks of one name, and chords named without
their bass (F/G as Fadd9).
"""

from __future__ import annotations

import math
import struct
import tracemalloc

import numpy as np
import pytest

from kaleidophone.audio import midi as M

PPQ = 480


# --------------------------------------------------------------------------
# a Standard MIDI File, byte by byte
# --------------------------------------------------------------------------
def vlq(n: int) -> bytes:
    """A variable-length quantity: 7 bits a byte, most significant first."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def chunk(kind: bytes, body: bytes) -> bytes:
    return kind + len(body).to_bytes(4, "big") + body


def header(fmt: int, ntracks: int, division: int = PPQ) -> bytes:
    return chunk(b"MThd", struct.pack(">HHH", fmt, ntracks, division))


def ev(delta: int, *data: int) -> bytes:
    return vlq(delta) + bytes(data)


def meta(delta: int, kind: int, payload: bytes) -> bytes:
    return vlq(delta) + bytes([0xFF, kind]) + vlq(len(payload)) + payload


def tempo(delta: int, bpm: float) -> bytes:
    return meta(delta, 0x51, round(60e6 / bpm).to_bytes(3, "big"))


def timesig(delta: int, num: int, den: int, clocks: int = 24) -> bytes:
    """A time signature; `clocks` is its metronome byte, MIDI clocks per click."""
    return meta(delta, 0x58, bytes([num, den.bit_length() - 1, clocks, 8]))


def keysig(delta: int, sharps: int) -> bytes:
    return meta(delta, 0x59, bytes([sharps & 0xFF, 0]))


def name(delta: int, text: str | bytes, kind: int = 0x03) -> bytes:
    return meta(delta, kind, text.encode("utf-8") if isinstance(text, str) else text)


def eot(delta: int = 0) -> bytes:
    return meta(delta, 0x2F, b"")


def mtrk(*events: bytes) -> bytes:
    return chunk(b"MTrk", b"".join(events))


def note_track(notes, title: str | None = None, channel: int = 0) -> bytes:
    """A track of (start tick, end tick, pitch, velocity) notes; offs sort
    before ons at the same tick, as DAWs write them."""
    events = []
    for start, end, pitch, velocity in notes:
        events.append((start, 1, bytes([0x90 | channel, pitch, velocity])))
        events.append((end, 0, bytes([0x80 | channel, pitch, 0])))
    events.sort()
    out = [name(0, title)] if title else []
    tick = 0
    for at, _, data in events:
        out.append(vlq(at - tick) + data)
        tick = at
    return mtrk(*out, eot())


def conductor(tempos=((0, 120.0),), meters=((0, 4, 4),)) -> bytes:
    """Track 1 of a format-1 file: the tempo map and the time signatures,
    each (tick, num, den) or (tick, num, den, metronome clocks)."""
    events = sorted([(t, 0, b) for t, b in tempos] + [(m[0], 1, tuple(m[1:])) for m in meters])
    out, tick = [], 0
    for at, kind, value in events:
        out.append(tempo(at - tick, value) if kind == 0 else timesig(at - tick, *value))
        tick = at
    return mtrk(*out, eot())


def smf(tracks, ppq: int = PPQ, fmt: int = 1) -> bytes:
    return header(fmt, len(tracks), ppq) + b"".join(tracks)


def q(quarters: float) -> int:
    return round(quarters * PPQ)


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------
def test_a_format_0_file_with_no_tempo_event_runs_at_120_bpm():
    data = header(0, 1, 96) + mtrk(ev(96, 0x90, 60, 100), ev(48, 0x80, 60, 0), eot())
    midi = M.parse_midi(data)
    (track,) = midi.tracks
    assert (midi.format, midi.ppq, midi.smpte) == (0, 96, None)
    assert track.notes == (M.Note(t=0.5, dur=0.25, pitch=60, velocity=100, channel=0),)
    assert midi.tempo.bpm_at(0.0) == 120.0 and midi.end == 0.75
    assert midi.meter == ((0.0, 4, 4),) and not midi.has_meter


def test_format_1_names_its_tracks_and_leaves_the_conductor_track_out():
    data = smf(
        [
            conductor(),
            note_track([(0, q(1), 36, 127)], "Kick", 9),
            note_track([(q(1), q(2), 64, 64)], "Keys"),
        ]
    )
    midi = M.parse_midi(data, name="song.mid")
    assert [(t.label, t.slug, t.number) for t in midi.tracks] == [("Kick", "kick", 2), ("Keys", "keys", 3)]
    assert midi.notes == 2 and midi.name == "song.mid"
    assert [t.drum_like for t in midi.tracks] == [True, False]


def test_ticks_become_seconds_through_every_tempo_change():
    """Two quarters at 120 (1.0 s), then 60 BPM: tick 1440 is one quarter
    into the slow part (2.0 s), tick 2400 three quarters in (4.0 s)."""
    data = smf(
        [
            conductor(tempos=((0, 120.0), (q(2), 60.0))),
            note_track([(q(1), q(2), 60, 90), (q(3), q(5), 62, 90)]),
        ]
    )
    midi = M.parse_midi(data)
    notes = midi.tracks[0].notes
    assert [(n.t, n.dur) for n in notes] == [(0.5, 0.5), (2.0, 2.0)]
    assert midi.tempo.bpm_at(0.99) == 120.0 and midi.tempo.bpm_at(1.0) == 60.0
    assert midi.tempo.seconds_at(5.0) == pytest.approx(4.0)
    assert midi.tempo.quarters_at(-0.5) == pytest.approx(-1.0)  # pre-roll runs at the first tempo


def test_tempo_events_count_from_any_track_and_the_last_at_a_tick_wins():
    data = smf(
        [
            conductor(tempos=((0, 120.0),)),
            mtrk(
                tempo(0, 90.0),
                tempo(q(1), 100.0),
                tempo(0, 60.0),
                ev(0, 0x90, 60, 1),
                ev(q(1), 0x80, 60, 0),
                eot(),
            ),
        ]
    )
    midi = M.parse_midi(data)
    # Track 2's tick-0 tempo overrides track 1's. Stored in whole microseconds a
    # quarter note, 90 BPM is 666,667 us: 89.99996 BPM.
    assert midi.tempo.bpm_at(0.0) == pytest.approx(90.0, abs=1e-4)
    assert midi.tempo.bpm_at(0.7) == 60.0  # at tick 480, 100 then 60: the last wins
    note = midi.tracks[0].notes[0]  # on at tick 480, one quarter at 60 BPM
    assert note.t == pytest.approx(60.0 / 90.0, abs=1e-6) and note.dur == pytest.approx(1.0)


def test_a_first_tempo_event_after_tick_0_leaves_120_bpm_before_it():
    data = smf([conductor(tempos=((q(4), 60.0),)), note_track([(q(5), q(6), 60, 90)])])
    midi = M.parse_midi(data)
    assert midi.tempo.bpm_at(1.0) == 120.0
    assert midi.tracks[0].notes[0].t == pytest.approx(2.0 + 1.0)


@pytest.mark.parametrize(("code", "fps"), [(25, 25.0), (29, 30000.0 / 1001.0)])
def test_an_smpte_division_counts_real_time_and_ignores_tempo_for_timing(code, fps):
    division = ((256 - code) << 8) | 40
    ticks = round(1.5 * fps * 40)
    data = (
        header(1, 2, division)
        + conductor(tempos=((0, 60.0),))
        + mtrk(ev(ticks, 0x90, 60, 80), ev(40, 0x80, 60, 0), eot())
    )
    midi = M.parse_midi(data)
    note = midi.tracks[0].notes[0]
    assert midi.ppq is None and midi.smpte == (fps, 40)
    assert note.t == pytest.approx(ticks / (fps * 40)) and note.dur == pytest.approx(1.0 / fps)
    # The tempo still says where the beats are: 60 BPM, one a second.
    assert midi.tempo.quarters_at(note.t) == pytest.approx(note.t)


def test_running_status_reads_events_without_their_status_byte_even_across_a_meta_event():
    data = header(0, 1) + mtrk(
        ev(0, 0x90, 60, 100),
        ev(0, 64, 100),  # running status: another note-on
        meta(0, 0x01, b"a marker"),
        ev(q(1), 60, 0),  # still running after the meta event: a note-on at velocity 0
        ev(0, 64, 0),
        eot(),
    )
    notes = M.parse_midi(data).tracks[0].notes
    assert [(n.pitch, n.t, n.dur) for n in notes] == [(60, 0.0, 0.5), (64, 0.0, 0.5)]


def test_a_note_on_at_velocity_0_is_a_note_off():
    data = header(0, 1) + mtrk(ev(0, 0x91, 50, 70), ev(q(2), 0x91, 50, 0), eot(q(4)))
    (note,) = M.parse_midi(data).tracks[0].notes
    assert (note.dur, note.velocity, note.channel) == (1.0, 70, 1)


def test_overlapping_notes_on_one_pitch_end_first_in_first_out():
    """on 0, on 240, off 480, off 960: the first off ends the first note. A
    stray off is ignored, and a note never turned off ends with its track."""
    data = header(0, 1) + mtrk(
        ev(0, 0x90, 60, 100),
        ev(240, 0x90, 60, 50),
        ev(240, 0x80, 60, 0),
        ev(480, 0x80, 60, 0),
        ev(0, 0x80, 61, 0),  # nothing to end
        ev(0, 0x90, 62, 80),  # never ended
        eot(q(2)),
    )
    midi = M.parse_midi(data)
    notes = [(n.pitch, n.t, n.dur, n.velocity) for n in midi.tracks[0].notes]
    assert notes == [(60, 0.0, 0.5, 100), (60, 0.25, 0.75, 50), (62, 1.0, 1.0, 80)]
    assert midi.unclosed == 1


def test_sysex_escapes_alien_chunks_and_events_a_pack_has_no_use_for_are_skipped():
    data = (
        header(1, 1)
        + chunk(b"XFIH", b"\x01\x02\x03")
        + mtrk(
            ev(0, 0xF0, 3, 0x7E, 0x7F, 0xF7),  # sysex
            ev(0, 0xF7, 2, 0x01, 0x02),  # escape
            meta(0, 0x7F, b"\x00\x00\x41"),  # sequencer-specific
            meta(0, 0x21, b"\x00"),  # port
            ev(0, 0xC0, 5),  # program change: one data byte
            ev(0, 0xB0, 7, 100),  # controller
            ev(0, 0xE0, 0, 64),  # pitch bend
            ev(0, 0xD0, 30),  # channel pressure: one data byte
            ev(0, 0xA0, 60, 10),  # poly pressure
            ev(0, 0x90, 60, 100),
            ev(q(1), 0x80, 60, 0),
            eot(),
            b"trailing bytes after the end of track are ignored",
        )
    )
    (note,) = M.parse_midi(data).tracks[0].notes
    assert (note.pitch, note.t, note.dur) == (60, 0.0, 0.5)


def test_track_names_become_unique_slugs_and_unnamed_tracks_get_their_number():
    one = [(0, q(1), 60, 90)]
    data = smf(
        [
            note_track(one, "Keys"),
            note_track(one, "Keys"),
            note_track(one, "Keys 2"),
            note_track(one),
            note_track(one, "Bajo Eléctrico"),
            note_track(one, "صدا"),
            mtrk(name(0, "Lead Synth", kind=0x04), ev(0, 0x90, 70, 90), ev(q(1), 0x80, 70, 0), eot()),
            note_track(one, "Track 4"),
        ]
    )
    tracks = M.parse_midi(data).tracks
    assert [t.slug for t in tracks] == [
        "keys",
        "keys-2",
        "keys-2-2",
        "track-4",
        "bajo-electrico",
        "track-6",
        "lead-synth",
        "track-4-2",
    ]
    assert tracks[5].label == "صدا" and tracks[5].name == "صدا"  # the name is kept; the key is its number
    assert tracks[3].label == "track-4" and tracks[3].name is None


def test_a_name_that_is_not_utf_8_is_read_as_latin_1_and_a_blank_one_is_no_name():
    data = smf([note_track([(0, q(1), 60, 90)], b"Caf\xe9"), mtrk(name(0, b"  \x00 "), eot())])
    midi = M.parse_midi(data)
    assert [t.name for t in midi.tracks] == ["Café"]


def test_a_format_0_file_is_split_by_channel():
    data = header(0, 1) + mtrk(
        name(0, "the song"),
        ev(0, 0x90, 60, 90),
        ev(0, 0x99, 36, 120),
        ev(q(1), 0x80, 60, 0),
        ev(0, 0x89, 36, 0),
        eot(),
    )
    tracks = M.parse_midi(data).tracks
    assert [(t.label, t.slug, t.drum_like) for t in tracks] == [
        ("channel-1", "channel-1", False),
        ("channel-10", "channel-10", True),
    ]


@pytest.mark.parametrize(
    ("title", "drums"),
    [
        ("Kick", True),
        ("HiHat", True),
        ("Perc_Loop", True),
        ("808 Drums", True),
        ("Keys", False),
        ("Kickstart Pad", False),
    ],
)
def test_a_track_is_drum_like_by_its_name(title, drums):
    data = smf([note_track([(0, q(1), 60, 90)], title)])
    assert M.parse_midi(data).tracks[0].drum_like is drums


def test_the_first_key_signature_is_kept_and_4_4_runs_until_the_first_time_signature():
    data = smf(
        [mtrk(timesig(q(1), 3, 4), keysig(q(3), 2), keysig(0, -3), eot()), note_track([(0, q(1), 60, 90)])]
    )
    midi = M.parse_midi(data)
    assert midi.key_signature == 2  # two at one tick: the first in the file
    assert midi.meter == ((0.0, 4, 4), (1.0, 3, 4)) and midi.has_meter


def test_read_midi_reads_a_file_and_is_named_by_its_basename(tmp_path):
    path = tmp_path / "Song.mid"
    path.write_bytes(smf([note_track([(0, q(1), 60, 90)], "Keys")]))
    assert M.read_midi(str(path)).name == "Song.mid"
    with pytest.raises(FileNotFoundError):
        M.read_midi(str(tmp_path / "missing.mid"))


def _track(*events: bytes) -> bytes:
    return header(0, 1) + mtrk(*events)


@pytest.mark.parametrize(
    ("data", "says"),
    [
        (b"RIFF\x00\x00\x00\x00RMIDdata", "RIFF"),
        (b"ID3 not a midi file at all", "doesn't start with an 'MThd'"),
        (b"MThd\x00\x00\x00\x06\x00\x01", "cut short"),
        (b"MThd\x00\x00\x00\x04\x00\x01\x00\x01\x01\xe0", "at least 6"),
        (header(2, 1) + mtrk(eot()), "format 2"),
        (header(7, 1) + mtrk(eot()), "unknown MIDI file format 7"),
        (header(1, 0), "no tracks"),
        (header(1, 1, (256 - 26) << 8 | 40) + mtrk(eot()), "SMPTE division of 26 fps"),
        (header(1, 1, 0) + mtrk(eot()), "a division of 0"),
        (header(1, 2) + mtrk(eot()), "promises 2 tracks"),
        (header(1, 1) + b"\x00\x01\x02\x03\x00\x00\x00\x00", "garbage"),
        (header(1, 1) + b"MTrk\x00\x00\x01\x00" + eot(), "says it is 256 bytes long"),
        (_track(ev(0, 0x90, 60)), "cut short"),
        (_track(vlq(0)), "cut short"),
        (_track(b"\x81\x80\x80\x80\x00"), "longer than MIDI's 4 bytes"),
        (_track(b"\x81"), "cut short"),
        (_track(ev(0, 60, 100)), "no status before it"),
        (_track(ev(0, 0xF3, 1)), "never appears"),
        (_track(ev(0, 0x90, 0x90, 100)), "a status byte where event data belongs"),
        (_track(meta(0, 0x51, b"\x07\xa1")), "a tempo event 2 bytes long"),
        (_track(meta(0, 0x51, b"\x00\x00\x00")), "a tempo of 0"),
        (_track(meta(0, 0x51, b"\x00\x00\x01")), "a tempo of 6e+07 BPM (1 microseconds per quarter note)"),
        (_track(meta(0, 0x51, (59_999).to_bytes(3, "big"))), "outside the 10-1000 BPM"),
        (_track(meta(0, 0x51, (6_000_001).to_bytes(3, "big"))), "a tempo of 9.999998 BPM"),
        (_track(meta(0, 0x58, b"\x00\x02\x18\x08")), "time signature MIDI can't mean (0/2^2)"),
        (_track(meta(0, 0x58, b"\x04\x09\x18\x08")), "(4/2^9)"),
        (_track(meta(0, 0x58, b"\x04")), "(1 bytes)"),
        (_track(b"\x00\xff"), "cut short"),
        (_track(b"\x00\xff\x03\x05ab"), "cut short"),
        (_track(b"\x00\xf0\x05\x01\x02"), "cut short"),
    ],
)
def test_a_file_this_reader_cannot_use_is_refused_with_what_is_wrong(data, says):
    with pytest.raises(M.MidiError, match=None) as exc:
        M.parse_midi(data, name="x.mid")
    assert says in str(exc.value) and str(exc.value).startswith("x.mid")


def test_a_file_with_no_notes_still_has_a_tempo_map():
    midi = M.parse_midi(smf([conductor(tempos=((0, 96.0),))]))
    assert midi.tracks == () and midi.notes == 0 and midi.tempo.bpm_at(0.0) == 96.0


def test_the_tempo_limits_themselves_are_tempos():
    for bpm in (10.0, 1000.0):
        assert M.parse_midi(smf([conductor(tempos=((0, bpm),))])).tempo.bpm_at(0.0) == pytest.approx(bpm)


def test_read_midi_checks_the_header_before_reading_the_file_and_refuses_one_far_too_big(tmp_path, monkeypatch):
    riff = tmp_path / "Song.wav"
    riff.write_bytes(b"RIFF" + b"\x00" * 1000)
    with pytest.raises(M.MidiError, match=r"^Song.wav: not a Standard MIDI File.*a RIFF file"):
        M.read_midi(str(riff))
    big = tmp_path / "Big.mid"
    big.write_bytes(smf([note_track([(0, q(1), 60, 90)], "Keys")]))
    monkeypatch.setattr(M, "MAX_MIDI_BYTES", 2 << 20)
    with open(big, "ab") as fh:
        fh.write(b"\x00" * (3 << 20))  # alien bytes after the tracks, read past nowhere
    with pytest.raises(M.MidiError, match=r"^Big.mid: 3 MB, and a song's MIDI is kilobytes \(this reads at most 2 MB\)"):
        M.read_midi(str(big))


def test_ten_thousand_tracks_of_one_name_get_their_numbers_without_counting_up_each_time():
    """The staff review's case: every track named 'x'. A name taken by a
    later track ('x 3' -> x-3) is skipped, not handed out twice."""
    one = [(0, 10, 60, 90)]
    tracks = [note_track(one, "x") for _ in range(3)] + [note_track(one, "x 4"), note_track(one, "x")]
    tracks += [note_track(one, "x")] * 9995
    slugs = [t.slug for t in M.parse_midi(smf(tracks)).tracks]
    assert slugs[:6] == ["x", "x-2", "x-3", "x-4", "x-5", "x-6"]
    assert len(set(slugs)) == len(slugs) == 10_000 and slugs[-1] == "x-10000"


# --------------------------------------------------------------------------
# the sustain pedal
# --------------------------------------------------------------------------
def _pedal(delta: int, down: bool, channel: int = 0) -> bytes:
    return ev(delta, 0xB0 | channel, 64, 127 if down else 0)


def test_a_note_released_under_the_pedal_sounds_until_the_pedal_comes_up():
    """Pedal down at 0; C released at beat 1 and E at beat 2 sound on to the
    pedal's release at beat 3. G, released after it, ends at its own off."""
    data = header(0, 1) + mtrk(
        _pedal(0, True),
        ev(0, 0x90, 60, 90),
        ev(q(1), 0x80, 60, 0),
        ev(0, 0x90, 64, 90),
        ev(q(1), 0x80, 64, 0),
        ev(0, 0x90, 67, 90),
        ev(q(1), 0xB0, 64, 63),  # 63: the pedal is up below 64
        ev(q(1), 0x80, 67, 0),
        eot(),
    )
    notes = {n.pitch: (n.t, n.dur) for n in M.parse_midi(data).tracks[0].notes}
    assert notes == {60: (0.0, 1.5), 64: (0.5, 1.0), 67: (1.0, 1.0)}


def test_a_key_struck_again_under_the_pedal_ends_the_note_it_held_and_the_pedal_is_per_channel():
    data = header(0, 1) + mtrk(
        _pedal(0, True),
        _pedal(0, True),  # pressed again while down: nothing changes
        ev(0, 0x90, 60, 90),
        ev(q(1), 0x80, 60, 0),
        ev(q(1), 0x90, 60, 70),  # struck again at beat 2: the held C ends there
        ev(0, 0x91, 50, 90),  # channel 2 has no pedal down
        ev(q(1), 0x81, 50, 0),
        ev(0, 0x80, 60, 0),
        _pedal(0, False, channel=1),  # up on a channel whose pedal was never down
        eot(q(2)),  # the pedal is still down when the track ends: its notes end there
    )
    midi = M.parse_midi(data)
    notes = sorted((n.channel, n.pitch, n.t, n.dur, n.velocity) for t in midi.tracks for n in t.notes)
    assert notes == [(0, 60, 0.0, 1.0, 90), (0, 60, 1.0, 1.5, 70), (1, 50, 1.0, 0.5, 90)]
    assert midi.unclosed == 0  # a note the pedal holds to the end was released: it isn't unclosed


def test_a_pedalled_arpeggio_is_the_chord_it_sounds_like():
    """The musician's case: a piano arpeggiating C, Am, F, G in 8ths of a
    fifth of a beat each, the pedal down for each bar. Read without the
    pedal it is single notes and no chord at all."""
    events, tick = [name(0, "Piano")], 0
    for bar, root in enumerate([48, 45, 41, 43]):
        third = 3 if root == 45 else 4
        timed = [(q(4 * bar), _pedal, True), (q(4 * bar + 3.95), _pedal, False)]
        for i, pitch in enumerate([root, root + third, root + 7, root + 12, root + 7, root + third, root + 12, root + 7]):
            at = q(4 * bar + 0.5 * i)
            timed += [(at, "on", pitch), (at + q(0.2), "off", pitch)]
        for at, kind, value in sorted(timed, key=lambda e: (e[0], e[1] != "off")):
            if kind == "on":
                events.append(ev(at - tick, 0x90, value, 90))
            elif kind == "off":
                events.append(ev(at - tick, 0x80, value, 0))
            else:
                events.append(kind(at - tick, value))
            tick = at
    midi = M.parse_midi(smf([conductor(tempos=((0, 90.0),)), mtrk(*events, eot())]))
    (piano,) = midi.tracks
    assert M.is_harmonic(piano)
    changes = M.chord_events(piano, midi.tempo)
    assert [(round(t, 3), name) for t, _, name in changes] == [
        (0.667, "C"),
        (3.333, "Am"),
        (6.0, "F"),
        (8.667, "G"),
    ]


# --------------------------------------------------------------------------
# bars and the session's grid on the master
# --------------------------------------------------------------------------
def _midi(tempos=((0, 120.0),), meters=((0, 4, 4),), bars: int = 8) -> M.MidiFile:
    """A conductor track and one quarter-note click track, `bars` 4/4 bars long."""
    clicks = [(q(k), q(k) + 60, 37, 100) for k in range(4 * bars)]
    return M.parse_midi(smf([conductor(tempos, meters), note_track(clicks, "Click", 9)]))


def test_bars_follow_the_time_signatures_from_3_4_to_4_4():
    midi = _midi(meters=((0, 3, 4), (q(6), 4, 4)))
    lines = M.bar_lines(midi, 14.0)
    assert [(line[0], line[1], line[2]) for line in lines] == [
        (0, 1, 3),
        (3, 2, 3),
        (6, 3, 4),
        (10, 4, 4),
        (14, 5, 4),
    ]


def test_a_time_signature_arriving_mid_bar_starts_a_new_bar_there():
    midi = _midi(meters=((0, 4, 4), (q(2), 3, 4)))
    assert [line[0] for line in M.bar_lines(midi, 9.0)] == [0.0, 2.0, 5.0, 8.0]


def test_a_6_8_bar_is_three_quarter_notes_and_a_7_8_bar_three_and_a_half():
    assert [line[0] for line in M.bar_lines(_midi(meters=((0, 6, 8),)), 6.0)] == [0.0, 3.0, 6.0]
    assert [line[0] for line in M.bar_lines(_midi(meters=((0, 7, 8),)), 7.0)] == [0.0, 3.5, 7.0]


def test_bars_before_tick_0_are_extrapolated_and_numbered_down_from_0():
    lines = M.bar_lines(_midi(), 4.0, q_from=-6.0)
    assert [(line[0], line[1]) for line in lines] == [(-8.0, -1), (-4.0, 0), (0.0, 1), (4.0, 2)]
    with pytest.raises(ValueError, match="check the offset"):
        M.bar_lines(_midi(), 4.0, q_from=-2e6)


def test_the_grid_lands_on_the_master_with_pre_roll():
    grid = M.session_grid(_midi(), 0.5, 10.0)
    assert grid.downbeat == 0.5 and grid.downbeat_bar == 1 and grid.bpm == 120.0
    assert grid.beats[0] == pytest.approx(0.0) and np.allclose(np.diff(grid.beats), 0.5)
    assert grid.beat_bars[:3].tolist() == [0, 1, 1]  # the pre-roll beat is in the extrapolated bar 0
    assert grid.tempo_map == [(0.0, 120.0)] and grid.time_signatures == [(0.0, 4, 4)]


def test_a_bounce_that_starts_after_the_session_takes_its_first_whole_bar_as_bar_1():
    grid = M.session_grid(_midi(), -1.25, 10.0)
    assert grid.downbeat == pytest.approx(0.75) and grid.downbeat_bar == 2
    assert grid.beats[0] == pytest.approx(0.25)
    assert grid.bars[0][:2] == (pytest.approx(0.75), 2)


def test_a_bar_line_a_hair_before_0_is_bar_1_at_0():
    grid = M.session_grid(_midi(), -2.0003, 10.0)
    assert grid.downbeat == 0.0 and grid.downbeat_bar == 2 and grid.beats[0] == 0.0


def test_the_grid_follows_a_tempo_change_exactly():
    """120 BPM for two bars (4 s), then 60: beats 0.5 s apart, then 1 s."""
    grid = M.session_grid(_midi(tempos=((0, 120.0), (q(8), 60.0))), 0.0, 12.0)
    assert np.allclose(grid.beats, [0.5 * k for k in range(8)] + [4.0 + k for k in range(8)])
    assert grid.tempo_map == [(0.0, 120.0), (4.0, 60.0)]
    assert [bar[0] for bar in grid.bars] == [0.0, 2.0, 4.0, 8.0]


def test_the_time_signatures_in_the_song_start_with_the_one_in_effect_at_0():
    grid = M.session_grid(_midi(meters=((0, 3, 4), (q(6), 4, 4))), -2.0, 20.0)
    assert grid.time_signatures == [(0.0, 3, 4), (pytest.approx(1.0), 4, 4)]
    assert grid.downbeat == pytest.approx(1.0) and grid.downbeat_bar == 3


def test_a_meter_given_for_a_file_without_one_sets_the_bars():
    grid = M.session_grid(_midi(meters=()), 0.0, 6.0, meter=((0.0, 3, 4),))
    assert [bar[0] for bar in grid.bars] == [0.0, 1.5, 3.0, 4.5]


def test_an_offset_that_puts_bar_1_after_the_song_is_refused():
    with pytest.raises(ValueError, match="don't reach into the song"):
        M.session_grid(_midi(bars=4), 12.0, 10.0)


def test_the_grid_runs_on_past_the_midis_last_event_at_its_last_tempo():
    """A conductor track that ends at tick 0 still sets the tempo for the
    whole song -- as the DAW's timeline does after its last region."""
    midi = M.parse_midi(smf([conductor(tempos=((0, 100.0),))]))
    grid = M.session_grid(midi, -40.0, 10.0)
    assert np.allclose(np.diff(grid.beats), 0.6) and grid.downbeat_bar == 18


def test_beats_are_counted_from_every_bar_line_after_an_odd_bar():
    """The musician's case: 4/4 at 120 with one 3/8 bar (bar 5). Counted in
    quarters from tick 0, every later bar line sat 250 ms -- half a beat --
    from the nearest beat; counted from each bar line, every bar starts on
    one, and the 3/8 bar has a beat and a half."""
    midi = _midi(meters=((0, 4, 4), (q(16), 3, 8), (q(17.5), 4, 4)), bars=10)
    grid = M.session_grid(midi, 0.0, 20.0)
    lines = [bar[0] for bar in grid.bars]
    assert lines[3:7] == [6.0, 8.0, 8.75, 10.75]
    assert all(np.min(np.abs(grid.beats - line)) < 1e-9 for line in lines)
    assert grid.beats[16:20].tolist() == [8.0, 8.5, 8.75, 9.25]  # 1, 2 of the 3/8 bar, then bar 6
    assert grid.beat_bars[16:19].tolist() == [5, 5, 6]


def test_a_7_8_bar_has_four_beats_the_last_an_eighth():
    grid = M.session_grid(_midi(meters=((0, 7, 8),)), 0.0, 3.6)
    assert grid.beats.tolist() == [0.0, 0.5, 1.0, 1.5, 1.75, 2.25, 2.75, 3.25, 3.5]
    assert grid.pulses.tolist() == [0.25 * k for k in range(15)] and grid.pulses_per_bar == 7


@pytest.mark.parametrize(
    ("num", "den", "clocks", "pulse"),
    [
        (4, 4, 24, 1.0),
        (3, 4, 24, 1.0),
        (6, 8, 24, 1.5),  # 24, the default writers put anywhere, says nothing: 6/8 is felt in 2
        (6, 8, 36, 1.5),  # the spec's own example: a click every dotted quarter
        (6, 8, 12, 0.5),  # a slow 6/8, counted in six
        (9, 8, 24, 1.5),
        (12, 8, 36, 1.5),
        (12, 16, 24, 0.75),
        (3, 8, 24, 0.5),
        (7, 8, 24, 0.5),
        (7, 8, 36, 0.5),  # 36 doesn't divide a 7/8 bar
        (2, 2, 24, 2.0),
        (4, 4, 48, 2.0),  # cut time, said by the metronome
        (6, 4, 24, 1.0),  # 6/4 isn't inferred to be compound: only 8ths and shorter are
        (6, 4, 72, 3.0),
        (4, 4, 3, 1.0),  # a click every 32nd note is no felt beat
        (4, 4, None, 1.0),  # a time signature two bytes long has no metronome byte
        (6, 8, None, 1.5),
    ],
)
def test_the_pulse_is_the_felt_beat(num, den, clocks, pulse):
    assert M.pulse_length(num, den, clocks) == pulse


def test_6_8_pulses_on_the_dotted_quarter_while_beats_stay_quarters():
    """The musician's case: 6/8 at quarter = 120, as Logic shows it. The
    beats are 0.5 s apart, three to a bar; the felt pulse is 0.75 s, two to
    a bar -- from the metronome byte when it says so, inferred when it is 24."""
    for clocks in (36, 24):
        midi = M.parse_midi(smf([conductor(meters=((0, 6, 8, clocks),)), note_track([(0, q(1), 36, 100)], "Kick", 9)]))
        grid = M.session_grid(midi, 0.0, 6.0)
        assert grid.beats.tolist()[:4] == [0.0, 0.5, 1.0, 1.5]
        assert grid.pulses.tolist() == [0.75 * k for k in range(8)] and grid.pulses_per_bar == 2
        assert midi.pulses == (1.5,)


def test_a_two_byte_time_signature_and_a_late_first_one_still_have_pulses():
    data = smf([mtrk(meta(q(4), 0x58, bytes([6, 3])), eot()), note_track([(0, q(1), 60, 90)])])
    midi = M.parse_midi(data)
    assert midi.meter == ((0.0, 4, 4), (4.0, 6, 8)) and midi.pulses == (1.0, 1.5)
    grid = M.session_grid(midi, 0.0, 4.0)
    assert grid.pulses.tolist() == [0.0, 0.5, 1.0, 1.5, 2.0, 2.75, 3.5] and grid.pulses_per_bar == 4


def test_a_meter_given_for_a_file_without_one_pulses_on_its_beats():
    grid = M.session_grid(_midi(meters=()), 0.0, 3.0, meter=((0.0, 6, 4),))
    assert np.array_equal(grid.pulses, grid.beats) and grid.pulses_per_bar == 6


def test_a_downbeat_given_moves_bar_1_off_tick_0_for_a_clip_that_opens_on_a_pickup():
    """A clip exported one beat before bar 1: tick 0 is beat 4 of a pickup
    bar. Given bar 1 at 1.0 s (master), the bars run in 4/4 from there and
    the pickup's beat is in bar 0."""
    grid = M.session_grid(_midi(), 0.5, 10.0, downbeat=1.0)
    assert grid.downbeat == 1.0 and grid.downbeat_bar == 1
    assert [bar[:2] for bar in grid.bars[:3]] == [(1.0, 1), (3.0, 2), (5.0, 3)]
    assert grid.beats[:4].tolist() == [0.0, 0.5, 1.0, 1.5] and grid.beat_bars[:3].tolist() == [0, 0, 1]
    # a meter change at its own bar line still lands on one
    grid = M.session_grid(_midi(meters=((0, 4, 4), (q(9), 3, 4))), 0.0, 10.0, downbeat=0.5)
    assert [bar[0] for bar in grid.bars[:5]] == [0.5, 2.5, 4.5, 6.0, 7.5]
    assert grid.time_signatures == [(0.0, 4, 4), (4.5, 3, 4)]


def test_bar_1_given_after_a_meter_change_takes_the_meter_in_effect_there_and_back():
    lines = M.bar_lines(_midi(meters=((0, 4, 4), (q(8), 3, 4))), 12.0, q_from=6.5, anchor=9.0)
    assert lines == [(6.0, 0, 3, 4), (9.0, 1, 3, 4), (12.0, 2, 3, 4)]


def test_bar_1_given_before_the_midi_starts_runs_its_bars_from_there():
    lines = M.bar_lines(_midi(), 6.0, q_from=-3.0, anchor=-2.0)
    assert [(line[0], line[1]) for line in lines] == [(-6.0, 0), (-2.0, 1), (2.0, 2), (6.0, 3)]


def test_a_bar_1_after_the_song_ends_leaves_only_the_bars_before_it():
    lines = M.bar_lines(_midi(), 6.0, q_from=0.0, anchor=40.0)
    assert [(line[0], line[1]) for line in lines] == [(0.0, -9), (4.0, -8)]


def test_a_song_an_hour_into_the_session_is_found_without_walking_every_bar():
    midi = _midi(meters=((0, 4, 4), (q(100), 3, 4)))
    grid = M.session_grid(midi, -3600.0, 10.0)
    # 100 quarters of 4/4 (25 bars), then 3/4 bars of 1.5 s: 3600 s is bar 26 + (3600 - 50) / 1.5
    assert grid.bars[0][1] == 26 + math.ceil((3600 - 50) / 1.5) and grid.time_signatures[0][1:] == (3, 4)
    assert np.allclose(np.diff(grid.beats), 0.5)


def test_a_grid_of_more_bars_or_beats_than_any_song_has_is_refused(monkeypatch):
    sixty_fourths = M.parse_midi(smf([conductor(tempos=((0, 1000.0),), meters=((0, 1, 64),))]))
    with pytest.raises(ValueError, match=r"more than 100000 bars inside the song \(1/64 bars\)"):
        M.session_grid(sixty_fourths, 0.0, 400.0)
    monkeypatch.setattr(M, "MAX_GRID", 20)
    with pytest.raises(ValueError, match="more than 20 bars"):
        M.session_grid(_midi(), 30.0, 40.0)  # 6 bars from tick 0, and the 16 of pre-roll count too
    with pytest.raises(ValueError, match="more than 20 beats"):
        M.session_grid(_midi(meters=((0, 255, 4),)), 0.0, 20.0)
    with pytest.raises(ValueError, match="before the MIDI's bar 1"):
        M.bar_lines(_midi(), 0.0, q_from=-2e6)


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------
def _pattern(bars: int = 24, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Onsets of a song-like pattern at 120 BPM: a quiet intro, a groove with
    a syncopated kick, a break, a busier chorus -- velocities varied."""
    rng = np.random.default_rng(seed)
    times, weights = [], []
    for b in range(bars):
        part = "intro" if b < 2 else "break" if 10 <= b < 12 else "chorus" if b >= 12 else "verse"
        hits = [0.0]
        if part == "verse":
            hits = [0.0, 1.0, 1.5, 2.5, 3.0]
        elif part == "chorus":
            hits = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        for h in hits:
            times.append(2.0 * b + 0.5 * h)
            weights.append(float(rng.uniform(0.4, 1.0)))
    return np.array(times), np.array(weights)


def _onset(times, weights, offset: float, dur: float, *, noise: float = 0.02, seed: int = 2) -> np.ndarray:
    """An onset envelope at 100 Hz: a Gaussian bump (sigma 12 ms) centred on
    each onset, sampled between frames, plus a noise floor -- not the train's
    own shape, so the fit isn't exact by construction. Symmetric, because
    this tests the alignment, not where a flux envelope puts an attack
    (test_envelope.py measures that, on audio)."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(dur * 100) + 1)
    frames = np.arange(len(x))
    for t, w in zip(times + offset, weights):
        d = frames - t * 100.0
        x += w * np.exp(-0.5 * (d / 1.2) ** 2) * (np.abs(d) < 6)
    return x + noise * rng.random(len(x))


@pytest.mark.parametrize("offset", [0.5, -1.25, 0.0137, -7.0071])
def test_align_finds_the_offset_below_a_frame(offset):
    times, weights = _pattern()
    found = M.align(times, weights, _onset(times, weights, offset, 50.0))
    assert found.offset == pytest.approx(offset, abs=0.003)
    assert found.sure and found.r > 0.6 and found.margin >= M.ALIGN_MIN_MARGIN
    assert found.runner_up is not None and abs(found.runner_up - offset) > 0.05
    assert found.source == "auto"


def test_a_loop_lines_up_as_well_a_bar_away_and_is_not_sure():
    """60 identical bars: only the ends tell one bar's shift from another."""
    times = np.arange(0.0, 120.0, 0.5)
    weights = np.where(np.arange(len(times)) % 4 == 0, 1.0, 0.6)
    found = M.align(times, weights, _onset(times, weights, 0.5, 122.0))
    assert found.offset == pytest.approx(0.5, abs=0.003)  # right, but only just
    assert abs(abs(found.runner_up - found.offset) - 2.0) < 0.02  # a bar away
    assert found.margin < M.ALIGN_MIN_MARGIN and not found.sure


def test_onsets_that_are_not_the_songs_are_not_sure():
    times, weights = _pattern()
    other = np.sort(np.random.default_rng(9).uniform(0.0, 48.0, len(times)))
    found = M.align(other, weights, _onset(times, weights, 0.5, 50.0))
    assert found.r < M.ALIGN_MIN_R and not found.sure


def test_align_needs_notes_and_onsets():
    with pytest.raises(ValueError, match="no notes"):
        M.align(np.zeros(0), np.zeros(0), np.ones(100))
    with pytest.raises(ValueError, match="no notes"):
        M.align(np.array([1.0]), np.array([0.0]), np.ones(100))
    with pytest.raises(ValueError, match="silent"):
        M.align(np.array([1.0]), np.array([1.0]), np.zeros(100))


def test_a_search_too_narrow_for_a_distinct_alignment_has_no_runner_up():
    one = np.array([1.0])
    found = M.align(one, one, _onset(one, one, 0.02, 3.0, noise=0.0), search=0.04)
    assert found.offset == pytest.approx(0.02, abs=0.005)
    assert found.runner_up is None and found.margin is None and found.sure


def test_correlation_at_is_what_align_scores_an_offset():
    times, weights = _pattern()
    onset = _onset(times, weights, 0.5, 50.0)
    found = M.align(times, weights, onset)
    # r is the best of the 0.05-frame samples; the offset is the parabola's vertex between them.
    assert M.correlation_at(times, weights, onset, found.offset) == pytest.approx(found.r, abs=1e-3)
    assert M.correlation_at(times, weights, onset, 1.5) < found.r - M.ALIGN_MIN_MARGIN
    assert M.correlation_at(times, weights, onset, 400.0) == 0.0  # no overlap at all
    assert M.correlation_at(np.zeros(0), np.zeros(0), onset, 0.0) is None
    assert M.correlation_at(times, np.zeros(len(times)), onset, 0.0) == 0.0
    assert M.correlation_at(times, weights, np.zeros(100), 0.0) is None


def test_onset_impulses_weigh_by_velocity_double_drums_and_count_a_chord_once():
    data = smf(
        [
            note_track(
                [(0, q(1), 60, 64), (4, q(1), 64, 127), (8, q(1), 67, 32), (q(2), q(3), 60, 127)], "Keys"
            ),
            note_track([(q(1), q(1) + 30, 36, 127)], "Kick", 9),
        ]
    )
    times, weights = M.onset_impulses(M.parse_midi(data).tracks)
    assert times.tolist() == pytest.approx([0.0, 0.5, 1.0])
    assert weights.tolist() == pytest.approx([1.0, 2.0, 1.0])


def test_a_flat_peak_is_not_moved():
    assert M._parabola(np.array([1.0, 1.0, 1.0]), 1) == 0.0


def _far_away_note_file() -> bytes:
    """The staff review's 70-byte file: at 1 tick a quarter note, one note at
    the start and one 4 x 0x0FFFFFFF ticks later -- 17 years at 120 BPM."""
    body = b"\x00\x90\x3c\x40\x01\x80\x3c\x00" + b"\xff\xff\xff\x7f\xff\x01\x00" * 4 + b"\x00\x90\x3c\x40\x01\x80\x3c\x00"
    return header(1, 1, 1) + mtrk(body, eot())


def test_a_note_far_past_the_song_cannot_make_the_alignment_allocate_for_it():
    """align() rendered its onset train out to the last note: 400 GiB for
    this file. Only notes that can reach the song within the search are in
    it now, so the train is the song's length, whatever the file holds."""
    assert len(_far_away_note_file()) == 70
    midi = M.parse_midi(_far_away_note_file())
    assert midi.end > 5e8  # seconds: 17 years
    times, weights = M.onset_impulses(midi.tracks)
    onset = _onset(times[:1], weights[:1], 0.25, 60.0)
    tracemalloc.start()
    try:
        found = M.align(times, weights, onset)
        at = M.correlation_at(times, weights, onset, found.offset)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64 << 20  # measured 2.4 MB; the whole train is 12,000 frames
    assert found.offset == pytest.approx(0.25, abs=0.005) and at == pytest.approx(found.r, abs=1e-3)


def test_only_notes_that_can_reach_the_song_are_lined_up():
    times, weights = np.array([0.0, 5.0, 40.0, 95.0, 1e9]), np.ones(5)
    near, w = M.reachable(times, weights, 10.0, 0.0, 30.0)
    assert near.tolist() == [0.0, 5.0, 40.0] and len(w) == 3
    assert M.reachable(times, weights, 10.0, -60.0, 30.0)[0].tolist() == [40.0, 95.0]


def test_a_search_centred_on_a_given_offset_checks_only_near_it():
    times, weights = _pattern()
    onset = _onset(times, weights, 0.5, 50.0)
    near = M.align(times, weights, onset, search=0.5, center=0.8)
    assert near.offset == pytest.approx(0.5, abs=0.003) and near.sure
    assert all(abs(lag - 0.8) <= 0.5 + 1e-9 for lag in (near.offset, near.runner_up))
    with pytest.raises(ValueError, match="no notes"):
        M.align(times, weights, onset, search=0.5, center=-200.0)
    assert M.correlation_at(times, weights, onset, -200.0) == 0.0  # nothing comes near the song there


def test_an_alignment_is_sure_only_above_both_bars():
    assert M.Alignment(0.0, r=0.5, margin=0.1).sure
    assert not M.Alignment(0.0, r=0.2, margin=0.1).sure
    assert not M.Alignment(0.0, r=0.5, margin=0.01).sure
    assert not M.Alignment(0.0, r=None, source="given").sure


# --------------------------------------------------------------------------
# chords
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("pitches", "chord"),
    [
        ([60, 64, 67], "C"),
        ([64, 67, 72], "C/E"),  # first inversion
        ([55, 60, 64], "C/G"),  # second inversion
        ([57, 60, 64], "Am"),
        ([60, 64, 69], "Am/C"),  # C in the bass
        ([55, 59, 62, 65], "G7"),
        ([59, 62, 65, 67], "G7/B"),  # B in the bass: D-F-G above it is no chord of its own
        ([53, 55, 59, 62], "G/F"),  # the seventh walking under a G triad
        ([62, 67, 69], "Dsus4"),
        ([57, 62, 67], "Dsus4/A"),  # over its fifth: sus4 is preferred to Gsus2
        ([55, 57, 62], "Gsus2"),  # over a G it is Gsus2
        ([40, 47], "E5"),
        ([47, 52], "E5/B"),  # the fourth is a fifth inverted
        ([40, 47, 52, 59], "E5"),
        ([57, 60, 64, 67], "Am7"),
        ([60, 64, 67, 69], "C6"),  # the same pitch classes over a C
        ([60, 64, 67, 71], "Cmaj7"),
        ([59, 62, 65], "Bdim"),
        ([60, 64, 68], "Caug"),
        ([64, 68, 72], "Eaug"),  # symmetric: rooted on the bass
        ([60, 64, 70], "C7"),  # a seventh voiced without its fifth
        ([60, 62, 64, 67], "Cadd9"),
        ([60, 61, 62], "?"),  # a cluster: a chord, but not one the table names
        ([60, 72], None),  # one pitch class
        ([60, 64], None),  # a third is not a chord
    ],
)
def test_chords_are_named_by_pitch_class_over_their_bass(pitches, chord):
    assert M.chord_name(pitches) == chord


@pytest.mark.parametrize(
    ("voicing", "pitches", "chord"),
    [
        # the musician's list
        ("C over E", [52, 60, 67], "C/E"),
        ("F triad over a G bass", [43, 53, 57, 60], "F/G"),  # not Fadd9
        ("C triad over a B bass", [35, 60, 64, 67], "C/B"),  # not Cmaj7
        ("a rootless Dm9 on keys", [53, 57, 60, 64], "Fmaj7"),  # the keys alone spell Fmaj7
        ("C6/9", [48, 52, 55, 57, 62], "C6/9"),
        ("Cm11", [48, 51, 55, 58, 62, 65], "Cm11"),
        ("E7#9 without its fifth", [40, 56, 62, 67], "E7#9"),
        ("Cmaj7#11", [48, 52, 55, 59, 66], "Cmaj7#11"),
        ("C-D-E, no chord the table names", [60, 62, 64], "?"),
        # a bass walking under held chords, and inversions
        ("Am over G", [43, 57, 60, 64], "Am/G"),
        ("C over Bb", [46, 60, 64, 67], "C/Bb"),
        ("D over F#", [42, 50, 54, 57], "D/F#"),
        ("Ab over C", [48, 56, 60, 63], "Ab/C"),
        ("Cmaj7 over E", [52, 55, 59, 60], "Cmaj7/E"),  # E-G-B under C is the chord's own, not a bass
        ("E-G-B-C an octave up", [52, 60, 64, 67, 71], "Cmaj7/E"),
        ("Db over G", [43, 49, 53, 56], "C#/G"),  # the whole set has no name; the upper triad does
    ],
)
def test_a_bass_under_a_chord_reads_as_a_chart_writes_it(voicing, pitches, chord):
    assert M.chord_name(pitches) == chord, voicing


def test_chord_roots_are_spelled_for_the_key_signature():
    """A sharp key spells its own sharps sharp and everything else as a
    chart does: Bb in G or D major (a borrowed bVII), not A#."""
    assert [M.chord_name([58, 62, 65], key_signature=k) for k in (None, 0, 1, 2, 5, -2)] == [
        "Bb",
        "Bb",
        "Bb",
        "Bb",
        "A#",
        "Bb",
    ]
    assert [M.chord_name([61, 65, 68], key_signature=k) for k in (None, 3, -4)] == ["C#", "C#", "Db"]
    assert M.chord_name([54, 58, 61], key_signature=1) == "F#"  # F# is G major's own
    assert M.chord_name([42, 50, 54, 57], key_signature=1) == "D/F#"  # the bass is spelled as a root is
    assert M.chord_name([43, 49, 53, 56], key_signature=-1) == "Db/G"


def test_every_chord_in_the_table_names_itself_from_every_root_over_its_root():
    for root in range(12):
        for suffix, intervals in M._QUALITIES:
            pitches = [48 + root + i for i in sorted(intervals)]
            assert M.chord_name(pitches) == M._PLAIN[root] + suffix, (root, suffix)


def test_a_track_of_notes_never_turned_off_is_read_in_one_pass():
    """The staff review's case: 20,000 note-ons and no note-off, every note
    held to the end of the track. Each cluster lists a held pitch once."""
    events = b"".join(vlq(48) + bytes([0x90, 48 + k % 24, 100]) for k in range(20_000))
    midi = M.parse_midi(header(0, 1) + mtrk(events, eot(q(4))))
    (track,) = midi.tracks
    assert midi.unclosed == 20_000
    clusters = M._sounding(track.notes)
    last = clusters[-1][1]
    assert len(clusters) == 20_000 and sorted(set(last)) == list(range(48, 72)) and len(last) == 25
    assert M.is_harmonic(track)


def _keys(chords, title="Keys", channel=0):
    """(start quarter, length in quarters, pitches) -> a track."""
    notes = [(q(s), q(s + n), p, 90) for s, n, pitches in chords for p in pitches]
    return M.parse_midi(smf([note_track(notes, title, channel)])).tracks[0]


def test_a_chord_change_needs_a_new_set_that_holds_for_an_8th():
    """Am for a beat, a passing Bdim for a 16th, Am again (not a change), F
    struck twice (one change), C for a 16th (too short), then G."""
    track = _keys(
        [
            (0.0, 1.0, [57, 60, 64]),
            (1.0, 0.25, [59, 62, 65]),
            (1.25, 0.75, [57, 60, 64]),
            (2.0, 1.0, [53, 57, 60]),
            (3.0, 1.0, [53, 57, 60]),
            (4.0, 0.25, [48, 52, 55]),
            (4.25, 1.75, [55, 59, 62]),
        ]
    )
    changes = M.chord_events(track, _midi().tempo)
    assert [(t, until, chord) for t, until, chord in changes] == [
        (0.0, 1.0, "Am"),
        (1.0, 2.125, "F"),
        (2.125, 3.0, "G"),
    ]
    assert M.is_harmonic(track)


def test_a_pad_held_under_a_stab_counts_and_a_legato_overlap_does_not():
    held = _keys([(0.0, 4.0, [48]), (0.0, 1.0, [52, 55])])  # C held, E-G stabbed over it
    assert [c[2] for c in M.chord_events(held, _midi().tempo)] == ["C"]
    legato = M.parse_midi(
        smf([note_track([(0, q(1) + 5, 57, 90), (q(1), q(2), 60, 90), (q(1), q(2), 64, 90)], "Keys")])
    ).tracks[0]
    # The A overlaps the next beat by 5 ticks (5 ms): not held into it, so beat 2 is C-E, no chord.
    assert M.chord_events(legato, _midi().tempo) == []


def test_only_tracks_that_play_chords_are_harmonic():
    assert not M.is_harmonic(_keys([(k, 1.0, [36 + k]) for k in range(8)], "Bass"))
    assert not M.is_harmonic(_keys([(k, 1.0, [36, 42]) for k in range(8)], "Drums", channel=9))
    assert M.chord_events(_keys([(0.0, 1.0, [60])]), _midi().tempo) == []
    empty = M.Track(name=None, number=1, label="track-1", slug="track-1", notes=(), drum_like=False)
    assert not M.is_harmonic(empty) and M.chord_events(empty, _midi().tempo) == []
