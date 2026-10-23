"""Failures shared by the parser and commands."""

from typing import TypedDict


class ErrorKind(TypedDict):
    exit_code: int
    defined_by: str
    meaning: str
    recovery: str


ERROR_KINDS: dict[str, ErrorKind] = {
    "confirmation_required": {
        "exit_code": 1,
        "defined_by": "cli-design-standard",
        "meaning": (
            "The run would replace protected outputs or move originals to the trash, and no "
            "consent was given."
        ),
        "recovery": (
            "Check the preview with --dry-run, then repeat the original command with --yes."
        ),
    },
    "conflict": {
        "exit_code": 1,
        "defined_by": "cli-design-standard",
        "meaning": (
            "Existing state blocks the run: planned outputs already exist, or another run "
            "holds the output folder lock."
        ),
        "recovery": (
            "For a held lock, wait for the run named in the message, then repeat; --force "
            "does not clear it. For existing files, repeat with --force only if replacing "
            "them is intended."
        ),
    },
    "internal_error": {
        "exit_code": 1,
        "defined_by": "lastencode",
        "meaning": (
            "An unexpected exception in lastencode stopped the run; this is a bug, not a "
            "problem with the input."
        ),
        "recovery": (
            "Do not retry with other flags; report the command, `lastencode --version` and "
            "this error."
        ),
    },
    "interrupted": {
        "exit_code": 1,
        "defined_by": "cli-design-standard",
        "meaning": (
            "A signal or keyboard interrupt stopped the run. In convert, finished files "
            "already recorded in the manifest stay verified."
        ),
        "recovery": (
            "Repeat the same command; convert converts only what is missing or failed. For "
            "bench, add --force to replace the partial benchmark."
        ),
    },
    "invalid_input": {
        "exit_code": 2,
        "defined_by": "cli-design-standard",
        "meaning": (
            "An argument, flag value or preset file is invalid, or a bench source has no "
            "positive video duration. Nothing was written."
        ),
        "recovery": (
            "Correct the value or source named in the message; valid values are listed there "
            "or in `lastencode presets`."
        ),
    },
    "io_error": {
        "exit_code": 1,
        "defined_by": "lastencode",
        "meaning": (
            "A filesystem or stream operation failed (disk full, permission, removed device). "
            "The message names the operation and the OS cause."
        ),
        "recovery": "Fix the OS cause, then repeat the same command.",
    },
    "missing_tool": {
        "exit_code": 3,
        "defined_by": "lastencode",
        "meaning": (
            "ffmpeg, ffprobe or exiftool is absent, too old, or lacks a required encoder, "
            "filter or model."
        ),
        "recovery": (
            "Install the tool or build named in the message on PATH; retrying without that "
            "changes nothing."
        ),
    },
    "not_found": {
        "exit_code": 1,
        "defined_by": "cli-design-standard",
        "meaning": "A source path does not exist.",
        "recovery": "Correct the path or restore the file.",
    },
    "sources_failed": {
        "exit_code": 1,
        "defined_by": "lastencode",
        "meaning": (
            "convert finished, but one or more sources failed. Each failure is in its "
            "manifest record and in `failures` on stdout."
        ),
        "recovery": (
            "Read `failing_check` and the message of each failure, fix those sources, then "
            "repeat; passed files are not converted again."
        ),
    },
    "unreadable_source": {
        "exit_code": 1,
        "defined_by": "lastencode",
        "meaning": (
            "ffprobe cannot read a source (damaged or not a video). For a finished convert "
            "run, every failed source has this cause."
        ),
        "recovery": (
            "Repair or replace those sources; repeating the command unchanged fails the same way."
        ),
    },
}


class InvalidInput(ValueError):
    """A locally checkable usage error, before any work starts."""


class MissingTool(RuntimeError):
    """A required tool, supported version or encoder is unavailable."""


class UnreadableSource(ValueError):
    """An installed probe could not read a media source."""


class Conflict(RuntimeError):
    """Authoritative output state conflicts with this run."""


class Locked(Conflict):
    """Another run holds the output-folder lock; --force cannot clear it."""


class ConfirmationRequired(Exception):
    """Caller must explicitly consent before any writes."""


class NotFound(Exception):
    """A source identified by the caller does not exist."""
