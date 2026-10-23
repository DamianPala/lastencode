"""Read-only conversion decisions and disk-space estimates."""

import shutil
import sys
from collections import Counter
from datetime import tzinfo
from pathlib import Path
from typing import cast

from lastencode.conflicts import output_conflict
from lastencode.dates import ns_text, recording_date
from lastencode.errors import InvalidInput, MissingTool, UnreadableSource
from lastencode.paths import Source, is_system_clutter
from lastencode.preset_fields import SPEED_PRESETS
from lastencode.presets import Category, Setting
from lastencode.probe import keys_creation_date, number, object_dict, probe, validate_picture


def validate_settings(category: Category, target: str) -> None:
    settings = category.settings[target]
    x265 = settings["encoder"].value == "libx265"
    speeds = SPEED_PRESETS[:10] if x265 else tuple(str(n) for n in range(14))
    crf = settings["quality_crf"].value
    checks = {
        "speed_preset": settings["speed_preset"].value in speeds,
        "quality_crf": isinstance(crf, int) and (0 if x265 else 1) <= crf <= (51 if x265 else 63),
    }
    for key, valid in checks.items():
        if not valid:
            raise InvalidInput(
                f"{category.name}.{target}.{key}={settings[key].value!r}: "
                f"invalid for encoder {settings['encoder'].value}"
            )


def copy_video(
    info: dict[str, object],
    settings: dict[str, Setting],
    *,
    above_frame_rate_cap: bool = False,
) -> bool:
    threshold = settings["copy_video_below_bps"].value
    bitrate = number(info.get("video_bitrate_bps"))
    eligible = (
        info.get("video_codec") in ("h264", "hevc")
        and isinstance(threshold, int)
        and bitrate is not None
        and bitrate < threshold
    )
    if above_frame_rate_cap:
        return False
    return eligible


def estimate_video_bitrate(info: dict[str, object], size_bytes: int) -> bool:
    if info.get("video_bitrate_bps") is not None:
        return False
    duration = number(info.get("duration_seconds"))
    if duration is None or duration <= 0:
        return False
    audio_bytes = sum(
        (bitrate or 0) * duration / 8
        for stream in cast(list[dict[str, object]], info.get("audio_streams", []))
        if (bitrate := number(stream.get("bit_rate"))) is not None
    )
    info["video_bitrate_bps"] = max(0, (size_bytes - audio_bytes) * 8 / duration)
    info["video_bitrate_estimated"] = True
    return True


def base_record(source: Source, category: Category, target: str) -> dict[str, object]:
    settings = category.settings[target]
    return {
        "record_type": "source",
        "next_to_source": source.next_to_source,
        "source_path": str(source.path),
        "output_path": str(source.output),
        "no_gain_path": str(source.no_gain),
        "category": category.name,
        "target": target,
        "settings": {key: value.value for key, value in settings.items()}
        | {"location": category.location.value},
        "warnings": [],
        "action": "copy-file",
        "status": "planned",
        "reason": None,
        "checks": [],
        "failing_check": None,
        "source_size_bytes": None,
        "source_sha256": None,
        "output_sha256": None,
        "video_bitrate_estimated": False,
        "frame_rate_cap": None,
        "frame_rate_change": None,
        "video_copy_reason": None,
        "source_mtime": None,
        "recording_date": None,
        "date_source": None,
        "location": None,
        "gps_present": None,
        "probe": None,
        "no_gain_note": None,
        "output_upper_bound_bytes": 0,
    }


