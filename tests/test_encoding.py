"""Synthetic integration coverage for per-target encoding; no archived media."""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from fixture_builders import STILL_TIMES, _run
from lastencode.encoder_check import check_record_encoders, probe_encoder
from lastencode.encoding import encode_source, result_totals
from lastencode.errors import MissingTool
from lastencode.metadata import is_faststart
from lastencode.paths import discover
from lastencode.planning import plan_source
from lastencode.presets import load_categories
from lastencode.probe import probe as raw_probe
from lastencode.video import encoder_parameters
from test_cli import cli, validate_schema


def inspect(path: Path, *options: str) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", *options, "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def probe(path: Path) -> dict[str, Any]:
    return raw_probe(path)


def frames(path: Path) -> list[dict[str, Any]]:
    return inspect(path, "-select_streams", "v:0", "-show_frames")["frames"]


def exiftool_tags(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["exiftool", "-j", "-G1", "-a", "-s", "-api", "QuickTimeUTC=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)[0]


def convert(
    source: Path,
    output: Path,
    presets: Path,
    *,
    category: str = "apartment-tour",
    target: str = "portable",
    force_encode: bool = False,
    force_smaller: bool = False,
) -> dict[str, Any]:
    categories = {c.name: c for c in load_categories(str(presets))}
    sources, _ = discover([str(source)], output)
    record = plan_source(sources[0], categories[category], target, ZoneInfo("UTC"))
    if force_encode:
        record["action"] = "encode"
    try:
        check_record_encoders([record], set())
    except MissingTool as error:
        pytest.skip(str(error))
    if force_smaller:
        import lastencode.encoding as encoding

        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
            encode_source(record)
    else:
        encode_source(record)
    return record


def completed(record: dict[str, Any]) -> Path:
    assert record["status"] == "completed", record.get("reason")
    path = Path(record["output_path"])
    assert path.exists()
    assert record["output_size_bytes"] == path.stat().st_size
    assert not list(path.parent.glob(".*.lastencode-part.*"))
    return path


def keyframe_times(data: list[dict[str, Any]]) -> list[float]:
    return [float(f["pts_time"]) for f in data if f["key_frame"]]


def assert_keyframes(path: Path, data: list[dict[str, Any]], interval: float) -> None:
    times = keyframe_times(data)
    assert times[0] == float(data[0]["pts_time"])
    assert all(b - a <= interval + 0.002 for a, b in zip(times, times[1:], strict=False))
    # Last GOP is bounded too, so disabling forced keys cannot pass on a single I-frame.
    assert float(data[-1]["pts_time"]) - times[-1] <= interval + 0.002
    from lastencode.bitstream import random_access

    codec = probe(path)["video_codec"]
    assert random_access(path, codec, len(times))["random_access_valid"]


@pytest.mark.parametrize(
    "target,pixel,colour,audio",
    [
        ("portable", "yuv420p10le", "tv", "opus"),
        ("desktop", "yuv420p10le", "tv", "opus"),
    ],
)
def test_R12d_phone_targets(
    phone_clip: Path,
    tmp_path: Path,
    fast_presets: Path,
    target: str,
    pixel: str,
    colour: str,
    audio: str,
) -> None:
    record = convert(
        phone_clip,
        tmp_path / "out",
        fast_presets,
        target=target,
        force_encode=True,
        force_smaller=True,
    )
    path = completed(record)
    assert record["action"] == "encode"
    schema = json.loads(cli("schema", "convert").stdout)["output"]
    validate_schema(record, schema)
    summary = result_totals([record])
    assert summary["completed_count"] == 1
    assert summary["output_size_bytes"] == path.stat().st_size
    info = inspect(path, "-show_streams")["streams"]
    video = info[0]
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["pix_fmt"] == pixel and video["color_range"] == colour
    for description in (video, frames(path)[0]):
        assert description["color_primaries"] == description["color_space"] == "bt470bg"
        assert description["color_transfer"] == "smpte170m"
        assert description["color_range"] == colour
    assert all(
        row["passed"] for row in record["checks"] if row["name"] in ("Colour", "Colour tags")
    )
    assert "side_data_list" not in video
    assert "rotate" not in video.get("tags", {})
    assert info[1]["codec_name"] == audio
    data, original = frames(path), frames(phone_clip)
    assert len(data) == len(original)
    offsets = [
        float(d["pts_time"]) - float(s["pts_time"]) for d, s in zip(data, original, strict=True)
    ]
    assert max(offsets) - min(offsets) <= 0.002
    assert_keyframes(path, data, 2)
    raw = path.read_bytes()
    assert raw.index(b"moov") < raw.index(b"mdat")


def test_phone_metadata_roundtrip(phone_clip: Path, tmp_path: Path, fast_presets: Path) -> None:
    source_stat = phone_clip.stat()
    result = cli(
        "convert",
        str(phone_clip),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "apartment-tour",
        "--target",
        "portable",
        "--presets",
        str(fast_presets),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    record, summary = records
    output = completed(record)
    source_tags = exiftool_tags(phone_clip)
    output_tags = exiftool_tags(output)
    expected = record["recording_date"]
    assert record["date_source"] == "creation_time"
    assert record["location"] == "kept"
    assert record["gps_present"] is True
    assert summary["gps_outputs"] == [str(output)]
    assert probe(output)["creation_time"].startswith(expected.removesuffix("Z"))
    date_suffixes = {
        "CreateDate",
        "ModifyDate",
        "TrackCreateDate",
        "TrackModifyDate",
        "MediaCreateDate",
        "MediaModifyDate",
    }
    output_dates = [
        value for name, value in output_tags.items() if name.split(":")[-1] in date_suffixes
    ]
    assert len(output_dates) >= 6
    assert len(set(output_dates)) == 1
    assert output_tags["Keys:GPSCoordinates"] == source_tags["Keys:GPSCoordinates"]
    assert output_tags["UserData:GPSCoordinates"] == source_tags["UserData:GPSCoordinates"]
    assert output_tags["QuickTime:CreateDate"] == source_tags["QuickTime:CreateDate"]
    assert output.stat().st_mtime_ns // 1_000_000_000 == source_stat.st_mtime_ns // 1_000_000_000
    assert phone_clip.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert not list(output.parent.glob("*_original"))
    assert is_faststart(output)
    assert output.read_bytes().index(b"moov") < output.read_bytes().index(b"mdat")


@pytest.mark.parametrize(
    "name, timestamp, expected_date, expected_source, timezone",
    [
        (
            "20260915_143012.mp4",
            1_800_000_000,
            "2026-09-15T12:30:12Z",
            "filename",
            "Europe/Warsaw",
        ),
        (
            "mtime-only.mp4",
            1_800_000_000,
            datetime.fromtimestamp(1_800_000_000, UTC).isoformat().replace("+00:00", "Z"),
            "mtime",
            None,
        ),
    ],
)
def test_filename_and_mtime_dates_are_written(
    tmp_path: Path,
    fast_presets: Path,
    name: str,
    timestamp: int,
    expected_date: str,
    expected_source: str,
    timezone: str | None,
) -> None:
    source = tmp_path / "in" / name
    build_small(source)
    os.utime(source, (timestamp, timestamp))
    assert probe(source)["creation_time"] is None
    args = [
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    ]
    if timezone:
        args += ["--tz", timezone]
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    record = records[0]
    output = completed(record)
    assert record["date_source"] == expected_source
    assert record["recording_date"] == expected_date
    assert probe(output)["creation_time"].startswith(expected_date.removesuffix("Z"))


def test_keys_creation_date_android_tags_and_languages(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in" / "tagged.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x64:r=10:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-metadata:s:v:0",
            "language=eng",
            "-metadata:s:a:0",
            "language=pol",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "40",
            "-c:a",
            "aac",
            str(source),
        ]
    )
    creation_date = "2026:02:03 12:30:00+02:00"
    _run(
        [
            "exiftool",
            "-overwrite_original",
            f"-Keys:CreationDate={creation_date}",
            "-Keys:AndroidVersion=14",
            "-Keys:AndroidMake=Example",
            "-Keys:AndroidModel=CaptureFixture",
            "-Keys:AndroidTimeZone=+02:00",
            str(source),
        ]
    )
    source_tags = exiftool_tags(source)
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(sources[0], categories["webinar"], "portable", ZoneInfo("UTC"))
    assert record["action"] == "copy-video"
    encode_source(record)
    output = completed(record)
    output_tags = exiftool_tags(output)
    assert record["date_source"] == "Keys:CreationDate"
    assert record["recording_date"] == "2026-02-03T10:30:00Z"
    assert output_tags["Keys:CreationDate"] == source_tags["Keys:CreationDate"] == creation_date
    for key in (
        "Keys:AndroidVersion",
        "Keys:AndroidMake",
        "Keys:AndroidModel",
        "Keys:AndroidTimeZone",
    ):
        assert output_tags[key] == source_tags[key]
    source_streams = inspect(source, "-show_streams")["streams"]
    output_streams = inspect(output, "-show_streams")["streams"]
    assert source_streams[0]["tags"]["language"] == output_streams[0]["tags"]["language"] == "eng"
    assert source_streams[1]["tags"]["language"] == output_streams[1]["tags"]["language"] == "pol"


@pytest.mark.parametrize("policy", ["flag", "preset"])
def test_strip_location_removes_every_location_tag(
    tmp_path: Path, fast_presets: Path, policy: str
) -> None:
    source = tmp_path / "in" / "located.mp4"
    source.parent.mkdir()
    build_small(source)
    coordinate = "+37.7749-122.4194+15.0/"
    _run(
        [
            "exiftool",
            "-overwrite_original",
            f"-Keys:GPSCoordinates={coordinate}",
            f"-UserData:GPSCoordinates={coordinate}",
            "-Keys:LocationName=Fixture Street",
            "-XMP-exif:GPSLatitude=37.7749",
            "-XMP-exif:GPSLongitude=-122.4194",
            str(source),
        ]
    )
    source_tags = exiftool_tags(source)
    assert source_tags["XMP-exif:GPSLatitude"]
    assert source_tags["XMP-exif:GPSLongitude"]
    args = [
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    ]
    if policy == "flag":
        args.append("--strip-location")
    else:
        strip_preset = tmp_path / "strip.toml"
        strip_preset.write_text(
            '[categories.apartment-tour]\nlocation = "strip"\n'
            '[categories.apartment-tour.portable]\nspeed_preset = "ultrafast"\n'
        )
        args[args.index(str(fast_presets))] = str(strip_preset)
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    record, summary = records
    output = completed(record)
    output_tags = exiftool_tags(output)
    assert record["location"] == "stripped"
    assert record["gps_present"] is False
    assert summary["gps_outputs"] == []
    assert not any(
        word in name.casefold()
        for name in output_tags
        for word in ("gps", "location", "iso6709", "loci")
    )
    for name, value in source_tags.items():
        if name.casefold().endswith("gpscoordinates"):
            assert str(value).encode("utf-8") not in output.read_bytes()
    output_bytes = output.read_bytes()
    assert b"37.7749" not in output_bytes
    assert b"-122.4194" not in output_bytes


@pytest.mark.parametrize("stereo_aac", [False, True])
def test_still_desktop(
    still_clip: Path, tmp_path: Path, fast_presets: Path, stereo_aac: bool
) -> None:
    if stereo_aac:
        variant = tmp_path / "in" / "stereo.mkv"
        variant.parent.mkdir()
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(still_clip),
                "-c:v",
                "copy",
                "-af",
                "pan=stereo|c0=c0|c1=c0",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(variant),
            ]
        )
        still_clip = variant
    record = convert(
        still_clip, tmp_path / "out", fast_presets, category="webinar", target="desktop"
    )
    output = completed(record)
    data = frames(output)
    times = [float(f["pts_time"]) for f in data]
    assert 60 <= len(times) < 100
    assert max(b - a for a, b in zip(times, times[1:], strict=False)) <= 1.002
    offset = times[0]
    assert all(abs((t - offset) * 25 - round((t - offset) * 25)) < 0.002 for t in times)
    assert_keyframes(output, data, 6)
    # Decode the actual output luma; timestamps alone cannot prove the flashes survived.
    detected = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(output),
            "-vf",
            "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    pairs = re.findall(r"pts_time:([\d.]+).*?YAVG=([\d.]+)", detected, re.S)
    white = [float(t) for t, y in pairs if float(y) > 800]
    assert white == pytest.approx([t + offset for t in STILL_TIMES], abs=0.002)
    detected = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(output),
            "-map",
            "0:a",
            "-af",
            "silencedetect=n=-30dB:d=0.01",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    ends = [float(t) for t in re.findall(r"silence_end: ([\d.]+)", detected)]
    starts = re.findall(r"silence_start: ([\d.]+)", detected)
    beeps = ends[: len(starts) - 1]
    assert len(beeps) == len(white)
    assert all(abs(a - b) <= 0.002 for a, b in zip(white, beeps, strict=True))
    assert probe(output)["audio_streams"][0]["channels"] == 1
    assert record["audio_decisions"][0]["bitrate_bps"] == 24000


