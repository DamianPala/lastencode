"""Single packet scan per file for stream, timeline and random-access checks."""

import json
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
from pathlib import Path

from lastencode.bitstream import random_access
from lastencode.errors import UnreadableSource
from lastencode.probe import object_dict, stream_list
from lastencode.processes import run


@dataclass
class Media:
    document: dict[str, object]

    @cached_property
    def streams(self) -> list[dict[str, object]]:
        return stream_list(self.document.get("streams"))

    @cached_property
    def video(self) -> dict[str, object]:
        videos = [
            s
            for s in self.streams
            if s.get("codec_type") == "video"
            and not object_dict(s.get("disposition")).get("attached_pic")
        ]
        if not videos:
            raise ValueError("ffprobe found no video stream")
        return videos[0]

    @cached_property
    def packets(self) -> list[dict[str, object]]:
        index = self.video["index"]
        # Packets an edit list discards (flag D, e.g. after a lossless cut) are never shown.
        return [
            p
            for p in stream_list(self.document.get("packets"))
            if p["stream_index"] == index and "D" not in str(p.get("flags"))
        ]

    @cached_property
    def times(self) -> list[float]:
        times = sorted(finite(p.get("pts_time")) for p in self.packets)
        if not times or len(set(times)) != len(times):
            raise ValueError("missing video packets or duplicate presentation times")
        return times

    @cached_property
    def end(self) -> float:
        return max(finite(p.get("pts_time")) + finite(p.get("duration_time")) for p in self.packets)

    @cached_property
    def duration(self) -> float:
        return finite(object_dict(self.document.get("format")).get("duration"))


def finite(value: object) -> float:
    number = float(str(value))
    if not math.isfinite(number):
        raise ValueError(f"invalid timestamp or duration: {value!r}")
    return number


def scan(path: Path, *, read_intervals: str | None = None) -> Media:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            *(
                ["-select_streams", "v:0", "-read_intervals", read_intervals]
                if read_intervals is not None
                else []
            ),
            "-show_packets",
            "-show_streams",
            "-show_format",
            "-show_chapters",
            "-show_entries",
            "packet=pts_time,duration_time,flags,stream_index",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise UnreadableSource(f"Read media {path} with ffprobe: " + result.stderr[-2000:])
    return Media(object_dict(json.loads(result.stdout)))


def longest_gap(source: Media) -> float:
    times = source.times
    return max([1.0, *(b - a for a, b in zip(times, times[1:], strict=False))])


def maximum_window_frames(times: list[float], seconds: float = 1.0) -> int:
    exact_times = [Fraction(str(timestamp)) for timestamp in times]
    window = Fraction(str(seconds))
    right = 0
    maximum = 0
    for left, start in enumerate(exact_times):
        right = max(right, left)
        while right < len(exact_times) and exact_times[right] - start < window:
            right += 1
        maximum = max(maximum, right - left)
    return maximum


def source_above_frame_rate_cap(source: Media, cap: int) -> bool:
    return maximum_window_frames(source.times) > cap + 1


def frame_values(
    source: Media, output: Media, dropping: bool, copying: bool = False, cap: int | None = None
) -> dict[str, object]:
    original, actual = source.times, output.times
    if cap is not None and not copying:
        return capped_frame_values(source, output, dropping, cap)
    # R10 counts from the first frame: a container start offset (MPEG-TS) is not a frame change.
    reference = [t - original[0] for t in original]
    observed = [t - actual[0] for t in actual]
    if dropping:
        errors = subsequence_errors(reference, observed)
    else:
        errors = [abs(a - b) for a, b in zip(reference, observed, strict=False)]
    gap = max((b - a for a, b in zip(actual, actual[1:], strict=False)), default=0.0)
    valid_count = 0 < len(actual) <= len(original) if dropping else len(actual) == len(original)
    max_error = max(errors, default=math.inf)
    tolerance = 0.0000011 if copying else 0.0020001
    return {
        "source_count": len(original),
        "output_count": len(actual),
        "max_time_error_seconds": max_error if math.isfinite(max_error) else None,
        "timestamp_tolerance_seconds": tolerance,
        "absolute_packet_times": copying,
        "max_gap_seconds": gap,
        "allowed_gap_seconds": longest_gap(source),
        "valid": valid_count
        and max_error <= tolerance
        and (not dropping or gap <= longest_gap(source) + 0.0000001),
    }


