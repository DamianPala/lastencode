"""Synthetic coverage for mirror copies and no-gain video fallback."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import lastencode.encoding as encoding
from lastencode.check_media import scan
from lastencode.encoder_check import check_record_encoders
from lastencode.encoding import encode_source
from lastencode.errors import MissingTool
from lastencode.metadata import exiftool_tags
from lastencode.paths import discover
from lastencode.planning import copy_video, estimate_video_bitrate, plan_source, space_summary
from lastencode.presets import builtin_categories, load_categories
from lastencode.probe import number, object_dict, probe, stream_list
from test_cli import cli

CREATION_DATE = "2026:10:20 12:00:00Z"
GPS = "+37.77490000-122.41940000+15.00/"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def build_video(
    path: Path,
    *,
    duration: float = 1.5,
    pixel_format: str = "yuv420p",
    video_codec: str = "libx264",
    video_bitrate: str | None = None,
    subtitle: Path | None = None,
    location: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=96x64:rate=10:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={duration}",
    ]
    if subtitle:
        command += ["-i", str(subtitle)]
    command += ["-map", "0:v:0", "-map", "1:a:0"]
    if subtitle:
        command += ["-map", "2:s:0"]
    command += ["-c:v", video_codec, "-preset", "ultrafast", "-g", "10"]
    if video_codec == "libx265":
        command += ["-x265-params", "pools=1:frame-threads=1"]
    if video_bitrate:
        command += ["-b:v", video_bitrate, "-maxrate", video_bitrate]
    else:
        command += ["-crf", "40"]
    command += ["-pix_fmt", pixel_format, "-color_trc", "bt709", "-c:a", "aac", "-b:a", "32k"]
    if subtitle:
        command += ["-c:s", "ass"]
    command += ["-metadata", "creation_time=2026-10-20T12:00:00Z"]
    if location:
        command += ["-metadata", f"location={GPS}"]
    if path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        command += ["-movflags", "+faststart"]
    command.append(str(path))
    run(command)
    return path


def add_quicktime_tags(path: Path) -> Path:
    run(
        [
            "exiftool",
            "-overwrite_original",
            "-api",
            "QuickTimeUTC=1",
            f"-QuickTime:CreateDate={CREATION_DATE}",
            f"-Keys:GPSCoordinates={GPS}",
            f"-UserData:GPSCoordinates={GPS}",
            str(path),
        ]
    )
    return path


def add_rotation(path: Path, rotation: int) -> Path:
    rotated = path.with_name(f"{path.stem}.rotated{path.suffix}")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-display_rotation:v:0",
            str(rotation),
            "-i",
            str(path),
            "-map",
            "0",
            "-c",
            "copy",
            str(rotated),
        ]
    )
    rotated.replace(path)
    return path


def make_record(
    source: Path,
    output: Path,
    presets: Path,
    *,
    target: str = "portable",
    force_encode: bool = False,
    strip_location: bool = False,
) -> dict[str, Any]:
    categories = {item.name: item for item in load_categories(str(presets))}
    sources, _ = discover([str(source)], output)
    record = plan_source(
        sources[0],
        categories["apartment-tour"],
        target,
        ZoneInfo("UTC"),
        strip_location,
    )
    if force_encode:
        record["action"] = "encode"
        try:
            check_record_encoders([record], set())
        except MissingTool as error:
            pytest.skip(str(error))
    encode_source(record)
    return record


def force_no_gain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: True)


@pytest.mark.needs_media
def test_r13c_no_gain_fallback_keeps_above_cap_source_rate(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input" / "sixty-fps.mp4"
    source.parent.mkdir()
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x808080:s=160x120:r=60:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-qp",
            "0",
            "-g",
            "60",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-metadata",
            "creation_time=2026-10-20T12:00:00Z",
            "-movflags",
            "+faststart",
            str(source),
        ]
    )
    categories = {item.name: item for item in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "output")
    record = plan_source(sources[0], categories["webinar"], "portable", ZoneInfo("UTC"))
    assert record["frame_rate_cap"] == 25
    assert record["action"] == "encode"
    try:
        check_record_encoders([record], set())
    except MissingTool as error:
        pytest.skip(str(error))
    force_no_gain(monkeypatch)
    encode_source(record)
    assert record["status"] == "completed", record["checks"]
    assert record["action"] == "no-gain"
    assert record["frame_rate_cap"] is None
    assert record["frame_rate_change"] == "native (no-gain)"
    original_frames = len(scan(source).times)
    copied_frames = len(scan(Path(str(record["output_path"]))).times)
    assert copied_frames == original_frames


def packet_hashes(path: Path, streams: str = "v:0") -> list[str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            streams,
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-show_entries",
            "packet=data_hash",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [str(item["data_hash"]) for item in json.loads(result.stdout)["packets"]]


def assert_no_keyframe_check(record: dict[str, Any]) -> None:
    assert "Keyframes" not in {check["name"] for check in record["checks"]}


@pytest.mark.needs_media
def test_copy_files_hash_mtime_skip_and_recopies_after_mtime_change(
    tmp_path: Path, fast_presets: Path
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "notes.txt").write_text("course notes\n", encoding="utf-8")
    (source / "slides.pdf").write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 4)
    for path in source.iterdir():
        os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    output = tmp_path / "mirror"

    first = cli(
        "convert",
        str(source),
        "--output-dir",
        str(output),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    )
    first_records = [json.loads(line) for line in first.stdout.splitlines()]
    assert first.returncode == 0, first.stderr
    assert [item["action"] for item in first_records[:-1]] == ["copy-file", "copy-file"]
    for item in first_records[:-1]:
        original = Path(item["source_path"])
        mirrored = Path(item["output_path"])
        assert mirrored.read_bytes() == original.read_bytes()
        assert mirrored.stat().st_mtime_ns == original.stat().st_mtime_ns
        assert item["source_sha256"] == item["output_sha256"]
    assert first_records[-1]["actions"] == {"copy-file": 2}

    second = cli(
        "convert",
        str(source),
        "--output-dir",
        str(output),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    )
    second_records = [json.loads(line) for line in second.stdout.splitlines()]
    assert second.returncode == 0, second.stderr
    assert [item["action"] for item in second_records[:-1]] == ["skip", "skip"]

    changed = source / "notes.txt"
    os.utime(changed, ns=(changed.stat().st_atime_ns, changed.stat().st_mtime_ns + 5_000_000_000))
    third = cli(
        "convert",
        str(source),
        "--output-dir",
        str(output),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    )
    third_records = [json.loads(line) for line in third.stdout.splitlines()]
    assert third.returncode == 0, third.stderr
    assert third_records[0]["action"] == "copy-file"
    assert third_records[1]["action"] == "skip"
    assert (output / "notes.txt").stat().st_mtime_ns == changed.stat().st_mtime_ns


@pytest.mark.needs_media
def test_no_gain_mp4_keeps_packets_date_and_gps(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = add_quicktime_tags(add_rotation(build_video(tmp_path / "in" / "clip.mp4"), -90))
    force_no_gain(monkeypatch)
    record = make_record(source, tmp_path / "out", fast_presets, force_encode=True)
    output = Path(record["output_path"])
    assert record["action"] == "no-gain" and record["status"] == "completed", record
    assert output.suffix == ".mp4"
    assert list((tmp_path / "out").iterdir()) == [output]
    assert packet_hashes(source) == packet_hashes(output)
    assert packet_hashes(source, "a:0") == packet_hashes(output, "a:0")
    assert record["recording_date"] == "2026-10-20T12:00:00Z"
    assert record["gps_present"] is True
    assert exiftool_tags(output)["Keys:GPSCoordinates"]
    assert probe(output)["rotation"] == probe(source)["rotation"] == -90
    assert space_summary([record], tmp_path / "out", [])["actions"] == {"no-gain": 1}
    assert_no_keyframe_check(record)


@pytest.mark.needs_media
def test_no_gain_failing_fast_check_fails_source(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = add_quicktime_tags(build_video(tmp_path / "in" / "clip.mp4"))
    force_no_gain(monkeypatch)
    results = iter((True, False))
    monkeypatch.setattr(encoding, "fast_check", lambda _work, _record: next(results))
    record = make_record(source, tmp_path / "out", fast_presets, force_encode=True)
    assert (record["action"], record["status"]) == ("no-gain", "failed")
    assert space_summary([record], tmp_path / "out", [])["failed_count"] == 1
    assert list((tmp_path / "out").iterdir()) == []


@pytest.mark.parametrize(
    "extension,expected_extension",
    [(".mov", ".mov"), (".mkv", ".mp4")],
)
@pytest.mark.needs_media
def test_no_gain_preserves_mov_and_repacks_compatible_mkv(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    expected_extension: str,
) -> None:
    source = build_video(tmp_path / "in" / f"clip{extension}")
    if extension == ".mov":
        add_quicktime_tags(source)
    force_no_gain(monkeypatch)
    record = make_record(source, tmp_path / "out", fast_presets, force_encode=True)
    output = Path(record["output_path"])
    assert record["status"] == "completed", record
    assert record["action"] == "no-gain"
    assert output.suffix == expected_extension
    assert packet_hashes(source) == packet_hashes(output)
    assert_no_keyframe_check(record)


def ass_fixture(path: Path) -> Path:
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,1,1,0,2,10,10,10,1\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Synthetic subtitle\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("strip_location", "location"), [(False, True), (True, True), (True, False)]
)
@pytest.mark.needs_media
def test_incompatible_mkv_uses_byte_copy_or_fails_when_stripping_location(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    strip_location: bool,
    location: bool,
) -> None:
    subtitle = ass_fixture(tmp_path / "subtitle.ass")
    source = build_video(tmp_path / "in" / "clip.mkv", subtitle=subtitle, location=location)
    force_no_gain(monkeypatch)
    record = make_record(
        source,
        tmp_path / "out",
        fast_presets,
        force_encode=True,
        strip_location=strip_location,
    )
    output = Path(record["output_path"])
    if strip_location:
        assert record["status"] == "failed"
        assert "must strip source location" in str(record["reason"])
        assert not output.exists()
        return
    assert record["status"] == "completed", record
    assert record["action"] == "no-gain"
    assert output.suffix == ".mkv"
    assert output.read_bytes() == source.read_bytes()
    assert record["source_sha256"] == record["output_sha256"]
    assert record["source_sha256"]
    assert record["checks"][0]["name"] == "ByteCopy"


@pytest.mark.needs_media
def test_mkv_missing_stream_bitrate_uses_duration_estimate(
    tmp_path: Path, fast_presets: Path
) -> None:
    source = build_video(
        tmp_path / "in" / "low-bitrate.mkv",
        duration=4,
        video_bitrate="100k",
    )
    info = probe(source)
    video = next(
        stream for stream in stream_list(info["streams"]) if stream["codec_type"] == "video"
    )
    assert video.get("bit_rate") in (None, "N/A")
    categories = {item.name: item for item in load_categories(str(fast_presets))}
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(sources[0], categories["apartment-tour"], "portable", ZoneInfo("UTC"))
    assert record["action"] == "copy-video"
    assert record["video_bitrate_estimated"] is True
    probed = object_dict(record["probe"])
    assert probed["video_bitrate_estimated"] is True
    duration = float(str(probed["duration_seconds"]))
    audio_bitrate = sum(
        number(stream.get("bit_rate")) or 0 for stream in stream_list(probed.get("audio_streams"))
    )
    source_size = int(str(record["source_size_bytes"]))
    expected = max(0, (source_size - audio_bitrate * duration / 8) * 8 / duration)
    assert probed["video_bitrate_bps"] == pytest.approx(expected)


def test_unknown_duration_does_not_estimate_bitrate() -> None:
    info: dict[str, object] = {
        "video_codec": "h264",
        "video_bitrate_bps": None,
        "duration_seconds": None,
        "audio_streams": [],
    }
    assert not estimate_video_bitrate(info, 100_000)
    assert info["video_bitrate_bps"] is None
    settings = builtin_categories()["apartment-tour"].settings["portable"]
    assert not copy_video(info, settings)
