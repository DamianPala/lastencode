"""Stable source identity and canonical output settings, shared by records and tags."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from lastencode import __version__
from lastencode.dates import ns_text, text_ns, utc_text
from lastencode.processes import check_cancelled


def now() -> str:
    return utc_text(datetime.now(UTC))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            check_cancelled()
            digest.update(chunk)
        return digest.hexdigest()


def fingerprint(record: dict[str, object]) -> str:
    # Resolved metadata decisions matter too: --tz can change a filename-derived date.
    settings = {
        key: record.get(key) for key in ("settings", "target", "location", "recording_date")
    }
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def initialize(record: dict[str, object]) -> None:
    record.setdefault("settings_fingerprint", fingerprint(record))
    for key in (
        "output_size_bytes",
        "output_sha256",
        "dropped_frame_share",
        "trash_outcome",
        "ffmpeg_version",
        "encoder_version",
        "source_mtime",
        "source_ctime",
    ):
        record.setdefault(key, None)
    record.setdefault("tool_version", __version__)
    record.setdefault("started_at", now())
    record.setdefault("ended_at", None)
    record.setdefault("recovered", False)
    record.setdefault("dropped_streams", [])
    record.setdefault("changed", False)


def hash_source(record: dict[str, object]) -> None:
    source = Path(str(record["source_path"]))
    before = source.stat()
    digest = sha256(source)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError(f"Source changed while hashing: {source}; retry with a stable source")
    if (
        record.get("source_size_bytes") != before.st_size
        or text_ns(record.get("source_mtime")) != before.st_mtime_ns
    ):
        raise ValueError(f"Source changed after planning: {source}; retry")
    record.update(
        source_sha256=digest,
        source_mtime=ns_text(before.st_mtime_ns),
        source_ctime=ns_text(before.st_ctime_ns),
    )


def tag_payload(record: dict[str, object]) -> dict[str, object]:
    return {
        key: record.get(key)
        for key in (
            "tool_version",
            "settings_fingerprint",
            "source_size_bytes",
            "source_mtime",
            "source_sha256",
        )
    }


def verify_source(record: dict[str, object]) -> None:
    source = Path(str(record["source_path"]))
    stat = source.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (
        record["source_size_bytes"],
        text_ns(record["source_mtime"]),
        text_ns(record["source_ctime"]),
    ):
        raise ValueError(f"Source changed during processing: {source}; retry with a stable source")
