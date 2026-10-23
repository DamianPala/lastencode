"""Read-only external tool checks and bounded subprocess execution."""

import re
import subprocess

from lastencode.errors import MissingTool, UnreadableSource
from lastencode.executables import find_tool
from lastencode.presets import Setting
from lastencode.processes import run


def capture(command: list[str]) -> str:
    try:
        result = run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MissingTool(f"{command[0]}: {error}") from error
    if result.returncode:
        cause = result.stderr.strip() or "command failed"
        if command[0] == "ffprobe" and "-version" not in command:
            raise UnreadableSource(f"Read media {command[-1]} with ffprobe: {cause}")
        raise MissingTool(f"Run {' '.join(command[:2])}: {cause}")
    return result.stdout


def supported_version(line: str) -> bool:
    match = re.search(r"version\s+n?(\d+)\.(\d+)", line, re.IGNORECASE)
    # Unnumbered development builds cannot prove the minimum version.
    return bool(match and tuple(map(int, match.groups())) >= (9, 0))


def check_tools(settings: dict[str, Setting]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("ffmpeg", "ffprobe"):
        if find_tool(name) is None:
            raise MissingTool(f"{name}: required on PATH (minimum version 9.0)")
        lines = capture([name, "-version"]).splitlines()
        line = lines[0] if lines else "(empty version output)"
        if not supported_version(line):
            raise MissingTool(f"{name}: need a numbered version >= 9.0; found {line}")
        versions[name] = line
    check_ffmpeg_capabilities(settings)
    if find_tool("exiftool") is None:
        raise MissingTool("exiftool: required on PATH")
    versions["exiftool"] = capture(["exiftool", "-ver"]).strip()
    check_exiftool_version(versions["exiftool"])
    return versions


def check_ffmpeg_capabilities(settings: dict[str, Setting]) -> None:
    encoders = capture(["ffmpeg", "-hide_banner", "-encoders"])
    available = {parts[1] for line in encoders.splitlines() if len(parts := line.split()) >= 2}
    audio = "libopus" if settings["audio_codec"].value == "opus" else "aac"
    for encoder in (str(settings["encoder"].value), audio):
        if encoder not in available:
            raise MissingTool(f"ffmpeg: required encoder {encoder} is missing")
    filters = capture(["ffmpeg", "-hide_banner", "-filters"])
    available_filters = {
        parts[1] for line in filters.splitlines() if len(parts := line.split()) >= 2
    }
    if "zscale" not in available_filters:
        raise MissingTool(
            "ffmpeg: required filter zscale is missing; install a build with zimg "
            "(on macOS: brew install ffmpeg-full and put its bin directory first on PATH)"
        )


def check_exiftool_version(exif_version: str) -> None:
    match = re.fullmatch(r"(\d+)\.(\d+)", exif_version)
    if not match or tuple(map(int, match.groups())) < (13, 43):
        raise MissingTool(
            f"exiftool: need version >= 13.43 to preserve Android capture tags; "
            f"found {exif_version}; install the Perl distribution from https://exiftool.org/"
        )
