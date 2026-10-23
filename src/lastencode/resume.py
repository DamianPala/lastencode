"""Conservative manifest skips and hash-backed recovery from planned output paths."""

import os
from pathlib import Path
from typing import cast

from lastencode.conflicts import output_tag, tag_conflict
from lastencode.dates import text_ns
from lastencode.encoding import byte_copy_requirements, work_path
from lastencode.identity import hash_source, sha256, tag_payload
from lastencode.platform_io import same_file_time, unique_paths, unlink_retry

IDENTITY_FIELDS = ("settings_fingerprint", "source_size_bytes")


def planned_paths(record: dict[str, object]) -> set[Path]:
    return {Path(str(record[key])) for key in ("output_path", "no_gain_path")}


def clean_leftovers(record: dict[str, object]) -> None:
    for output in planned_paths(record):
        work = work_path(output)
        paths = (
            work,
            Path(str(work) + "_exiftool_tmp"),
            work.with_name(f"{work.stem}.faststart{work.suffix}"),
        )
        for path in paths:
            if os.path.lexists(path):
                # Interrupted work names belong to the pipeline, never follow a symlink.
                unlink_retry(path)


def manifest_skip(record: dict[str, object], previous: dict[str, object]) -> bool:
    if previous.get("status") != "completed":
        return False
    if not previous.get("source_sha256") or not previous.get("output_sha256"):
        return False
    if not same_mtime(record, previous) or any(
        record.get(key) != previous.get(key) for key in IDENTITY_FIELDS
    ):
        return False
    output = Path(str(previous.get("output_path")))
    if output not in planned_paths(record) or not output.is_file():
        return False
    if output.stat().st_size != previous.get("output_size_bytes"):
        return False
    for key in (
        "source_sha256",
        "output_sha256",
        "output_size_bytes",
        "output_path",
        "checks",
        "dropped_frame_share",
        "dropped_streams",
        "gps_present",
        "recovered",
        "date_source",
        "audio_decisions",
        "ffmpeg_version",
        "encoder_version",
    ):
        record[key] = previous.get(key)
    if previous.get("verification_action") is not None:
        record["verification_action"] = previous["verification_action"]
    record.update(action="skip", status="completed")
    return True


def matching_tag(output: Path, record: dict[str, object]) -> bool:
    identity = output_tag(output)
    if identity is None:
        return False
    # Tool upgrades alone do not invalidate an otherwise matching fingerprint.
    expected = tag_payload(record)
    return same_mtime(identity, expected) and all(
        identity.get(key) == expected[key] for key in (*IDENTITY_FIELDS, "source_sha256")
    )


def same_mtime(left: dict[str, object], right: dict[str, object]) -> bool:
    try:
        return text_ns(left.get("source_mtime")) == text_ns(right.get("source_mtime"))
    except ValueError:
        return False


def matches_copy(output: Path, record: dict[str, object]) -> bool:
    if not output.is_file() or output.stat().st_size != record["source_size_bytes"]:
        return False
    if sha256(output) != record["source_sha256"]:
        return False
    if not same_file_time(output.stat().st_mtime_ns, text_ns(record["source_mtime"])):
        return False
    if record["action"] == "copy-file":
        return True
    blocker, _ = byte_copy_requirements(record)
    return blocker is None


def recover(record: dict[str, object], candidates: list[Path]) -> bool:
    matches = [
        path
        for path in candidates
        if matches_copy(path, record)
        or (record["action"] != "copy-file" and matching_tag(path, record))
    ]
    if len(matches) > 1:
        fail_conflict(
            record, "conflict: multiple matching outputs: " + ", ".join(map(str, matches))
        )
    if len(matches) != 1:
        return False
    output = matches[0]
    record["verification_action"] = record["action"]
    record.update(
        action="skip",
        status="completed",
        recovered=True,
        output_path=str(output),
        output_size_bytes=output.stat().st_size,
        output_sha256=sha256(output),
        checks=[{"name": "Recovery", "passed": None, "status": "not-rerun", "reason": None}],
        ffmpeg_version=None,
        encoder_version=None,
        date_source=None,
        audio_decisions=None,
        dropped_frame_share=None,
        dropped_streams=None,
        gps_present=None,
    )
    return True


def prepare(record: dict[str, object], previous: dict[str, object] | None, force: bool) -> bool:
    """Return True only when execution is still needed. Hash at most once per source."""
    if not force and protected_conflict(record, previous):
        return False
    candidates = unique_paths(path for path in planned_paths(record) if os.path.lexists(path))
    identities = {path: output_tag(path) for path in candidates} if not force else {}
    if not force and previous is not None:
        expected = {"source_sha256": previous.get("source_sha256")}
        if not foreign_tag(identities, expected) and manifest_skip(record, previous):
            return False
    hash_source(record)
    if record["status"] == "failed":
        return False
    if force or not candidates:
        return True
    return prepare_existing(record, previous, identities)


def prepare_existing(
    record: dict[str, object],
    previous: dict[str, object] | None,
    identities: dict[Path, dict[str, object] | None],
) -> bool:
    candidates = list(identities)
    reason = foreign_tag(identities, {"source_sha256": record["source_sha256"]})
    if reason:
        fail_conflict(record, reason)
        return False
    if previous is None and recover(record, candidates):
        return False
    if record["status"] == "failed":
        return False
    if all(replaceable(path, record, previous, identities[path]) for path in candidates):
        return True
    fail_conflict(
        record,
        "conflict: existing output does not identify this source and settings; "
        "use --force to replace: " + ", ".join(map(str, candidates)),
    )
    return False


def foreign_tag(
    identities: dict[Path, dict[str, object] | None], expected: dict[str, object]
) -> str | None:
    for path, identity in identities.items():
        if identity is not None and (reason := tag_conflict(path, identity, expected)):
            return reason
    return None


def fail_conflict(record: dict[str, object], reason: str) -> None:
    record.update(action="failure", status="failed", failing_check="Conflict", reason=reason)


def replaceable(
    path: Path,
    record: dict[str, object],
    previous: dict[str, object] | None,
    identity: dict[str, object] | None,
) -> bool:
    if identity is not None:
        return identity.get("source_sha256") == record["source_sha256"]
    # Without a manifest, matching copies must also satisfy recovery's metadata rules.
    return previous is not None and (owned_output(path, previous) or copy_of_source(path, record))


def copy_of_source(path: Path, record: dict[str, object]) -> bool:
    # R6a: a byte-identical copy of this source is never foreign, even after a failed line.
    return (
        path.is_file()
        and path.stat().st_size == record["source_size_bytes"]
        and sha256(path) == record["source_sha256"]
    )


def owned_output(path: Path, previous: dict[str, object]) -> bool:
    return (
        str(path) == previous.get("output_path")
        and path.is_file()
        and path.stat().st_size == previous.get("output_size_bytes")
        and sha256(path) == previous.get("output_sha256")
    )


def protected_conflict(record: dict[str, object], previous: dict[str, object] | None) -> bool:
    protected = cast(list[str], previous.get("protected_outputs", [])) if previous else []
    if any(str(path) in protected for path in planned_paths(record)):
        fail_conflict(record, "conflict: output original was trashed; use --force to replace")
        return True
    return False
