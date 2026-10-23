"""Independent decoder read-back and small player-rendered RGB samples."""

import re
from bisect import bisect_left, bisect_right
from fractions import Fraction
from pathlib import Path

from lastencode.check_media import Media
from lastencode.probe import COLOUR_KEYS, UNKNOWN, colour_description, first_frame, object_dict
from lastencode.processes import run_bytes
from lastencode.video import video_stream


def tag_values(path: Path, record: dict[str, object], output: Media) -> dict[str, object]:
    frame = first_frame(path)
    actual = colour_description(frame, output.video)
    info = object_dict(record["probe"])
    copying = record["action"] != "encode"
    reference = object_dict(info.get("first_frame")) if copying else video_stream(info)
    expected = {key: reference.get(key) for key in COLOUR_KEYS}
    if not copying:
        expected["color_range"] = "tv"
    required = {key: value for key, value in expected.items() if value not in UNKNOWN}
    header_valid = all(
        frame.get(key) == value or (copying and frame.get(key) in UNKNOWN)
        for key, value in required.items()
    )
    container_valid = all(
        output.video.get(key) == value or (copying and output.video.get(key) in UNKNOWN)
        for key, value in required.items()
    )
    # Even unspecified source properties must not acquire contradictory output labels.
    consistent = all(
        frame.get(key) in UNKNOWN
        or output.video.get(key) in UNKNOWN
        or frame.get(key) == output.video.get(key)
        for key in COLOUR_KEYS
    )
    return {
        "valid": header_valid and container_valid and consistent,
        "expected": expected,
        "frame": actual,
        "container": {key: output.video.get(key) for key in COLOUR_KEYS},
    }


def rgb_means(path: Path, indices: list[float], media: Media) -> list[list[float]]:
    # Untagged SDR needs a conventional fallback; specified decoder properties stay intact.
    # This is a fresh decoder read, never the planner's colour description.
    frame = first_frame(path)
    defaults = {"color_primaries": "bt709", "color_trc": "bt709", "colorspace": "bt709"}
    keys = {
        "color_primaries": "color_primaries",
        "color_trc": "color_transfer",
        "colorspace": "color_space",
    }
    fallback = [
        f"{key}={value}" for key, value in defaults.items() if frame.get(keys[key]) in UNKNOWN
    ]
    filters: list[str] = []
    if fallback:
        filters.append("setparams=" + ":".join(fallback))
    filters += [
        "zscale=matrix=gbr:primaries=709:transfer=709:range=full",
        "format=gbrp",
        "scale=64:64:flags=area",
        "format=rgb24",
    ]
    means: dict[float, list[float]] = {}
    for timestamp in sorted(set(indices)):
        data = render_rgb(path, timestamp, filters, seek_from=seek_start(media, timestamp))
        means[timestamp] = [sum(data[channel::3]) / (64 * 64) for channel in range(3)]
    return [means[timestamp] for timestamp in indices]


def seek_start(media: Media, timestamp: float) -> float | None:
    container = object_dict(media.document.get("format"))
    offset = float(str(container.get("start_time") or 0))
    if "mpegts" not in str(container.get("format_name")) and abs(offset) < 0.000001:
        return None
    keys = sorted(float(str(p["pts_time"])) for p in media.packets if "K" in str(p.get("flags")))
    if not keys:
        return None
    # Start one random-access point earlier, allowing for codec reordering and TS seeking
    # into the middle of a GOP; only the first GOP ever needs a seek to file start.
    previous = max(0, bisect_right(keys, timestamp) - 2)
    return max(0.0, keys[previous] - 1.0) if previous else 0.0


def render_rgb(
    path: Path, timestamp: float, filters: list[str], *, seek_from: float | None = None
) -> bytes:
    # ffprobe rounds packet PTS to microseconds; seek just before it to avoid skipping
    # a frame whose true rational PTS lies a fraction of a microsecond earlier.
    position = timestamp - 0.000002 if seek_from is None else seek_from
    selection = [] if seek_from is None else [f"select='gte(t,{timestamp - 0.000002:.6f})'"]
    result = run_bytes(
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "info",
            "-nostdin",
            "-copyts",
            "-seek_timestamp",
            "1",
            "-ss",
            f"{position:.6f}",
            *([] if seek_from is None else ["-noaccurate_seek"]),
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-vf",
            ",".join([*selection, "showinfo", *filters]),
            "-frames:v",
            "1",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
    )
    diagnostic = result.stderr.decode(errors="replace")
    if result.returncode:
        raise ValueError("Colour rendering: " + diagnostic[-2000:])
    pts = re.search(r"Parsed_showinfo[^\n]*\bn:\s*0\s+pts:\s*(-?\d+)", diagnostic)
    base = re.search(r"config in time_base:\s*(\d+/\d+)", diagnostic)
    actual = float(int(pts[1]) * Fraction(base[1])) if pts and base else None
    if actual is None or abs(actual - timestamp) > 0.000003:
        raise ValueError(f"Colour rendering: seek did not return requested PTS {timestamp}")
    if len(result.stdout) != 64 * 64 * 3:
        raise ValueError("Colour rendering: expected one 64-by-64 RGB frame")
    return result.stdout


def sample_pairs(source: Media, output: Media, cap: int | None) -> tuple[list[float], list[float]]:
    duration = min(source.end - source.times[0], output.end - output.times[0])
    samples = [duration * (i + 0.5) / 5 for i in range(5)]
    output_times = [
        output.times[max(0, bisect_right(output.times, t + output.times[0]) - 1)] for t in samples
    ]
    pairs: list[float] = []
    for timestamp in output_times:
        shown = Fraction(str(timestamp)) - Fraction(str(output.times[0]))
        # fps=round=near holds the latest frame before the next half-interval boundary.
        # Without a cap, kept frames retain their source PTS (allow demuxer rounding).
        half_interval = Fraction(1, 2 * cap) if cap else Fraction(2, 1_000_000)
        limit = Fraction(str(source.times[0])) + shown + half_interval
        index = max(0, bisect_left(source.times, float(limit)) - 1)
        pairs.append(source.times[index])
    return pairs, output_times


def colour_values(
    source_path: Path, output_path: Path, source: Media, output: Media, *, cap: int | None = None
) -> dict[str, object]:
    source_times, output_times = sample_pairs(source, output, cap)
    original = rgb_means(source_path, source_times, source)
    actual = rgb_means(output_path, output_times, output)
    differences = [
        [abs(a - b) for a, b in zip(s, o, strict=True)]
        for s, o in zip(original, actual, strict=True)
    ]
    maximum = max(max(channels) for channels in differences)
    return {
        "valid": maximum <= 3,
        "max_channel_difference": maximum,
        "threshold": 3,
        "source_pts_seconds": source_times,
        "output_pts_seconds": output_times,
        "channel_differences": differences,
    }
