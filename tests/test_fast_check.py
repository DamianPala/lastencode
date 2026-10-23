"""Adversarial publication tests use only generated media in pytest scratch."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from fixture_builders import SIXTY_FPS_TIMES, _run
from lastencode.check_media import (
    Media,
    frame_values,
    nearest_frame_errors,
    on_screen_error,
    scan,
    source_above_frame_rate_cap,
)
from lastencode.encoding import encode_source, result_totals
from lastencode.fast_check import (
    CHECKS,
    Context,
    check_decode,
    check_duration,
    check_frames,
    check_keyframes,
    check_layout,
    check_metadata,
    check_probe,
    check_streams,
    fast_check,
)
from lastencode.paths import discover
from lastencode.presets import load_categories
from test_cli import cli
from test_encoding import build_small, completed, convert


@pytest.fixture
def checked_clip(tmp_path: Path, fast_presets: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "in" / "source.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=10:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=d=4",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-c:a",
            "aac",
            str(source),
        ]
    )
    _run(
        [
            "exiftool",
            "-overwrite_original",
            "-Keys:GPSCoordinates=+52.123456+21.123456/",
            str(source),
        ]
    )
    record = convert(source, tmp_path / "out", fast_presets, force_encode=True)
    return completed(record), record


def remux(path: Path, output: Path, *args: str) -> None:
    _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0", "-c", "copy", *args, str(output)])


def test_good_rows_and_timing(checked_clip: tuple[Path, dict[str, Any]]) -> None:
    work, record = checked_clip
    context = Context(work, record)
    for check in CHECKS:
        result = check(context)
        assert result["passed"], result
    assert fast_check(work, record)
    assert len(record["checks"]) == 10
    print(
        f"phone-independent small clip: encode={record['encode_time_seconds']}, "
        f"check={record['check_time_seconds']}"
    )


def test_probe_rejects_nonvideo(tmp_path: Path) -> None:
    work = tmp_path / "audio.mp4"
    _run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(work)])
    record: dict[str, Any] = {"source_path": str(work)}
    assert not fast_check(work, record)
    assert record["failing_check"] == "Probe"


def test_decode_rejects_truncated(
    checked_clip: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    good, record = checked_clip
    broken = tmp_path / "truncated.mp4"
    data = good.read_bytes()
    broken.write_bytes(data[: len(data) - 1000])
    assert check_probe(Context(broken, record))["passed"]
    assert not check_decode(Context(broken, record))["passed"]


def test_streams_missing_audio(checked_clip: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    good, record = checked_clip
    broken = tmp_path / "silent.mp4"
    remux(good, broken, "-an", "-movflags", "+faststart")
    result = check_streams(Context(broken, record))
    assert not result["passed"]
    assert cast(dict[str, Any], result["values"])["audio_counts"] == (1, 0)


@pytest.mark.parametrize("filter_value", ["select='not(eq(n,12))'", "setpts=PTS+0.005/TB"])
def test_frames_removed_or_shifted(
    checked_clip: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    filter_value: str,
) -> None:
    good, record = checked_clip
    broken = tmp_path / "frames.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(good),
            "-vf",
            filter_value,
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "pools=1",
            "-enc_time_base",
            "1:10000",
            "-fps_mode",
            "passthrough",
            "-c:a",
            "copy",
            str(broken),
        ]
    )
    # R10 deliberately normalizes the first frame. Shift a later timestamp, not the origin.
    if "setpts" in filter_value:
        shifted = tmp_path / "shifted.mp4"
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(good),
                "-vf",
                "setpts=PTS+if(gte(N\\,12)\\,0.005/TB\\,0)",
                "-c:v",
                "libx265",
                "-preset",
                "ultrafast",
                "-x265-params",
                "pools=1",
                "-enc_time_base",
                "1:10000",
                "-fps_mode",
                "passthrough",
                "-c:a",
                "copy",
                str(shifted),
            ]
        )
        broken = shifted
    assert not check_frames(Context(broken, record))["passed"]


def test_duration_rejects_short(checked_clip: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    good, record = checked_clip
    broken = tmp_path / "short.mp4"
    remux(good, broken, "-t", "2")
    assert not check_duration(Context(broken, record))["passed"]


@pytest.mark.parametrize(
    "params,interval",
    [
        ("open-gop=1:keyint=20:min-keyint=20:scenecut=0", "2"),
        ("open-gop=0:keyint=30:min-keyint=30:scenecut=0", "3"),
    ],
)
def test_keyframes_reject_cra_or_long_gap(
    checked_clip: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    params: str,
    interval: str,
) -> None:
    good, record = checked_clip
    broken = tmp_path / "gop.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(good),
            "-an",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "pools=1:" + params,
            "-force_key_frames",
            "expr:gte(t,n_forced*" + interval + ")",
            str(broken),
        ]
    )
    result = check_keyframes(Context(broken, record))
    assert not result["passed"], result


@pytest.mark.parametrize("tag", ["-QuickTime:CreateDate=2001:01:01 00:00:00", "-GPSCoordinates="])
def test_metadata_wrong_date_or_missing_gps(
    checked_clip: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    tag: str,
) -> None:
    good, record = checked_clip
    broken = tmp_path / "metadata.mp4"
    shutil.copyfile(good, broken)
    _run(["exiftool", "-overwrite_original", tag, str(broken)])
    with pytest.raises(ValueError):
        check_metadata(Context(broken, record))


def test_layout_rejects_tail_moov(
    checked_clip: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    good, record = checked_clip
    broken = tmp_path / "tail.mp4"
    remux(good, broken)
    assert not check_layout(Context(broken, record))["passed"]


def inject_output(monkeypatch: pytest.MonkeyPatch, bad: Path) -> None:
    import lastencode.encoding as encoding

    original = subprocess.run

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffmpeg" and command[-1].endswith(".lastencode-part.mp4"):
            shutil.copyfile(bad, command[-1])
            return subprocess.CompletedProcess(command, 0, "", "")
        return original(command, **kwargs)

    monkeypatch.setattr(encoding.subprocess, "run", run)
    # The stub represents an encoder and metadata tool that both report success.
    # Read-back must catch their bad artifact rather than trust those exit codes.
    monkeypatch.setattr(encoding, "apply_metadata", lambda *args: None)


def test_failed_gate_preserves_previous_and_names_check(
    checked_clip: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good, record = checked_clip
    before = good.read_bytes()
    bad = tmp_path / "silent.mp4"
    remux(good, bad, "-an", "-movflags", "+faststart")
    inject_output(monkeypatch, bad)
    record["status"] = "planned"
    encode_source(record)
    assert record["status"] == "failed"
    assert record["failing_check"] == "Streams"
    assert record["reason"].startswith("Streams:")
    assert good.read_bytes() == before
    assert record["output_size_bytes"] is None
    assert not list(good.parent.glob(".*.lastencode-part.*"))


@pytest.mark.parametrize("failure", ["raise", "mismatch"])
def test_postrename_filetime_failure_removes_output(
    checked_clip: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    import lastencode.fast_check as gate

    good, record = checked_clip
    original = os.utime

    def utime(path: Path, **kwargs: Any) -> None:
        if Path(path) == good:
            if failure == "raise":
                raise OSError("deliberate timestamp failure")
            original(path, ns=(0, 0))
        else:
            original(path, **kwargs)

    monkeypatch.setattr(gate.os, "utime", utime)
    record["status"] = "planned"
    encode_source(record)
    assert record["status"] == "failed"
    assert record["failing_check"] == "Metadata"
    assert not good.exists()
    assert not list(good.parent.glob(".*.lastencode-part.*"))


def timeline(times: list[float]) -> Media:
    return Media(
        {
            "streams": [{"index": 0, "codec_type": "video"}],
            "packets": [{"stream_index": 0, "pts_time": t, "duration_time": 0.1} for t in times],
        }
    )


def test_dropped_frames_limits_and_subsequence() -> None:
    source = timeline([i / 10 for i in range(41)])
    assert frame_values(source, timeline([0, 1, 2, 3, 4]), True)["valid"]
    assert frame_values(source, timeline([1.4, 2.4, 3.4, 4.4, 5.4]), True)["valid"]
    assert not frame_values(source, timeline([0, 1.005, 2, 3, 4]), True)["valid"]
    assert not frame_values(source, timeline([0, 1.1, 2, 3, 4]), True)["valid"]
    assert not frame_values(source, timeline([0, 0.001, 1, 2, 3, 4]), True)["valid"]
    sparse = timeline([0, 0.1, 2.5, 3, 4])
    assert frame_values(sparse, timeline([0, 0.1, 2.5, 4]), True)["valid"]


def test_r10b_capped_output_below_window_minimum_fails() -> None:
    source = timeline([index / 60 for index in range(181)])
    output = timeline([index / 20 for index in range(61)])
    values = frame_values(source, output, False, cap=25)
    minimum = values["min_one_second_window_frames"]
    maximum = values["max_one_second_window_frames"]
    assert isinstance(minimum, int) and isinstance(maximum, int)
    assert minimum < 24
    assert maximum <= 25
    assert values["valid"] is False


def test_r10b_source_rate_uses_half_open_windows_and_tolerates_25_fps_jitter() -> None:
    within = timeline([index / 25 + (0.0005 if index % 2 else -0.0005) for index in range(200)])
    above_2997 = timeline([index * 1001 / 30000 for index in range(150)])
    above_30 = timeline([index / 30 for index in range(150)])
    assert source_above_frame_rate_cap(within, 25) is False
    assert source_above_frame_rate_cap(above_2997, 25) is True
    assert source_above_frame_rate_cap(above_30, 25) is True


def test_r10b_sixty_fps_webinar_portable_preserves_flashes_and_beeps(
    sixty_fps_clip: Path, tmp_path: Path, fast_presets: Path
) -> None:
    record = convert(
        sixty_fps_clip,
        tmp_path / "portable-output",
        fast_presets,
        category="webinar",
    )
    assert record["status"] == "completed", record["checks"]
    output = Path(str(record["output_path"]))
    assert record["action"] == "encode"
    assert record["frame_rate_change"] == "60 → 25 fps"
    summary_files = cast(list[dict[str, Any]], result_totals([record])["files"])
    summary_file = summary_files[0]
    assert summary_file["frame_rate_change"] == "60 → 25 fps"
    frame_check = next(check for check in record["checks"] if check["name"] == "Frames")
    assert frame_check["passed"] is True
    assert frame_check["values"]["max_one_second_window_frames"] <= 25

    signal = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"movie={output},signalstats",
            "-show_entries",
            "frame=pts_time:frame_tags=lavfi.signalstats.YAVG",
            "-of",
            "csv=p=0",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    white_times = [
        float(timestamp)
        for timestamp, mean, *_ in (line.split(",") for line in signal.splitlines())
        if float(mean) > 200
    ]
    flash_frames = [
        next(time for time in white_times if start <= time <= start + 0.1)
        for start in SIXTY_FPS_TIMES
    ]
    assert all(
        0 <= frame - start <= 0.04
        for frame, start in zip(flash_frames, SIXTY_FPS_TIMES, strict=True)
    )

    detected = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(output),
            "-map",
            "0:a:0",
            "-af",
            "silencedetect=n=-30dB:d=0.01",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stderr
    beep_starts = [float(value) for value in re.findall(r"silence_end: ([\d.]+)", detected)]
    assert len(beep_starts) >= len(flash_frames)
    assert all(
        abs(beep - flash) <= 0.04 for beep, flash in zip(beep_starts, flash_frames, strict=False)
    )


def test_r10b_sixty_fps_webinar_desktop_caps_before_dropping(
    sixty_fps_clip: Path, tmp_path: Path, fast_presets: Path
) -> None:
    # SVT preset 12 extends the white flash at CRF 50; use R9's bound preset for Colour.
    fast_presets.write_text(
        fast_presets.read_text().replace(
            '[categories.webinar.desktop]\nspeed_preset = "12"',
            '[categories.webinar.desktop]\nspeed_preset = "4"',
        )
    )
    record = convert(
        sixty_fps_clip,
        tmp_path / "desktop-output",
        fast_presets,
        category="webinar",
        target="desktop",
    )
    completed(record)
    frame_check = next(check for check in record["checks"] if check["name"] == "Frames")
    assert frame_check["passed"] is True
    assert frame_check["values"]["max_one_second_window_frames"] <= 25
    assert frame_check["values"]["max_gap_seconds"] <= 1.0000001


def test_r10b_within_cap_webinar_portable_keeps_every_still_frame(
    still_clip: Path, tmp_path: Path, fast_presets: Path
) -> None:
    record = convert(
        still_clip,
        tmp_path / "still-output",
        fast_presets,
        category="webinar",
    )
    completed(record)
    assert record["frame_rate_cap"] is None
    frame_check = next(check for check in record["checks"] if check["name"] == "Frames")
    assert frame_check["passed"] is True
    assert frame_check["values"]["source_count"] == frame_check["values"]["output_count"]


def test_r13a_low_bitrate_source_above_cap_is_encoded_with_reason(
    sixty_fps_clip: Path, tmp_path: Path, fast_presets: Path
) -> None:
    low_bitrate = tmp_path / "low-bitrate-sixty-fps.mp4"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(sixty_fps_clip),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "45",
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            "-movflags",
            "+faststart",
            str(low_bitrate),
        ]
    )
    result = cli(
        "convert",
        str(low_bitrate),
        "--output-dir",
        str(tmp_path.parent / f"{tmp_path.name}-dry-output"),
        "--category",
        "webinar",
        "--target",
        "portable",
        "--presets",
        str(fast_presets),
        "--dry-run",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout.splitlines()[0])
    assert record["probe"]["video_bitrate_bps"] < 300_000
    assert record["action"] == "encode"
    assert record["video_copy_reason"] == "Source exceeds the 25 fps cap; video will be encoded."


@pytest.mark.parametrize("previous,stop", [(False, "kill"), (True, "kill"), (False, "term")])
def test_cli_signal_publication(
    tmp_path: Path,
    fast_presets: Path,
    previous: bool,
    stop: str,
) -> None:
    import signal
    import sys
    import time

    source = tmp_path / "in" / "source.mp4"

    build_small(source)
    output = tmp_path / "out"
    output.mkdir()
    final = output / source.name
    before = source.read_bytes()
    if previous:
        final.write_bytes(before)
    marker = tmp_path / "child.json"
    wrapper = tmp_path / "bin" / "ffmpeg"
    wrapper.parent.mkdir()
    real = shutil.which("ffmpeg")
    wrapper.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        'if sys.argv[-1].endswith(".lastencode-part.mp4"):\n'
        f'    open({str(marker)!r}, "w").write(json.dumps({{"pid": os.getpid()}}))\n'
        '    index = sys.argv.index("-i")\n'
        '    sys.argv[index:index] = ["-re", "-stream_loop", "-1"]\n'
        f"os.execv({real!r}, [{real!r}] + sys.argv[1:])\n"
    )
    wrapper.chmod(0o755)
    environment = dict(os.environ, PATH=str(wrapper.parent) + os.pathsep + os.environ["PATH"])
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "lastencode",
            "convert",
            str(source),
            "--output-dir",
            str(output),
            "--category",
            "apartment-tour",
            "--presets",
            str(fast_presets),
            "--json",
            "--force",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        start_new_session=True,
    )
    child = None
    work = output / ".source.lastencode-part.mp4"
    try:
        deadline = time.monotonic() + 20
        while not work.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert work.exists(), process.communicate(timeout=2)
        child = json.loads(marker.read_text())["pid"]
        if stop == "kill":
            # Kill the group to model an interrupted job without orphaning the test stub.
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.send_signal(signal.SIGTERM)
        _, errors = process.communicate(timeout=10)
        if previous:
            assert final.read_bytes() == before
        else:
            assert not final.exists()
        if stop == "term":
            assert process.returncode == 1
            assert json.loads(errors.splitlines()[-1])["error"]["kind"] == "interrupted"
            assert not list(output.glob(".*.lastencode-part.*"))
            with pytest.raises(ProcessLookupError):
                os.kill(child, 0)
        else:
            assert process.returncode == -signal.SIGKILL
            assert len(list(output.glob(".*.lastencode-part.*"))) == 1
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        kill_child(child)


def kill_child(child: int | None) -> None:
    import signal

    if child is not None:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_failed_check_continues_and_summary_names_it(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lastencode.commands.convert as converting
    import lastencode.encoding as encoding

    source = tmp_path / "in"
    build_small(source / "a.mp4", audio="sine=d=1")
    build_small(source / "b.mp4", audio="sine=d=1")
    bad = tmp_path / "bad.mp4"
    remux(source / "a.mp4", bad, "-an", "-movflags", "+faststart")
    original = encoding.run

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffmpeg" and command[-1].endswith(".a.lastencode-part.mp4"):
            shutil.copyfile(bad, command[-1])
            return subprocess.CompletedProcess(command, 0, "", "")
        return original(command, **kwargs)

    monkeypatch.setattr(encoding, "run", run)
    categories = {c.name: c for c in load_categories(str(fast_presets))}
    sources, ignored = discover([str(source)], tmp_path / "out")
    plan = converting.Plan(
        sources=sources,
        category=categories["apartment-tour"],
        target="portable",
        zone=ZoneInfo("UTC"),
        output=tmp_path / "out",
        ignored=ignored,
        dry_run=False,
    )
    records = list(plan.records())
    assert records[0]["status"] == "failed"
    # Metadata read-back also compares languages/counts, so it may catch this before Streams.
    assert records[0]["failing_check"] in {"Streams", "Metadata"}
    assert records[1]["status"] == "completed"
    summary: Any = records[-1]
    assert summary["failures"][0]["failing_check"] == records[0]["failing_check"]
    assert summary["failures"][0]["source_path"].endswith("a.mp4")
    assert plan.exit_code == 1


def test_phone_gate_timing(phone_clip: Path, tmp_path: Path, fast_presets: Path) -> None:
    record = convert(phone_clip, tmp_path / "out", fast_presets, force_encode=True)
    completed(record)
    encode = record["encode_time_seconds"]
    check = record["check_time_seconds"]
    print(
        f"PHONE_TIMING encode_seconds={encode:.6f} check_seconds={check:.6f} "
        f"ratio={check / encode:.6f}"
    )
    assert len(record["checks"]) == 10


def tail_moov(good: Path, bad: Path) -> None:
    """Move the index back without changing its metadata; repair chunk offsets."""
    import struct

    data = good.read_bytes()
    offset = 0
    while data[offset + 4 : offset + 8] != b"moov":
        offset += struct.unpack_from(">I", data, offset)[0]
    size = struct.unpack_from(">I", data, offset)[0]
    moov = bytearray(data[offset : offset + size])
    cursor = moov.find(b"stco")
    while cursor != -1:
        count = struct.unpack_from(">I", moov, cursor + 8)[0]
        for index in range(count):
            position = cursor + 12 + index * 4
            chunk = struct.unpack_from(">I", moov, position)[0]
            struct.pack_into(">I", moov, position, chunk - size)
        cursor = moov.find(b"stco", cursor + 4)
    bad.write_bytes(data[:offset] + data[offset + size :] + moov)


def malformed_work(name: str, good: Path, bad: Path) -> None:
    if name == "Probe":
        bad.write_bytes(b"not an MP4")
    elif name == "Decode":
        bad.write_bytes(good.read_bytes()[:-1000])
    elif name == "Streams":
        remux(good, bad, "-an", "-movflags", "+faststart")
    elif name == "Duration":
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(good),
                "-f",
                "lavfi",
                "-i",
                "sine=d=6",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                str(bad),
            ]
        )
    elif name == "Layout":
        tail_moov(good, bad)
    elif name == "Metadata":
        shutil.copyfile(good, bad)
        _run(["exiftool", "-overwrite_original", "-GPSCoordinates=", str(bad)])
    else:
        malformed_video(name, good, bad)


def malformed_video(name: str, good: Path, bad: Path) -> None:
    options = (
        ["-vf", "select='not(eq(n,12))'", "-fps_mode", "passthrough"] if name == "Frames" else []
    )
    params = "pools=1:open-gop=1:keyint=20:min-keyint=20:scenecut=0"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(good),
            *options,
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            params,
            "-c:a",
            "copy",
            str(bad),
        ]
    )


@pytest.mark.parametrize(
    "name",
    [
        "Probe",
        "Decode",
        "Streams",
        "Frames",
        "Duration",
        "Keyframes",
        "Metadata",
        "Layout",
    ],
)
def test_each_bad_encoder_artifact_is_denied_publication(
    checked_clip: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    good, record = checked_clip
    before = good.read_bytes()
    bad = tmp_path / "bad.mp4"
    malformed_work(name, good, bad)
    inject_output(monkeypatch, bad)
    record["status"] = "planned"
    encode_source(record)
    assert record["status"] == "failed"
    assert record["failing_check"] == name, record["checks"]
    assert good.read_bytes() == before
    assert record["output_size_bytes"] is None
    assert not list(good.parent.glob(".*.lastencode-part.*"))


def test_copied_packets_match_from_first_frame() -> None:
    source = timeline([0, 0.1, 0.2])
    # A container start offset (MPEG-TS starts near 1,4 s) is not a timing change.
    assert frame_values(source, timeline([1.4, 1.5, 1.6]), False, copying=True)["valid"]
    nudged = timeline([0, 0.101, 0.2])
    assert frame_values(source, nudged, False)["valid"]
    assert not frame_values(source, nudged, False, copying=True)["valid"]
    cut = source.document | {"packets": [{"stream_index": 0, "pts_time": -0.1, "flags": "_D_"}]}
    assert Media(cut).packets == []


@pytest.mark.parametrize("selection", ["not(eq(mod(n,30),28))", "lt(mod(n,30),27)"])
def test_R10b_VFR_gaps_pass_full_gate(tmp_path: Path, fast_presets: Path, selection: str) -> None:
    source = tmp_path / "in" / "vfr.mp4"
    source.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=30:d=4",
            "-vf",
            f"select='{selection}'",
            "-fps_mode",
            "passthrough",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            str(source),
        ]
    )
    record = convert(source, tmp_path / "out", fast_presets, category="webinar", force_smaller=True)
    completed(record)
    assert record["frame_rate_cap"] == 25
    assert all(row["passed"] for row in record["checks"])
    assert len(scan(Path(record["output_path"])).times) > len(scan(source).times) - 30


def test_R10b_held_frame_can_repeat_but_wrong_picture_time_fails() -> None:
    times = [0.0, 0.033333, 0.166667, 0.2]
    errors, matches = nearest_frame_errors(
        times, [0.04, 0.08, 0.12, 0.16], tolerance=0.02, end=0.24
    )
    assert max(errors) <= 0.02
    assert matches[:3] == [1, 1, 1]
    assert on_screen_error(times, 0, 0.12, 0.24) > 0.02
    assert on_screen_error(times, 3, 0.12, 0.24) > 0.02
    assert on_screen_error([0, 0.1], 0, 0.12, 0.2) > 0.02
