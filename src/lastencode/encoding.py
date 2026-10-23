"""Execute planned encodes via a fresh hidden work file and an atomic rename."""

import os
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import cast

from lastencode.audio import audio_arguments
from lastencode.dates import parse_date
from lastencode.encoder_check import rejected_options
from lastencode.errors import MissingTool
from lastencode.fast_check import TEXT_SUBTITLES, fast_check, publish, verdict
from lastencode.identity import hash_source, initialize, sha256, verify_source
from lastencode.metadata import (
    apply_metadata,
    exiftool_tags,
    format_location_tags,
    source_coordinates,
)
from lastencode.platform_io import same_file_time, unlink_retry
from lastencode.probe import object_dict, stream_list
from lastencode.processes import run
from lastencode.video import colour_arguments, video_arguments, video_stream

MP4_MOV_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def stream_arguments(info: dict[str, object]) -> tuple[list[str], list[dict[str, object]]]:
    args = ["-map_chapters", "0"]
    dropped: list[dict[str, object]] = []
    selected = video_stream(info)["index"]
    for stream in stream_list(info["streams"]):
        kind, codec = stream.get("codec_type"), stream.get("codec_name")
        if stream["index"] == selected or kind == "audio":
            continue
        if kind == "subtitle" and codec in TEXT_SUBTITLES:
            args += ["-map", f"0:{stream['index']}"]
        else:
            dropped.append(
                {
                    "source_stream_index": stream["index"],
                    "type": kind,
                    "codec": codec,
                    "codec_tag": stream.get("codec_tag_string"),
                    "tags": object_dict(stream.get("tags")),
                    "reason": "not supported by output stream policy",
                }
            )
    return args + ["-c:s", "mov_text"], dropped


def encoding_command(
    record: dict[str, object], work: Path, *, jobs: int = 1, overwrite: bool = False
) -> list[str]:
    path = Path(str(record["source_path"]))
    info = object_dict(record["probe"])
    settings = object_dict(record["settings"])
    copying = record["action"] == "copy-video"
    audio, decisions = audio_arguments(path, info, settings)
    streams, dropped = stream_arguments(info)
    record.update(audio_decisions=decisions, dropped_streams=dropped)
    raw_frame_rate_cap = record.get("frame_rate_cap")
    frame_rate_cap = raw_frame_rate_cap if type(raw_frame_rate_cap) is int else None
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-y" if overwrite else "-n",
    ]
    if copying:
        command.append("-noautorotate")
    command += ["-i", str(path), "-map_metadata", "0", "-map", f"0:{video_stream(info)['index']}"]
    command += (
        ["-c:v", "copy"] + colour_arguments(video_stream(info), preserve_range=True)
        if copying
        else video_arguments(
            path,
            info,
            settings,
            jobs=jobs,
            frame_rate_cap=frame_rate_cap,
        )
    )
    if copying and info.get("video_codec") == "hevc":
        command += ["-tag:v", "hvc1"]
    command += audio + streams
    video_language = object_dict(video_stream(info).get("tags")).get("language")
    if video_language:
        command += ["-metadata:s:v:0", f"language={video_language}"]
    if not copying:
        command += ["-metadata:s:v:0", "rotate=0"]
    if record.get("recording_date"):
        command += ["-metadata", f"creation_time={record['recording_date']}"]
    if record["location"] == "stripped":
        command += ["-metadata", "location=", "-metadata", "location-eng="]
    return command + ["-movflags", "+faststart", "-write_tmcd", "0", "-f", "mp4", str(work)]


def work_path(output: Path) -> Path:
    return output.with_name(f".{output.stem}.lastencode-part{output.suffix}")


def not_smaller(encoded_size: int, source_size: int) -> bool:
    return encoded_size >= source_size


def reserve_work(work: Path, owned: set[Path]) -> None:
    if os.path.lexists(work):
        raise ValueError(f"Work path already exists: {work}; remove it before retrying")
    owned.add(work)


def publish_video(
    record: dict[str, object],
    work: Path,
    output: Path,
    source_stat: os.stat_result,
    owned: set[Path],
) -> None:
    size = work.stat().st_size
    record["output_sha256"] = sha256(work)
    publish_checked(work, output, source_stat, record)
    owned.discard(work)
    record.update(output_size_bytes=size, output_path=str(output), status="completed")


