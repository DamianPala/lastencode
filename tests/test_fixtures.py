"""Behavior checks for the generated test fixtures."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fixture_builders import PHONE_CREATION_DATE, STILL_TIMES


def _missing_tools(*names: str) -> str | None:
    missing = [name for name in names if shutil.which(name) is None]
    return f"required tools are unavailable: {', '.join(missing)}" if missing else None


def _json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    parsed: object = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    return parsed


def _json_records(command: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    parsed: object = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert all(isinstance(record, dict) for record in parsed)
    return parsed


@pytest.mark.skipif(
    _missing_tools("ffmpeg", "ffprobe", "exiftool") is not None,
    reason=_missing_tools("ffmpeg", "ffprobe", "exiftool") or "required tools unavailable",
)
@pytest.mark.needs_media
def test_phone_clip_properties(phone_clip: Path) -> None:
    """The phone fixture has the expected video, audio, rotation, date, and GPS metadata."""
    probe = _json(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(phone_clip),
        ]
    )
    streams = probe["streams"]
    assert isinstance(streams, list)
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert video["width"] == 1920
    assert video["height"] == 1080
    assert video["pix_fmt"] == "yuvj420p"
    assert video["color_range"] == "tv"
    assert video["color_primaries"] == "bt2020"
    frame = _json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-read_intervals",
            "%+#1",
            "-show_frames",
            "-of",
            "json",
            str(phone_clip),
        ]
    )["frames"][0]
    assert frame["color_range"] == "pc"
    assert frame["color_primaries"] == frame["color_space"] == "bt470bg"
    assert frame["color_transfer"] == "smpte170m"
    assert 6_000_000 <= int(video["bit_rate"]) <= 8_000_000
    assert audio["codec_name"] == "aac"
    assert audio["channels"] == 2
    assert abs(float(probe["format"]["duration"]) - 20) < 0.2
    side_data = video.get("side_data_list", [])
    assert any(item.get("rotation") == -90 for item in side_data)

    frames = _json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=duration_time",
            "-of",
            "json",
            str(phone_clip),
        ]
    )["frames"]
    durations = {
        round(float(frame["duration_time"]), 6)
        for frame in frames
        if frame.get("duration_time") is not None
    }
    assert len(durations) > 1

    records = _json_records(
        [
            "exiftool",
            "-api",
            "QuickTimeUTC=1",
            "-j",
            "-G1",
            "-s",
            "-QuickTime:CreateDate",
            "-Keys:GPSCoordinates",
            "-UserData:GPSCoordinates",
            str(phone_clip),
        ]
    )
    assert isinstance(records, list) and records
    tags = records[0]
    creation_date = datetime.strptime(tags["QuickTime:CreateDate"], "%Y:%m:%d %H:%M:%S%z")
    expected_date = datetime.strptime(PHONE_CREATION_DATE, "%Y:%m:%d %H:%M:%S%z")
    assert creation_date.astimezone(UTC) == expected_date.astimezone(UTC)
    assert tags["Keys:GPSCoordinates"]
    assert tags["UserData:GPSCoordinates"]


@pytest.mark.skipif(
    _missing_tools("ffmpeg", "ffprobe") is not None,
    reason=_missing_tools("ffmpeg", "ffprobe") or "required tools unavailable",
)
@pytest.mark.needs_media
def test_still_clip_properties(still_clip: Path, tmp_path: Path) -> None:
    """The still fixture has 1,500 frames, exactly five white flashes and beeps, and FLAC audio."""
    probe = _json(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-of",
            "json",
            str(still_clip),
        ]
    )
    streams = probe["streams"]
    assert isinstance(streams, list)
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert video["nb_read_frames"] == "1500"
    assert audio["codec_name"] == "flac"

    target_frames = [round(time * 25) for time in STILL_TIMES]
    sample_frames = [number + offset for number in target_frames for offset in (-1, 0, 1)]
    selections = "+".join(f"eq(n,{number})" for number in sample_frames)
    output = tmp_path / "selected-frames.gray"
    with output.open("wb") as frame_data:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(still_clip),
                "-vf",
                f"select='{selections}',format=gray",
                "-fps_mode",
                "passthrough",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "pipe:1",
            ],
            check=True,
            stdout=frame_data,
        )
    frame_size = 1280 * 720
    raw_frames = output.read_bytes()
    assert len(raw_frames) == frame_size * len(sample_frames)
    means = [
        sum(raw_frames[offset : offset + frame_size]) / frame_size
        for offset in range(0, len(raw_frames), frame_size)
    ]
    for index in range(0, len(means), 3):
        assert means[index] < 150
        assert means[index + 1] > 220
        assert means[index + 2] < 150

    luma = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi", "-i", f"movie={still_clip.name},signalstats"]
        + ["-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG", "-of", "csv=p=0"],
        check=True,
        capture_output=True,
        text=True,
        cwd=still_clip.parent,
    ).stdout.split()
    white_times = [
        float(time) for time, yavg, *_ in (line.split(",") for line in luma) if float(yavg) > 200
    ]
    assert white_times == [float(time) for time in STILL_TIMES]

    detect = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(still_clip), "-map", "0:a"]
        + ["-af", "silencedetect=n=-30dB:d=0.01", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stderr
    ends = [float(value) for value in re.findall(r"silence_end: ([\d.]+)", detect)]
    starts = [float(value) for value in re.findall(r"silence_start: ([\d.]+)", detect)]
    beeps = list(zip(ends, starts[1:], strict=False))
    assert [round(start, 2) for start, _ in beeps] == [float(time) for time in STILL_TIMES]
    assert all(0.03 < end - start < 0.05 for start, end in beeps)


def test_old_ffmpeg_stub(old_ffmpeg_stub: Path) -> None:
    """The old ffmpeg fixture reports version 6.1 and exits successfully."""
    environment = {
        **os.environ,
        "PATH": os.pathsep.join((str(old_ffmpeg_stub), os.environ.get("PATH", ""))),
    }
    executable = shutil.which("ffmpeg", path=environment["PATH"])
    assert executable is not None
    result = subprocess.run(
        [executable, "-version"], check=True, capture_output=True, text=True, env=environment
    )
    assert "ffmpeg version 6.1" in result.stdout.splitlines()[0]
