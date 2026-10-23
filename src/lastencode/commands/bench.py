"""Benchmark preset variants on lossless excerpts and score their decoded frames."""

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from statistics import fmean
from typing import cast

from lastencode import processes
from lastencode.check_media import Media, scan, source_above_frame_rate_cap
from lastencode.command import Command
from lastencode.contracts import FORMAT_FLAG, bench_schema
from lastencode.encoder_check import probe_encoder
from lastencode.encoding import encoding_command
from lastencode.errors import Conflict, InvalidInput, MissingTool
from lastencode.paths import Source, discover
from lastencode.planning import validate_settings
from lastencode.preset_fields import TARGETS
from lastencode.presets import Category, load_categories
from lastencode.probe import (
    light_probe,
    number,
    object_dict,
    packet_facts,
    probe,
    read_picture,
    stream_list,
)
from lastencode.render import safe_text
from lastencode.video import encoder_parameters, video_stream

MODELS = ("vmaf_v1.0.16_3d0h", "vmaf_v1.0.16_5d0h")
CSV_FIELDS: tuple[str, ...] = (
    "source",
    "excerpt_index",
    "excerpt_start_seconds",
    "excerpt_seconds",
    "target",
    "quality_crf",
    "frame_rate_change",
    "size_bytes",
    "bitrate_bps",
    "encode_time_seconds",
    "encode_time_realtime_multiple",
    "vmaf_desktop_mean",
    "vmaf_desktop_p5",
    "vmaf_phone_mean",
    "vmaf_phone_p5",
    "xpsnr_y",
    "scaling",
    "dropped_frame_share",
    "valid",
    "reason",
    "variant_path",
    "side_by_side_path",
)


@dataclass(frozen=True)
class Variant:
    target: str
    quality_crf: int
    frame_rate_change: str
    settings: dict[str, object]
    use_preset_cap: bool = False

    @property
    def key(self) -> str:
        rate = "native" if self.frame_rate_change == "native" else "25fps"
        return f"{self.target}-crf{self.quality_crf}-{rate}"


