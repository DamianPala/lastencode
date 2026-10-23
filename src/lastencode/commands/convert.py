"""Plan and execute mirrored per-source conversions."""

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path
from typing import cast

from lastencode.command import Command
from lastencode.consent import confirm, preview
from lastencode.contracts import FORMAT_FLAG
from lastencode.dates import local_zone
from lastencode.encoder_check import check_record_encoders, probe_encoder
from lastencode.encoding import result_totals
from lastencode.errors import ERROR_KINDS, InvalidInput
from lastencode.identity import fingerprint
from lastencode.jobs import Run
from lastencode.manifest import NAME, append, load, protected_paths
from lastencode.paths import Source, discover
from lastencode.plan_schema import convert_schema
from lastencode.planning import (
    apply_plan_conflict,
    inspect_source,
    plan_source,
    space_summary,
    validate_settings,
)
from lastencode.preset_fields import TARGETS
from lastencode.presets import Category, load_categories
from lastencode.render import safe_text
from lastencode.resume import manifest_skip, protected_conflict
from lastencode.run_lock import RunLock, probe_lock
from lastencode.tools import check_tools
from lastencode.video import encoder_parameters

FLAGS: list[dict[str, object]] = [
    {
        "name": "output-dir",
        "type": "string",
        "required": True,
        "description": "Separate mirror folder; must lie outside every source tree.",
    },
    {
        "name": "category",
        "type": "string",
        "required": True,
        "description": "Content category; list valid names with presets.",
    },
    {
        "name": "target",
        "type": "string",
        "required": False,
        "default": "portable",
        "enum": list(TARGETS),
        "description": "Playback target: portable (default) or desktop.",
    },
    {
        "name": "dry-run",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Print the plan and space estimate; writes nothing anywhere.",
    },
    {
        "name": "tz",
        "type": "string",
        "required": False,
        "description": "IANA zone for file-name dates; default machine zone; earlier DST offset.",
    },
    {
        "name": "strip-location",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Remove GPS location from every output.",
    },
    {
        "name": "jobs",
        "type": "integer",
        "required": False,
        "default": 1,
        "description": "Concurrent sources, positive integer; default 1 limits CPU and memory.",
    },
    {
        "name": "force",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Disable skips and recovery; protected replacements require confirmation. "
        "With --trash-originals, trash previous outputs at other paths after success.",
    },
    {
        "name": "trash-originals",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Move verified video originals to their own mount trash; requires consent.",
    },
    {
        "name": "yes",
        "type": "boolean",
        "required": False,
        "default": False,
        "description": (
            "Confirm protected replacements and trash moves; ignored with "
            "--dry-run. Does not force overwrites."
        ),
    },
    FORMAT_FLAG
    | {
        "enum": ["ndjson", "text"],
        "description": (
            "Select NDJSON or text; conflicts with --json; default text on TTY, NDJSON otherwise."
        ),
    },
]


