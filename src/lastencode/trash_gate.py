"""Conservative original retention rules and cleanup of owned previous outputs."""

from pathlib import Path
from typing import cast

from lastencode.conflicts import output_tag
from lastencode.dates import text_ns
from lastencode.errors import MissingTool
from lastencode.fast_check import TEXT_SUBTITLES, fast_check, verdict
from lastencode.identity import sha256
from lastencode.probe import light_probe, object_dict, stream_list
from lastencode.resume import owned_output
from lastencode.trash import move


def changed_source(record: dict[str, object]) -> bool:
    source = Path(str(record["source_path"]))
    before = source.stat()
    if (before.st_size, before.st_mtime_ns) != (
        record["source_size_bytes"],
        text_ns(record["source_mtime"]),
    ):
        return True
    digest = sha256(source)
    after = source.stat()
    return digest != record.get("source_sha256") or (
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)


def refresh_recovered(record: dict[str, object], output: Path) -> bool:
    # Keep the probed operation through recovery, so repeated-frame checks use the
    # preset's actual frame policy. An inherited source codec can identify a no-gain copy.
    check_record = dict(record)
    info = object_dict(record.get("probe"))
    output_info = light_probe(output)
    action = record.get("verification_action", "encode")
    expected_codec = (
        "hevc" if object_dict(record.get("settings")).get("encoder") == "libx265" else "av1"
    )
    if action == "encode" and output_info.get("video_codec") != expected_codec:
        action = "no-gain"
    check_record["action"] = action
    passed = fast_check(output, check_record)
    for key in ("checks", "check_time_seconds", "failing_check", "dropped_frame_share"):
        if key in check_record:
            record[key] = check_record[key]
    record["dropped_streams"] = missing_streams(info, output_info)
    return passed


def keep_reason(record: dict[str, object]) -> str | None:
    if record.get("status") != "completed":
        return "output did not pass"
    if record.get("probe") is None:
        return "copy-file sources are never trashed"
    output = Path(str(record["output_path"]))
    # A rename would move only a link, leaving the original in place or the output dangling.
    if output.is_symlink() or Path(str(record["source_path"])).is_symlink():
        return "source or output is a symbolic link"
    if not record.get("output_sha256"):
        return "output SHA-256 is unverified"
    source = Path(str(record["source_path"]))
    info = source.stat()
    if (info.st_size, info.st_mtime_ns) != (
        record["source_size_bytes"],
        text_ns(record["source_mtime"]),
    ):
        return "source changed since probing (size or mtime)"
    return recovered_keep_reason(record, output)


def recovered_keep_reason(record: dict[str, object], output: Path) -> str | None:
    if record.get("recovered"):
        if record["output_sha256"] == record.get("source_sha256"):
            return None  # The final fresh hashes must establish ByteCopy, not inherited checks.
        if not refresh_recovered(record, output):
            reason = "recovered output did not pass a fresh fast check"
            record.update(
                status="failed", reason=reason, output_size_bytes=None, output_sha256=None
            )
            return reason
    return stream_keep_reason(record)


def verify_trash_identity(record: dict[str, object]) -> None:
    output = Path(str(record["output_path"]))
    output_hash = sha256(output)
    if changed_source(record):
        raise ValueError("source changed before trash move (size, mtime or SHA-256)")
    if output_hash != record["output_sha256"]:
        raise ValueError("output SHA-256 changed before trash move")
    if record.get("recovered"):
        verify_recovered(record, output_hash)
    if reason := stream_keep_reason(record):
        raise ValueError(reason)


def verify_recovered(record: dict[str, object], output_hash: str) -> None:
    if output_hash == record["source_sha256"]:
        record.update(
            checks=[verdict("ByteCopy", True, "source and output SHA-256 match this run")],
            check_time_seconds=0.0,
            dropped_streams=[],
            dropped_frame_share=0.0,
            failing_check=None,
        )


def stream_key(stream: dict[str, object]) -> tuple[object, object]:
    kind, codec = stream.get("codec_type"), stream.get("codec_name")
    if kind in ("video", "audio") or (kind == "subtitle" and codec in TEXT_SUBTITLES):
        return kind, None
    return kind, codec


