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
                              (or --song/--title; --llm ollama:<model> drafts captions locally)

    kaleidophone envelope     <audio>                  -> 100 Hz song pack (JSON) for canvas pieces and frame effects
    kaleidophone master-check <old.wav> <new.wav>      -> is a new master a drop-in for the picture?
    kaleidophone deliver      <sheet.yaml>             -> every deliverable, cut from one silent render, audio muxed
    kaleidophone platforms    [ID]                     -> what each platform asks for, cited and dated

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
import math
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
from kaleidophone.release import generate_release_pack, minimal_brief, mood_line, release_facts
from kaleidophone.render import platforms
from kaleidophone.render._ffmpeg_util import FfmpegNotFound
from kaleidophone.render.deliver import deliver, delivery_script, finding_line, format_table, load_sheet
from kaleidophone.render.ffmpeg_pipeline import mux_audio, render_silent
from kaleidophone.render.ffmpeg_pipeline import render as render_edl
from kaleidophone.render.preview import generate_contact_sheet, generate_overlay_proof
from kaleidophone.render.variants import extract_teaser, extract_thumbnail
from kaleidophone.timeline.autobrief import build_default_brief
from kaleidophone.timeline.compose import compose
from kaleidophone.timeline.model import EDL
from kaleidophone.timeline.schema import ASPECT_RESOLUTIONS, CreativeBrief, ReleaseConfig

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
    p.add_argument("brief_path", nargs="?", help="A brief -- or describe the release with --song and --title.")
    p.add_argument("--song", help="The song file, for a release with no brief (a canvas piece's, say).")
    p.add_argument("--title", help="With --song: the release title.")
    p.add_argument("--artist", help="With --song: the artist name.")
    p.add_argument("--concept", help="With --song: the one line every caption is written around.")
    p.add_argument("--lang", default="en", help="With --song: primary[,secondary] language codes, e.g. en,fa.")
    p.add_argument(
        "--llm",
        help="Also draft each caption with a model on this machine: ollama:<model>, e.g. ollama:qwen3:8b. "
        "No tokens, no network. See docs/PORTABILITY.md.",
    )
    p.add_argument(
        "--llm-host",
        default=None,
        help="The Ollama server, an http:// or https:// URL (default http://127.0.0.1:11434). "
        "Asked directly, never through a proxy.",
    )
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
        type=_finite_float,
        metavar=("LO", "HI"),
        default=DEFAULT_BPM_RANGE,
        help="Tempos the beat grid may take (default 60 200). Narrow it when the grid comes "
        "back at double or half time -- the pack prints the other octave and its score; e.g. "
        "50 100 for a ballad, 150 190 for drum and bass.",
    )
    p.add_argument(
        "--downbeat",
        type=_finite_float,
        metavar="SECONDS",
        help="Bar 1, in seconds, when you know it. Otherwise it is estimated (bass onsets and harmony "
        "changes) and the pack says how sure that is. With --midi, it moves bar 1 off the MIDI's tick 0 -- "
        "for a clip exported from a pickup -- and the bars follow the MIDI's meter from there.",
    )
    p.add_argument(
        "--beats-per-bar",
        type=int,
        default=4,
        help="Beats in a bar (default 4; 3 for a waltz): sets which beat can be bar 1, and the bars "
        "`loudest` snaps to.",
    )
    p.add_argument(
        "--midi",
        metavar="FILE",
        help="The session's MIDI export (a Standard MIDI File): the grid comes from its tempo map and bars "
        "instead of being estimated, and every note and chord change goes into the pack's `events`.",
    )
    p.add_argument(
        "--midi-offset",
        type=_finite_float,
        metavar="SECONDS",
        help="Where the MIDI's 0 s falls on the master (master time = MIDI time + S): + for pre-roll, - for a "
        "bounce that starts after the session does. Left out, it is found by matching the notes to the audio.",
    )
    p.add_argument(
        "--stem",
        action="append",
        type=_stem_arg,
        metavar="NAME=PATH",
        help="A stem bounced over the master's range, lined up with the master and analysed like it into "
        "`stems.NAME` (repeat for each). One named vocals, vocal, vox or voice becomes `voc`.",
    )
    p.add_argument(
        "--stem-offset",
        action="append",
        type=_stem_offset_arg,
        metavar="NAME=SECONDS",
        help="Where stem NAME's 0 s falls on the master (master time = stem time + S): - for a master trimmed "
        "at the head, + for one padded. Left out, it is found by matching the stem to the master, and a stem "
        "that can't be matched is refused until you give it.",
    )
    p.add_argument(
        "--voc-stem",
        metavar="NAME",
        help="The --stem whose level becomes `voc`, whatever it is called (default: one named vocals, vocal, "
        "vox or voice).",
    )
    p.set_defaults(func=_cmd_envelope)

    p = sub.add_parser(
        "master-check",
        help="Is a new master a drop-in for the one the picture was cut to? "
        "Exit 0 remux, 3 re-render some bars, 4 new grid, 5 offset (set silent_start and deliver).",
    )
    p.add_argument("old_path", help="The master the silent render was cut against.")
    p.add_argument("new_path", help="The master that just arrived.")
    p.add_argument("--bpm", type=_finite_float, help="The edit's tempo. Estimated from the old master if left out.")
    p.add_argument(
        "--downbeat",
        type=_finite_float,
        help="Seconds to the edit's bar 1. Estimated from the old master if left out.",
    )
    p.add_argument("--beats-per-bar", type=int, default=4)
    p.add_argument(
        "--tolerance-ms",
        type=_finite_float,
        default=round(TOLERANCE * 1000.0, 1),
        help=f"A shift up to this many ms is the same grid (default {TOLERANCE * 1000:.1f}: half a frame "
        "at 24 fps). Beyond it, the same material shifted is an offset (exit 5).",
    )
    p.add_argument(
        "--silent-start",
        type=_finite_float,
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

    p = sub.add_parser(
        "platforms",
        help="What each platform asks for -- size, length, audio, file size, loudness -- with its sources, "
        "how sure that is, and when it was checked.",
    )
    p.add_argument("platform_id", nargs="?", metavar="ID", help="One platform (an id or alias), in full.")
    shape = p.add_mutually_exclusive_group()
    shape.add_argument("--json", dest="as_json", action="store_true", help="As JSON.")
    shape.add_argument("--markdown", action="store_true", help="As markdown: docs/PLATFORMS.md is this, whole.")
    p.set_defaults(func=_cmd_platforms)

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
    from kaleidophone.release import local_llm

    describing = any(v is not None for v in (args.song, args.title, args.artist, args.concept))
    if args.brief_path and describing:
        print("kit: give a brief, or --song/--title (and --artist/--concept), not both", file=sys.stderr)
        return 2
    if not args.brief_path and not (args.song and args.title):
        print("kit: give a brief, or describe the release with --song and --title", file=sys.stderr)
        return 2
    spec = None
    if args.llm:
        try:
            spec = local_llm.parse_model_spec(args.llm)
        except ValueError as e:
            print(f"kit: {e}", file=sys.stderr)
            return 2
    host = args.llm_host or local_llm.DEFAULT_HOST
    if spec:
        try:
            host = local_llm.check_host(host)
        except ValueError as e:
            print(f"kit: {e}", file=sys.stderr)
            return 2
        if not local_llm.is_local(host):
            # A notice, not a result: stderr, with the other things kit says about itself.
            print(
                f"kit: note -- {host} is not this machine, so the brief's concept and facts go there.",
                file=sys.stderr,
            )

    if args.brief_path:
        brief = CreativeBrief.from_yaml(args.brief_path)
        analysis = analyze(brief.song.audio_path, bpm_override=brief.song.bpm)
    else:
        langs = [c.strip() for c in args.lang.split(",") if c.strip()] or ["en"]
        analysis = analyze(args.song)
        brief = minimal_brief(
            args.song,
            args.title,
            analysis.duration,
            artist=args.artist,
            concept=args.concept,
            primary_language=langs[0],
            secondary_language=langs[1] if len(langs) > 1 else None,
        )

    drafts = None
    failed = None
    if spec:
        rel = brief.release or ReleaseConfig()
        try:
            texts = local_llm.draft_captions(
                spec,
                title=brief.song.title,
                artist=brief.song.artist,
                concept=rel.concept,
                mood=mood_line(brief),
                facts=release_facts(brief, analysis),
                surfaces=list(rel.platforms),
                primary_language=rel.primary_language,
                secondary_language=rel.secondary_language,
                host=host,
            )
            drafts = local_llm.render_drafts(texts, spec, rel.primary_language, rel.secondary_language)
        except local_llm.LocalModelError as e:
            failed = str(e)

    Path(args.out).write_text(generate_release_pack(brief, analysis, drafts), encoding="utf-8")
    print(f"wrote {args.out} -- facts are derived, the voice is yours. Read the notes at the end.")
    if drafts:
        print(f"  with caption drafts from {spec.label} -- drafts to rewrite, not copy to post.")
    if failed:
        print(f"kit: the pack is written, without drafts: {failed}", file=sys.stderr)
        return 1
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
    session: dict = {}
    if args.midi_offset is not None and args.midi is None:
        raise ValueError("--midi-offset places the MIDI on the master: it needs --midi")
    if args.midi is not None:
        session["midi"] = args.midi
        if args.midi_offset is not None:
            session["midi_offset"] = args.midi_offset
    if args.stem:
        stems: dict[str, str] = {}
        for name, path in args.stem:
            if name in stems:
                raise ValueError(f"--stem {name}=... is given twice; each stem needs its own name")
            stems[name] = path
        session["stems"] = stems
    offsets: dict[str, float] = {}
    for name, seconds in args.stem_offset or ():
        if name in offsets:
            raise ValueError(f"--stem-offset {name}=... is given twice")
        offsets[name] = seconds
    if offsets or args.voc_stem is not None:
        if not args.stem:
            flag = "--stem-offset" if offsets else "--voc-stem"
            raise ValueError(f"{flag} names a stem: it needs --stem NAME=PATH")
        session.update(stem_offsets=offsets, voc_stem=args.voc_stem)
    # Without session inputs, the call is exactly what it was before 0.4.
    pack = envelope(
        args.audio_path,
        bpm_range=tuple(args.bpm_range),
        downbeat=args.downbeat,
        beats_per_bar=args.beats_per_bar,
        **session,
    )
    path = write_songpack(pack, args.out)
    loudest = pack["loudest"]
    voc = "no (mono input)"
    if "voc" in pack:
        voc = f"yes ({pack['voc_source']})" if pack.get("voc_source") else "yes"
    print(
        f"bpm={pack['bpm']:.2f} beats={len(pack['beats'])} downbeat={pack['downbeat']:.3f}s "
        f"dur={pack['dur']:.1f}s loudest={loudest['start']:.2f}s+{loudest['len']}s voc={voc}"
    )
    for line in _session_lines(pack) + _grid_check_lines(pack):
        print(line)
    hint = (
        "The grid is the MIDI's."
        if "midi" in pack
        else "If the grid is at double or half time, re-run with --bpm-range."
    )
    print(f"wrote {path} -- a piece reads frame round(t * {pack['fps']}) of each envelope. {hint}")
    return EXIT_OK


def _stem_arg(text: str) -> tuple[str, str]:
    """`--stem NAME=PATH` -> (name, path); the name is checked by envelope()."""
    name, sep, path = text.partition("=")
    if not sep or not name.strip() or not path:
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, e.g. vocals=stems/Vocals.wav; got {text!r}")
    return name.strip(), path


def _finite_float(text: str) -> float:
    """A number of seconds (or BPM): float() would also take 'nan' and 'inf',
    which no time is, and which fail later with a traceback instead of here."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"expected a finite number, got {text!r}")
    return value


def _stem_offset_arg(text: str) -> tuple[str, float]:
    """`--stem-offset NAME=SECONDS` -> (name, seconds); the name is checked by envelope()."""
    name, sep, seconds = text.partition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"expected NAME=SECONDS, e.g. vocals=-0.3; got {text!r}")
    try:
        return name.strip(), _finite_float(seconds)
    except argparse.ArgumentTypeError:
        raise argparse.ArgumentTypeError(
            f"expected NAME=SECONDS with a finite number of seconds, e.g. vocals=-0.3; got {text!r}"
        ) from None


def _session_lines(pack: dict) -> list[str]:
    """What came in from the session, as a person reads it: the MIDI's tracks
    and notes, where it sits on the master and how sure that is, its tempo
    changes, its pulse when that isn't the quarter note, the chord changes per
    harmonic track, and the stems and where each was lined up. Nothing for a
    pack made from the master alone."""
    lines = []
    info = pack.get("midi")
    pulses = pack.get("pulses") or []
    if info and len(pulses) > 1 and pulses != pack.get("beats"):
        lines.append(
            f"pulse     {pack['pulses_per_bar']} a bar, {pulses[1] - pulses[0]:.3f} s apart at the start -- the "
            f"felt beat (`pulses`); `beats` count quarter notes"
        )
    if info:
        events = pack.get("events") or {}
        notes = events.get("midi") or {}
        counts = ", ".join(f"{slug} {len(rows)}" for slug, rows in notes.items())
        division = f"{info['ppq']} ppq" if info.get("ppq") else "SMPTE time"
        dropped = f"; {info['dropped']} outside the song dropped" if info.get("dropped") else ""
        lines.append(
            f"midi      {info.get('file') or 'MIDI'} ({division}): {len(notes)} tracks, "
            f"{sum(len(rows) for rows in notes.values())} notes -- {counts}{dropped}"
        )
        conf = info.get("confidence") or {}
        if info.get("offset_source") == "given":
            there = f"; the notes match the audio at r {conf['r']:.2f} there" if conf.get("r") is not None else ""
            lines.append(f"offset    {info['offset']:+.3f} s (given{there})")
        else:
            runner = ""
            if conf.get("margin") is not None:
                runner = f", {conf['margin']:.2f} over the runner-up at {conf['runner_up']:+.3f} s"
            lines.append(f"offset    {info['offset']:+.3f} s (found: r {conf['r']:.2f}{runner})")
        tempo_map = info.get("tempo_map") or []
        if len(tempo_map) > 1:
            changes = ", ".join(f"{bpm:.2f} at {t:.3f} s" for t, bpm in tempo_map[1:4])
            more = f" and {len(tempo_map) - 4} more" if len(tempo_map) > 4 else ""
            lines.append(f"tempo map {tempo_map[0][1]:.2f} BPM, then {changes}{more}")
        chords = events.get("chords") or {}
        if chords:
            lines.append("chords    " + ", ".join(f"{slug} {len(rows)} changes" for slug, rows in chords.items()))
    stems = pack.get("stems")
    if stems:
        voc = " (voc is the vocal stem's level)" if pack.get("voc_source") == "stem" else ""
        lines.append(f"stems     {', '.join(stems)}{voc}")
        placed = []
        for name, where in (pack.get("stems_alignment") or {}).items():
            r = where.get("r")
            if where.get("source") == "none":
                placed.append(f"{name} left at +0.000 s (nothing in it to line up by)")
            elif where.get("source") == "given":
                there = f"; r {r:.2f} there" if r is not None else ""
                placed.append(f"{name} {where['lag']:+.3f} s (given{there})")
            else:
                placed.append(f"{name} {where['lag']:+.3f} s (r {r:.2f})")
        if placed:
            lines.append("stem lag  " + ", ".join(placed))
    return lines


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
    elif bar1.get("source") == "midi":
        bar = bar1.get("session_bar")
        where = f": the session's bar {bar}" if bar is not None else ""
        lines.append(f"downbeat  {pack['downbeat']:.3f} s (the MIDI's bar line{where})")
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
        if r.picture != "copy":
            how += f", picture {r.picture}"
        print(f"wrote {r.out} ({r.frames_expected} frames, {how})")
    # deliver() returns a Delivery: the files, a list as it always was, with
    # the covers and the manifest alongside.
    covers, manifest = getattr(results, "covers", []), getattr(results, "manifest", None)
    for cover in covers:
        print(f"wrote {cover.describe()}")
    if sheet.check and results:
        print(format_table(results))
    for cover in covers:
        for finding in cover.findings:
            print(finding_line(cover.out, finding))
    if manifest:
        print(f"manifest {manifest}")
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
    refused = [(r.out, f) for r in results for f in r.findings if f.level == "refuse"]
    refused += [(c.out, f) for c in covers for f in c.findings if f.level == "refuse"]
    if refused:
        files = "; ".join(f"{os.path.basename(out)} ({f.platform}): {f.message}" for out, f in refused)
        raise RuntimeError(
            f"a platform won't take {'this file' if len(refused) == 1 else 'these files'} as delivered: {files}. "
            f"The files are written, and the manifest has every finding."
        )
    return EXIT_OK


def _cmd_platforms(args: argparse.Namespace) -> int:
    entry = platforms.get(args.platform_id) if args.platform_id else None
    if args.as_json:
        print(platforms.to_json(entry))
    elif args.markdown:
        sys.stdout.write(platforms.platforms_markdown() if entry is None else platforms.entry_markdown(entry))
    else:
        print(platforms.describe(entry) if entry is not None else platforms.platform_table())
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