@dataclass(kw_only=True)
class Plan:
    sources: list[Source]
    category: Category
    target: str
    zone: tzinfo
    output: Path
    ignored: list[str]
    dry_run: bool = True
    strip_location: bool = False
    jobs: int = 1
    force: bool = False
    trash_originals: bool = False
    yes: bool = False
    machine: bool = False
    versions: dict[str, str | None] = field(default_factory=dict[str, str | None])
    exit_code: int = 0
    failure_kind: str = "sources_failed"
    checked_encoders: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])

    def records(self) -> Iterator[dict[str, object]]:
        probe_lock(self.output)
        if self.dry_run:
            records = [
                plan_source(
                    s,
                    self.category,
                    self.target,
                    self.zone,
                    self.strip_location,
                    hash_copies=False,
                    force=self.force,
                )
                for s in self.sources
            ]
            self.apply_protection(records)
            self.apply_skips(records)
            for record in records:
                record["changed"] = False
                yield record
            yield self.summary(records)
            return
        records = [
            inspect_source(s, self.category, self.target, self.zone, self.strip_location)
            for s in self.sources
        ]
        check_record_encoders(records, self.checked_encoders, jobs=self.jobs)
        consent_records = [dict(record) for record in records]
        for record, source in zip(consent_records, self.sources, strict=True):
            apply_plan_conflict(record, source, hash_copies=False, force=self.force)
        self.apply_protection(consent_records)
        consent_preview = self.trash_preview(consent_records)
        confirm(consent_preview, yes=self.yes, machine=self.machine)
        trash_targets = {
            str(target["path"])
            for target in cast(list[dict[str, object]], consent_preview["targets"])
            if target["effect"] == "trash"
        }
        with RunLock(self.output):
            runner = Run(
                self.output,
                self.jobs,
                self.force,
                self.versions,
                trash_originals=self.trash_originals,
                trash_targets=trash_targets,
            )
            finished = list[dict[str, object]]()
            for record in runner.records(records):
                finished.append(record)
                yield record
            summary = self.summary(finished)
            summary["changed"] = runner.changed
            append(self.output, summary)
            yield summary

    def apply_skips(self, records: list[dict[str, object]]) -> None:
        if self.force:
            return
        previous = load(self.output)
        for record in records:
            prior = previous.get(str(record["source_path"]))
            if record["status"] != "failed" and prior is not None:
                record["settings_fingerprint"] = fingerprint(record)
                manifest_skip(record, prior)

    def apply_protection(self, records: list[dict[str, object]]) -> None:
        if not self.force:
            protected: dict[str, object] = {"protected_outputs": protected_paths(load(self.output))}
            for record in records:
                protected_conflict(record, protected)

    def trash_preview(self, records: list[dict[str, object]]) -> dict[str, object]:
        return preview(
            records,
            self.trash_originals,
            previous=load(self.output),
            force=self.force,
            hash_copies=not self.dry_run,
            manifest=self.output / NAME,
        )

    def summary(self, records: list[dict[str, object]]) -> dict[str, object]:
        summary = space_summary(records, self.output, self.ignored)
        if not self.dry_run:
            summary.update(result_totals(records))
        space_failures = [r for r in records if r.get("failing_check") == "Space"]
        if space_failures:
            summary.update(
                space_needed_bytes=space_failures[0]["space_needed_bytes"],
                space_available_bytes=space_failures[0]["space_available_bytes"],
                space_sufficient=False,
            )
        trash_preview = self.trash_preview(records)
        if not self.dry_run:
            trash_preview.pop("requires_confirmation")
            trash_preview.pop("targets")
        summary.update(trash_preview)
        summary["changed"] = False
        failures = [r for r in records if r["status"] == "failed"]
        if failures and all(r.get("failing_check") == "SourceRead" for r in failures):
            self.failure_kind = "unreadable_source"
        self.exit_code = (
            ERROR_KINDS[self.failure_kind]["exit_code"]
            if not self.dry_run and summary["failed_count"]
            else 0
        )
        for warning in cast(list[str], summary["warnings"]):
            print(safe_text(warning), file=sys.stderr)
        return summary


def configure(parser: argparse.ArgumentParser) -> None:
    # Validate category before missing paths so R33 gives useful recovery values.
    parser.usage = "%(prog)s --category CATEGORY --output-dir DIR [options] SOURCE [SOURCE ...]"
    parser.add_argument("sources", nargs="*", metavar="SOURCE", help="Files or recursive folders.")
    for flag in FLAGS:
        name = str(flag["name"])
        if flag["type"] == "boolean":
            parser.add_argument("--" + name, action="store_true", help=str(flag["description"]))
        elif name == "format":
            parser.add_argument(
                "--format", choices=["ndjson", "text"], help=str(flag["description"])
            )
        else:
            parser.add_argument(
                "--" + name, default=flag.get("default"), help=str(flag["description"])
            )


def run(args: argparse.Namespace) -> Plan:
    categories = {category.name: category for category in load_categories(args.presets)}
    if args.category not in categories:
        option = "missing --category" if args.category is None else f"--category {args.category!r}"
        raise InvalidInput(f"{option}: valid categories: {', '.join(categories)}")
    if args.target not in TARGETS:
        raise InvalidInput(f"--target {args.target!r}: valid targets: {', '.join(TARGETS)}")
    if not args.output_dir or not args.sources:
        missing = " and ".join(
            name
            for name, value in (("SOURCE...", args.sources), ("--output-dir DIR", args.output_dir))
            if not value
        )
        raise InvalidInput(f"convert requires {missing}")
    try:
        jobs = int(args.jobs)
    except (ValueError, TypeError) as error:
        raise InvalidInput("--jobs requires a positive integer") from error
    if jobs < 1:
        raise InvalidInput("--jobs requires a positive integer")
    zone = local_zone(args.tz)
    category = categories[args.category]
    validate_settings(category, args.target)
    versions = check_tools(category.settings[args.target])
    settings: dict[str, object] = {
        key: value.value for key, value in category.settings[args.target].items()
    }
    checked: set[tuple[str, str]] = set()
    encoder_version = probe_encoder(
        settings, encoder_parameters(Path("."), {}, settings, jobs=jobs), checked
    )
    output = Path(args.output_dir).absolute()
    sources, ignored = discover(args.sources, output)
    return Plan(
        sources=sources,
        category=category,
        target=args.target,
        zone=zone,
        output=output,
        ignored=ignored,
        dry_run=args.dry_run,
        strip_location=args.strip_location,
        checked_encoders=checked,
        jobs=jobs,
        force=args.force,
        trash_originals=args.trash_originals,
        yes=args.yes,
        machine=args.json or args.format == "ndjson",
        versions={"ffmpeg_version": versions["ffmpeg"], "encoder_version": encoder_version},
    )


