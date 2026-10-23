"""Detect encoder options that ffmpeg otherwise silently ignores."""

import re
import subprocess
from pathlib import Path

from lastencode.errors import MissingTool
from lastencode.executables import resolved_command
from lastencode.probe import object_dict
from lastencode.video import encoder_parameters, video_stream

REJECTION = re.compile(
    r"error parsing option|invalid value for|unknown option|unrecognized (?:option|parameter)"
    r"|(?:invalid|unsupported|unknown) parameter|failed to (?:parse|set) (?:option|parameter)",
    re.IGNORECASE,
)


def rejected_options(stderr: str) -> list[str]:
    return [line.strip() for line in stderr.splitlines() if REJECTION.search(line)]


def probe_encoder(
    settings: dict[str, object], params: str, checked: set[tuple[str, str]]
) -> str | None:
    encoder = str(settings["encoder"])
    pair = (encoder, params)
    if pair in checked:
        return
    option = "-x265-params" if encoder == "libx265" else "-svtav1-params"
    # Info level: ffmpeg 9 lets libx265 print its version line only at info or above.
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostats",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=s=128x128:r=1:d=1",
        "-frames:v",
        "1",
        "-c:v",
        encoder,
        "-preset",
        str(settings["speed_preset"]),
        "-crf",
        str(settings["quality_crf"]),
        "-pix_fmt",
        "yuv420p10le" if settings["bit_depth"] == 10 else "yuv420p",
        option,
        params,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            resolved_command(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MissingTool(f"{encoder}: parameter probe failed: {error}") from error
    rejected = rejected_options(result.stderr)
    if rejected or result.returncode:
        version = next(
            (
                line.strip()
                for line in result.stderr.splitlines()
                if re.search(r"SVT.*(?:version|Encoder Lib)|x265.*version", line, re.IGNORECASE)
            ),
            "library version unavailable",
        )
        detail = "\n".join(rejected or result.stderr.splitlines()[-15:])
        raise MissingTool(
            f"{encoder} ({version}): rejected encoder parameters: {detail}; "
            "install an ffmpeg whose encoder accepts these parameters"
        )
    checked.add(pair)
    return next(
        (
            line.strip()
            for line in result.stderr.splitlines()
            if re.search(r"SVT.*(?:version|Encoder Lib)|x265.*version", line, re.IGNORECASE)
        ),
        None,
    )


def check_record_encoders(
    records: list[dict[str, object]], checked: set[tuple[str, str]], *, jobs: int = 1
) -> None:
    # Prepare all source-dependent strings before any source can create an output.
    for record in records:
        if record["status"] == "failed" or record["action"] != "encode":
            continue
        info, settings = object_dict(record["probe"]), object_dict(record["settings"])
        try:
            params = encoder_parameters(
                Path(str(record["source_path"])), video_stream(info), settings, jobs=jobs
            )
        except (ValueError, MissingTool) as error:
            record.update(status="failed", reason=str(error))
            continue
        probe_encoder(settings, params, checked)