def remux_no_gain(source: Path, work: Path, record: dict[str, object]) -> str | None:
    # Name the muxer: ffmpeg would pick the restrictive ipod muxer for .m4v and refuse HEVC.
    output_format = "mov" if source.suffix.lower() == ".mov" else "mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-n"]
    command += ["-noautorotate", "-i", str(source), "-map", "0", "-map_metadata", "0"]
    record["dropped_streams"] = []
    if record["location"] == "stripped":
        command += ["-map", "-0:d", "-map", "-0:t"]
        record["dropped_streams"] = location_streams(record)
    command += ["-map_chapters", "0", "-c", "copy", "-movflags", "+faststart"]
    command += colour_arguments(video_stream(object_dict(record["probe"])), preserve_range=True)
    command += ["-metadata", f"creation_time={record['recording_date']}"]
    if record["location"] == "stripped":
        command += ["-metadata", "location=", "-metadata", "location-eng="]
    command += ["-f", output_format, str(work)]
    record["remux_arguments"] = command
    result = run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0 and work.is_file() and work.stat().st_size:
        return None
    unlink_retry(work, missing_ok=True)
    detail = result.stderr.strip().splitlines()
    return "\n".join(detail[-12:]) or f"ffmpeg exited {result.returncode}"


def location_streams(record: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "source_stream_index": stream["index"],
            "type": stream.get("codec_type"),
            "codec": stream.get("codec_name"),
            "codec_tag": stream.get("codec_tag_string"),
            "tags": object_dict(stream.get("tags")),
            "reason": "excluded for location stripping",
        }
        for stream in stream_list(object_dict(record["probe"])["streams"])
        if stream.get("codec_type") in ("data", "attachment")
    ]


def byte_copy_requirements(record: dict[str, object]) -> tuple[str | None, bool]:
    source = Path(str(record["source_path"]))
    tags = exiftool_tags(source) | format_location_tags(source)
    coordinates = source_coordinates(tags)
    # R13b: a byte copy cannot be edited, and absence of GPS is not provable for
    # every container, so a run that must strip location never publishes one.
    if record["location"] == "stripped":
        return "the run must strip source location", coordinates.present
    if record["date_source"] != "creation_time":
        return "the source lacks the required recording creation date", coordinates.present
    expected = parse_date(str(record["recording_date"]))
    actual = parse_date(str(object_dict(record["probe"]).get("creation_time") or ""))
    if actual != expected:
        return "the source lacks the required recording creation date", coordinates.present
    return None, coordinates.present


def publish_byte_copy(
    record: dict[str, object],
    source: Path,
    work: Path,
    output: Path,
    source_stat: os.stat_result,
) -> None:
    blocker, gps_present = byte_copy_requirements(record)
    if blocker:
        raise ValueError(f"no-gain byte copy cannot pass metadata rules: {blocker}")
    shutil.copyfile(source, work)
    source_hash = str(record["source_sha256"])
    output_hash = sha256(work)
    output_size = work.stat().st_size
    if output_size != source_stat.st_size or output_hash != source_hash:
        raise ValueError("no-gain byte copy: output size or SHA-256 does not match source")
    verify_source(record)
    publish(work, output, source_stat)
    record.update(
        source_sha256=source_hash,
        output_sha256=output_hash,
        output_size_bytes=output_size,
        gps_present=gps_present if record["location"] == "kept" else False,
        checks=[verdict("ByteCopy", True, "source and output size and SHA-256 match")],
        dropped_frame_share=0.0,
        dropped_streams=[],
        output_path=str(output),
        status="completed",
    )