@dataclass(frozen=True)
class ExcerptPlan:
    source: Source
    source_index: int
    source_info: dict[str, object]
    source_duration: float
    source_size_bytes: int
    excerpt_index: int
    start_seconds: float
    duration_seconds: float
    path: Path


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("sources", nargs="+", metavar="SOURCE", help="Video files or folders.")
    parser.add_argument(
        "--category", required=True, help="Content category; list names with presets."
    )
    parser.add_argument("--output-dir", required=True, help="Folder for benchmark output.")
    parser.add_argument(
        "--target",
        action="append",
        choices=TARGETS,
        help="Distinct playback target per occurrence; repeat for more; default portable.",
    )
    parser.add_argument(
        "--quality-settings",
        action="append",
        type=int,
        metavar="CRF",
        help=(
            "Distinct CRF per occurrence (x265: 0-51; SVT-AV1: 1-63); "
            "repeat for more; default preset CRF and +/-2."
        ),
    )
    parser.add_argument(
        "--excerpt-seconds",
        type=float,
        default=20,
        help="Positive excerpt length in seconds, default 20.",
    )
    parser.add_argument(
        "--excerpts", type=int, default=3, help="Positive excerpts per source, default 3."
    )
    parser.add_argument(
        "--include-25-fps",
        action="store_true",
        help=(
            "Without it, variants follow the preset's frame-rate cap. With it, native variants "
            "keep the source rate uncapped and a 25 fps set is added."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print variant count and space estimate."
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing benchmark.")
    parser.add_argument("--format", choices=["json", "text"], help=str(FORMAT_FLAG["description"]))


def run(args: argparse.Namespace) -> dict[str, object]:
    categories = {category.name: category for category in load_categories(args.presets)}
    if args.category not in categories:
        raise InvalidInput(
            f"--category {args.category!r}: valid categories: {', '.join(categories)}"
        )
    category = categories[args.category]
    targets = args.target or ["portable"]
    if not args.sources:
        raise InvalidInput("bench requires SOURCE... and --output-dir DIR")
    if args.excerpts < 1 or not math.isfinite(args.excerpt_seconds) or args.excerpt_seconds <= 0:
        raise InvalidInput("--excerpts and --excerpt-seconds must be positive")
    variants = make_variants(category, targets, args.quality_settings, args.include_25_fps)
    output = Path(args.output_dir).absolute()
    check_bench_tools(variants)
    check_variant_encoders(variants)
    sources, _ = discover(args.sources, output)
    videos = [source for source in sources if source.is_video]
    if not videos:
        raise InvalidInput("bench requires at least one supported video source")
    plans = plan_excerpts(videos, output, args.excerpts, args.excerpt_seconds)
    targets_preview = benchmark_targets(output, plans, variants)
    existing = [str(t["path"]) for t in targets_preview if t["effect"] == "replace"]
    if existing and not args.force:
        raise Conflict(
            "Benchmark files already exist; use --force to replace: " + ", ".join(existing)
        )
    estimate = estimate_space(plans, variants)
    if args.dry_run:
        return summary(category.name, videos, plans, variants, estimate, [], True)
    # Retain the pre-write effects, even after the files have been created.
    result = execute_benchmark(category, output, plans, variants, estimate)
    result["targets"] = targets_preview
    return result


def benchmark_targets(
    output: Path, plans: list[ExcerptPlan], variants: list[Variant]
) -> list[dict[str, object]]:
    paths = [output / "bench.csv"]
    for plan in plans:
        paths.append(plan.path)
        for variant in variants:
            name = f"{plan.path.stem}-{variant.key}.mp4"
            paths.extend(output / folder / name for folder in ("variants", "side-by-side"))
            # Frame-rate references depend on the cut excerpt, so list each possible one.
            cap = 25 if variant.frame_rate_change == "25 fps" else None
            if variant.use_preset_cap:
                cap = variant.settings["max_frame_rate"]
            if type(cap) is int:
                paths.append(output / "excerpts" / f"{plan.path.stem}-{cap}fps.mkv")
    return [
        {
            "path": str(path),
            "effect": "replace" if path.exists() else "create",
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }
        for path in dict.fromkeys(paths)
    ]


def make_variants(
    category: Category,
    targets: list[str],
    requested_quality: list[int] | None,
    include_25_fps: bool,
) -> list[Variant]:
    variants: list[Variant] = []
    rates = ["native", "25 fps"] if include_25_fps else ["native"]
    for target in unique(targets, "--target"):
        if target not in TARGETS:
            raise InvalidInput(f"--target: valid targets: {', '.join(TARGETS)}")
        validate_settings(category, target)
        base: dict[str, object] = {
            key: setting.value for key, setting in category.settings[target].items()
        }
        quality = requested_quality or [
            int(str(base["quality_crf"])) - 2,
            int(str(base["quality_crf"])),
            int(str(base["quality_crf"])) + 2,
        ]
        quality_values = unique(quality, "--quality-settings")
        encoder = str(base["encoder"])
        minimum, maximum = (0, 51) if encoder == "libx265" else (1, 63)
        for crf in quality_values:
            if not minimum <= crf <= maximum:
                raise InvalidInput(
                    f"--quality-settings {crf}: valid CRF range for {encoder} is "
                    f"{minimum} to {maximum}"
                )
            settings = base | {"quality_crf": crf}
            variants.extend(
                Variant(target, crf, rate, settings, use_preset_cap=not include_25_fps)
                for rate in rates
            )
    return variants


def unique[T: (int, str)](values: list[T], flag: str) -> list[T]:
    if len(set(values)) != len(values):
        raise InvalidInput(f"{flag}: duplicate values are not allowed")
    return list(values)


def check_bench_tools(variants: list[Variant]) -> None:
    if shutil.which("ffmpeg") is None:
        raise MissingTool("ffmpeg: required on PATH for bench")
    if shutil.which("ffprobe") is None:
        raise MissingTool("ffprobe: required on PATH for bench")
    filters = capture(["ffmpeg", "-hide_banner", "-filters"])
    available_filters = {
        parts[1] for line in filters.splitlines() if len(parts := line.split()) >= 2
    }
    missing = [name for name in ("libvmaf", "xpsnr") if name not in available_filters]
    if missing:
        raise MissingTool("ffmpeg: missing required filters: " + ", ".join(missing))
    for model in MODELS:
        check_vmaf_model(model)
    encoders = capture(["ffmpeg", "-hide_banner", "-encoders"])
    available_encoders = {
        parts[1] for line in encoders.splitlines() if len(parts := line.split()) >= 2
    }
    required = {"ffv1", "libx264", *(str(variant.settings["encoder"]) for variant in variants)}
    missing_encoders = sorted(required - available_encoders)
    if missing_encoders:
        raise MissingTool("ffmpeg: missing required encoders: " + ", ".join(missing_encoders))


def check_vmaf_model(model: str) -> None:
    graph = (
        "[0:v]format=yuv420p10le[dist];[1:v]format=yuv420p10le[ref];"
        f"[dist][ref]libvmaf=model=version={model}:n_threads=1"
    )
    result = capture_result(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1280x720:r=2:d=1",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1280x720:r=2:d=1",
            "-filter_complex",
            graph,
            "-f",
            "null",
            "-",
        ]
    )
    if result.returncode:
        detail = last_lines(result.stderr)
        raise MissingTool(f"ffmpeg: required libvmaf model {model} is unavailable: {detail}")


def check_variant_encoders(variants: list[Variant]) -> None:
    checked: set[tuple[str, str]] = set()
    for variant in variants:
        settings = variant.settings
        params = encoder_parameters(Path("."), {}, settings)
        probe_encoder(settings, params, checked)


def capture(command: list[str]) -> str:
    result = capture_result(command)
    if result.returncode:
        raise MissingTool(f"{command[0]}: {last_lines(result.stderr)}")
    return result.stdout


def capture_result(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return processes.run(command, cwd=cwd)
    except OSError as error:
        raise MissingTool(f"{command[0]}: {error}") from error


def last_lines(output: str) -> str:
    return "\n".join(output.strip().splitlines()[-8:]) or "command failed without details"


def plan_excerpts(
    sources: list[Source], output: Path, requested: int, requested_seconds: float
) -> list[ExcerptPlan]:
    plans: list[ExcerptPlan] = []
    for source_index, source in enumerate(sources, start=1):
        info = light_probe(source.path)
        packet_facts(info, scan(source.path, read_intervals="%+#128").times)
        duration = video_duration(info)
        count = min(requested, max(1, int(duration // requested_seconds)))
        excerpt_duration = min(duration, requested_seconds)
        starts = excerpt_starts(duration, excerpt_duration, count)
        slug = safe_slug(source.path.stem)
        for excerpt_index, start in enumerate(starts, start=1):
            path = output / "excerpts" / f"{source_index:02d}-{slug}-e{excerpt_index:02d}.mkv"
            plans.append(
                ExcerptPlan(
                    source,
                    source_index,
                    info,
                    duration,
                    source.path.stat().st_size,
                    excerpt_index,
                    start,
                    excerpt_duration,
                    path,
                )
            )
    return plans


def video_duration(info: dict[str, object]) -> float:
    stream = video_stream(info)
    duration = number(stream.get("duration")) or number(info.get("duration_seconds"))
    if duration is None or duration <= 0:
        raise InvalidInput("ffprobe: source video has no positive duration")
    return duration


def excerpt_starts(duration: float, excerpt: float, count: int) -> list[float]:
    available = max(0.0, duration - excerpt)
    if count == 1:
        return [available / 2]
    return [available * index / (count - 1) for index in range(count)]


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_").lower()
    return slug[:60] or "source"


def estimate_space(plans: list[ExcerptPlan], variants: list[Variant]) -> int:
    estimate = 1_048_576
    has_25_fps = any(variant.frame_rate_change == "25 fps" for variant in variants)
    for plan in plans:
        info = plan.source_info
        stream = video_stream(info)
        width, height = display_size(stream)
        source_raw = yuv420_bytes(width, height, pixel_depth(stream))
        fps = frame_rate(info)
        frames = max(1, math.ceil(plan.duration_seconds * float(fps)) + 2)
        excerpt_raw = source_raw * frames
        source_excerpt_bytes = plan.source_size_bytes * min(
            1.0, plan.duration_seconds / plan.source_duration
        )
        estimate += math.ceil(excerpt_raw * 1.1)
        if has_25_fps:
            frames_25fps = max(1, math.ceil(plan.duration_seconds * 25) + 2)
            estimate += math.ceil(source_raw * frames_25fps * 1.1)
        for variant in variants:
            vwidth, vheight = scaled_dimensions(
                width, height, int(str(variant.settings["scale_short_side"]))
            )
            rate = 25 if variant.frame_rate_change == "25 fps" else float(fps)
            vframes = max(1, math.ceil(plan.duration_seconds * rate) + 2)
            variant_raw = yuv420_bytes(vwidth, vheight, int(str(variant.settings["bit_depth"])))
            ratio = quality_size_ratio(str(variant.settings["encoder"]), variant.quality_crf)
            estimate += max(source_excerpt_bytes * 8, variant_raw * vframes * ratio)
            estimate += max(source_excerpt_bytes * 10, excerpt_raw * 0.2)
    return math.ceil(estimate)


def quality_size_ratio(encoder: str, crf: int) -> float:
    maximum = 51 if encoder == "libx265" else 63
    return max(0.04, 1.2 * ((maximum + 1 - crf) / (maximum + 1)) ** 2)


def frame_rate(info: dict[str, object]) -> Fraction:
    return Fraction(str(info["packet_frame_rate"]))


def variant_frame_rate_cap(variant: Variant, excerpt: Media | None) -> int | None:
    if variant.frame_rate_change == "25 fps":
        return 25
    if not variant.use_preset_cap:
        return None
    cap = variant.settings["max_frame_rate"]
    if type(cap) is int and excerpt is not None and source_above_frame_rate_cap(excerpt, cap):
        return cap
    return None


def display_size(stream: dict[str, object]) -> tuple[int, int]:
    width, height = int(str(stream["width"])), int(str(stream["height"]))
    rotation = stream_rotation(stream)
    if int(rotation) % 180:
        return height, width
    return width, height


def stream_rotation(stream: dict[str, object]) -> float:
    side_data = stream_list(stream.get("side_data_list"))
    values: list[float] = []
    for side in side_data:
        try:
            values.append(float(str(side["rotation"])))
        except (KeyError, ValueError):
            continue
    if values:
        return values[0]
    try:
        return float(str(object_dict(stream.get("tags")).get("rotate", 0)))
    except ValueError:
        return 0.0


def pixel_depth(stream: dict[str, object]) -> int:
    pix_fmt = str(stream.get("pix_fmt", ""))
    match = re.search(r"(?:p|gray|gbrp)(9|10|12|14|16)", pix_fmt)
    return 16 if match else 8


def yuv420_bytes(width: int, height: int, depth: int) -> int:
    component_bytes = 1 if depth <= 8 else 2
    return (width * height + 2 * math.ceil(width / 2) * math.ceil(height / 2)) * component_bytes


def scaled_dimensions(width: int, height: int, short_side: int) -> tuple[int, int]:
    if not short_side or min(width, height) <= short_side:
        return width, height
    factor = short_side / min(width, height)
    return max(2, int(width * factor / 2) * 2), max(2, int(height * factor / 2) * 2)


def execute_benchmark(
    category: Category,
    output: Path,
    plans: list[ExcerptPlan],
    variants: list[Variant],
    estimate: int,
) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    (output / "excerpts").mkdir(exist_ok=True)
    (output / "variants").mkdir(exist_ok=True)
    (output / "side-by-side").mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix=".lastencode-bench-", dir=output) as raw_work:
        work = Path(raw_work)
        transformed: dict[tuple[Path, int], Path] = {}
        for plan in plans:
            cut_error = cut_excerpt(plan)
            excerpt_media = scan(plan.path) if cut_error is None else None
            for variant_index, variant in enumerate(variants, start=1):
                reference = plan.path
                variant_error = cut_error
                frame_rate_cap = variant_frame_rate_cap(variant, excerpt_media)
                if frame_rate_cap is not None and cut_error is None:
                    cache_key = (plan.path, frame_rate_cap)
                    cached_reference = transformed.get(cache_key)
                    if cached_reference is None:
                        reference = (
                            output / "excerpts" / (f"{plan.path.stem}-{frame_rate_cap}fps.mkv")
                        )
                        transform_error = make_frame_rate_reference(
                            plan.path, reference, frame_rate_cap
                        )
                        if transform_error:
                            variant_error = transform_error
                        else:
                            transformed[cache_key] = reference
                            variant_error = None
                    else:
                        reference = cached_reference
                        variant_error = None
                rows.append(
                    process_variant(
                        plan,
                        variant,
                        variant_index,
                        reference,
                        output,
                        work,
                        variant_error,
                        frame_rate_cap,
                    )
                )
    rows.sort(key=row_size_key)
    write_csv(output / "bench.csv", rows)
    return summary(
        category.name,
        [plan.source for plan in plans],
        plans,
        variants,
        estimate,
        rows,
        False,
    )


def cut_excerpt(plan: ExcerptPlan) -> str | None:
    if not plan.source_info.get("first_frame"):
        read_picture(plan.source.path, plan.source_info)
    source_stream = video_stream(plan.source_info)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-ss",
        f"{plan.start_seconds:.6f}",
        "-i",
        str(plan.source.path),
        "-t",
        f"{plan.duration_seconds:.6f}",
        "-map",
        f"0:{video_stream(plan.source_info)['index']}",
        "-map_metadata",
        "-1",
        "-an",
        "-vf",
        "setpts=PTS-STARTPTS",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
    ]
    if ffmpeg_range(source_stream) == "full":
        command.extend(["-color_range", "pc"])
    command.extend(
        [
            "-f",
            "matroska",
            str(plan.path),
        ]
    )
    return run_output(command, plan.path)


def make_25fps_reference(source: Path, output: Path) -> str | None:
    return make_frame_rate_reference(source, output, 25)


def make_frame_rate_reference(source: Path, output: Path, frame_rate: int) -> str | None:
    source_stream = video_stream(probe(source))
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map_metadata",
        "-1",
        "-vf",
        f"fps={frame_rate}:round=near,setpts=PTS-STARTPTS",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
    ]
    if ffmpeg_range(source_stream) == "full":
        command.extend(["-color_range", "pc"])
    command.extend(
        [
            "-f",
            "matroska",
            str(output),
        ]
    )
    return run_output(command, output)


def run_output(command: list[str], output: Path, cwd: Path | None = None) -> str | None:
    result = capture_result(command, cwd=cwd)
    if result.returncode == 0 and output.is_file() and output.stat().st_size:
        return None
    output.unlink(missing_ok=True)
    detail = last_lines(result.stderr)
    return f"{command[0]}: {detail}"


def process_variant(
    plan: ExcerptPlan,
    variant: Variant,
    variant_index: int,
    reference: Path,
    output: Path,
    work: Path,
    excerpt_error: str | None,
    frame_rate_cap: int | None = None,
) -> dict[str, object]:
    row = base_row(plan, variant, frame_rate_cap)
    if excerpt_error:
        row["reason"] = excerpt_error
        return row
    reference_info = probe(reference, packet_times=bool(variant.settings["drop_repeated_frames"]))
    variant_path = output / "variants" / f"{plan.path.stem}-{variant.key}.mp4"
    side_path = output / "side-by-side" / f"{plan.path.stem}-{variant.key}.mp4"
    row["variant_path"] = str(variant_path)
    error, encode_time = encode_variant(
        reference, reference_info, variant, variant_path, frame_rate_cap
    )
    row["encode_time_seconds"] = encode_time
    row["encode_time_realtime_multiple"] = (
        round(encode_time / plan.duration_seconds, 6) if encode_time is not None else None
    )
    if error:
        row["reason"] = error
        return row
    try:
        row["size_bytes"] = variant_path.stat().st_size
        row["bitrate_bps"] = round(variant_path.stat().st_size * 8 / plan.duration_seconds, 2)
        candidate_info = probe(variant_path)
        side_error = encode_side_by_side(
            reference, reference_info, variant_path, candidate_info, side_path
        )
        if side_error:
            row["reason"] = side_error
            return row
        row["side_by_side_path"] = str(side_path)
        if variant.settings["drop_repeated_frames"]:
            reference_count = len(frame_timestamps(reference))
            candidate_count = len(frame_timestamps(variant_path))
            if reference_count:
                row["dropped_frame_share"] = round(
                    max(0.0, (reference_count - candidate_count) / reference_count), 6
                )
        metrics = score_variant(
            reference,
            reference_info,
            variant_path,
            candidate_info,
            variant,
            work,
            f"{plan.source_index}-{plan.excerpt_index}-{variant_index}",
        )
    except (MissingTool, OSError, ValueError, subprocess.SubprocessError) as error:
        row["reason"] = str(error)
        return row
    finally:
        cleanup_expansion_temporaries(work)
    row.update(metrics)
    row["valid"] = True
    return row


def base_row(
    plan: ExcerptPlan, variant: Variant, frame_rate_cap: int | None = None
) -> dict[str, object]:
    frame_rate_change = variant.frame_rate_change
    if frame_rate_cap is not None and variant.frame_rate_change == "native":
        frame_rate_change = f"preset cap ({frame_rate_cap} fps)"
    return {
        "source": str(plan.source.path),
        "excerpt_index": plan.excerpt_index,
        "excerpt_start_seconds": round(plan.start_seconds, 6),
        "excerpt_seconds": round(plan.duration_seconds, 6),
        "target": variant.target,
        "quality_crf": variant.quality_crf,
        "frame_rate_change": frame_rate_change,
        "size_bytes": None,
        "bitrate_bps": None,
        "encode_time_seconds": None,
        "encode_time_realtime_multiple": None,
        "vmaf_desktop_mean": None,
        "vmaf_desktop_p5": None,
        "vmaf_phone_mean": None,
        "vmaf_phone_p5": None,
        "xpsnr_y": None,
        "scaling": "",
        "dropped_frame_share": 0.0,
        "valid": False,
        "reason": None,
        "variant_path": None,
        "side_by_side_path": None,
    }


def encode_variant(
    reference: Path,
    reference_info: dict[str, object],
    variant: Variant,
    output: Path,
    frame_rate_cap: int | None = None,
) -> tuple[str | None, float | None]:
    record: dict[str, object] = {
        "source_path": str(reference),
        "probe": reference_info,
        "settings": variant.settings,
        "action": "encode",
        "target": variant.target,
        "location": "kept",
        "frame_rate_cap": frame_rate_cap,
    }
    command = encoding_command(record, output, overwrite=True)
    started = time.perf_counter()
    result = capture_result(command)
    elapsed = round(time.perf_counter() - started, 6)
    if result.returncode == 0 and output.is_file() and output.stat().st_size:
        return None, elapsed
    output.unlink(missing_ok=True)
    return f"ffmpeg exited {result.returncode}: {last_lines(result.stderr)}", elapsed


def encode_side_by_side(
    reference: Path,
    reference_info: dict[str, object],
    candidate: Path,
    candidate_info: dict[str, object],
    output: Path,
) -> str | None:
    stream = video_stream(reference_info)
    width, height = display_size(stream)
    excerpt_range = ffmpeg_range(stream)
    candidate_range = ffmpeg_range(video_stream(candidate_info))
    graph = (
        f"[0:v]setpts=PTS-STARTPTS,scale={width}:{height}:flags=bicubic:"
        f"in_range={excerpt_range}:out_range={excerpt_range},format=yuv420p[left];"
        f"[1:v]setpts=PTS-STARTPTS,scale={width}:{height}:flags=bicubic:"
        f"in_range={candidate_range}:out_range={excerpt_range},"
        "format=yuv420p[right];[left][right]hstack=inputs=2:shortest=0[out]"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(reference),
        "-i",
        str(candidate),
        "-filter_complex",
        graph,
        "-map",
        "[out]",
        "-an",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "16",
        "-g",
        "2147483647",
        "-force_key_frames",
        "expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+1))",
        "-x264-params",
        "open-gop=0",
        "-color_range",
        "pc" if excerpt_range == "full" else "tv",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(output),
    ]
    return run_output(command, output)


def score_variant(
    reference: Path,
    reference_info: dict[str, object],
    candidate: Path,
    candidate_info: dict[str, object],
    variant: Variant,
    work: Path,
    name: str,
) -> dict[str, object]:
    scaling = scaling_description(candidate_info, reference_info)
    reference_pts = frame_timestamps(reference)
    candidate_pts = frame_timestamps(candidate)
    ref_count, candidate_count = len(reference_pts), len(candidate_pts)
    dropped = bool(variant.settings["drop_repeated_frames"])
    share = max(0.0, (ref_count - candidate_count) / ref_count) if dropped and ref_count else 0.0
    if candidate_count < ref_count and dropped:
        expanded = work / f"expanded-{name}.mkv"
        expand_dropped_frames(
            candidate,
            candidate_info,
            reference_info,
            candidate_pts,
            reference_pts,
            expanded,
        )
        candidate = expanded
        candidate_info = probe(candidate)
        candidate_pts = frame_timestamps(candidate)
        candidate_count = len(candidate_pts)
    if ref_count != candidate_count:
        raise ValueError(
            f"frame count mismatch after playback expansion: reference {ref_count}, "
            f"variant {candidate_count}"
        )
    if not matching_frame_times(reference_pts, candidate_pts):
        raise ValueError("frame timestamps differ by more than 2 ms after playback expansion")
    desktop_mean, desktop_p5, phone_mean, phone_p5 = score_vmaf(
        candidate, candidate_info, reference, reference_info, work, f"vmaf-{name}"
    )
    xpsnr = score_xpsnr(candidate, candidate_info, reference, reference_info)
    return {
        "vmaf_desktop_mean": desktop_mean,
        "vmaf_desktop_p5": desktop_p5,
        "vmaf_phone_mean": phone_mean,
        "vmaf_phone_p5": phone_p5,
        "xpsnr_y": xpsnr,
        "scaling": scaling,
        "dropped_frame_share": round(share, 6),
    }


def frame_timestamps(path: Path) -> list[Fraction]:
    raw = capture(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time,pts_time",
            "-of",
            "json",
            str(path),
        ]
    )
    document = object_dict(json.loads(raw))
    result: list[Fraction] = []
    for frame in stream_list(document.get("frames")):
        value = frame.get("best_effort_timestamp_time") or frame.get("pts_time")
        if value is None or str(value) == "N/A":
            raise ValueError(f"ffprobe: missing video timestamp in {path}")
        result.append(Fraction(str(value)))
    if not result:
        raise ValueError(f"ffprobe: no video frames in {path}")
    return result


def expand_dropped_frames(
    candidate: Path,
    candidate_info: dict[str, object],
    reference_info: dict[str, object],
    candidate_pts: list[Fraction],
    reference_pts: list[Fraction],
    output: Path,
) -> None:
    if not candidate_pts or not reference_pts:
        raise ValueError("cannot expand dropped frames without reference and variant timestamps")
    ref_first, candidate_first = reference_pts[0], candidate_pts[0]
    ref_times = [timestamp - ref_first for timestamp in reference_pts]
    variant_times = [timestamp - candidate_first for timestamp in candidate_pts]
    mapping = held_frame_indices(variant_times, ref_times)
    ref_stream = video_stream(reference_info)
    work = output.parent
    segments, error = extract_candidate_segments(
        candidate, candidate_info, reference_info, len(candidate_pts), work
    )
    if error:
        raise ValueError(error)
    manifest = work / f"{output.stem}.ffconcat"
    manifest.write_text(concat_manifest(segments, mapping, ref_times), encoding="utf-8")
    error = run_output(concat_frames_command(manifest, output, ref_stream), output, cwd=work)
    if error:
        raise ValueError(error)


def extract_candidate_segments(
    candidate: Path,
    candidate_info: dict[str, object],
    reference_info: dict[str, object],
    frame_count: int,
    work: Path,
) -> tuple[list[Path], str | None]:
    pattern = work / "candidate-frame-%05d.mkv"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(candidate),
        "-map",
        "0:v:0",
        "-vf",
        decode_filter(candidate_info, reference_info),
        "-fps_mode",
        "passthrough",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
    ]
    if frame_count == 1:
        output = work / "candidate-frame-00000.mkv"
        command += ["-f", "matroska", str(output)]
    else:
        boundaries = ",".join(str(index) for index in range(1, frame_count))
        command += [
            "-segment_frames",
            boundaries,
            "-reset_timestamps",
            "1",
            "-segment_format",
            "matroska",
            "-f",
            "segment",
            str(pattern),
        ]
    result = capture_result(command)
    if result.returncode:
        return [], f"frame extraction failed: {last_lines(result.stderr)}"
    segments = [work / f"candidate-frame-{index:05d}.mkv" for index in range(frame_count)]
    if not all(path.is_file() and path.stat().st_size for path in segments):
        return [], "frame extraction did not create one lossless segment per kept frame"
    return segments, None


