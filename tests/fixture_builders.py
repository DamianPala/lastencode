"""Builders for generated test media and command stubs."""

from __future__ import annotations

import subprocess
from pathlib import Path

PHONE_CREATION_DATE = "2026:09:15 12:30:12Z"
PHONE_GPS = "+37.7749-122.4194+15.0/"
STILL_TIMES = (3, 10, 17.4, 31, 52)
SIXTY_FPS_TIMES = (3, 10.4, 17)


def build_phone_clip(directory: Path) -> Path:
    """Build the synthetic 20-second variable-frame-rate phone clip."""
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / "phone-clip.mp4"
    unrotated_path = directory / "phone-clip-unrotated.mp4"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30:duration=20",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=20",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            "select='not(eq(mod(n,29),28))',format=yuvj420p",
            "-fps_mode:v:0",
            "passthrough",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-x264-params",
            "colorprim=bt470bg:transfer=smpte170m:colormatrix=bt470bg:range=full",
            "-b:v",
            "7M",
            "-maxrate",
            "7M",
            "-bufsize",
            "14M",
            "-pix_fmt",
            "yuvj420p",
            "-color_range",
            "pc",
            "-color_primaries",
            "bt470bg",
            "-color_trc",
            "smpte170m",
            "-colorspace",
            "bt470bg",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-t",
            "20",
            "-movflags",
            "+faststart",
            str(unrotated_path),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-display_rotation:v:0",
            "-90",
            "-i",
            str(unrotated_path),
            "-map",
            "0",
            "-c",
            "copy",
            "-color_primaries",
            "bt2020",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt2020nc",
            "-color_range",
            "tv",
            str(output_path),
        ]
    )
    unrotated_path.unlink()
    _run(
        [
            "exiftool",
            "-overwrite_original",
            "-api",
            "QuickTimeUTC=1",
            f"-QuickTime:CreateDate={PHONE_CREATION_DATE}",
            f"-Keys:GPSCoordinates={PHONE_GPS}",
            f"-UserData:GPSCoordinates={PHONE_GPS}",
            str(output_path),
        ]
    )
    return output_path


def build_still_clip(directory: Path) -> Path:
    """Build the lossless 60-second still clip with five one-frame flashes and beeps."""
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / "still-clip.mkv"
    on_expression = "+".join(f"between(t,{time},{time + 0.039})" for time in STILL_TIMES)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x808080:s=1280x720:r=25:d=60,"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{on_expression}',"
            "format=yuv420p",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='0.5*sin(2*PI*1000*t)*({on_expression})':s=48000:d=60",
            "-c:v",
            "libx264",
            "-qp",
            "0",
            "-g",
            "25",
            "-c:a",
            "flac",
            str(output_path),
        ]
    )
    return output_path


def build_sixty_fps_clip(directory: Path) -> Path:
    """Build the lossless 20-second 60 fps flash-and-beep fixture from SPEC Terms."""
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / "sixty-fps-clip.mkv"
    flashes = "+".join(f"between(t,{time},{time + 0.049})" for time in SIXTY_FPS_TIMES)
    beeps = "+".join(f"between(t,{time},{time + 0.039})" for time in SIXTY_FPS_TIMES)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x808080:s=1280x720:r=60:d=20,"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{flashes}',"
            "format=yuv420p",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='0.5*sin(2*PI*1000*t)*({beeps})':s=48000:d=20",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-qp",
            "0",
            "-g",
            "60",
            "-c:a",
            "flac",
            "-t",
            "20",
            str(output_path),
        ]
    )
    return output_path


def build_old_ffmpeg_stub(directory: Path) -> Path:
    """Create an executable ffmpeg 6.1 stub and return its directory."""
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / "ffmpeg"
    executable.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'ffmpeg version 6.1 Copyright (c) 2000-2023 the FFmpeg developers'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    return directory


def _run(command: list[str]) -> None:
    """Run a fixture-building command and include its command in any failure."""
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise RuntimeError(f"Required fixture tool not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() or error.stdout.strip()
        raise RuntimeError(f"Fixture command failed: {command[0]}: {details}") from error