def build_small(path: Path, *, size: str = "160x120", audio: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={size}:r=10:d=1"]
    if audio:
        args += ["-f", "lavfi", "-i", audio, "-c:a", "aac", "-b:a", "128k"]
    _run(
        args
        + [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            "-color_trc",
            "bt709",
            str(path),
        ]
    )


@pytest.mark.parametrize("stereo", [False, True])
def test_copy_and_audio_channels(tmp_path: Path, fast_presets: Path, stereo: bool) -> None:
    source = tmp_path / "in" / "source.mp4"
    signal = "sin(2*PI*440*t)"
    right = "sin(2*PI*660*t)" if stereo else signal
    build_small(source, audio=f"aevalsrc=0.1*{signal}|0.1*{right}:s=48000:d=1")
    record = convert(source, tmp_path / "out", fast_presets, category="webinar")
    output = completed(record)
    assert record["action"] == "copy-video"
    assert inspect(output, "-show_streams")["streams"][0]["codec_tag_string"] == "avc1"
    for path in (source, output):
        data = inspect(path, "-select_streams", "v:0", "-show_packets", "-show_data_hash", "sha256")
        hashes = [packet["data_hash"] for packet in data["packets"]]
        if path == source:
            original = hashes
        else:
            assert hashes == original
    decision = record["audio_decisions"][0]
    assert decision["channels"] == (2 if stereo else 1)
    assert decision["dual_mono"] == (not stereo)
    assert decision["bitrate_bps"] == (48000 if stereo else 24000)
    assert probe(output)["audio_streams"][0]["codec_name"] == "opus"


@pytest.mark.parametrize("size,expected", [("1920x1080", (1280, 720)), ("640x480", (640, 480))])
def test_scale(tmp_path: Path, fast_presets: Path, size: str, expected: tuple[int, int]) -> None:
    source = tmp_path / "in" / "scale.mp4"
    build_small(source, size=size)
    record = convert(
        source,
        tmp_path / "out",
        fast_presets,
        category="dance-lesson",
        force_encode=True,
        force_smaller=True,
    )
    video = inspect(completed(record), "-show_streams")["streams"][0]
    assert (video["width"], video["height"]) == expected


@pytest.fixture
def hdr_clip(tmp_path: Path) -> Path:
    path = tmp_path / "in" / "hdr.mp4"
    path.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=10:d=1",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p10le",
            "-color_primaries",
            "bt2020",
            "-color_trc",
            "smpte2084",
            "-colorspace",
            "bt2020nc",
            "-x265-params",
            "pools=1:frame-threads=1:hdr10=1:colorprim=bt2020:transfer=smpte2084:"
            "colormatrix=bt2020nc:"
            "master-display=G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)"
            "L(10000000,1):max-cll=1000,400",
            str(path),
        ]
    )
    return path