def concat_manifest(
    segments: list[Path], mapping: list[int], reference_times: list[Fraction]
) -> str:
    lines = ["ffconcat version 1.0"]
    for position, frame_index in enumerate(mapping):
        lines.append(f"file '{segments[frame_index].name}'")
        if position + 1 < len(mapping):
            duration = reference_times[position + 1] - reference_times[position]
            lines.append(f"duration {float(duration):.6f}")
    return "\n".join(lines) + "\n"


def concat_frames_command(
    manifest: Path, output: Path, reference_stream: dict[str, object]
) -> list[str]:
    color_range = "pc" if ffmpeg_range(reference_stream) == "full" else "tv"
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-map",
        "0:v:0",
        "-map_metadata",
        "-1",
        "-fps_mode",
        "passthrough",
        # The concat stream's guessed rate can be 1 fps; its 1 s encoder time base rounds times.
        "-enc_time_base",
        "demux",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
        "-color_range",
        color_range,
        "-f",
        "matroska",
        str(output),
    ]


def held_frame_indices(
    candidate_times: list[Fraction], reference_times: list[Fraction]
) -> list[int]:
    if not candidate_times or not reference_times:
        raise ValueError("cannot expand dropped frames without reference and variant timestamps")
    if candidate_times[0] > reference_times[0]:
        raise ValueError(
            "variant starts after the excerpt; playback expansion cannot align frame 1"
        )
    candidate_index = 0
    tolerance = Fraction(1, 500)
    mapping: list[int] = []
    for timestamp in reference_times:
        while (
            candidate_index + 1 < len(candidate_times)
            and candidate_times[candidate_index + 1] <= timestamp + tolerance
        ):
            candidate_index += 1
        mapping.append(candidate_index)
    return mapping


