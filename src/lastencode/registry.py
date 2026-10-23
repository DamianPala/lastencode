"""Add a command module and its COMMAND here to extend the CLI."""

from lastencode.commands.bench import COMMAND as BENCH
from lastencode.commands.convert import COMMAND as CONVERT
from lastencode.commands.presets import COMMAND as PRESETS
from lastencode.commands.schema import COMMAND as SCHEMA

COMMANDS = {command.name: command for command in (SCHEMA, PRESETS, CONVERT, BENCH)}