def render_text(document: object) -> str:
    record = cast(dict[str, object], document)
    if record["record_type"] == "summary":
        return "Summary: " + safe_text(json.dumps(record))
    lines = [f"{record['action']}: {safe_text(record['source_path'])}"]
    for key in (
        "output_path",
        "no_gain_path",
        "recording_date",
        "date_source",
        "location",
        "gps_present",
        "settings",
        "frame_rate_change",
        "video_copy_reason",
        "reason",
        "no_gain_note",
        "warnings",
        "status",
        "audio_decisions",
        "dropped_streams",
        "source_size_bytes",
        "output_size_bytes",
        "source_sha256",
        "output_sha256",
        "video_bitrate_estimated",
        "encode_time_seconds",
        "check_time_seconds",
        "dropped_frame_share",
        "checks",
        "failing_check",
        "trash_outcome",
        "previous_output_trash",
    ):
        lines.append(f"  {key}: {safe_text(record.get(key))}")
    return "\n".join(lines)


COMMAND = Command(
    name="convert",
    description="Encode a mirrored conversion, or inspect its plan with --dry-run.",
    configure=configure,
    run=run,
    args=[
        {
            "name": "sources",
            "type": "string",
            "required": True,
            "variadic": True,
            "description": "Files or recursively discovered folders, including hidden entries.",
        }
    ],
    flags=FLAGS,
    output=convert_schema(),
    output_description=(
        "Finite NDJSON stream: exactly one record per discovered file plus one summary. "
        "Order: input argument order then sorted paths, for any --jobs. "
        "Summary last. "
        "Paths are absolute. Source records contain per-file fields; summary holds totals. "
        "A failed source has status=failed and reason; action identifies the attempted operation. "
        "Other sources continue. "
        "Any failed source in a real run makes exit 1 with error kind unreadable_source "
        "for unreadable media only, "
        "otherwise sources_failed; "
        "dry-run succeeds with planned failures retained in source records. "
        "source_mtime and source_ctime, and the file_mtime and source_mtime values of the "
        "Metadata check, are RFC 3339 UTC with nanosecond fractions; "
        "probe.first_frame holds decoded picture facts and duration_seconds, "
        "no ffprobe tick counts; "
        "recording_date is ISO 8601 UTC; location is kept or stripped; "
        "the summary lists outputs carrying GPS and counts ignored system clutter; "
        "sizes are bytes; source_sha256 and output_sha256 are SHA-256 digests when defined. "
        "Frame-rate mode comes from packet presentation times when the preset caps fps "
        "or drops repeated frames; otherwise it is unknown. "
        "no_gain_path reserves the original extension; output_path reserves MP4. "
        "Protected replacements with --force and --trash-originals ask "
        "once on stdin with a stderr TTY prompt before encoding; "
        "--json, --format ndjson, non-TTY stdin or NO_INPUT require --yes. "
        "Trash uses same-mount rename; space is freed only after emptying trash. "
        "--force with --trash-originals trashes an owned previous output at a different "
        "path after success; without --trash-originals the previous output stays. "
        "Dry-run targets list create, replace, trash and manifest append paths, "
        "including possible no-gain paths; skips have no output targets. "
        "Dry runs write no files. Encodes and stream copies check a hidden work file before "
        "atomic replacement; byte copies verify equal hashes; "
        "a failed check deletes it. The manifest appends even skips and failures, "
        "plus the final summary. "
        "The lock uses flock; unsupported locking fails closed with io_error (exit 1). "
        "An active run causes conflict (exit 1), naming host, PID and UTC start. "
        "Planning probes have a 60-second timeout; encodes and checks have no timeout or retry."
    ),
    render_text=render_text,
    effects="non_idempotent",
    confirm=True,
    stream=True,
    exit_codes={
        "0": "Every source passed or was skipped, or dry-run planning completed.",
        "1": "A source failed, or conversion failed or was interrupted.",
    },
)
