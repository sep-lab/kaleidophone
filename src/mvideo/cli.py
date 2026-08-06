"""
mvideo's command-line entry point.

    mvideo analyze <audio>                    -> AudioAnalysis JSON + a wave map PNG
    mvideo curate  <media_dir> <brief.yaml>    -> suggested station sort for an unsorted folder
    mvideo compose <brief.yaml>                -> EDL JSON
    mvideo render  <edl.json> <brief.yaml>     -> MP4 (+ teasers + thumbnails)
    mvideo promo   <brief.yaml>                -> promo pack markdown
    mvideo run     <brief.yaml>                -> all of the above, end to end

See docs/CONFIG-SCHEMA.md for the brief format and skills/ for the full
per-stage methodology.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from mvideo.assets.curation import scan_media, suggest_stations
from mvideo.audio.analysis import analyze
from mvideo.audio.wavemap import render_wavemap
from mvideo.cover.generate import generate_cover, pick_cover_station
from mvideo.promo.plan import generate_promo_pack
from mvideo.render.ffmpeg_pipeline import mux_audio, render_silent
from mvideo.render.ffmpeg_pipeline import render as render_edl
from mvideo.render.preview import generate_contact_sheet
from mvideo.render.variants import extract_teaser, extract_thumbnail
from mvideo.timeline.autobrief import build_default_brief
from mvideo.timeline.compose import compose
from mvideo.timeline.model import EDL
from mvideo.timeline.schema import CreativeBrief


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mvideo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
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

    p = sub.add_parser("run", help="analyze + compose + render + promo, end to end.")
    p.add_argument("brief_path")
    p.add_argument("-o", "--out", default="mvideo_out")
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
    p.add_argument("-o", "--out", default="mvideo_out")
    p.add_argument("--title")
    p.add_argument("--artist")
    p.add_argument(
        "--preview-only", action="store_true", help="Stop after the contact sheet -- skip the render."
    )
    p.set_defaults(func=_cmd_auto)

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
    return 0


def _cmd_silent(args: argparse.Namespace) -> int:
    edl = EDL.from_dict(json.loads(Path(args.edl_path).read_text()))
    brief = CreativeBrief.from_yaml(args.brief_path)
    path = render_silent(edl, brief, args.out)
    print(f"wrote {path} -- re-sync audio anytime with `mvideo remux {path} <audio> -o <out>`, no re-render")
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
        path = extract_teaser(master_path, teaser, start, str(out / "teasers"))
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
    if args.preview_only:
        print(
            "--preview-only: stopping here. Re-run without it (or `mvideo silent`) once the edit looks right."
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
        extract_teaser(master_path, teaser, start, str(out / "teasers"))
    for i in range(brief.output.thumbnail_count):
        t = edl.duration * (i + 1) / (brief.output.thumbnail_count + 1)
        extract_thumbnail(master_path, t, str(out / f"thumb_{i + 1}.jpg"))

    pack = generate_promo_pack(brief, analysis)
    (out / "promo_pack.md").write_text(pack)

    print(
        f"done -> {out}/  (master.mp4, cover.jpg, wavemap.png, edl.json, promo_pack.md, teasers/, thumb_*.jpg)"
    )
    return 0


def _cmd_auto(args: argparse.Namespace) -> int:
    brief, station_assets = build_default_brief(
        args.audio_path, args.media_dir, title=args.title, artist=args.artist
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    brief_path = out / "generated_brief.yaml"
    _write_yaml_brief(brief, brief_path)
    print(f"wrote {brief_path} -- edit it and re-run with `mvideo run` for full control")

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
    if args.preview_only:
        print("--preview-only: stopping here. Re-run without it once the edit looks right.")
        return 0

    master_path = str(out / "master.mp4")
    render_edl(edl, brief, master_path)

    for i in range(brief.output.thumbnail_count):
        t = edl.duration * (i + 1) / (brief.output.thumbnail_count + 1)
        extract_thumbnail(master_path, t, str(out / f"thumb_{i + 1}.jpg"))

    pack = generate_promo_pack(brief, analysis)
    (out / "promo_pack.md").write_text(pack)

    print(f"done -> {out}/")
    return 0


def _write_yaml_brief(brief: CreativeBrief, path) -> None:
    data = brief.model_dump(exclude_none=True, mode="json")
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _curate(brief: CreativeBrief) -> dict[str, list]:
    station_assets = {}
    for station in brief.stations:
        station_assets[station.name] = scan_media(station.media_dir) if station.media_dir else []
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
