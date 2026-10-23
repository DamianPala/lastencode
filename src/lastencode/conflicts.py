"""Read-only protection for pre-existing outputs (no manifest recovery or skips)."""

import hashlib
import json
from pathlib import Path

from lastencode.dates import ns_text
from lastencode.errors import MissingTool
from lastencode.identity import sha256
from lastencode.paths import Source
from lastencode.probe import object_dict, stream_list
from lastencode.tools import capture


def same_bytes(source: Path, output: Path) -> bool:
    if not output.is_file() or source.stat().st_size != output.stat().st_size:
        return False
    with source.open("rb") as original, output.open("rb") as mirror:
        return (
            hashlib.file_digest(original, "sha256").digest()
            == hashlib.file_digest(mirror, "sha256").digest()
        )


def matching_copy_stat(source: Path, output: Path) -> bool:
    if not output.is_file():
        return False
    source_stat, output_stat = source.stat(), output.stat()
    return (
        source_stat.st_size == output_stat.st_size
        and source_stat.st_mtime_ns == output_stat.st_mtime_ns
    )


def output_tag(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        raw: object = json.loads(capture(["exiftool", "-j", "-LastEncode", str(path)]))
        entries = stream_list(raw)
        value = entries[0].get("LastEncode") if entries else None
        return object_dict(json.loads(value)) if isinstance(value, str) else None
    except (MissingTool, ValueError):
        return None


def tag_conflict(
    path: Path, identity: dict[str, object], expected: dict[str, object]
) -> str | None:
    if any(identity.get(key) != value for key, value in expected.items()):
        return (
            f"conflict: existing output {path} has a lastencode tag belonging to another source; "
            "use --force to replace"
        )
    return None


def planned_copy_matches(source: Source, candidate: Path, hash_copies: bool) -> bool:
    if (
        not source.is_video or (not hash_copies and candidate == source.no_gain)
    ) and matching_copy_stat(source.path, candidate):
        return True
    if not hash_copies and not source.is_video and candidate.is_file():
        # A dry plan cannot establish byte identity without reading the source.
        return source.path.stat().st_size == candidate.stat().st_size
    return hash_copies and candidate == source.no_gain and same_bytes(source.path, candidate)


def output_conflict(source: Source, *, hash_copies: bool = True) -> str | None:
    for candidate in sorted({source.output, source.no_gain}):
        if not candidate.exists():
            continue
        identity = output_tag(candidate)
        if identity is not None:
            stat = source.path.stat()
            expected: dict[str, object] = {
                "source_size_bytes": stat.st_size,
                "source_mtime": ns_text(stat.st_mtime_ns),
            }
            if hash_copies:
                expected = {"source_sha256": sha256(source.path)}
            reason = tag_conflict(candidate, identity, expected)
            if reason:
                return reason
        elif not planned_copy_matches(source, candidate, hash_copies):
            return f"conflict: existing output {candidate} has no lastencode tag or matching copy"
    return None