def cleanup_expansion_temporaries(work: Path) -> None:
    for pattern in ("candidate-frame-*.mkv", "expanded-*.mkv", "*.ffconcat"):
        for path in work.glob(pattern):
            path.unlink(missing_ok=True)


def matching_frame_times(reference: list[Fraction], candidate: list[Fraction]) -> bool:
    tolerance = Fraction(1, 500)
    return len(reference) == len(candidate) and all(
        abs(left - right) <= tolerance for left, right in zip(reference, candidate, strict=True)
    )


def decode_filter(candidate_info: dict[str, object], reference_info: dict[str, object]) -> str:
    filters = ["setpts=PTS-STARTPTS"]
    candidate_stream = video_stream(candidate_info)
    reference_stream = video_stream(reference_info)
    source_width, source_height = display_size(candidate_stream)
    width, height = display_size(reference_stream)
    source_range = ffmpeg_range(candidate_stream)
    output_range = ffmpeg_range(reference_stream)
    if (source_width, source_height) != (width, height) or source_range != output_range:
        filters.append(
            f"scale={width}:{height}:flags=bicubic:in_range={source_range}:out_range={output_range}"
        )
    target_pix_fmt = str(reference_stream.get("pix_fmt", "yuv420p"))
    filters.append(f"format={target_pix_fmt}")
    return ",".join(filters)