def missing_streams(
    source: dict[str, object], output: dict[str, object]
) -> list[dict[str, object]]:
    available = [stream_key(s) for s in stream_list(output.get("streams"))]
    missing: list[dict[str, object]] = []
    for stream in stream_list(source.get("streams")):
        key = stream_key(stream)
        if key in available:
            available.remove(key)
        else:
            missing.append(
                {
                    "source_stream_index": stream.get("index"),
                    "type": stream.get("codec_type"),
                    "codec": stream.get("codec_name"),
                    "codec_tag": stream.get("codec_tag_string"),
                    "reason": "absent from recovered output",
                }
            )
    return missing


def stream_keep_reason(record: dict[str, object]) -> str | None:
    checks = stream_list(record.get("checks"))
    if not checks or any(check.get("passed") is not True for check in checks):
        return "output lacks passing checks"
    for stream in stream_list(record.get("dropped_streams")):
        if stream.get("type") not in ("data", "timecode"):
            return f"output lacks source stream: {stream}"
    return None


def trash_original(record: dict[str, object], *, allowed_paths: set[str] | None = None) -> None:
    try:
        reason = keep_reason(record)
        if (
            reason is None
            and allowed_paths is not None
            and str(record["source_path"]) not in allowed_paths
        ):
            reason = "source excluded by consent preview planning conflicts"
        if reason is None:
            move(
                Path(str(record["source_path"])),
                before_move=lambda: verify_trash_identity(record),
                on_moved=lambda path: record_move(record, "trash_outcome", path),
            )
            return
    except ValueError as error:
        reason = str(error)
    except (OSError, MissingTool) as error:
        reason = f"trash unavailable; original kept: {error}"
    record["trash_outcome"] = {"status": "kept", "path": None, "reason": reason}
    if reason and reason.startswith(
        ("trash unavailable", "source changed", "output lacks source stream")
    ):
        cast(list[str], record["warnings"]).append(f"{record['source_path']}: {reason}")


def trash_previous(
    record: dict[str, object],
    previous: dict[str, object] | None,
    output_root: Path,
    *,
    enabled: bool = True,
    allowed_paths: set[str] | None = None,
) -> None:
    if previous is None or record.get("status") != "completed":
        return
    path = Path(str(previous.get("output_path")))
    if str(path) == record["output_path"] or not path.exists():
        return
    if not enabled:
        reason = f"previous output kept because --trash-originals was not given: {path}"
        record["previous_output_trash"] = {"status": "kept", "path": None, "reason": reason}
        cast(list[str], record["warnings"]).append(reason)
        return
    if allowed_paths is not None and str(path) not in allowed_paths:
        record["previous_output_trash"] = {
            "status": "kept",
            "path": None,
            "reason": "previous output absent from consent preview",
        }
        return
    try:
        verify_previous_owner(path, record, previous, output_root)
        size = path.stat().st_size
        move(path, on_moved=lambda dest: record_move(record, "previous_output_trash", dest, size))
    except ValueError as error:
        record["previous_output_trash"] = {"status": "kept", "path": None, "reason": str(error)}
    except (OSError, MissingTool) as error:
        reason = f"trash unavailable for previous output {path}: {error}"
        record["previous_output_trash"] = {"status": "kept", "path": None, "reason": reason}
        cast(list[str], record["warnings"]).append(reason)


def record_move(
    record: dict[str, object], key: str, destination: Path, size: int | None = None
) -> None:
    outcome: dict[str, object] = {"status": "trashed", "path": str(destination), "reason": None}
    if size is not None:
        outcome["size_bytes"] = size
    record[key] = outcome


def verify_previous_owner(
    path: Path, record: dict[str, object], previous: dict[str, object], output_root: Path
) -> None:
    if not path.resolve().is_relative_to(output_root.resolve()) or path.is_symlink():
        raise ValueError(f"previous output outside the mirror or a symlink: {path}")
    identity = output_tag(path)
    owned = owned_output(path, previous) or (
        identity is not None and identity.get("source_sha256") == record.get("source_sha256")
    )
    if not owned:
        raise ValueError(f"previous output is not owned by this source: {path}")