@pytest.mark.parametrize("target", ["portable", "desktop"])
def test_r12c_hdr_preserved(
    hdr_clip: Path, tmp_path: Path, fast_presets: Path, target: str
) -> None:
    record = convert(
        hdr_clip,
        tmp_path / "out",
        fast_presets,
        target=target,
        category="webinar",
        force_encode=True,
        force_smaller=True,
    )
    output = completed(record)
    stream = inspect(output, "-show_streams")["streams"][0]
    assert record["action"] == "encode"
    assert stream["color_transfer"] == "smpte2084"
    assert stream["color_primaries"] == "bt2020"
    assert stream["color_space"] == "bt2020nc"
    source_side = frames(hdr_clip)[0]["side_data_list"]
    result_side = frames(output)[0]["side_data_list"]
    for side in source_side:
        if side["side_data_type"] in ("Mastering display metadata", "Content light level metadata"):
            actual = next(s for s in result_side if s["side_data_type"] == side["side_data_type"])
            for key, value in side.items():
                if key == "side_data_type":
                    continue
                # AV1 metadata uses 16-bit chromaticity and different luminance units.
                assert float(Fraction(str(actual[key]))) == pytest.approx(
                    float(Fraction(str(value))), abs=0.0001
                )


def test_overlapping_inputs(tmp_path: Path) -> None:
    root = tmp_path / "in"
    nested = root / "sub"
    nested.mkdir(parents=True)
    (nested / "x.txt").write_text("x")
    result = cli(
        "convert",
        str(root),
        str(nested),
        "--category",
        "webinar",
        "--output-dir",
        str(tmp_path / "out"),
    )
    assert result.returncode == 2 and "overlapping inputs" in result.stderr
    assert str(root) in result.stderr and str(nested) in result.stderr
    assert not (tmp_path / "out").exists()