def capped_frame_values(
    source: Media, output: Media, dropping: bool, cap: int
) -> dict[str, object]:
    source_times = [time - source.times[0] for time in source.times]
    actual = [time - output.times[0] for time in output.times]
    tolerance = 0.5 / cap + 0.0000001
    source_errors, source_indices = nearest_frame_errors(
        source_times, actual, tolerance=tolerance, end=source.end - source.times[0]
    )
    duration = source.end - source.times[0]
    capped_count = max(1, math.floor(duration * cap) + 1)
    capped_times = [index / cap for index in range(capped_count)]
    if dropping:
        errors = subsequence_errors(capped_times, actual)
    else:
        errors = source_errors
    windows = one_second_window_counts(actual, output.end - output.times[0])
    maximum = max(windows, default=0)
    minimum = min(windows, default=0)
    gap = max((b - a for a, b in zip(actual, actual[1:], strict=False)), default=0.0)
    allowed_gap = max(
        1.0,
        max((b - a for a, b in zip(capped_times, capped_times[1:], strict=False)), default=0.0),
    )
    count_valid = 0 < len(actual) <= len(capped_times) if dropping else bool(actual)
    valid = (
        count_valid
        and max(source_errors, default=math.inf) <= tolerance
        and len(source_indices) == len(actual)
        and max(errors, default=math.inf) <= tolerance
        and maximum <= cap
        and (dropping or minimum >= cap - 1)
        and (not dropping or gap <= allowed_gap + 0.0000001)
    )
    return {
        "source_count": len(source.times),
        "output_count": len(actual),
        "max_time_error_seconds": max(source_errors, default=math.inf),
        "timestamp_tolerance_seconds": tolerance,
        "absolute_packet_times": False,
        "max_gap_seconds": gap,
        "allowed_gap_seconds": allowed_gap,
        "frame_rate_cap": cap,
        "max_one_second_window_frames": maximum,
        "min_one_second_window_frames": minimum,
        "source_frame_matches": len(source_indices),
        "valid": valid,
    }


def on_screen_error(reference: list[float], index: int, timestamp: float, end: float) -> float:
    next_time = reference[index + 1] if index + 1 < len(reference) else end
    # The next frame must be strictly later than t - tolerance, even at the boundary.
    start_error = float(Fraction(str(reference[index])) - Fraction(str(timestamp)))
    end_error = (
        float(Fraction(str(timestamp)) - Fraction(str(next_time)))
        if math.isfinite(next_time)
        else -math.inf
    )
    return max(start_error, math.nextafter(end_error, math.inf), 0.0)


def nearest_frame_errors(
    reference: list[float], observed: list[float], *, tolerance: float = 0.0, end: float = math.inf
) -> tuple[list[float], list[int]]:
    """Match display intervals, allowing repeated source indices inside VFR gaps."""
    errors: list[float] = []
    matches: list[int] = []
    for timestamp in observed:
        index = bisect_right(reference, timestamp + tolerance) - 1
        if index < 0:
            return [math.inf], matches
        errors.append(on_screen_error(reference, index, timestamp, end))
        matches.append(index)
    return errors, matches


def one_second_window_counts(times: list[float], end: float) -> list[int]:
    exact_times = [Fraction(str(timestamp)) for timestamp in times]
    video_end = Fraction(str(end))
    start_min, start_max = exact_times[0], video_end - 1
    if start_max < start_min:
        return []
    starts = {start_min, start_max}
    epsilon = Fraction(1, 1_000_000_000_000)
    for timestamp in exact_times:
        for candidate in (timestamp, timestamp - 1):
            if start_min <= candidate <= start_max:
                for adjusted in (candidate - epsilon, candidate, candidate + epsilon):
                    if start_min <= adjusted <= start_max:
                        starts.add(adjusted)
    return [
        bisect_left(exact_times, start + 1) - bisect_left(exact_times, start) for start in starts
    ]


def subsequence_errors(reference: list[float], observed: list[float]) -> list[float]:
    errors: list[float] = []
    cursor = 0
    for timestamp in observed:
        index = bisect_left(reference, timestamp, lo=cursor)
        candidates = [i for i in (index - 1, index) if cursor <= i < len(reference)]
        if not candidates:
            return [math.inf]
        best = min(candidates, key=lambda i: abs(reference[i] - timestamp))
        errors.append(abs(reference[best] - timestamp))
        cursor = best + 1
    return errors


def keyframe_values(
    source: Media, output: Media, path: Path, settings: dict[str, object]
) -> dict[str, object]:
    keys = sorted(finite(p.get("pts_time")) for p in output.packets if "K" in str(p.get("flags")))
    interval = finite(settings["keyframe_interval_seconds"])
    allowance = longest_gap(source) if settings["drop_repeated_frames"] else interval * 0.1
    gaps = [b - a for a, b in zip(keys, [*keys[1:], output.end], strict=False)]
    headers = random_access(path, str(output.video.get("codec_name")), len(keys))
    maximum = max(gaps, default=math.inf)
    return headers | {
        "keyframe_count": len(keys),
        "max_gap_seconds": maximum if math.isfinite(maximum) else None,
        "allowed_gap_seconds": interval + allowance,
        "valid": bool(keys)
        and abs(keys[0] - output.times[0]) <= 0.0020001
        and maximum <= interval + allowance + 0.0000001
        and headers["random_access_valid"] is True,
    }
