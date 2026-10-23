"""Resolve tools from PATH, independently of a child's working directory."""

import os
import shutil
from functools import cache

from lastencode.errors import MissingTool


@cache
def resolve_tool(name: str, path: str, pathext: str) -> str:
    # Include the search environment in the cache: tests and callers may change PATH.
    resolved = shutil.which(name, path=path)
    if resolved is None:
        raise MissingTool(f"{name}: required on PATH")
    return os.path.abspath(resolved)


def resolved_command(command: list[str]) -> list[str]:
    if command[0] not in ("ffmpeg", "ffprobe", "exiftool"):
        return command
    executable = resolve_tool(command[0], os.environ.get("PATH", ""), os.environ.get("PATHEXT", ""))
    return [executable, *command[1:]]