def test_subtitle_and_audio_mapping(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in" / "source.mkv"
    source.parent.mkdir()
    base = tmp_path / "base.mp4"
    build_small(base, audio="sine=d=1")
    srt = tmp_path / "text.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nhello\n")
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(base),
            "-i",
            str(srt),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "0:a",
            "-map",
            "1:s",
            "-c",
            "copy",
            "-metadata:s:a:0",
            "language=pol",
            "-metadata:s:a:1",
            "language=eng",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "hearing_impaired",
            str(source),
        ]
    )
    output = completed(convert(source, tmp_path / "out", fast_presets))
    info = probe(output)
    assert [s["codec_name"] for s in info["subtitle_streams"]] == ["mov_text"]
    assert [s["tags"]["language"] for s in info["audio_streams"]] == ["pol", "eng"]
    assert info["audio_streams"][1]["disposition"]["hearing_impaired"] == 1
    assert info["audio_streams"][0]["disposition"]["default"] == 1


def test_failure_continues(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    build_small(source / "a.mp4")
    build_small(source / "b.mp4")
    # Filesystem failure on the first work path; ffmpeg must never overwrite it.
    output = tmp_path / "out"
    output.mkdir()
    work = output / ".a.lastencode-part.mp4"
    work.mkdir()
    backup = Path(str(work) + "_original")
    backup.write_text("also owned by someone else")
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(output),
        "--category",
        "webinar",
        "--presets",
        str(fast_presets),
        "--json",
    )
    assert result.returncode == 1
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]["status"] == "failed"
    assert records[1]["status"] == "completed"
    assert work.is_dir()
    assert backup.read_text() == "also owned by someone else"
    assert not (output / "a.mp4").exists()
    assert json.loads(result.stderr.splitlines()[-1])["error"]["kind"] == "sources_failed"