def copy_file_source(record: dict[str, object]) -> None:
    source = Path(str(record["source_path"]))
    output = Path(str(record["output_path"]))
    work = work_path(output)
    started = time.monotonic()
    owned: set[Path] = set()
    try:
        source_stat = source.stat()
        output.parent.mkdir(parents=True, exist_ok=True)
        if (
            not record.get("force")
            and output.is_file()
            and output.stat().st_size == source_stat.st_size
        ):
            if same_file_time(output.stat().st_mtime_ns, source_stat.st_mtime_ns):
                record.update(action="skip", output_size_bytes=source_stat.st_size)
                record["output_sha256"] = sha256(output)
                record["checks"] = [verdict("Skip", True, "mirror size and file time match source")]
                record["status"] = "completed"
                return
        reserve_work(work, owned)
        shutil.copyfile(source, work)
        source_hash = str(record["source_sha256"])
        output_hash = sha256(work)
        output_size = work.stat().st_size
        if output_size != source_stat.st_size or output_hash != source_hash:
            raise ValueError("copy-file: output size or SHA-256 does not match source")
        verify_source(record)
        publish(work, output, source_stat)
        owned.discard(work)
        record.update(
            source_sha256=source_hash,
            output_sha256=output_hash,
            output_size_bytes=output_size,
            checks=[verdict("CopyFile", True, "source and output size and SHA-256 match")],
            status="completed",
        )
    except (OSError, ValueError, MissingTool) as error:
        fail_copy_file(record, str(error))
    finally:
        record["encode_time_seconds"] = round(time.monotonic() - started, 6)
        for path in owned:
            unlink_retry(path, missing_ok=True)


def fail_copy_file(record: dict[str, object], reason: str) -> None:
    # R20: every failure names its check; a byte copy has the one CopyFile check (R5a).
    record.update(
        status="failed",
        reason=reason,
        output_size_bytes=None,
        output_sha256=None,
        checks=[verdict("CopyFile", False, reason)],
        failing_check="CopyFile",
    )


def copy_no_gain(
    record: dict[str, object],
    encoded_work: Path,
    source_stat: os.stat_result,
    owned: set[Path],
) -> None:
    source = Path(str(record["source_path"]))
    keep_extension = source.suffix.lower() in MP4_MOV_EXTENSIONS
    remux_output = (
        Path(str(record["no_gain_path"])) if keep_extension else Path(str(record["output_path"]))
    )
    record.update(
        action="no-gain",
        output_path=str(remux_output),
        frame_rate_cap=None,
        frame_rate_change="native (no-gain)",
    )
    record["no_gain_note"] = "Encoded output was not smaller; copying source streams."
    unlink_retry(encoded_work, missing_ok=True)
    owned.discard(encoded_work)
    remux_work = work_path(remux_output)
    reserve_work(remux_work, owned)
    remux_error = remux_no_gain(source, remux_work, record)
    if remux_error is None:
        write_metadata(remux_work, record)
        if not fast_check(remux_work, record):
            record["status"] = "failed"
            return
        publish_video(record, remux_work, remux_output, source_stat, owned)
        return
    unlink_retry(remux_work, missing_ok=True)
    owned.discard(remux_work)
    copy_output = Path(str(record["no_gain_path"]))
    copy_work = work_path(copy_output)
    reserve_work(copy_work, owned)
    record.update(output_path=str(copy_output))
    record["no_gain_note"] = f"MP4 stream copy failed; trying byte copy: {remux_error}"
    try:
        publish_byte_copy(record, source, copy_work, copy_output, source_stat)
    except ValueError as error:
        raise ValueError(f"{error}; stream copy also failed: {remux_error}") from error
    owned.discard(copy_work)


def initialize_source(record: dict[str, object]) -> None:
    initialize(record)
    if not record.get("source_sha256"):
        try:
            hash_source(record)
        except (OSError, ValueError) as error:
            record.update(status="failed", reason=str(error))


def encode_source(record: dict[str, object], *, jobs: int = 1) -> None:
    initialize_source(record)
    if record["status"] == "failed":
        if record["action"] == "copy-file":
            fail_copy_file(record, str(record["reason"]))
        return
    record.update(
        output_size_bytes=None,
        output_sha256=None,
        encode_time_seconds=0.0,
        audio_decisions=[],
        dropped_streams=[],
        checks=[],
        failing_check=None,
        check_time_seconds=0.0,
    )
    if record["action"] == "copy-file":
        copy_file_source(record)
        return
    output = Path(str(record["output_path"]))
    work = work_path(output)
    started = time.monotonic()
    owned: set[Path] = set()
    try:
        source_stat = Path(str(record["source_path"])).stat()
        command = encoding_command(record, work, jobs=jobs)
        output.parent.mkdir(parents=True, exist_ok=True)
        reserve_work(work, owned)
        result = run(command, capture_output=True, text=True, check=False)
        verify_encode(result)
        record["encode_time_seconds"] = round(time.monotonic() - started, 6)
        write_metadata(work, record)
        if not fast_check(work, record):
            record["status"] = "failed"
            return
        encoded_size = work.stat().st_size
        source_size = int(str(record["source_size_bytes"] or source_stat.st_size))
        if not not_smaller(encoded_size, source_size):
            publish_video(record, work, output, source_stat, owned)
            return
        copy_no_gain(record, work, source_stat, owned)
    except (OSError, ValueError, MissingTool) as error:
        record.update(status="failed", reason=str(error))
    finally:
        record["encode_time_seconds"] = record["encode_time_seconds"] or round(
            time.monotonic() - started, 6
        )
        for path in owned:
            unlink_retry(path, missing_ok=True)


