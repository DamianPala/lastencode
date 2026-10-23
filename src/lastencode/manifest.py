"""Append whole NDJSON records; tolerate only an interrupted final append on reading."""

import json
import os
from pathlib import Path
from typing import cast

from lastencode.conflicts import output_tag
from lastencode.errors import Conflict
from lastencode.platform_io import open_control, read_at
from lastencode.probe import object_dict

NAME = "lastencode-manifest.jsonl"


def load(output: Path) -> dict[str, dict[str, object]]:
    path = output / NAME
    if not path.exists():
        return {}
    records: dict[str, dict[str, object]] = {}
    fd = open_control(path, os.O_RDONLY)
    with os.fdopen(fd, "rb") as stream:
        for number, line in enumerate(stream, 1):
            # A hard kill can tear the last write. Never trust its partial identity.
            if not line.endswith(b"\n"):
                break
            record = read_record(line, path, number)
            if record is None:
                continue
            source = str(record["source_path"])
            # Verification uses only the last line; trash protection survives later failures.
            prior = records.get(source, {})
            protected = list(cast(list[str], prior.get("protected_outputs", [])))
            outcome = object_dict(record.get("trash_outcome"))
            output_path = str(record.get("output_path"))
            if output_path in protected and restored_identity(record):
                protected.remove(output_path)
            if outcome.get("status") == "trashed":
                protected.append(str(record.get("output_path")))
            record["protected_outputs"] = sorted(set(protected))
            records[source] = record
    return records


def read_record(line: bytes, path: Path, number: int) -> dict[str, object] | None:
    try:
        record = object_dict(json.loads(line))
        if record.get("record_type") == "summary":
            return None
        if not isinstance(record["source_path"], str):
            raise ValueError("source_path must be a string")
        return record
    except (ValueError, KeyError) as error:
        raise Conflict(f"Invalid manifest {path}, line {number}: {error}") from error


def append(output: Path, record: dict[str, object]) -> None:
    path = output / NAME
    fd = open_control(path, os.O_CREAT | os.O_RDWR | os.O_APPEND)
    try:
        # Remove only a torn suffix before appending, under the directory lock.
        size = os.fstat(fd).st_size
        end = size
        while end and read_at(fd, 1, end - 1) != b"\n":
            end -= 1
        if end != size:
            os.ftruncate(fd, end)
        line = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        if os.write(fd, line) != len(line):
            raise OSError(f"Short manifest write: {path}; stop and retry")
        os.fsync(fd)
    finally:
        os.close(fd)


def protected_paths(previous: dict[str, dict[str, object]]) -> list[str]:
    return sorted(
        {
            path
            for record in previous.values()
            for path in cast(list[str], record.get("protected_outputs", []))
        }
    )


def restored_identity(record: dict[str, object]) -> bool:
    """Only a later completed result for this source can release its own protection."""
    if record.get("status") != "completed" or not record.get("source_sha256"):
        return False
    output = Path(str(record.get("output_path")))
    try:
        tag = output_tag(output)
        if tag is not None:
            return tag.get("source_sha256") == record["source_sha256"]
        # A completed line already records the verified byte-copy hash. Reading it
        # here preserves hash-free dry runs and avoids rescanning historical copies.
        return output.is_file() and record.get("output_sha256") == record["source_sha256"]
    except OSError:
        return False
