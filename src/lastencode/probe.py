"""Header, decoded picture and optional packet reads with separate costs."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

from lastencode.errors import MissingTool, UnreadableSource
from lastencode.tools import capture

if TYPE_CHECKING:
    from lastencode.check_media import Media


def object_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def stream_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [object_dict(item) for item in cast(list[object], value)]


def number(value: object) -> float | None:
    try:
        result = float(str(value))
        return result if result >= 0 and result < float("inf") else None
    except ValueError:
        return None


def bit_depth(video: dict[str, object]) -> int | None:
    explicit = number(video.get("bits_per_raw_sample"))
    if explicit:
        return int(explicit)
    pixel = str(video.get("pix_fmt", ""))
    match = re.search(r"(?:p|gray|gbrp)(9|10|12|14|16)", pixel)
    if match:
        return int(match[1])
    if pixel.startswith(("yuv", "nv12", "nv21", "rgb24", "bgr24", "gbrp", "gray")):
        return 8
    return None


COLOUR_KEYS = ("color_range", "color_primaries", "color_transfer", "color_space")
UNKNOWN = (None, "unknown", "unspecified", "reserved")
# One packet decodes a file that starts on a keyframe; the wider reads cover cut GOPs.
FIRST_FRAME_PACKETS = (1, 64, 1024)
# Decoded first-frame facts the planner and checks read; published under probe.first_frame.
FRAME_KEYS = (
    "interlaced_frame",
    "field_order",
    "sample_aspect_ratio",
    *COLOUR_KEYS,
    "side_data_list",
)


def decoded_frames(path: Path, packets: int) -> list[dict[str, object]]:
    document = object_dict(
        json.loads(
            capture(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-read_intervals",
                    f"%+#{packets}",
                    "-show_frames",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )
    )
    return stream_list(document.get("frames"))


def first_frame(path: Path) -> dict[str, object]:
    # A stream-copied cut can open with packets the decoder drops: frames before the edit
    # list's start, or leading B frames. Widen the read until one decodes.
    frames: list[dict[str, object]] = []
    for packets in FIRST_FRAME_PACKETS:
        frames = decoded_frames(path, packets)
        if frames:
            break
    if not frames:
        raise UnreadableSource(
            f"Read media {path}: ffprobe found no decoded video frame "
            f"in the first {FIRST_FRAME_PACKETS[-1]} packets"
        )
    frame = frames[0]
    # ffprobe's pts, dts and duration count time-base ticks; keep the picture facts and seconds.
    return {key: frame[key] for key in FRAME_KEYS if key in frame} | {
        "duration_seconds": number(frame.get("duration_time"))
    }


def colour_description(frame: dict[str, object], stream: dict[str, object]) -> dict[str, object]:
    return {
        key: frame.get(key) if frame.get(key) not in UNKNOWN else stream.get(key)
        for key in COLOUR_KEYS
    }


def validate_picture(frame: dict[str, object]) -> None:
    if frame.get("interlaced_frame") == 1:
        raise ValueError("Unsupported source: interlaced_frame=1")
    order = frame.get("field_order")
    if order not in (None, "unknown", "progressive"):
        raise ValueError(f"Unsupported source: field_order={order}")
    sar = frame.get("sample_aspect_ratio")
    if sar not in (None, "0:1", "1:1"):
        raise ValueError(f"Unsupported source: sample_aspect_ratio={sar}")


def light_probe(path: Path) -> dict[str, object]:
    document = object_dict(
        json.loads(
            capture(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )
    )
    streams = stream_list(document.get("streams"))
    videos = [
        s
        for s in streams
        if s.get("codec_type") == "video"
        and not object_dict(s.get("disposition")).get("attached_pic")
    ]
    if not videos:
        raise UnreadableSource(f"Read media {path}: ffprobe found no video stream")
    video = videos[0]
    format_info = object_dict(document.get("format"))
    tags = object_dict(video.get("tags")) | object_dict(format_info.get("tags"))
    rotations = [s["rotation"] for s in stream_list(video.get("side_data_list")) if "rotation" in s]
    return {
        "container": format_info.get("format_name"),
        "video_codec": video.get("codec_name"),
        "bit_depth": bit_depth(video),
        "pixel_format": video.get("pix_fmt"),
        **{key: video.get(key) for key in COLOUR_KEYS},
        "first_frame": {},
        "warnings": [],
        "packet_frame_rate": None,
        "maximum_window_frames": None,
        "video_end_seconds": None,
        "container_start_seconds": number(format_info.get("start_time")) or 0.0,
        "rotation": number_rotation(rotations[0] if rotations else tags.get("rotate", 0)),
        "frame_rate_mode": "unknown",
        "avg_frame_rate": video.get("avg_frame_rate"),
        "r_frame_rate": video.get("r_frame_rate"),
        "video_bitrate_bps": number(video.get("bit_rate")),
        "video_bitrate_estimated": False,
        "duration_seconds": number(format_info.get("duration")),
        "creation_time": tags.get("creation_time"),
        "audio_streams": [s for s in streams if s.get("codec_type") == "audio"],
        "subtitle_streams": [s for s in streams if s.get("codec_type") == "subtitle"],
        "data_streams": [s for s in streams if s.get("codec_type") == "data"],
        "streams": streams,
    }


def read_picture(path: Path, info: dict[str, object]) -> None:
    video = next(
        s
        for s in stream_list(info["streams"])
        if s.get("codec_type") == "video"
        and not object_dict(s.get("disposition")).get("attached_pic")
    )
    frame = first_frame(path)
    description = colour_description(frame, video)
    warnings = [
        f"{key}: container={video.get(key)}, video={description[key]}"
        for key in COLOUR_KEYS
        if video.get(key) not in UNKNOWN and video.get(key) != description[key]
    ]
    info.update(description)
    info.update(first_frame=frame, warnings=warnings)


def packet_facts(info: dict[str, object], times: list[float]) -> None:
    from lastencode.check_media import maximum_window_frames

    rate = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 1.0
    info.update(
        packet_frame_rate=str(rate),
        maximum_window_frames=maximum_window_frames(times),
        frame_rate_mode=frame_rate_mode(times),
    )


def tail_start(info: dict[str, object]) -> float:
    video = next(s for s in stream_list(info["streams"]) if s.get("codec_type") == "video")
    duration = number(video.get("duration"))
    if duration is None:
        parts = str(object_dict(video.get("tags")).get("DURATION", "")).split(":")
        if len(parts) == 3:
            duration = sum(
                float(value) * factor for value, factor in zip(parts, (3600, 60, 1), strict=True)
            )
    duration = duration or number(info.get("duration_seconds")) or 0.0
    return max(0.0, float(str(info["container_start_seconds"])) + duration - 10.0)


def tail_scan(path: Path, info: dict[str, object]) -> "Media":
    from lastencode.check_media import scan

    media = scan(path, read_intervals=f"{tail_start(info):.6f}%")
    # ffprobe on Windows now and then returns no packets for an interval read (about 1 in
    # 100 on CI), with exit 0 and no message; a full read gives the same end exactly.
    return media if media.packets else scan(path)


def probe(path: Path, *, packet_times: bool = False) -> dict[str, object]:
    from lastencode.check_media import scan

    info = light_probe(path)
    read_picture(path, info)
    media = scan(path) if packet_times else tail_scan(path, info)
    if packet_times:
        packet_facts(info, media.times)
    warnings = cast(list[str], info["warnings"])
    # Preserve the reviewer's correction: format.duration excludes the TS start offset.
    video_end = media.end - float(str(info["container_start_seconds"]))
    container_duration = number(info.get("duration_seconds"))
    if container_duration is not None and abs(container_duration - video_end) > 0.5:
        warnings.append(f"duration: container={container_duration}, video packet end={video_end}")
    info["video_end_seconds"] = media.end
    return info


def frame_rate_mode(times: list[float]) -> str:
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    if not gaps:
        return "unknown"
    return "variable" if max(gaps) - min(gaps) > 0.00001 else "constant"


def keys_creation_date(path: Path) -> str | None:
    try:
        raw: object = json.loads(
            capture(["exiftool", "-j", "-G1", "-Keys:CreationDate", str(path)])
        )
        entries = stream_list(raw)
        value = entries[0].get("Keys:CreationDate") if entries else None
        return str(value) if value else None
    except (MissingTool, ValueError):
        return None


def number_rotation(value: object) -> float:
    try:
        return float(str(value))
    except ValueError:
        return 0