def ffmpeg_range(stream: dict[str, object]) -> str:
    return "full" if stream.get("color_range") in ("pc", "jpeg") else "limited"


def scaling_description(
    candidate_info: dict[str, object], reference_info: dict[str, object]
) -> str:
    candidate_size = display_size(video_stream(candidate_info))
    reference_size = display_size(video_stream(reference_info))
    if candidate_size == reference_size:
        return ""
    width, height = reference_size
    return f"bicubic to {width}x{height}"


def score_vmaf(
    candidate: Path,
    candidate_info: dict[str, object],
    reference: Path,
    reference_info: dict[str, object],
    work: Path,
    name: str,
) -> tuple[float, float, float, float]:
    graph = metric_graph(candidate_info, reference_info, "yuv420p10le")
    graph += (
        "[dist][ref]libvmaf=model='version=vmaf_v1.0.16_3d0h\\:name=desktop|"
        "version=vmaf_v1.0.16_5d0h\\:name=phone':log_fmt=json:"
        f"log_path=vmaf-{name}.json:n_threads=4"
    )
    result = capture_result(
        metric_command(
            candidate,
            reference,
            "-filter_complex",
            graph,
            "-enc_time_base",
            "demux",
            "-f",
            "null",
            "-",
        ),
        cwd=work,
    )
    if result.returncode:
        raise ValueError(f"VMAF failed: {last_lines(result.stderr)}")
    raw = (work / f"vmaf-{name}.json").read_text(encoding="utf-8")
    document = object_dict(json.loads(raw))
    frames = cast(list[object], document.get("frames", []))
    desktop = vmaf_values(frames, "desktop")
    phone = vmaf_values(frames, "phone")
    return percentile_scores(desktop) + percentile_scores(phone)