def test_existing_hardlink_replaced_by_rename(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "in" / "source.mp4"
    build_small(source)
    output = tmp_path / "out"
    output.mkdir()
    destination = output / source.name
    # Synthetic hard link specifically exercises R19a; production creates none.
    os.link(source, destination)
    before = source.read_bytes()
    record = convert(source, output, fast_presets)
    completed(record)
    assert source.read_bytes() == before
    assert source.stat().st_ino != destination.stat().st_ino


def test_encoder_failure_removes_work_and_continues(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    build_small(source / "a.mp4")
    build_small(source / "b.mp4")
    # Only a.mp4 fails inside ffmpeg, after it has opened its output. The wrapper
    # delegates all tool checks and the next encode to the actual installed binary.
    executable = tmp_path / "bin" / "ffmpeg"
    executable.parent.mkdir()
    real_ffmpeg = subprocess.run(
        ["which", "ffmpeg"], capture_output=True, text=True, check=True
    ).stdout.strip()
    executable.write_text(
        "#!/usr/bin/env python3\nimport os, sys\n"
        'if any(p.endswith("/a.mp4") for p in sys.argv[1:]) and "-f" in sys.argv:\n'
        '    open(sys.argv[-1], "wb").write(b"partial")\n'
        '    print("deliberate encoder failure", file=sys.stderr)\n'
        "    sys.exit(1)\n"
        f"os.execv({real_ffmpeg!r}, [{real_ffmpeg!r}] + sys.argv[1:])\n"
    )
    executable.chmod(0o755)
    environment = dict(os.environ, PATH=str(executable.parent) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lastencode",
            "convert",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--category",
            "apartment-tour",
            "--json",
            "--presets",
            str(fast_presets),
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]["status"] == "failed"
    assert "deliberate encoder failure" in records[0]["reason"]
    assert records[1]["status"] == "completed"
    assert not list((tmp_path / "out").glob(".*.lastencode-part.*"))
    assert not (tmp_path / "out/a.mp4").exists()
    assert json.loads(result.stderr.splitlines()[-1])["error"]["kind"] == "sources_failed"


def test_interrupt_cleans_work(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lastencode.encoding as encoding

    source = tmp_path / "in" / "source.mp4"
    build_small(source)
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(sources[0], categories["apartment-tour"], "portable", ZoneInfo("UTC"))

    def interrupted(command: list[str], **kwargs: object) -> None:
        Path(command[-1]).write_bytes(b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(encoding.subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        encode_source(record)
    assert not list((tmp_path / "out").iterdir())


def test_surround_layout(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in" / "surround.mp4"
    build_small(source, audio="anullsrc=cl=5.1:r=48000:d=1")
    record = convert(source, tmp_path / "out", fast_presets, category="webinar")
    output = completed(record)
    audio = probe(output)["audio_streams"][0]
    assert audio["channels"] == 6 and audio["channel_layout"] == "5.1"
    assert record["audio_decisions"][0]["bitrate_bps"] == 144000


def test_chapters_and_attachments(tmp_path: Path, fast_presets: Path) -> None:
    base = tmp_path / "base.mp4"
    build_small(base)
    metadata = tmp_path / "chapters.txt"
    metadata.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=900\ntitle=Intro\n")
    source = tmp_path / "in" / "attached.mkv"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(base),
            "-i",
            str(metadata),
            "-map",
            "0",
            "-map_chapters",
            "1",
            "-c",
            "copy",
            "-attach",
            str(metadata),
            "-metadata:s:t",
            "mimetype=text/plain",
            str(source),
        ]
    )
    record = convert(source, tmp_path / "out", fast_presets, force_smaller=True)
    output = completed(record)
    assert record["dropped_streams"][0]["type"] == "attachment"
    chapters = inspect(output, "-show_chapters")["chapters"]
    assert len(chapters) == 1 and chapters[0]["tags"]["title"] == "Intro"


def test_bitmap_drop_mapping() -> None:
    from lastencode.encoding import stream_arguments

    info: dict[str, object] = {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "subtitle", "codec_name": "dvd_subtitle"},
            {"index": 2, "codec_type": "data", "codec_name": "bin_data"},
        ]
    }
    args, dropped = stream_arguments(info)
    assert [s["codec"] for s in dropped] == ["dvd_subtitle", "bin_data"]
    assert "0:1" not in args and "0:2" not in args


def test_bitmap_fixture_unavailable() -> None:
    pytest.skip("ffmpeg cannot encode text/lavfi to dvd_subtitle; bitmap policy tested separately")


def test_timecode_dropped(tmp_path: Path, fast_presets: Path) -> None:
    base = tmp_path / "base.mp4"
    build_small(base)
    source = tmp_path / "in" / "timecode.mov"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(base),
            "-c",
            "copy",
            "-timecode",
            "01:00:00:00",
            str(source),
        ]
    )
    record = convert(source, tmp_path / "out", fast_presets)
    output = completed(record)
    assert any(s["codec_tag"] == "tmcd" for s in record["dropped_streams"])
    assert not probe(output)["data_streams"]