def verify_encode(result: subprocess.CompletedProcess[str]) -> None:
    rejected = rejected_options(result.stderr)
    if rejected:
        raise ValueError("Encoder rejected parameters: " + "\n".join(rejected))
    if result.returncode:
        raise ValueError(
            f"ffmpeg exited {result.returncode}: " + "\n".join(result.stderr.splitlines()[-30:])
        )


def write_metadata(work: Path, record: dict[str, object]) -> None:
    try:
        apply_metadata(Path(str(record["source_path"])), work, record)
    except (OSError, ValueError, MissingTool) as error:
        record.update(failing_check="Metadata", checks=[verdict("Metadata", False, str(error))])
        raise ValueError(f"Metadata: {error}") from error


def publish_checked(
    work: Path, output: Path, source_stat: os.stat_result, record: dict[str, object]
) -> None:
    verify_source(record)
    checks = cast(list[dict[str, object]], record["checks"])
    metadata = next(check for check in checks if check["name"] == "Metadata")
    try:
        values = publish(work, output, source_stat)
        cast(dict[str, object], metadata["values"]).update(values)
        metadata["reason"] = "date, GPS and file time verified"
    except (OSError, ValueError) as error:
        metadata.update(passed=False, reason=str(error))
        record["failing_check"] = "Metadata"
        raise ValueError(f"Metadata: publication/file time: {error}") from error


def result_totals(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "trashed_bytes": sum(
            int(str(r.get("source_size_bytes") or 0))
            for r in records
            if object_dict(r.get("trash_outcome")).get("status") == "trashed"
        )
        + sum(
            int(str(object_dict(r.get("previous_output_trash")).get("size_bytes") or 0))
            for r in records
        ),
        "trash_space_note": "Space is freed only when the trash is emptied.",
        "skipped_count": sum(r["action"] == "skip" for r in records),
        "recovered_count": sum(r.get("recovered") is True for r in records),
        "actions": dict(Counter(str(r["action"]) for r in records)),
        "failures": [
            {key: r.get(key) for key in ("source_path", "failing_check", "reason")}
            for r in records
            if r["status"] == "failed"
        ],
        "files": [
            {
                key: r.get(key)
                for key in (
                    "source_path",
                    "action",
                    "settings",
                    "frame_rate_change",
                    "source_size_bytes",
                    "output_size_bytes",
                    "source_sha256",
                    "output_sha256",
                    "video_bitrate_estimated",
                    "location",
                    "date_source",
                    "dropped_frame_share",
                    "audio_decisions",
                    "checks",
                    "failing_check",
                    "status",
                    "trash_outcome",
                    "previous_output_trash",
                    "dropped_streams",
                    "recovered",
                )
            }
            for r in records
        ],
        "output_size_bytes": sum(int(str(r.get("output_size_bytes") or 0)) for r in records),
        "source_size_bytes": sum(int(str(r.get("source_size_bytes") or 0)) for r in records),
        "encode_time_seconds": sum(float(str(r.get("encode_time_seconds", 0))) for r in records),
        "check_time_seconds": sum(float(str(r.get("check_time_seconds", 0))) for r in records),
        "completed_count": sum(r["status"] == "completed" for r in records),
        "dropped_streams": [
            {"source_path": r["source_path"], **stream}
            for r in records
            for stream in cast(list[dict[str, object]], r.get("dropped_streams") or [])
        ],
        "gps_outputs": [
            str(r["output_path"])
            for r in records
            if r.get("status") == "completed" and r.get("gps_present") is True
        ],
    }