def vmaf_values(frames: list[object], model: str) -> list[float]:
    result: list[float] = []
    for item in frames:
        metrics = object_dict(object_dict(item).get("metrics"))
        value = metrics.get(f"vmaf_{model}", metrics.get(model))
        if value is None and len(metrics) == 1:
            value = metrics.get("vmaf")
        if value is None:
            raise ValueError(f"VMAF output has no {model} score")
        result.append(float(str(value)))
    if not result:
        raise ValueError("VMAF produced no frame scores")
    return result


def percentile_scores(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    p5 = ordered[max(0, len(ordered) // 20 - 1)]
    return round(fmean(ordered), 2), round(p5, 2)


def score_xpsnr(
    candidate: Path,
    candidate_info: dict[str, object],
    reference: Path,
    reference_info: dict[str, object],
) -> float | None:
    # 8-bit: ffmpeg's xpsnr returns near-zero scores on 10-bit frames narrower than 1280 px.
    graph = metric_graph(candidate_info, reference_info, "yuv420p") + "[dist][ref]xpsnr"
    result = capture_result(
        metric_command(
            candidate,
            reference,
            "-filter_complex",
            graph,
            "-loglevel",
            "info",
            "-enc_time_base",
            "demux",
            "-f",
            "null",
            "-",
        )
    )
    if result.returncode:
        raise ValueError(f"XPSNR failed: {last_lines(result.stderr)}")
    match = re.search(
        r"XPSNR average,\s+\d+\s+frames\s+y:\s*([+\-\d.inf]+)", result.stderr
    ) or re.search(r"XPSNR\s+y:\s*([+\-\d.inf]+)", result.stderr)
    if not match:
        raise ValueError("XPSNR output has no average luma score")
    score = float(match.group(1))
    return round(score, 4) if math.isfinite(score) else None


def metric_graph(
    candidate_info: dict[str, object], reference_info: dict[str, object], metric_format: str
) -> str:
    candidate_filter = metric_filter(candidate_info, reference_info, metric_format)
    reference_filter = metric_filter(reference_info, reference_info, metric_format)
    return f"[0:v]{candidate_filter}[dist];[1:v]{reference_filter}[ref];"


def metric_filter(
    source_info: dict[str, object], reference_info: dict[str, object], metric_format: str
) -> str:
    filters = ["settb=expr=AVTB", "setpts=PTS-STARTPTS"]
    source_stream = video_stream(source_info)
    reference_stream = video_stream(reference_info)
    source_size = display_size(source_stream)
    target_size = display_size(reference_stream)
    source_range, target_range = ffmpeg_range(source_stream), ffmpeg_range(reference_stream)
    if source_size != target_size or source_range != target_range:
        width, height = target_size
        filters.append(
            f"scale={width}:{height}:flags=bicubic:in_range={source_range}:out_range={target_range}"
        )
    target_pix_fmt = str(reference_stream.get("pix_fmt", "yuv420p"))
    filters += [f"format={target_pix_fmt}", f"format={metric_format}"]
    return ",".join(filters)


def metric_command(
    candidate: Path,
    reference: Path,
    *filter_options: str,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(candidate),
        "-i",
        str(reference),
        *filter_options,
    ]


def row_size_key(row: dict[str, object]) -> tuple[int, int]:
    size = row.get("size_bytes")
    return (size if isinstance(size, int) else 2**63 - 1, int(str(row["excerpt_index"])))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_name(".bench.csv.tmp")
    try:
        # Paths keep their original bytes, as the file system's surrogate escapes encode them.
        with temporary.open("w", encoding="utf-8", errors="surrogateescape", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                values = dict(row)
                values["valid"] = str(bool(row["valid"])).lower()
                writer.writerow(values)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def summary(
    category: str,
    sources: list[Source],
    plans: list[ExcerptPlan],
    variants: list[Variant],
    estimate: int,
    rows: list[dict[str, object]],
    dry_run: bool,
) -> dict[str, object]:
    valid = sum(bool(row["valid"]) for row in rows)
    output = plans[0].path.parent.parent
    return {
        "record_type": "bench_summary",
        "category": category,
        "sources": list(dict.fromkeys(str(source.path) for source in sources)),
        "excerpt_count": len(plans),
        "variant_count": len(variants),
        "encode_count": len(plans) * len(variants),
        "valid_count": valid,
        "invalid_count": len(rows) - valid,
        "dry_run": dry_run,
        "changed": not dry_run,
        "requires_confirmation": False,
        "targets": benchmark_targets(output, plans, variants),
        "csv_path": str(output / "bench.csv"),
        "excerpt_paths": [str(plan.path) for plan in plans],
        "space_estimate_bytes": estimate,
        "rows": rows,
    }


def render_text(document: object) -> str:
    summary_data = object_dict(document)
    lines: list[str] = []
    if summary_data.get("dry_run"):
        lines.append(
            f"Bench dry-run: {summary_data['variant_count']} variants per excerpt, "
            f"{summary_data['encode_count']} encodes across "
            f"{summary_data['excerpt_count']} excerpts; "
            f"estimated space {summary_data['space_estimate_bytes']} bytes."
        )
        for item in cast(list[dict[str, object]], summary_data["targets"]):
            lines.append(f"{item['effect']}: {safe_text(item['path'])}")
    else:
        lines.extend(render_table(cast(list[object], summary_data.get("rows", []))))
        lines.append(
            f"Summary: {summary_data['valid_count']} valid, "
            f"{summary_data['invalid_count']} invalid; "
            f"estimated space {summary_data['space_estimate_bytes']} bytes."
        )
    return "\n".join(lines)


def render_table(raw_rows: list[object]) -> list[str]:
    headings = (
        "SOURCE",
        "EXCERPT",
        "SIZE B",
        "TARGET",
        "CRF",
        "FPS",
        "BITRATE",
        "ENCODE s",
        "ENCODE x realtime",
        "VMAF desk mean",
        "VMAF desk p5",
        "VMAF phone mean",
        "VMAF phone p5",
        "XPSNR Y",
        "SCALE",
        "DROP %",
        "VALID",
    )
    rows = [object_dict(item) for item in raw_rows]
    lines = ["\t".join(headings)]
    for row in rows:
        values = (
            row.get("source"),
            row.get("excerpt_index"),
            row.get("size_bytes"),
            row.get("target"),
            row.get("quality_crf"),
            row.get("frame_rate_change"),
            row.get("bitrate_bps"),
            row.get("encode_time_seconds"),
            row.get("encode_time_realtime_multiple"),
            row.get("vmaf_desktop_mean"),
            row.get("vmaf_desktop_p5"),
            row.get("vmaf_phone_mean"),
            row.get("vmaf_phone_p5"),
            row.get("xpsnr_y"),
            row.get("scaling"),
            round(float(str(row.get("dropped_frame_share", 0))) * 100, 2),
            "yes" if row.get("valid") else "no",
        )
        lines.append("\t".join(format_value(value) for value in values))
    return lines


def format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return safe_text(value)


FLAGS: list[dict[str, object]] = [
    {
        "name": "force",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Replace an existing benchmark in the output folder.",
    },
    {
        "name": "category",
        "type": "string",
        "required": True,
        "description": "Content category; list valid names with presets.",
    },
    {
        "name": "output-dir",
        "type": "string",
        "required": True,
        "description": "Benchmark output folder.",
    },
    {
        "name": "target",
        "type": "string",
        "required": False,
        "repeatable": True,
        "default": ["portable"],
        "enum": list(TARGETS),
        "description": (
            "Distinct playback target per occurrence; repeat for more; default portable."
        ),
    },
    {
        "name": "quality-settings",
        "type": "integer",
        "required": False,
        "repeatable": True,
        "description": (
            "Distinct CRF per occurrence, repeat for more; x265 0-51, SVT-AV1 1-63; "
            "default preset CRF and +/-2."
        ),
    },
    {
        "name": "excerpt-seconds",
        "type": "number",
        "required": False,
        "default": 20,
        "description": "Positive excerpt length in seconds; default 20.",
    },
    {
        "name": "excerpts",
        "type": "integer",
        "required": False,
        "default": 3,
        "description": "Positive excerpts per source; default 3.",
    },
    {
        "name": "include-25-fps",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": (
            "Without it, the native variants already follow the preset's frame-rate cap "
            "(max_frame_rate in presets). With it, the native variants keep the source rate "
            "uncapped, and a set capped at 25 fps, scored against an excerpt changed to 25 fps, "
            "is added."
        ),
    },
    {
        "name": "dry-run",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Print variant count and conservative space estimate without writing.",
    },
    FORMAT_FLAG
    | {"enum": ["json", "text"], "description": "Select JSON or text; conflicts with --json."},
]


COMMAND = Command(
    name="bench",
    description=(
        "Compare preset quality variants on short excerpts with objective scores and clips. "
        "A repeat fails with conflict and changes nothing unless --force replaces existing files."
    ),
    configure=configure,
    run=run,
    args=[
        {
            "name": "sources",
            "type": "string",
            "required": True,
            "variadic": True,
            "description": "Video files or folders containing supported video files.",
        }
    ],
    flags=FLAGS,
    output=bench_schema(),
    output_description=(
        "One JSON document with summary and size-sorted rows. The run writes bench.csv, "
        "lossless FFV1 excerpts, encoded variants and H.264 side-by-side clips inside "
        "--output-dir. Rows contain byte sizes, bitrates, encode time and its realtime multiple, "
        "metric scores, "
        "scaling, dropped-frame share and validity. "
        "A repeat fails with conflict if any planned file exists, unless --force replaces it. "
        "Dry runs list targets with create or replace effects, including possible "
        "frame-rate reference excerpts, and changed=false; "
        "--force needs no confirmation."
    ),
    render_text=render_text,
    effects="non_idempotent",
    exit_codes={"0": "Benchmark completed; invalid rows are reported in the table and counts."},
)
