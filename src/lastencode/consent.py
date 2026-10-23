"""Resolve output and trash targets before the single run-level consent gate."""

import os
import sys
from pathlib import Path

from lastencode.conflicts import output_conflict
from lastencode.errors import ConfirmationRequired
from lastencode.manifest import protected_paths
from lastencode.paths import Source
from lastencode.platform_io import unique_paths


def preview(
    records: list[dict[str, object]],
    enabled: bool,
    *,
    previous: dict[str, dict[str, object]] | None = None,
    force: bool = False,
    hash_copies: bool = False,
    manifest: Path | None = None,
) -> dict[str, object]:
    targets: list[dict[str, object]] = []
    protected = protected_paths(previous or {})
    for record in records:
        if record["status"] == "failed":
            continue
        targets.extend(output_targets(record, protected, force=force, hash_copies=hash_copies))
        if enabled and record.get("probe") is not None:
            targets.append(
                target(Path(str(record["source_path"])), "trash")
                | {"size_bytes": record["source_size_bytes"]}
            )
        prior = (previous or {}).get(str(record["source_path"]))
        if enabled and force and prior is not None:
            path = Path(str(prior.get("output_path")))
            alternatives = {str(record["output_path"]), str(record.get("no_gain_path", path))}
            if alternatives != {str(path)} and path.is_file():
                targets.append(target(path, "trash"))
    if manifest is not None:
        targets.append(target(manifest, "append" if manifest.exists() else "create"))
    trash = [t for t in targets if t["effect"] == "trash"]
    # Consume every internal marker before publishing targets, without short-circuiting.
    requires_confirmation = any(
        [bool(t.pop("protected", False)) or t["effect"] == "trash" for t in targets]
    )
    return {
        "targets": targets,
        "requires_confirmation": requires_confirmation,
        "trash_candidate_count": len(trash),
        "trash_candidate_bytes": sum(int(str(t["size_bytes"] or 0)) for t in trash),
    }


def target(path: Path, effect: str) -> dict[str, object]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "effect": effect,
    }


def output_targets(
    record: dict[str, object], protected: list[str], *, force: bool, hash_copies: bool
) -> list[dict[str, object]]:
    if record.get("action") == "skip":
        return []
    source = Path(str(record["source_path"]))
    paths = unique_paths(
        {Path(str(record[key])) for key in ("output_path", "no_gain_path") if key in record}
    )
    targets: list[dict[str, object]] = []
    for path in paths:
        entry = target(path, "replace" if path.exists() else "create")
        if force and record["status"] == "planned" and path.exists():
            candidate = Source(
                source, source.parent, path, path, bool(record.get("next_to_source"))
            )
            entry["protected"] = str(path) in protected or bool(
                output_conflict(candidate, hash_copies=hash_copies)
            )
        targets.append(entry)
    return targets


def confirm(preview: dict[str, object], *, yes: bool, machine: bool) -> None:
    if yes or not preview["requires_confirmation"]:
        return
    message = (
        "Confirm protected replacements and trash moves after verification? "
        f"Trash up to {preview['trash_candidate_count']} files "
        f"({preview['trash_candidate_bytes']} bytes)."
    )
    if machine or os.environ.get("NO_INPUT") or not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ConfirmationRequired(message + " Confirmation requires --yes.")
    print(message + " [y/N] ", end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().strip().lower() not in ("y", "yes"):
        raise ConfirmationRequired("Consent declined; repeat with --yes to confirm.")
