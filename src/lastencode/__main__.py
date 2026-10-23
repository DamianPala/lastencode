"""Argument parsing and stream discipline for the public command line."""

import argparse
import json
import os
import signal
import sys
from collections.abc import Callable, Sequence
from typing import NoReturn

from lastencode import __version__
from lastencode.commands.convert import Plan
from lastencode.contracts import GLOBAL_FLAGS
from lastencode.errors import (
    ERROR_KINDS,
    ConfirmationRequired,
    Conflict,
    InvalidInput,
    Locked,
    MissingTool,
    NotFound,
    UnreadableSource,
)
from lastencode.registry import COMMANDS


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InvalidInput(message)


def add_globals(parser: argparse.ArgumentParser) -> None:
    for descriptor in GLOBAL_FLAGS:
        name = str(descriptor["name"])
        if name == "json":
            parser.add_argument(
                "--json",
                action="store_true",
                default=argparse.SUPPRESS,
                help=str(descriptor["description"]),
            )
        else:
            parser.add_argument(
                "--" + name,
                default=argparse.SUPPRESS,
                metavar="FILE",
                help=str(descriptor["description"]),
            )


def build_parser() -> Parser:
    parser = Parser(
        prog="lastencode",
        allow_abbrev=False,
        description=(
            "Re-encode video recordings into smaller, verified MP4 files: presets lists the "
            "content categories and playback targets, convert converts files or folders into "
            "a mirrored output folder, and bench compares encoding settings on short excerpts."
        ),
        epilog="Introspection: lastencode schema. Command help: lastencode COMMAND --help. "
        "Use --json for programmatic parsing; every command defaults to JSON outside a terminal.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    add_globals(parser)
    parser.set_defaults(json=False, presets=None)
    commands = parser.add_subparsers(dest="command", parser_class=Parser)
    for command in COMMANDS.values():
        child = commands.add_parser(
            command.name,
            description=command.description,
            help=command.description,
            allow_abbrev=False,
        )
        add_globals(child)
        command.configure(child)
    return parser


def reject_repeated_flags(arguments: list[str], command: str) -> None:
    repeatable: set[str] = {"--target", "--quality-settings"} if command == "bench" else set()
    seen: set[str] = set()
    for argument in arguments:
        if argument == "--":
            break
        name = argument.split("=", 1)[0]
        if not name.startswith("--") or name in repeatable:
            continue
        if name in seen:
            message = (
                "format flags are mutually exclusive"
                if name in ("--json", "--format")
                else f"{name}: may only be given once"
            )
            raise InvalidInput(message)
        seen.add(name)


def execute(argv: Sequence[str] | None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Reject singleton repeats even when argparse would first report missing inputs.
    reject_repeated_flags(arguments, "bench")
    args = build_parser().parse_args(arguments)
    reject_repeated_flags(arguments, args.command)
    if args.command is None:
        raise InvalidInput("the following arguments are required: command")
    before_separator = arguments[: arguments.index("--")] if "--" in arguments else arguments
    formats = [
        arg
        for arg in before_separator
        if arg in ("--json", "--format") or arg.startswith("--format=")
    ]
    if len(formats) > 1:
        raise InvalidInput("format flags are mutually exclusive; select one format")
    command = COMMANDS[args.command]
    as_json: bool = args.json
    output_format: str | None = getattr(args, "format", None)
    result = command.run(args)
    defaults = command.format_defaults or {"tty": "text", "non_tty": "json"}
    selected = output_format or (
        "json" if as_json else defaults["tty" if sys.stdout.isatty() else "non_tty"]
    )
    if isinstance(result, Plan):
        for record in result.records():
            write_result(record, selected, command.render_text)
        if result.exit_code:
            return emit_error(
                result.failure_kind,
                "Convert sources: one or more sources could not be processed; see source reasons.",
                "Inspect failed source records and correct their reported causes before retrying.",
            )
        return result.exit_code
    write_result(result, selected, command.render_text)
    return 0


def render_result(result: object, selected: str, text_renderer: Callable[[object], str]) -> str:
    return (
        json.dumps(result, ensure_ascii=True)
        if selected in ("json", "ndjson")
        else text_renderer(result)
    )


def interrupt_run(signum: int, frame: object) -> NoReturn:
    raise KeyboardInterrupt


def emit_error(kind: str, message: str, hint: str | None = None) -> int:
    exit_code = ERROR_KINDS[kind]["exit_code"]
    error = {"kind": kind, "message": message}
    if hint is not None:
        error["hint"] = hint
    print(json.dumps({"error": error}, ensure_ascii=True), file=sys.stderr)
    return exit_code


def write_result(result: object, selected: str, renderer: Callable[[object], str]) -> None:
    rendered = render_result(result, selected, renderer)
    try:
        print(rendered, flush=True)
    except BrokenPipeError:
        # Redirect the descriptor too, so interpreter shutdown cannot flush the dead pipe.
        with open(os.devnull, "w", encoding="utf-8") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        # The caller keeps consuming the stream, persisting work and its summary.


def main(argv: Sequence[str] | None = None) -> int:
    previous = signal.signal(signal.SIGTERM, interrupt_run)
    operation = "lastencode " + " ".join(sys.argv[1:] if argv is None else argv)
    try:
        return execute(argv)
    except ConfirmationRequired as error:
        return emit_error("confirmation_required", str(error), "Repeat with --yes")
    except InvalidInput as error:
        return emit_error("invalid_input", str(error))
    except (Conflict, NotFound, UnreadableSource) as error:
        kind, hint = failure_guidance(error)
        return emit_error(kind, str(error), hint)
    except MissingTool as error:
        return emit_error(
            "missing_tool", str(error), "Install the required tool and capabilities on PATH."
        )
    except KeyboardInterrupt:
        return emit_error(
            "interrupted", f"{operation}: interrupted by SIGINT, SIGTERM or keyboard input."
        )
    except OSError as error:
        return emit_error(
            "io_error", f"{operation}: filesystem or stream operation failed: {error}"
        )
    except Exception as error:
        return emit_error(
            "internal_error", f"{operation}: unexpected {type(error).__name__}: {error}"
        )
    finally:
        signal.signal(signal.SIGTERM, previous)


def failure_guidance(error: Exception) -> tuple[str, str]:
    if isinstance(error, NotFound):
        return "not_found", "Correct the source path or restore the missing file."
    if isinstance(error, UnreadableSource):
        return "unreadable_source", "Repair the source media or select a readable source."
    if isinstance(error, Locked):
        return "conflict", "Wait for the run named in the message to finish, then repeat."
    return "conflict", "Resolve the reported conflict; use --force only for intended replacements."


if __name__ == "__main__":
    raise SystemExit(main())
