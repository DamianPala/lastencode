"""Configuration-independent introspection, including its own command detail."""

import argparse

from lastencode import __version__
from lastencode.command import Command
from lastencode.contracts import EXIT_CODES, GLOBAL_FLAGS
from lastencode.errors import ERROR_KINDS, InvalidInput

PATH_ARG: dict[str, object] = {
    "name": "path",
    "type": "string",
    "required": False,
    "variadic": True,
    "default": [],
    "description": (
        "Command path segments; omit for the index, use presets, convert or bench for detail."
    ),
}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="*", help=str(PATH_ARG["description"]))


def run(args: argparse.Namespace) -> object:
    # Import at dispatch time to keep command modules independent of registration order.
    from lastencode.registry import COMMANDS

    path: list[str] = args.path
    if path:
        name = " ".join(path)
        if name not in COMMANDS or name == "schema":
            raise InvalidInput(
                f"schema: unknown command path {name!r}; valid values: "
                + ", ".join(n for n in COMMANDS if n != "schema")
            )
        return COMMANDS[name].detail()
    return {
        "schema_version": "1",
        "tool_version": __version__,
        "conformance": {
            "name": "cli-design-standard",
            "standard": "0.2.0-draft.12",
            "extensions": [],
        },
        "global_flags": GLOBAL_FLAGS,
        "format_defaults": {"tty": "text", "non_tty": "json"},
        "exit_codes": EXIT_CODES,
        "error_kinds": {kind: ERROR_KINDS[kind] for kind in sorted(ERROR_KINDS)},
        "commands": [
            {"name": command.name, "description": command.description, "effects": command.effects}
            for name, command in sorted(COMMANDS.items())
            if name != "schema"
        ],
    }


COMMAND = Command(
    name="schema",
    description="Inspect the CLI index or one command contract as JSON, without configuration.",
    configure=configure,
    run=run,
    args=[PATH_ARG],
    flags=[],
    output={},
    output_description=(
        "The result shape depends on path: no path returns the CLI Design Standard D6 index; "
        "a command path returns its D7 detail. The introspection command is excluded from "
        "the index by D6a and is not a valid detail path. Always JSON."
    ),
    format_defaults={"tty": "json", "non_tty": "json"},
)
