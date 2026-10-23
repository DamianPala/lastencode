"""Timestamp-preserving video filters and closed-GOP encoder arguments."""

import os
from fractions import Fraction
from pathlib import Path

from lastencode.probe import COLOUR_KEYS, object_dict, stream_list

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def video_stream(info: dict[str, object]) -> dict[str, object]:
    stream = next(
        s
        for s in stream_list(info["streams"])
        if s.get("codec_type") == "video"
        and not object_dict(s.get("disposition")).get("attached_pic")
    )

    return (
        stream
        | {key: info[key] for key in COLOUR_KEYS if key in info}
        | {
            "packet_frame_rate": info.get("packet_frame_rate"),
            "decoded_side_data": object_dict(info.get("first_frame")).get("side_data_list"),
        }
    )


def mastering_display(side: dict[str, object], encoder: str) -> str:
    def units(key: str, scale: int) -> int | str:
        value = Fraction(str(side[key]))
        return round(value * scale) if encoder == "libx265" else f"{float(value):.8f}"

    parts: list[str] = []
    for label, prefix in (("G", "green"), ("B", "blue"), ("R", "red"), ("WP", "white_point")):
        parts.append(f"{label}({units(prefix + '_x', 50000)},{units(prefix + '_y', 50000)})")
    parts.append(f"L({units('max_luminance', 10000)},{units('min_luminance', 10000)})")
    return "".join(parts)


def hdr_parameters(side_data: list[dict[str, object]], encoder: str) -> list[str]:
    params: list[str] = []
    for side in side_data:
        kind = side.get("side_data_type")
        if kind == "Mastering display metadata":
            name = "master-display" if encoder == "libx265" else "mastering-display"
            params.append(f"{name}={mastering_display(side, encoder)}")
        elif kind == "Content light level metadata":
            name = "max-cll" if encoder == "libx265" else "content-light"
            params.append(f"{name}={side['max_content']},{side['max_average']}")
    return params


def source_fps(video: dict[str, object]) -> Fraction:
    try:
        rate = Fraction(str(video.get("packet_frame_rate", "0")))
        if rate > 0:
            return rate
    except (ValueError, ZeroDivisionError):
        pass
    raise ValueError("Cannot bound repeated-frame dropping: source packet frame rate is unknown")


def video_filters(
    video: dict[str, object],
    settings: dict[str, object],
    frame_rate_cap: int | None = None,
) -> str:
    filters: list[str] = []
    if frame_rate_cap is not None:
        filters.append(f"fps={frame_rate_cap}:round=near")
    if settings["drop_repeated_frames"]:
        fps = frame_rate_cap or round(source_fps(video))
        if fps > 1:
            filters.append(f"mpdecimate=max={fps - 1}")
    limit = int(str(settings["scale_short_side"]))
    factor = f"min(1,{limit}/min(iw,ih))" if limit else "1"
    source_range = "full" if video.get("color_range") == "pc" else "limited"
    filters.append(
        f"scale=w='max(2,trunc(iw*{factor}/2)*2)':"
        f"h='max(2,trunc(ih*{factor}/2)*2)':flags=bicubic:"
        f"in_range={source_range}:out_range=limited"
    )
    filters.append("format=" + ("yuv420p10le" if settings["bit_depth"] == 10 else "yuv420p"))
    # Autorotation consumes the display matrix; explicitly remove any frame-level remnant.
    filters.append("sidedata=mode=delete:type=DISPLAYMATRIX")
    tags = colour_arguments(video)
    names = {
        "-color_range": "range",
        "-color_primaries": "color_primaries",
        "-color_trc": "color_trc",
        "-colorspace": "colorspace",
    }
    filters.append(
        "setparams="
        + ":".join(
            f"{names[option]}={value}" for option, value in zip(tags[::2], tags[1::2], strict=True)
        )
    )
    return ",".join(filters)


def colour_arguments(video: dict[str, object], *, preserve_range: bool = False) -> list[str]:
    full = preserve_range and video.get("color_range") == "pc"
    args = ["-color_range", "pc" if full else "tv"]
    for key, option in (
        ("color_primaries", "-color_primaries"),
        ("color_transfer", "-color_trc"),
        ("color_space", "-colorspace"),
    ):
        value = video.get(key)
        if value and value not in ("unknown", "reserved", "unspecified"):
            args += [option, str(value)]
    return args


def video_arguments(
    path: Path,
    info: dict[str, object],
    settings: dict[str, object],
    *,
    frame_rate_cap: int | None = None,
    jobs: int = 1,
) -> list[str]:
    video = video_stream(info)
    encoder = str(settings["encoder"])
    interval = settings["keyframe_interval_seconds"]
    args = [
        "-c:v",
        encoder,
        "-preset",
        str(settings["speed_preset"]),
        "-crf",
        str(settings["quality_crf"]),
        "-vf",
        video_filters(video, settings, frame_rate_cap),
        "-fps_mode",
        "passthrough",
        "-enc_time_base",
        "demux",
        "-force_key_frames",
        f"expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{interval}))",
        "-g",
        "2147483647",
    ]
    if encoder == "libx265":
        args += ["-forced-idr", "1", "-tag:v", "hvc1"]
    args += [
        "-x265-params" if encoder == "libx265" else "-svtav1-params",
        encoder_parameters(path, video, settings, jobs=jobs),
    ]
    return args + colour_arguments(video)


def encoder_parameters(
    path: Path, video: dict[str, object], settings: dict[str, object], *, jobs: int = 1
) -> str:
    encoder = str(settings["encoder"])
    params = [str(settings["extra_encoder_params"])]
    if settings["deblocking"] != "default":
        params.append("deblock=" + str(settings["deblocking"]))
    if encoder == "libx265":
        params += [
            "open-gop=0",
            "range=limited",
            f"pools={max(1, hardware_threads() // jobs)}",
            "frame-threads=2",
        ]
        params += x265_colour(video)
    else:
        # No lp: SVT-AV1 >= 2.3 maps it to a 0-6 parallelism level, so lp=12 meant maximum
        # parallelism (+0.6 GB RSS at 1080p, identical output), not a 12-core cap.
        params += ["irefresh-type=2"]
    if video.get("color_transfer") in HDR_TRANSFERS:
        try:
            params += hdr_parameters(stream_list(video.get("decoded_side_data")), encoder)
        except (KeyError, ValueError, ZeroDivisionError) as error:
            raise ValueError(f"Malformed HDR metadata in {path}: {error}") from error
    return ":".join(p for p in params if p)


def x265_colour(video: dict[str, object]) -> list[str]:
    params: list[str] = []
    for key, name in (
        ("color_primaries", "colorprim"),
        ("color_transfer", "transfer"),
        ("color_space", "colormatrix"),
    ):
        value = video.get(key)
        if value and value not in ("unknown", "reserved", "unspecified"):
            params.append(f"{name}={value}")
    return params


def hardware_threads() -> int:
    """Respect the CPU affinity available to this process."""
    getter = getattr(os, "sched_getaffinity", None)
    return max(1, len(getter(0)) if getter else (os.cpu_count() or 1))
