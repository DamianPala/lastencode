"""The R18 publication gate: each row yields a reason and measured values."""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lastencode.check_media import Media, finite, frame_values, keyframe_values, longest_gap, scan
from lastencode.colour_check import colour_values, tag_values
from lastencode.dates import ns_text
from lastencode.errors import MissingTool
from lastencode.metadata import (
    exiftool_tags,
    format_location_tags,
    is_faststart,
    source_coordinates,
    verify_metadata,
)
from lastencode.probe import object_dict, stream_list
from lastencode.processes import run

# Shared by the encode mapper and this independent read-back of its result.
TEXT_SUBTITLES = {
    "subrip",
    "srt",
    "ass",
    "ssa",
    "webvtt",
    "mov_text",
    "text",
    "microdvd",
    "subviewer",
    "subviewer1",
    "sami",
    "realtext",
    "jacosub",
    "mpl2",
    "vplayer",
}


@dataclass
class Context:
    work: Path
    record: dict[str, object]
    output: Media | None = None
    source: Media | None = None

    def media(self) -> tuple[Media, Media]:
        if self.source is None:
            self.source = scan(Path(str(self.record["source_path"])))
        if self.output is None:
            self.output = scan(self.work)
        return self.source, self.output

    @property
    def dropping(self) -> bool:
        return self.record["action"] == "encode" and bool(
            object_dict(self.record["settings"])["drop_repeated_frames"]
        )


def verdict(name: str, passed: bool, reason: str, **values: object) -> dict[str, object]:
    return {"name": name, "passed": passed, "reason": reason, "values": values}


def check_probe(context: Context) -> dict[str, object]:
    context.output = scan(context.work)
    video = context.output.video
    return verdict("Probe", True, "ffprobe found video", codec=video.get("codec_name"))


def check_decode(context: Context) -> dict[str, object]:
    result = run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(context.work),
            "-map",
            "0",
            "-c:s",
            "srt",
            # The default 1/frame-rate time base merges close VFR frames and the null muxer
            # then reports non-monotonic dts for a valid file.
            "-enc_time_base",
            "demux",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stderr.strip()
    return verdict(
        "Decode",
        result.returncode == 0 and not lines,
        lines[-2000:] or "full decode without errors",
        exit_code=result.returncode,
        error_lines=len(lines.splitlines()),
    )


def chapter_values(media: Media) -> list[tuple[float, float, dict[str, object]]]:
    return [
        (finite(c.get("start_time")), finite(c.get("end_time")), object_dict(c.get("tags")))
        for c in stream_list(media.document.get("chapters"))
    ]


def check_streams(context: Context) -> dict[str, object]:
    source, output = context.media()
    counts: list[tuple[int, int]] = []
    for kind in ("audio", "subtitle"):
        original = [
            s
            for s in source.streams
            if s.get("codec_type") == kind
            and (kind != "subtitle" or s.get("codec_name") in TEXT_SUBTITLES)
        ]
        actual = [s for s in output.streams if s.get("codec_type") == kind]
        counts.append((len(original), len(actual)))
    original_chapters, actual_chapters = chapter_values(source), chapter_values(output)
    chapters_match = len(original_chapters) == len(actual_chapters) and all(
        abs(a[0] - b[0]) <= 0.002 and abs(a[1] - b[1]) <= 0.002 and a[2] == b[2]
        for a, b in zip(original_chapters, actual_chapters, strict=False)
    )
    return verdict(
        "Streams",
        all(a == b for a, b in counts) and chapters_match,
        f"audio source/output={counts[0]}, text subtitles={counts[1]}, "
        f"chapters match={chapters_match}",
        video_index=output.video["index"],
        audio_counts=counts[0],
        subtitle_counts=counts[1],
        chapter_counts=[len(original_chapters), len(actual_chapters)],
        chapters_match=chapters_match,
    )


def check_frames(context: Context) -> dict[str, object]:
    source, output = context.media()
    raw_frame_rate_cap = context.record.get("frame_rate_cap")
    frame_rate_cap = raw_frame_rate_cap if type(raw_frame_rate_cap) is int else None
    values = frame_values(
        source,
        output,
        context.dropping,
        context.record["action"] == "copy-video",
        cap=frame_rate_cap,
    )
    context.record["dropped_frame_share"] = 1 - len(output.times) / len(source.times)
    return verdict("Frames", values["valid"] is True, "video presentation times compared", **values)