def test_copy_rotation(phone_clip: Path, tmp_path: Path, fast_presets: Path) -> None:
    record = convert(phone_clip, tmp_path / "out", fast_presets)
    # Exercise the explicit copy path independently of the high-bitrate plan decision.
    output = Path(record["output_path"])
    output.unlink()
    record.update(action="copy-video", status="planned")
    encode_source(record)
    assert probe(completed(record))["rotation"] == -90
    assert probe(output)["bit_depth"] == 8
    assert probe(output)["color_range"] == "pc"


@pytest.mark.parametrize("target,minimum,maximum", [("portable", 64, 940), ("desktop", 64, 940)])
def test_R12a_full_range_HEVC_values(
    tmp_path: Path,
    fast_presets: Path,
    target: str,
    minimum: int,
    maximum: int,
) -> None:
    source = tmp_path / "in" / "ramp.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=256x64:r=1:d=1,geq=lum=X:cb=128:cr=128",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "pools=1:frame-threads=1:lossless=1:range=full:"
            "colorprim=bt709:transfer=bt709:colormatrix=bt709",
            "-color_range",
            "pc",
            str(source.with_name("raw.mp4")),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source.with_name("raw.mp4")),
            "-c",
            "copy",
            "-color_range",
            "tv",
            str(source),
        ]
    )
    assert probe(source)["color_range"] == "pc"
    assert inspect(source, "-show_streams")["streams"][0]["color_range"] == "tv"
    output = completed(
        convert(
            source,
            tmp_path / "out",
            fast_presets,
            target=target,
            force_encode=True,
            force_smaller=True,
        )
    )
    signal = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(output),
            "-vf",
            "signalstats,metadata=print",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    low_match = re.search(r"YMIN=(\d+)", signal)
    high_match = re.search(r"YMAX=(\d+)", signal)
    assert low_match and high_match
    low, high = int(low_match[1]), int(high_match[1])
    assert abs(low - minimum) <= 4
    assert abs(high - maximum) <= 4


