"""Resolve tools from PATH, independently of a child's working directory."""

import os
import shutil
from functools import cache

from lastencode.errors import MissingTool


@cache
def resolve_tool(name: str, path: str, pathext: str) -> str:
    # Include the search environment in the cache: tests and callers may change PATH.
    # An absolute candidate prevents Windows which() from prepending the current folder.
    for folder in path.split(os.pathsep):
        if not folder:
            continue
        candidate = os.path.join(os.path.abspath(folder.strip('"')), name)
        resolved = shutil.which(candidate, path="")
        if resolved is not None:
            return os.path.abspath(resolved)
    raise MissingTool(f"{name}: required on PATH")


def find_tool(name: str) -> str | None:
    try:
        return resolve_tool(name, os.environ.get("PATH", ""), os.environ.get("PATHEXT", ""))
    except MissingTool:
        return None


def resolved_command(command: list[str]) -> list[str]:
    if command[0] not in ("ffmpeg", "ffprobe", "exiftool"):
        return command
    executable = resolve_tool(command[0], os.environ.get("PATH", ""), os.environ.get("PATHEXT", ""))
    return [executable, *command[1:]]
