"""
kaleidophone's command-line entry point.

    kaleidophone auto         <audio> <media_dir>      -> zero-config: brief + the whole pipeline
    kaleidophone run          <brief.yaml>             -> the whole pipeline from a brief

    kaleidophone analyze      <audio>                  -> AudioAnalysis JSON + a wave map PNG
    kaleidophone curate       <media_dir> <brief.yaml> -> suggested station sort for an unsorted folder
    kaleidophone compose      <brief.yaml>             -> EDL JSON
    kaleidophone preview      <edl.json>               -> contact sheet, no ffmpeg
    kaleidophone silent       <edl.json> <brief.yaml>  -> the visual cut only (expensive, reusable)
    kaleidophone remux        <silent.mp4> <audio>     -> swap the audio in, no re-render (cheap)
    kaleidophone render       <edl.json> <brief.yaml>  -> silent + remux + teasers + thumbnails
    kaleidophone cover        <brief.yaml>             -> procedural cover art
    kaleidophone promo        <brief.yaml>             -> promo pack markdown
    kaleidophone kit          <brief.yaml>             -> per-platform release copy pack

    kaleidophone envelope     <audio>                  -> 100 Hz song pack (JSON) for canvas pieces and frame effects
    kaleidophone master-check <old.wav> <new.wav>      -> is a new master a drop-in for the picture?
    kaleidophone deliver      <sheet.yaml>             -> every deliverable, cut from one silent render, audio muxed

`master-check` answers in its exit code as well as in words: 0 remux, 3
re-render the listed bars, 4 new grid, 5 offset (the same material starting
earlier or later: set the delivery sheet's silent_start to the printed
value). 2 keeps meaning what it means for every command: a failure -- bad
usage (argparse's own exit code) or an error the command reported. 1 is
kaleidophone run with no command at all.

See docs/CONFIG-SCHEMA.md for the brief format and skills/ for the full
per-stage methodology.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from kaleidophone import __version__
from kaleidophone.assets.curation import scan_media, suggest_stations
from kaleidophone.audio.analysis import analyze
from kaleidophone.audio.envelope import DEFAULT_BPM_RANGE, envelope, write_songpack
from kaleidophone.audio.mastercheck import (
    DELTA_THRESHOLD,
    ENVELOPES,
    NEW_VOICE_THRESHOLD,
    SHAPE_THRESHOLD,
    TOLERANCE,
    format_report,
    master_check,
)
from kaleidophone.audio.wavemap import render_wavemap
from kaleidophone.cover.generate import generate_cover, pick_cover_station
from kaleidophone.promo.plan import generate_promo_pack
from kaleidophone.release import generate_release_pack
from kaleidophone.render._ffmpeg_util import FfmpegNotFound
from kaleidophone.render.deliver import deliver, delivery_script, format_table, load_sheet
from kaleidophone.render.ffmpeg_pipeline import mux_audio, render_silent
from kaleidophone.render.ffmpeg_pipeline import render as render_edl
from kaleidophone.render.preview import generate_contact_sheet, generate_overlay_proof
from kaleidophone.render.variants import extract_teaser, extract_thumbnail
from kaleidophone.timeline.autobrief import build_default_brief
from kaleidophone.timeline.compose import compose
from kaleidophone.timeline.model import EDL
from kaleidophone.timeline.schema import ASPECT_RESOLUTIONS, CreativeBrief

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE

    # Every failure below is one a user can act on -- a missing ffmpeg, a
    # brief that doesn't validate, a station with no media, a file that isn't
    # there. The code already raises those with carefully written, actionable
    # messages; printing a 30-line traceback on top of one buries it. Show the
    # message, exit non-zero, and keep the traceback one flag away.
    try:
        return args.func(args)
    except FfmpegNotFound as exc:
        return _fail(exc, args)
    except ValidationError as exc:
        return _fail(f"{getattr(args, 'brief_path', 'the brief')} is not a valid brief:\n{exc}", args)
    except FileNotFoundError as exc:
        return _fail(f"{exc.filename}: no such file or directory", args)
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        return _fail(exc, args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


def _fail(message: object, args: argparse.Namespace) -> int:
    if getattr(args, "traceback", False) or os.environ.get("KALEIDOPHONE_DEBUG"):
        raise
    print(f"kaleidophone: error: {message}", file=sys.stderr)
    print("(re-run with --traceback, or KALEIDOPHONE_DEBUG=1, for the full trace)", file=sys.stderr)
    return EXIT_ERROR


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kaleidophone", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="version", version=f"kaleidophone {__version__}")
    parser.add_argument(
        "--traceback",
        action="store_true",
        help="Show the full Python traceback on error instead of a single message.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("analyze", help="Analyze a song: BPM, beats, structure, wave map.")
    p.add_argument("audio_path")
    p.add_argument("-o", "--out", default="analysis_out", help="Output directory.")
    p.set_defaults(func=_cmd_analyze)

    p = sub.add_parser("curate", help="Suggest a station sort for a folder of unsorted photos/clips.")
    p.add_argument("media_dir")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="curation_suggestion.json")
    p.set_defaults(func=_cmd_curate)

    p = sub.add_parser("compose", help="Turn a brief into an EDL (no rendering).")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="edl.json")
    p.set_defaults(func=_cmd_compose)

    p = sub.add_parser(
        "preview", help="Cheap, no-ffmpeg contact sheet of an EDL -- sanity-check before rendering."
    )
    p.add_argument("edl_path")
    p.add_argument("-o", "--out", default="preview_contact_sheet.jpg")
    p.add_argument(
        "--brief",
        help="Also proof this brief's overlays -- text placement can't be judged from "
        "the contact sheet's thumbnails.",
    )
    p.set_defaults(func=_cmd_preview)

    p = sub.add_parser(
        "silent", help="Render the visual cut only (no audio) -- the expensive, reusable step."
    )
    p.add_argument("edl_path")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="silent.mp4")
    p.set_defaults(func=_cmd_silent)

    p = sub.add_parser(
        "remux",
        help="Sync a (possibly new) audio file onto an already-rendered silent video. Fast, no re-render.",
    )
    p.add_argument("silent_path")
    p.add_argument("audio_path")
    p.add_argument("-o", "--out", default="master.mp4")
    p.set_defaults(func=_cmd_remux)

    p = sub.add_parser("render", help="Render an EDL to MP4, plus teasers/thumbnails.")
    p.add_argument("edl_path")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="render_out")
    p.set_defaults(func=_cmd_render)

    p = sub.add_parser("cover", help="Generate procedural cover art for a brief.")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="cover.jpg")
    p.set_defaults(func=_cmd_cover)

    p = sub.add_parser("promo", help="Generate the promo pack for a brief.")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="promo_pack.md")
    p.set_defaults(func=_cmd_promo)

    p = sub.add_parser(
        "kit",
        help="Generate the per-platform release copy pack (captions, chapters, "
        "timed comments, posting order).",
    )
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="release_pack.md")
    p.set_defaults(func=_cmd_kit)

    p = sub.add_parser("run", help="analyze + compose + render + promo, end to end.")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="kaleidophone_out")
    p.add_argument(
        "--preview-only", action="store_true", help="Stop after the contact sheet -- skip the render."
    )
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser(
        "auto",
        help="Default mode: one song + one folder of media -> a full result. No brief required.",
    )
    p.add_argument("audio_path")
    p.add_argument("media_dir")
    p.add_argument("-o", "--out", default="kaleidophone_out")
    p.add_argument("--title")
    p.add_argument("--artist")
    p.add_argument(
        "--aspect",
        choices=sorted(ASPECT_RESOLUTIONS),
        help="Frame shape for the delivery, e.g. 9:16 for a reel. Picks the canonical "
        "resolution and writes it into the generated brief.",
    )
    p.add_argument(
        "--preview-only", action="store_true", help="Stop after the contact sheet -- skip the render."
    )
    p.set_defaults(func=_cmd_auto)

    p = sub.add_parser(
        "envelope",
        help="Song pack: 100 Hz band, flux and beat envelopes (JSON) that drive canvas pieces "
        "and frame effects.",
    )
    p.add_argument("audio_path")
    p.add_argument("-o", "--out", default="songpack.json")
    p.add_argument(
        "--bpm-range",
        nargs=2,
        type=float,
        metavar=("LO", "HI"),
        default=DEFAULT_BPM_RANGE,
        help="Tempos the beat grid may take (default 60 200). Narrow it when the grid comes "
        "back at double or half time -- the pack prints the other octave and its score; e.g. "
        "50 100 for a ballad, 150 190 for drum and bass.",
    )
    p.add_argument(
        "--downbeat",
        type=float,
        metavar="SECONDS",
        help="Bar 1, in seconds, when you know it. Otherwise it is estimated (bass onsets and harmony "
        "changes) and the pack says how sure that is.",
    )
    p.add_argument(
        "--beats-per-bar",
        type=int,
        default=4,
        help="Beats in a bar (default 4; 3 for a waltz): sets which beat can be bar 1, and the bars "
        "`loudest` snaps to.",
    )
    p.set_defaults(func=_cmd_envelope)

    p = sub.add_parser(
        "master-check",
        help="Is a new master a drop-in for the one the picture was cut to? "
        "Exit 0 remux, 3 re-render some bars, 4 new grid, 5 offset (set silent_start and deliver).",
    )
    p.add_argument("old_path", help="The master the silent render was cut against.")
    p.add_argument("new_path", help="The master that just arrived.")
    p.add_argument("--bpm", type=float, help="The edit's tempo. Estimated from the old master if left out.")
    p.add_argument(
        "--downbeat",
        type=float,
        help="Seconds to the edit's bar 1. Estimated from the old master if left out.",
    )
    p.add_argument("--beats-per-bar", type=int, default=4)
    p.add_argument(
        "--tolerance-ms",
        type=float,
        default=round(TOLERANCE * 1000.0, 1),
        help=f"A shift up to this many ms is the same grid (default {TOLERANCE * 1000:.1f}: half a frame "
        "at 24 fps). Beyond it, the same material shifted is an offset (exit 5).",
    )
    p.add_argument(
        "--silent-start",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="The delivery sheet's current silent_start (default 0); the report prints it plus the shift.",
    )
    p.add_argument(
        "--envelopes",
        type=lambda text: tuple(k.strip() for k in text.split(",") if k.strip()),
        default=ENVELOPES,
        metavar="KEY,KEY",
        help="Compare only these song-pack envelopes per bar -- the ones the piece reads "
        f"(default all: {','.join(ENVELOPES)}).",
    )
    p.add_argument(
        "--max-delta",
        type=float,
        default=DELTA_THRESHOLD,
        help="Flag a bar where an envelope's mean change, on the old master's 0..1 scale, exceeds this "
        f"(default {DELTA_THRESHOLD}).",
    )
    p.add_argument(
        "--min-r",
        type=float,
        default=SHAPE_THRESHOLD,
        help=f"Flag a bar where an envelope's shape correlates below this (default {SHAPE_THRESHOLD}).",
    )
    p.add_argument(
        "--max-new-voice",
        type=float,
        default=NEW_VOICE_THRESHOLD,
        help=f"Flag a bar where more than this share is new sound (0..1, default {NEW_VOICE_THRESHOLD}).",
    )
    p.add_argument("--json", dest="json_out", help="Also write the full check (every window and bar) here.")
    p.set_defaults(func=_cmd_master_check)

    p = sub.add_parser(
        "deliver",
        help="Cut every deliverable in a delivery sheet from one silent render and mux the audio.",
    )
    p.add_argument("sheet_path")
    p.add_argument(
        "-o",
        "--out",
        help="Directory the sheet's `out:` names are written into (default: the sheet's own directory).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print every ffmpeg command as a shell script instead of running them -- for the "
        "machine the WAV lives on.",
    )
    p.set_defaults(func=_cmd_deliver)

    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    analysis = analyze(args.audio_path)
    (out / "analysis.json").write_text(json.dumps(_analysis_to_dict(analysis), indent=2))
    render_wavemap(analysis, str(out / "wavemap.png"))
    print(
        f"bpm={analysis.bpm:.1f} duration={analysis.duration:.1f}s "
        f"beats={len(analysis.beat_times)} quiet_passages={len(analysis.quiet_passages)} "
        f"energy_jumps={len(analysis.energy_jumps)}"
    )
    print(f"wrote {out / 'analysis.json'} and {out / 'wavemap.png'}")
    return 0


def _cmd_curate(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    assets = scan_media(args.media_dir)
    buckets = suggest_stations(assets, brief.stations)
    payload = {name: [a.path for a in items] for name, items in buckets.items()}
    Path(args.out).write_text(json.dumps(payload, indent=2))
    for name, items in buckets.items():
        print(f"{name}: {len(items)} suggested")
    print(f"wrote {args.out} -- skim it, this is a starting sort, not a final cut")
    return 0


def _cmd_compose(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    station_assets = _curate(brief)
    edl = compose(brief, analysis, station_assets)
    Path(args.out).write_text(json.dumps(edl.to_dict(), indent=2))
    print(f"composed {len(edl.cuts)} cuts -> {args.out}")
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    edl = EDL.from_dict(json.loads(Path(args.edl_path).read_text()))
    path = generate_contact_sheet(edl, args.out)
    print(f"wrote {path} ({len(edl.cuts)} cuts) -- sanity-check the edit before rendering")
    if args.brief:
        brief = CreativeBrief.from_yaml(args.brief)
        _proof_overlays(brief, edl, Path(args.out).parent)
    return 0


def _proof_overlays(brief: CreativeBrief, edl: EDL, out_dir) -> None:
    """Write the overlay proof sheet, if the brief has any cards.

    Split out because `preview`, `run` and `auto` all want it and all three
    would otherwise repeat the same emptiness check.
    """
    if not brief.overlays:
        return
    path = Path(out_dir) / "preview_overlays.jpg"
    generate_overlay_proof(brief.overlays, edl, str(path), brief.output.resolution)
    print(
        f"wrote {path} ({len(brief.overlays)} card(s)) -- check size, placement and overflow. "
        f"Frames are ungraded, so contrast against the final look still needs a render."
    )


def _cmd_silent(args: argparse.Namespace) -> int:
    edl = EDL.from_dict(json.loads(Path(args.edl_path).read_text()))
    brief = CreativeBrief.from_yaml(args.brief_path)
    path = render_silent(edl, brief, args.out)
    print(f"wrote {path} -- re-sync audio anytime with `kaleidophone remux {path} <audio> -o <out>`, no re-render")
    return 0


def _cmd_remux(args: argparse.Namespace) -> int:
    path = mux_audio(args.silent_path, args.audio_path, args.out)
    print(f"wrote {path}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    edl = EDL.from_dict(json.loads(Path(args.edl_path).read_text()))
    brief = CreativeBrief.from_yaml(args.brief_path)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    master_path = str(out / "master.mp4")
    render_edl(edl, brief, master_path)
    print(f"wrote {master_path}")

    for teaser in brief.output.teasers:
        start = (
            teaser.source_start
            if teaser.source_start is not None
            else max(0.0, edl.duration / 2 - teaser.duration / 2)
        )
        path = extract_teaser(master_path, teaser, start, str(out / "teasers"), edl.resolution)
        print(f"wrote {path}")

    for i in range(brief.output.thumbnail_count):
        t = edl.duration * (i + 1) / (brief.output.thumbnail_count + 1)
        path = extract_thumbnail(master_path, t, str(out / f"thumb_{i + 1}.jpg"))
        print(f"wrote {path}")

    return 0


def _cmd_cover(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    station = pick_cover_station(brief, analysis)
    path = generate_cover(analysis, station, args.out, size=brief.output.cover_size)
    print(f"wrote {path} (station={station.name})")
    return 0


def _cmd_promo(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    pack = generate_promo_pack(brief, analysis)
    Path(args.out).write_text(pack)
    print(f"wrote {args.out}")
    return 0


def _cmd_kit(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    Path(args.out).write_text(generate_release_pack(brief, analysis))
    print(f"wrote {args.out} -- facts are derived, the voice is yours. Read the notes at the end.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    brief = CreativeBrief.from_yaml(args.brief_path)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    render_wavemap(
        analysis, str(out / "wavemap.png"), section_markers=[(s.start, s.name) for s in brief.sections]
    )

    cover_station = pick_cover_station(brief, analysis)
    generate_cover(analysis, cover_station, str(out / "cover.jpg"), size=brief.output.cover_size)

    station_assets = _curate(brief)
    edl = compose(brief, analysis, station_assets)
    (out / "edl.json").write_text(json.dumps(edl.to_dict(), indent=2))

    generate_contact_sheet(edl, str(out / "preview_contact_sheet.jpg"))
    print(f"wrote {out / 'preview_contact_sheet.jpg'} -- sanity-check the edit before the render")
    _proof_overlays(brief, edl, out)
    if args.preview_only:
        print(
            "--preview-only: stopping here. Re-run without it (or `kaleidophone silent`) once the edit looks right."
        )
        return 0

    master_path = str(out / "master.mp4")
    render_edl(edl, brief, master_path)

    for teaser in brief.output.teasers:
        start = (
            teaser.source_start
            if teaser.source_start is not None
            else max(0.0, edl.duration / 2 - teaser.duration / 2)
        )
        extract_teaser(master_path, teaser, start, str(out / "teasers"), edl.resolution)
    for i in range(brief.output.thumbnail_count):
        t = edl.duration * (i + 1) / (brief.output.thumbnail_count + 1)
        extract_thumbnail(master_path, t, str(out / f"thumb_{i + 1}.jpg"))

    (out / "promo_pack.md").write_text(generate_promo_pack(brief, analysis))
    (out / "release_pack.md").write_text(generate_release_pack(brief, analysis))

    print(
        f"done -> {out}/  (master.mp4, cover.jpg, wavemap.png, edl.json, promo_pack.md, teasers/, thumb_*.jpg)"
    )
    return 0


def _cmd_auto(args: argparse.Namespace) -> int:
    brief, station_assets = build_default_brief(
        args.audio_path, args.media_dir, title=args.title, artist=args.artist
    )
    if args.aspect:
        brief.output.aspect = args.aspect
        brief.output.resolution = ASPECT_RESOLUTIONS[args.aspect]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    brief_path = out / "generated_brief.yaml"
    _write_yaml_brief(brief, brief_path)
    print(f"wrote {brief_path} -- edit it and re-run with `kaleidophone run` for full control")

    analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    render_wavemap(
        analysis, str(out / "wavemap.png"), section_markers=[(s.start, s.name) for s in brief.sections]
    )

    cover_station = pick_cover_station(brief, analysis)
    generate_cover(analysis, cover_station, str(out / "cover.jpg"), size=brief.output.cover_size)

    edl = compose(brief, analysis, station_assets)
    (out / "edl.json").write_text(json.dumps(edl.to_dict(), indent=2))

    generate_contact_sheet(edl, str(out / "preview_contact_sheet.jpg"))
    print(f"wrote {out / 'preview_contact_sheet.jpg'} -- sanity-check the edit before the render")
    _proof_overlays(brief, edl, out)
    if args.preview_only:
        print("--preview-only: stopping here. Re-run without it once the edit looks right.")
        return 0

    master_path = str(out / "master.mp4")
    render_edl(edl, brief, master_path)

    for i in range(brief.output.thumbnail_count):
        t = edl.duration * (i + 1) / (brief.output.thumbnail_count + 1)
        extract_thumbnail(master_path, t, str(out / f"thumb_{i + 1}.jpg"))

    (out / "promo_pack.md").write_text(generate_promo_pack(brief, analysis))
    (out / "release_pack.md").write_text(generate_release_pack(brief, analysis))

    print(f"done -> {out}/")
    return 0


def _cmd_envelope(args: argparse.Namespace) -> int:
    pack = envelope(
        args.audio_path,
        bpm_range=tuple(args.bpm_range),
        downbeat=args.downbeat,
        beats_per_bar=args.beats_per_bar,
    )
    path = write_songpack(pack, args.out)
    loudest = pack["loudest"]
    print(
        f"bpm={pack['bpm']:.2f} beats={len(pack['beats'])} downbeat={pack['downbeat']:.3f}s "
        f"dur={pack['dur']:.1f}s loudest={loudest['start']:.2f}s+{loudest['len']}s "
        f"voc={'yes' if 'voc' in pack else 'no (mono input)'}"
    )
    for line in _grid_check_lines(pack):
        print(line)
    print(
        f"wrote {path} -- a piece reads frame round(t * {pack['fps']}) of each envelope. "
        f"If the grid is at double or half time, re-run with --bpm-range."
    )
    return EXIT_OK


def _grid_check_lines(pack: dict) -> list[str]:
    """The pack's `grid_check`, as a person reads it: the other octave, how
    sure bar 1 is, how well the fixed grid fits each 8-bar section, and any
    warning. Nothing for a pack without one."""
    check = pack.get("grid_check")
    if not check:
        return []
    lines = []
    octave = check.get("octave")
    if octave:
        lines.append(
            f"tempo     {pack['bpm']:.2f} BPM; the other octave, {octave['bpm']:.2f} BPM, scores "
            f"{octave['score']:.2f} of it"
        )
    bar1 = check.get("downbeat", {})
    if bar1.get("source") == "given":
        lines.append(f"downbeat  {pack['downbeat']:.3f} s (given)")
    elif bar1:
        runner = bar1.get("runner_up")
        tail = "" if runner is None else f"; runner-up {runner:.3f} s"
        lines.append(
            f"downbeat  {pack['downbeat']:.3f} s (estimated, confidence {bar1['confidence']:.2f}{tail})"
        )
    measured = [s for s in check.get("sections", []) if s.get("max_ms") is not None]
    if measured:
        worst = max(s["max_ms"] for s in measured)
        if worst <= 1000.0 / 48.0:
            lines.append(
                f"grid fit  within {worst} ms of the music in all {len(measured)} sections with a pulse"
            )
        else:
            fits = ", ".join(
                f"{s['bars'][0]}-{s['bars'][1]} {s['offset_ms']:+d} (worst {s['max_ms']})" for s in measured
            )
            lines.append(f"grid fit  ms from the music per 8 bars: {fits}")
    lines.extend(f"warning: {text}" for text in check.get("warnings", []))
    return lines


def _cmd_master_check(args: argparse.Namespace) -> int:
    check = master_check(
        args.old_path,
        args.new_path,
        bpm=args.bpm,
        downbeat=args.downbeat,
        beats_per_bar=args.beats_per_bar,
        max_delta=args.max_delta,
        max_new_voice=args.max_new_voice,
        min_r=args.min_r,
        tolerance=args.tolerance_ms / 1000.0,
        silent_start=args.silent_start,
        envelopes=args.envelopes,
    )
    print(format_report(check))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(check.to_dict(), indent=2))
        print(f"wrote {out}")
    # The verdict is the exit code (0 remux, 3 rerender, 4 new grid, 5 offset),
    # so a delivery script can stop itself before remuxing onto a grid that moved.
    return check.exit_code


def _cmd_deliver(args: argparse.Namespace) -> int:
    if args.dry_run:
        # Only the script goes to stdout, so `> deliver.sh` captures exactly it.
        sys.stdout.write(delivery_script(args.sheet_path, out_dir=args.out))
        if os.path.isabs(args.sheet_path) or (args.out and os.path.isabs(args.out)):
            print(
                "note: an absolute sheet or --out path makes the script's paths absolute, so it "
                "only runs on this machine's layout. From the project folder, `kaleidophone "
                "deliver <sheet> --dry-run` gives one that runs anywhere the folder does.",
                file=sys.stderr,
            )
        return EXIT_OK
    sheet = load_sheet(args.sheet_path)
    results = deliver(args.sheet_path, out_dir=args.out, log=print)
    for r in results:
        how = "no audio"
        if r.has_audio:
            how = f"gain {r.gain_db:+.2f} dB"
            if r.limiter_dbfs is not None:
                how += f", limiter {r.limiter_dbfs:.2f} dBFS"
            if r.source_lufs is not None:
                how += f" on a {r.source_lufs:.1f} LUFS master"
            if len(r.attempts) > 1:
                how += f", after {len(r.attempts)} encodes"
        print(f"wrote {r.out} ({r.frames_expected} frames, {how})")
    if sheet.check:
        print(format_table(results))
    failed = [r for r in results if r.guard_failed]
    if failed:
        # One master, one gain, one ceiling: every failed cut shares them.
        ceiling, mode = failed[0].ceiling_dbtp, failed[0].mode
        files = ", ".join(f"{r.out} ({r.true_peak:+.1f} dBTP at {r.gain_db:+.2f} dB)" for r in failed)
        if mode == "fixed":
            raise RuntimeError(
                f"{files}: over the {ceiling:g} dBTP ceiling at the fixed gain. The files are written; "
                "lower gain.db, or use mode: auto, which steps the gain down until every file is under it."
            )
        fix = (
            "raise gain.max_steps or lower gain.limiter_dbfs"
            if mode == "loudness"
            else "raise gain.max_steps or lower gain.start_db, or use mode: loudness, which limits before the encode"
        )
        raise RuntimeError(
            f"the true-peak guard ran out of steps for {files} -- still over the {ceiling:g} dBTP "
            f"ceiling. The files are written; {fix}."
        )
    return EXIT_OK


def _write_yaml_brief(brief: CreativeBrief, path) -> None:
    data = brief.model_dump(exclude_none=True, mode="json")
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _curate(brief: CreativeBrief) -> dict[str, list]:
    """Scan each station's media_dir.

    Cached by resolved path, because sharing one folder across stations is the
    common case rather than the exotic one -- `kaleidophone auto` writes exactly
    that brief, and the README's own next step is to re-run it through
    `kaleidophone run`. Without the cache that decodes every photo in the folder
    once per station.
    """
    scans: dict[str, list] = {}
    station_assets = {}
    for station in brief.stations:
        if not station.media_dir:
            station_assets[station.name] = []
            continue
        key = os.path.realpath(station.media_dir)
        if key not in scans:
            scans[key] = scan_media(station.media_dir)
        station_assets[station.name] = scans[key]
    return station_assets


def _analysis_to_dict(analysis) -> dict:
    return {
        "path": analysis.path,
        "duration": analysis.duration,
        "sr": analysis.sr,
        "bpm": analysis.bpm,
        "beat_times": list(analysis.beat_times),
        "onset_times": list(analysis.onset_times),
        "quiet_passages": [vars(q) for q in analysis.quiet_passages],
        "energy_jumps": [vars(j) for j in analysis.energy_jumps],
    }


if __name__ == "__main__":
    sys.exit(main())