def test_real_encoder_failure_continues(tmp_path: Path, fast_presets: Path) -> None:
    # Use the category by name, independent of registry ordering.
    settings: dict[str, object] = {
        key: value.value
        for category in load_categories(str(fast_presets))
        if category.name == "webinar"
        for key, value in category.settings["desktop"].items()
    }
    try:
        probe_encoder(settings, encoder_parameters(Path("."), {}, settings), set())
    except MissingTool as error:
        pytest.skip(str(error))
    source = tmp_path / "in"
    # SVT rejects widths above 16384; newer versions pad small inputs automatically.
    source.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=16400x64:r=1:d=1",
            "-c:v",
            "ffv1",
            str(source / "a.mkv"),
        ]
    )
    build_small(source / "b.mp4")
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "webinar",
        "--target",
        "desktop",
        "--presets",
        str(fast_presets),
        "--json",
    )
    assert result.returncode == 1
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]["status"] == "failed" and "ffmpeg exited" in records[0]["reason"]
    assert records[1]["status"] == "completed"
    assert not (tmp_path / "out/a.mp4").exists()
    assert not list((tmp_path / "out").glob(".*.lastencode-part.*"))


def test_text_encoding_result(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "in" / "source.mp4"
    build_small(source, audio="sine=d=1")
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "webinar",
        "--presets",
        str(fast_presets),
        "--format",
        "text",
    )
    assert result.returncode == 0, result.stderr
    assert "status: completed" in result.stdout
    for field in (
        "source_size_bytes",
        "output_size_bytes",
        "encode_time_seconds",
        "audio_decisions",
        "dropped_streams",
        "settings",
    ):
        assert field + ":" in result.stdout


@pytest.mark.parametrize("target,encoder", [("desktop", "libsvtav1"), ("portable", "libx265")])
def test_bogus_encoder_option_stops_before_work(tmp_path: Path, target: str, encoder: str) -> None:
    source = tmp_path / "in" / "clip.mp4"
    build_small(source)
    presets = tmp_path / "bogus.toml"
    presets.write_text(f'[categories.webinar.{target}]\nextra_encoder_params = "bogus-s3=1"\n')
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "webinar",
        "--target",
        target,
        "--presets",
        str(presets),
        "--json",
    )
    assert result.returncode == 3, result.stderr
    message = json.loads(result.stderr)["error"]
    assert message["kind"] == "missing_tool"
    assert encoder in message["message"] and "bogus-s3" in message["message"]
    assert re.search(r"(?:encoder version|Encoder Lib v)\s*\d", message["message"])
    assert "install an ffmpeg" in message["message"]
    assert not (tmp_path / "out").exists() and not result.stdout


def test_hevc_mkv_copy_tag(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    source = tmp_path / "in" / "hevc.mkv"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x120:r=10:d=1",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "pools=1:frame-threads=1",
            str(source),
        ]
    )
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(sources[0], categories["webinar"], "portable", ZoneInfo("UTC"))
    assert source.stat().st_size * 8 < 200_000  # One-second, low-bitrate synthetic clip.
    # MKV does not expose stream bit_rate to the planner; isolate the copy execution path.
    record["action"] = "copy-video"
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
    encode_source(record)
    assert inspect(completed(record), "-show_streams")["streams"][0]["codec_tag_string"] == "hvc1"