def check_duration(context: Context) -> dict[str, object]:
    source, output = context.media()
    difference = abs(source.duration - output.duration)
    if abs(source.duration - source.end) > 0.5:
        # R35a: a misleading source container duration warns, it cannot veto good video.
        difference = min(difference, abs(source.end - output.end))
    end_shortfall = (source.end - source.times[0]) - (output.end - output.times[0])
    return verdict(
        "Duration",
        difference <= 0.5
        and (not context.dropping or end_shortfall <= longest_gap(source) + 0.0000001),
        "video presentation duration and video end compared",
        difference_seconds=difference,
        video_end_shortfall_seconds=end_shortfall,
        allowed_end_shortfall_seconds=longest_gap(source),
    )


def check_keyframes(context: Context) -> dict[str, object]:
    if context.record["action"] == "copy-video":
        return verdict("Keyframes", True, "copied video keeps source keyframes", applicable=False)
    source, output = context.media()
    values = keyframe_values(source, output, context.work, object_dict(context.record["settings"]))
    return verdict("Keyframes", values["valid"] is True, "random access and GOP spacing", **values)


def check_metadata(context: Context) -> dict[str, object]:
    source = Path(str(context.record["source_path"]))
    tags = exiftool_tags(source)
    coordinates = source_coordinates(tags | format_location_tags(source))
    gps = verify_metadata(
        tags,
        exiftool_tags(context.work),
        object_dict(context.record["probe"]),
        context.work,
        context.record,
        coordinates,
    )
    return verdict(
        "Metadata",
        True,
        "date and GPS read back; file time checked at publication",
        recording_date=context.record["recording_date"],
        gps_present=gps,
    )


def check_layout(context: Context) -> dict[str, object]:
    before = is_faststart(context.work)
    return verdict("Layout", before, "moov must precede mdat", moov_before_mdat=before)


def check_colour_tags(context: Context) -> dict[str, object]:
    _, output = context.media()
    values = tag_values(context.work, context.record, output)
    return verdict("Colour tags", values["valid"] is True, "header and container colours", **values)


def check_colour(context: Context) -> dict[str, object]:
    if context.record["action"] != "encode":
        return verdict("Colour", True, "copied output", applicable=False)
    source, output = context.media()
    raw_cap = context.record.get("frame_rate_cap")
    cap = raw_cap if type(raw_cap) is int else None
    values = colour_values(
        Path(str(context.record["source_path"])), context.work, source, output, cap=cap
    )
    return verdict("Colour", values["valid"] is True, "player RGB channel means", **values)


CHECKS: tuple[Callable[[Context], dict[str, object]], ...] = (
    check_probe,
    check_decode,
    check_streams,
    check_frames,
    check_duration,
    check_keyframes,
    check_colour_tags,
    check_colour,
    check_metadata,
    check_layout,
)


def fast_check(work: Path, record: dict[str, object]) -> bool:
    started = time.monotonic()
    context = Context(work, record)
    results: list[dict[str, object]] = []
    record["checks"] = results
    try:
        checks = CHECKS
        if record.get("action") == "no-gain":
            checks = tuple(check for check in CHECKS if check is not check_keyframes)
        for check in checks:
            try:
                result = check(context)
            except (OSError, ValueError, MissingTool) as error:
                result = verdict(
                    check.__name__.removeprefix("check_").replace("_", " ").capitalize(),
                    False,
                    str(error),
                )
            results.append(result)
            if result["passed"] is False:
                record.update(
                    failing_check=result["name"], reason=f"{result['name']}: {result['reason']}"
                )
                return False
        return True
    finally:
        record["check_time_seconds"] = round(time.monotonic() - started, 6)


def publish(work: Path, output: Path, source_stat: os.stat_result) -> dict[str, object]:
    # Set it before rename as well: SIGKILL immediately after rename still leaves correct mtime.
    os.utime(work, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    expected = source_stat.st_mtime_ns // 1_000_000_000
    if work.stat().st_mtime_ns // 1_000_000_000 != expected:
        raise ValueError("work file time does not match source after setting it")
    os.replace(work, output)
    try:
        os.utime(output, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        actual_ns = output.stat().st_mtime_ns
        if actual_ns // 1_000_000_000 != expected:
            raise ValueError(
                f"file time is {ns_text(actual_ns)}, expected {ns_text(source_stat.st_mtime_ns)}"
            )
    except BaseException:
        os.replace(output, work)
        raise
    return {"file_mtime": ns_text(actual_ns), "source_mtime": ns_text(source_stat.st_mtime_ns)}
