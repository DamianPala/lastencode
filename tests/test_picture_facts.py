"""Slice 12 regressions, all media generated under pytest's temporary directories."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from fixture_builders import _run
from lastencode.check_media import Media, on_screen_error, scan
from lastencode.colour_check import colour_values, render_rgb, rgb_means, sample_pairs
from lastencode.commands import bench
from lastencode.fast_check import Context, check_colour, check_colour_tags, check_decode
from lastencode.paths import discover
from lastencode.planning import copy_video, plan_source
from lastencode.presets import builtin_categories
from lastencode.probe import (
    colour_description,
    first_frame,
    light_probe,
    probe,
    stream_list,
)
from lastencode.video import source_fps, video_filters, video_stream
from test_cli import cli
from test_encoding import completed, convert


@pytest.fixture
def samsung(tmp_path: Path) -> Path:
    raw = tmp_path / "raw.mp4"
    source = tmp_path / "in" / "samsung.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=d=2:sample_rate=48000",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-ac",
            "2",
            "-vf",
            "scale=in_range=tv:out_range=pc",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-x264-params",
            "colorprim=bt470bg:transfer=smpte170m:colormatrix=bt470bg:range=full",
            "-color_range",
            "pc",
            "-color_primaries",
            "bt470bg",
            "-color_trc",
            "smpte170m",
            "-colorspace",
            "bt470bg",
            str(raw),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(raw),
            "-c",
            "copy",
            "-color_range",
            "tv",
            "-color_primaries",
            "bt2020",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt2020nc",
            str(source),
        ]
    )
    return source


def video_bytes(path: Path) -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "h264",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


@pytest.mark.parametrize("mode", ["copy", "no-gain-mp4", "no-gain-mov"])
@pytest.mark.needs_media
def test_R12e_bit_identical_header_colours(
    samsung: Path, tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    if mode.endswith("mov"):
        mov = samsung.with_suffix(".mov")
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(samsung),
                "-c",
                "copy",
                "-metadata:s:v",
                "language=eng",
                str(mov),
            ]
        )
        samsung = mov
    if mode != "copy":
        monkeypatch.setattr("lastencode.encoding.not_smaller", lambda *_: True)
    record = convert(samsung, tmp_path / "out", fast_presets, force_encode=mode != "copy")
    output = completed(record)
    assert record["action"] == ("copy-video" if mode == "copy" else "no-gain")
    assert video_bytes(output) == video_bytes(samsung)
    info = probe(output)
    assert stream_list(info["streams"])[0]["color_range"] == "pc"
    assert stream_list(info["streams"])[0]["color_primaries"] == "bt470bg"
    assert check_colour_tags(Context(output, record))["passed"]


@pytest.mark.needs_media
def test_R18_colour_independent_render_and_tags(
    samsung: Path, tmp_path: Path, fast_presets: Path
) -> None:
    record = convert(samsung, tmp_path / "out", fast_presets, force_encode=True, force_smaller=True)
    output = completed(record)
    assert check_colour(Context(output, record))["passed"]
    bad = tmp_path / "wrong.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(samsung),
            "-c",
            "copy",
            "-bsf:v",
            "h264_metadata=colour_primaries=9:transfer_characteristics=1:matrix_coefficients=9",
            "-color_range",
            "pc",
            "-color_primaries",
            "bt2020",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt2020nc",
            str(bad),
        ]
    )
    values = colour_values(samsung, bad, scan(samsung), scan(bad))
    assert not values["valid"], values
    assert not check_colour_tags(Context(samsung, record))["passed"]


@pytest.mark.needs_media
def test_R35a_colour_warnings_plan_manifest_summary(
    samsung: Path, tmp_path: Path, fast_presets: Path
) -> None:
    output = tmp_path / "out"
    args = [
        "convert",
        str(samsung),
        "--output-dir",
        str(output),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--json",
    ]
    for extra in (["--dry-run"], []):
        result = cli(*args, *extra)
        assert result.returncode == 0, result.stderr
        records = [json.loads(line) for line in result.stdout.splitlines()]
        for record in (records[0], records[-1]):
            assert any(
                "color_primaries" in w and "bt2020" in w and "bt470bg" in w
                for w in record["warnings"]
            )
    manifest = json.loads((output / "lastencode-manifest.jsonl").read_text().splitlines()[-2])
    assert any("color_range" in w and "tv" in w and "pc" in w for w in manifest["warnings"])


@pytest.mark.parametrize(
    "property_name,options",
    [
        ("interlaced_frame=1", ["-flags", "+ildct+ilme", "-x264-params", "tff=1"]),
        ("sample_aspect_ratio=16:15", ["-vf", "setsar=16/15"]),
    ],
)
@pytest.mark.needs_media
def test_R36_refuses_before_copy_or_encode(
    tmp_path: Path, fast_presets: Path, property_name: str, options: list[str]
) -> None:
    source = tmp_path / "in" / "unsupported.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=25:d=2",
            "-c:v",
            "libx264",
            *options,
            str(source),
        ]
    )
    frame = first_frame(source)
    assert (
        frame["interlaced_frame"] == 1
        if "interlaced" in property_name
        else (frame["sample_aspect_ratio"] == "16:15")
    )
    for dry in (True, False):
        output = tmp_path / ("dry" if dry else "out")
        result = cli(
            "convert",
            str(source),
            "--output-dir",
            str(output),
            "--category",
            "apartment-tour",
            "--presets",
            str(fast_presets),
            "--json",
            *(["--dry-run"] if dry else []),
        )
        assert result.returncode == (0 if dry else 1), result.stderr
        record = json.loads(result.stdout.splitlines()[0])
        assert record["status"] == "failed" and property_name in record["reason"]
        assert not (output / source.name).exists()
        assert not list(output.glob(".*.lastencode-part.*"))


@pytest.mark.needs_media
def test_R35_packet_rate_and_R18_VFR_decode_regression(tmp_path: Path) -> None:
    source = tmp_path / "jitter.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=5",
            "-vf",
            "settb=1/90000,setpts=N*3000+1400*sin(N*1.7)",
            "-fps_mode",
            "passthrough",
            "-enc_time_base",
            "1/90000",
            "-c:v",
            "libx264",
            str(source),
        ]
    )
    previous = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "non monotonically increasing dts" in previous.stderr
    assert check_decode(Context(source, {}))["passed"]
    info = probe(source, packet_times=True)
    rate = source_fps(video_stream(info))
    assert abs(float(rate) - 30) < 1
    assert str(info["r_frame_rate"]) != str(rate)
    settings: dict[str, Any] = {
        "drop_repeated_frames": True,
        "scale_short_side": 0,
        "bit_depth": 10,
    }
    assert "mpdecimate=max=29" in video_filters(video_stream(info), settings)
    assert info["frame_rate_mode"] == "variable"


@pytest.mark.parametrize("version,code", [("8.1", 3), ("9.0", 0)])
@pytest.mark.needs_media
@pytest.mark.posix_only
def test_R24_ffmpeg_minimum_stub(
    *,
    samsung: Path,
    tmp_path: Path,
    fast_presets: Path,
    version: str,
    code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = shutil.which("ffmpeg")
    stub = tmp_path / "bin" / "ffmpeg"
    stub.parent.mkdir()
    stub.write_text(
        "#!/usr/bin/env python3\nimport os, sys\n"
        f"if '-version' in sys.argv: print('ffmpeg version {version}'); sys.exit(0)\n"
        f"os.execv({real!r}, [{real!r}] + sys.argv[1:])\n"
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(stub.parent) + os.pathsep + os.environ["PATH"])
    result = cli(
        "convert",
        str(samsung),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--dry-run",
        "--json",
    )
    assert result.returncode == code, result.stderr


def test_R35_HDR_frame_transfer_and_fallback() -> None:
    description = colour_description(
        {"color_transfer": "smpte2084", "color_space": "unknown"},
        {"color_transfer": "bt709", "color_space": "bt2020nc"},
    )
    assert description["color_transfer"] == "smpte2084"
    assert description["color_space"] == "bt2020nc"
    info = description | {"video_codec": "hevc", "video_bitrate_bps": 1000, "bit_depth": 8}
    assert copy_video(info, builtin_categories()["apartment-tour"].settings["portable"])


@pytest.mark.needs_media
def test_R35a_duration_warning_does_not_fail(
    samsung: Path, tmp_path: Path, fast_presets: Path
) -> None:
    longer = samsung.with_name("longer.mp4")
    # A longer audio track extends the container without changing any video packet time.
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(samsung),
            "-c:v",
            "copy",
            "-af",
            "apad=pad_dur=2",
            "-c:a",
            "aac",
            str(longer),
        ]
    )
    samsung = longer
    for dry in (True, False):
        result = cli(
            "convert",
            str(samsung),
            "--output-dir",
            str(tmp_path / "out"),
            "--category",
            "apartment-tour",
            "--presets",
            str(fast_presets),
            "--json",
            *(["--dry-run"] if dry else []),
        )
        assert result.returncode == 0, result.stderr
        records = [json.loads(line) for line in result.stdout.splitlines()]
        for record in (records[0], records[-1]):
            assert any(
                "duration" in warning and "4.0" in warning and "2.0" in warning
                for warning in record["warnings"]
            )
    manifest = json.loads(
        (tmp_path / "out" / "lastencode-manifest.jsonl").read_text().splitlines()[-2]
    )
    assert any("duration" in warning for warning in manifest["warnings"])


def media(times: list[float], duration: float) -> Media:
    return Media(
        {
            "streams": [{"index": 0, "codec_type": "video"}],
            "packets": [
                {"stream_index": 0, "pts_time": t, "duration_time": duration} for t in times
            ],
        }
    )


def test_R18_pairs_follow_kept_output_frame_not_arbitrary_sample_time() -> None:
    source = media([i / 60 for i in range(120)], 1 / 60)
    dropped = media([0, 0.5, 1, 1.5], 0.5)
    original, actual = sample_pairs(source, dropped, None)
    assert original == actual
    capped = media([i / 25 for i in range(50)], 1 / 25)
    original, actual = sample_pairs(source, capped, 25)
    assert all(abs(s - t) <= 0.02 for s, t in zip(original, actual, strict=True))
    assert any(s > t for s, t in zip(original, actual, strict=True))


@pytest.mark.needs_media
def test_R18_colour_seeks_one_frame_and_verifies_returned_pts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.colour_check as colours

    source = tmp_path / "frames.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=3",
            "-c:v",
            "libx264",
            "-g",
            "30",
            str(source),
        ]
    )
    commands: list[list[str]] = []
    original = colours.run_bytes

    def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return original(command)

    monkeypatch.setattr(colours, "run_bytes", run)
    values = colour_values(source, source, scan(source), scan(source))
    assert values["valid"]
    assert len(commands) == 10
    for command in commands:
        assert command.index("-ss") < command.index("-i")
        assert command[command.index("-frames:v") + 1] == "1"
        assert "eq(n" not in command[command.index("-vf") + 1]

    expected = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            "select=eq(n\\,2),scale=64:64,format=rgb24",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert render_rgb(source, 0.066667, ["scale=64:64", "format=rgb24"]) == expected

    def wrong_pts(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            command, 0, bytes(64 * 64 * 3), b"[Parsed_showinfo_0] pts_time:0.0"
        )

    monkeypatch.setattr(colours, "run_bytes", wrong_pts)
    with pytest.raises(ValueError, match="requested PTS"):
        render_rgb(source, 1.0, [])


@pytest.mark.needs_media
def test_R18_capped_scene_cut_compares_the_picture_selected_by_fps(
    tmp_path: Path, fast_presets: Path
) -> None:
    source = tmp_path / "in" / "cut.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=160x120:r=60:d=2,drawbox=color=white:t=fill:enable='gte(t,13/60)'",
            "-c:v",
            "libx264",
            "-qp",
            "0",
            str(source),
        ]
    )
    record = convert(source, tmp_path / "out", fast_presets, category="webinar", force_smaller=True)
    output = completed(record)
    assert record["frame_rate_cap"] == 25
    assert rgb_means(source, [0.2], scan(source))[0][0] < 5
    assert rgb_means(output, [0.2], scan(output))[0][0] > 250
    assert next(row for row in record["checks"] if row["name"] == "Colour")["passed"]

    wrong = tmp_path / "wrong-picture.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=160x120:r=25:d=2",
            "-c:v",
            "libx264",
            str(wrong),
        ]
    )
    assert on_screen_error(scan(source).times, 0, 0.6, 2.0) > 0.02
    assert not colour_values(source, wrong, scan(source), scan(wrong), cap=25)["valid"]


@pytest.mark.needs_media
def test_R18_colour_seek_with_MP4_start_offset(tmp_path: Path) -> None:
    source = tmp_path / "offset.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=25:d=4",
            "-c:v",
            "libx264",
            "-g",
            "25",
            "-output_ts_offset",
            "10",
            str(source),
        ]
    )
    original = scan(source)
    assert original.times[0] == 10
    assert colour_values(source, source, original, original)["valid"]


@pytest.mark.needs_media
def test_R35_non_capped_plan_and_light_callers_do_not_scan_whole_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "in" / "long.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x120:r=10:d=30",
            "-c:v",
            "libx264",
            str(source),
        ]
    )
    commands: list[list[str]] = []
    original = subprocess.run

    def run(command: list[str], **kwargs: Any) -> Any:
        if Path(command[0]).stem == "ffprobe":
            commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    sources, _ = discover([str(source)], tmp_path / "out")
    record = plan_source(
        sources[0], builtin_categories()["apartment-tour"], "portable", ZoneInfo("UTC")
    )
    assert record["status"] == "planned"
    packet_reads = [c for c in commands if "-show_packets" in c]
    assert len(packet_reads) == 1
    assert float(packet_reads[0][packet_reads[0].index("-read_intervals") + 1].rstrip("%")) >= 20
    commands.clear()
    light_probe(source)
    assert len(commands) == 1
    assert "-show_frames" not in commands[0] and "-show_packets" not in commands[0]
    commands.clear()
    bench.plan_excerpts(sources, tmp_path / "bench", 1, 2)
    assert all("-show_frames" not in c for c in commands)
    assert all("-show_packets" not in c or "%+#128" in c for c in commands)


@pytest.mark.needs_media
def test_R35a_TS_duration_warning_keeps_review_start_offset_fix(tmp_path: Path) -> None:
    source = tmp_path / "offset.ts"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=25:d=4",
            "-c:v",
            "libx264",
            "-output_ts_offset",
            "10",
            str(source),
        ]
    )
    info = probe(source)
    assert float(str(info["container_start_seconds"])) > 10
    assert not any("duration:" in warning for warning in cast(list[str], info["warnings"]))
    assert colour_values(source, source, scan(source), scan(source))["valid"]


@pytest.mark.needs_media
def test_r12d_acceptance12_phone_webinar_desktop_av1(
    samsung: Path, tmp_path: Path, fast_presets: Path
) -> None:
    # The two-second 320x180 Samsung fixture carries the phone's contradictory colour tags.
    rotated = samsung.with_name("rotated.mp4")
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-display_rotation:v:0",
            "-90",
            "-i",
            str(samsung),
            "-c",
            "copy",
            str(rotated),
        ]
    )
    record = convert(
        rotated,
        tmp_path / "out",
        fast_presets,
        category="webinar",
        target="desktop",
        force_smaller=True,
    )
    output = completed(record)
    info = probe(output, packet_times=True)
    assert record["action"] == "encode"
    assert info["video_codec"] == "av1"
    assert int(str(info["maximum_window_frames"])) <= 25
    assert info["rotation"] == 0
    assert info["color_range"] == "tv"
    assert info["color_primaries"] == info["color_space"] == "bt470bg"
    assert info["color_transfer"] == "smpte170m"
    assert check_colour_tags(Context(output, record))["passed"]
    assert check_colour(Context(output, record))["passed"]