@pytest.mark.parametrize("layout", ["2.1", "3.0", "quad", "7.1"])
def test_audio_layout_fallback(tmp_path: Path, fast_presets: Path, layout: str) -> None:
    source = tmp_path / "in" / "audio.mp4"
    build_small(source, audio=f"anullsrc=cl={layout}:r=48000:d=1")
    record = convert(source, tmp_path / "out", fast_presets, category="webinar")
    audio = probe(completed(record))["audio_streams"][0]
    downmixed = layout != "7.1"
    assert audio["channels"] == (2 if downmixed else 8)
    decision = record["audio_decisions"][0]
    assert decision["downmixed_to_stereo"] is downmixed
    assert decision["bitrate_bps"] == (48000 if downmixed else 192000)


def test_malformed_hdr_is_source_failure(
    hdr_clip: Path, tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.probe as probing

    original = probing.first_frame

    def decoded(path: Path) -> dict[str, object]:
        frame = original(path)
        if path == hdr_clip:
            frame["side_data_list"] = [
                {"side_data_type": "Content light level metadata", "max_content": 1000}
            ]
        return frame

    monkeypatch.setattr(probing, "first_frame", decoded)
    record = convert(hdr_clip, tmp_path / "out", fast_presets, force_encode=True)
    assert record["status"] == "failed"
    assert "Malformed HDR metadata" in record["reason"] and "max_average" in record["reason"]
    assert not (tmp_path / "out").exists()
    source = tmp_path / "normal-in" / "normal.mp4"
    build_small(source)
    completed(convert(source, tmp_path / "next", fast_presets))


def test_runtime_parameter_rejection_removes_output(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    source = tmp_path / "in" / "source.mp4"
    build_small(source)
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(sources[0], categories["apartment-tour"], "portable", ZoneInfo("UTC"))

    def rejected(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(command, 0, "", "Unknown option: runtime-bogus.")

    monkeypatch.setattr(encoding.subprocess, "run", rejected)
    encode_source(record)
    assert record["status"] == "failed" and "runtime-bogus" in str(record["reason"])
    assert not list((tmp_path / "out").iterdir())


def test_parameter_probe_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    import lastencode.encoder_check as checks

    calls: list[list[str]] = []

    def success(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(checks.subprocess, "run", success)
    settings: dict[str, object] = {
        "encoder": "libx265",
        "speed_preset": "ultrafast",
        "quality_crf": 28,
        "bit_depth": 10,
    }
    checked: set[tuple[str, str]] = set()
    for params in ("open-gop=0", "open-gop=0", "open-gop=0:range=full"):
        probe_encoder(settings, params, checked)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "line",
    [
        "Error parsing option bad-key: 1.",
        "Invalid value for colorprim: ebu3213.",
        "Unknown option: bogus.",
        "Unrecognized parameter bad-key",
        "Failed to set parameter bad-key",
    ],
)
def test_rejection_patterns(line: str) -> None:
    from lastencode.encoder_check import rejected_options

    assert rejected_options("harmless warning\n" + line) == [line]


def test_source_parameters_checked_before_first_encode(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.planning as planning
    from lastencode.commands.convert import Plan

    source = tmp_path / "in"
    build_small(source / "a.mp4")
    build_small(source / "b.mp4")
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, ignored = discover([str(source)], tmp_path / "out")
    original = planning.probe

    def probed(path: Path, *, packet_times: bool = False) -> dict[str, object]:
        info = original(path, packet_times=packet_times)
        info["video_bitrate_bps"] = 100_000_000
        if path.name == "b.mp4":
            info["color_primaries"] = "ebu3213"
        return info

    monkeypatch.setattr(planning, "probe", probed)
    plan = Plan(
        sources=sources,
        category=categories["apartment-tour"],
        target="portable",
        zone=ZoneInfo("UTC"),
        output=tmp_path / "out",
        ignored=ignored,
        dry_run=False,
    )
    with pytest.raises(MissingTool, match="colorprim"):
        list(plan.records())
    assert not (tmp_path / "out").exists()