def inspect_source(
    source: Source,
    category: Category,
    target: str,
    zone: tzinfo,
    strip_location: bool = False,
) -> dict[str, object]:
    record = base_record(source, category, target)
    record["location"] = (
        "stripped" if strip_location or category.location.value == "strip" else "kept"
    )
    try:
        validate_path_length(source)
        stat = source.path.stat()
        record.update(
            source_size_bytes=stat.st_size,
            source_mtime=ns_text(stat.st_mtime_ns),
            source_ctime=ns_text(stat.st_ctime_ns),
            output_upper_bound_bytes=stat.st_size,
        )
        if not source.is_video:
            record["output_path"] = str(source.no_gain)
            date, date_source = recording_date(None, None, source.path.name, stat.st_mtime, zone)
            record.update(recording_date=date, date_source=date_source)
            return record
        frame_rate_setting = category.settings[target]["max_frame_rate"].value
        needs_times = type(frame_rate_setting) is int or bool(
            category.settings[target]["drop_repeated_frames"].value
        )
        info = probe(source.path, packet_times=needs_times)
        validate_picture(object_dict(info.get("first_frame")))
        cast(list[str], record["warnings"]).extend(cast(list[str], info["warnings"]))
        frame_rate_cap = (
            frame_rate_setting
            if type(frame_rate_setting) is int
            and int(str(info["maximum_window_frames"])) > frame_rate_setting + 1
            else None
        )
        above_cap = frame_rate_cap is not None
        record["video_bitrate_estimated"] = estimate_video_bitrate(info, stat.st_size)
        keys_date = keys_creation_date(source.path)
        date, date_source = recording_date(
            str(info["creation_time"]) if info["creation_time"] else None,
            keys_date,
            source.path.name,
            stat.st_mtime,
            zone,
        )
        info["keys_creation_date"] = keys_date
        record.update(
            probe=info,
            recording_date=date,
            date_source=date_source,
            frame_rate_cap=frame_rate_cap,
            frame_rate_change=(
                frame_rate_change(info, int(frame_rate_cap)) if above_cap else "native"
            ),
            video_copy_reason=(
                f"Source exceeds the {frame_rate_cap} fps cap; video will be encoded."
                if above_cap
                else None
            ),
            action="copy-video"
            if copy_video(
                info,
                category.settings[target],
                above_frame_rate_cap=above_cap,
            )
            else "encode",
        )
        record["no_gain_note"] = no_gain_note(record, info)
    except (OSError, MissingTool, ValueError) as error:
        record.update(
            action="failure",
            status="failed",
            reason=str(error),
            output_upper_bound_bytes=0,
            failing_check="SourceRead" if isinstance(error, UnreadableSource) else None,
        )
    return record


def frame_rate_change(info: dict[str, object], cap: int) -> str:
    rate = float(str(info["packet_frame_rate"]))
    value = f"{rate:.2f}".rstrip("0").rstrip(".")
    return f"{value} → {cap} fps"


def no_gain_note(record: dict[str, object], info: dict[str, object]) -> str | None:
    if record.get("next_to_source"):
        return "If the output is not smaller, skip with reason no-gain; no copy is written."
    bitrate = number(info.get("video_bitrate_bps"))
    if record["action"] != "encode" or (bitrate is not None and bitrate > 2_000_000):
        return None
    return (
        "May not shrink (video bitrate <= 2000000 bps or unknown); fallback: "
        "MP4/MOV keep original extension, other containers remux to MP4 if possible, "
        "otherwise byte-copy under original extension (subject to metadata requirements)."
    )


def space_summary(
    records: list[dict[str, object]], output: Path, ignored: list[str]
) -> dict[str, object]:
    sizes = [int(str(record["source_size_bytes"] or 0)) for record in records]
    upper_bounds = [int(str(record["output_upper_bound_bytes"])) for record in records]
    required = sum(upper_bounds) + 2 * max(sizes, default=0)
    mount_path = output
    while not mount_path.exists():
        parent = mount_path.parent
        if parent == mount_path:
            raise InvalidInput(f"output drive or share not available: {output}")
        mount_path = parent
    free = shutil.disk_usage(mount_path).free
    warnings = sorted(
        {str(warning) for record in records for warning in cast(list[str], record["warnings"])}
    )
    return {
        "record_type": "summary",
        "source_count": len(records),
        "actions": dict(Counter(str(record["action"]) for record in records)),
        "failed_count": sum(record["status"] == "failed" for record in records),
        "ignored_paths": ignored,
        "system_clutter_count": sum(is_system_clutter(Path(path)) for path in ignored),
        "warnings": warnings,
        "space_needed_bytes": required,
        "space_available_bytes": free,
        "space_sufficient": free >= required,
        "space_checked_path": str(mount_path),
    }


def plan_source(
    source: Source,
    category: Category,
    target: str,
    zone: tzinfo,
    strip_location: bool = False,
    *,
    hash_copies: bool = True,
    force: bool = False,
) -> dict[str, object]:
    record = inspect_source(source, category, target, zone, strip_location)
    apply_plan_conflict(record, source, hash_copies=hash_copies, force=force)
    return record


def apply_plan_conflict(
    record: dict[str, object], source: Source, *, hash_copies: bool, force: bool
) -> None:
    if record["status"] == "failed" or force:
        return
    try:
        reason = output_conflict(source, hash_copies=hash_copies)
    except OSError as error:
        reason = str(error)
    if reason:
        record.update(action="failure", status="failed", reason=reason, output_upper_bound_bytes=0)


def validate_path_length(source: Source) -> None:
    if sys.platform != "win32":
        return
    # Local import avoids the encoding -> metadata -> planning dependency chain.
    from lastencode.encoding import work_path

    derived = [str(source.path)]
    for output in (source.output, source.no_gain):
        work = work_path(output)
        derived.extend(
            (
                str(output),
                str(work) + "_exiftool_tmp",
                str(work.with_name(f"{work.stem}.faststart{work.suffix}")),
            )
        )
    longest = max(map(len, derived))
    if longest > 259:
        raise ValueError(f"Windows derived path length {longest} exceeds the 259 character limit")
