"""Third conformance audit: non-UTF-8 names, lock hint, time fields and help text."""

import csv
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import lastencode.__main__ as entry
import lastencode.commands.bench as bench
import lastencode.encoding as encoding
from fixture_builders import _run
from lastencode.dates import text_ns
from lastencode.encoder_check import check_record_encoders
from lastencode.encoding import encode_source
from lastencode.errors import ERROR_KINDS, Conflict, Locked, MissingTool
from lastencode.paths import discover
from lastencode.planning import plan_source
from lastencode.presets import builtin_categories, load_categories
from lastencode.probe import FRAME_KEYS, decoded_frames, first_frame
from lastencode.registry import COMMANDS
from lastencode.run_lock import RunLock
from test_cli import document, validate_schema
from test_copying import build_video, force_no_gain
from test_runs import make_plan, text_sources

RFC3339_NS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z")


def non_utf8_path(folder: Path, name: bytes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(os.fsdecode(os.fsencode(folder) + b"/" + name))


def run_action(source: Path, output: Path, presets: Path, action: str) -> dict[str, Any]:
    categories = {item.name: item for item in load_categories(str(presets))}
    sources, _ = discover([str(source)], output)
    record = plan_source(sources[0], categories["apartment-tour"], "portable", ZoneInfo("UTC"))
    record["action"] = action
    try:
        check_record_encoders([record], set())
    except MissingTool as error:
        pytest.skip(str(error))
    encode_source(record)
    return record


@pytest.mark.parametrize("mode", ["encode", "copy-video", "no-gain"])
@pytest.mark.needs_media
@pytest.mark.linux_only
def test_serious_non_utf8_name_passes_checks(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    source = build_video(non_utf8_path(tmp_path / "input", b"bad\xffname.mp4"))
    if mode == "no-gain":
        force_no_gain(monkeypatch)
    else:
        monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
    action = "copy-video" if mode == "copy-video" else "encode"
    record = run_action(source, tmp_path / "out", fast_presets, action)
    assert record["status"] == "completed", record.get("reason")
    assert record["action"] == mode
    assert record["failing_check"] is None
    assert b"bad\xffname" in os.fsencode(record["output_path"])
    assert Path(record["output_path"]).is_file()
    keyframes = [check for check in record["checks"] if check["name"] == "Keyframes"]
    if mode == "encode":
        # The bitstream read echoes the work file's non-UTF-8 name on stderr.
        assert keyframes[0]["passed"] is True and "random_access_valid" in keyframes[0]["values"]
    elif mode == "copy-video":
        assert keyframes[0]["values"] == {"applicable": False}
    else:
        # No-gain publishes the copy only after the encoded work file passed every check.
        assert not keyframes


@pytest.mark.needs_media
@pytest.mark.linux_only
def test_serious_bench_non_utf8_name(tmp_path: Path) -> None:
    missing = non_utf8_path(tmp_path / "media", b"bad\xffname.mp4")
    # ffmpeg echoes the input path in its error; decoding must not fail on its bytes.
    result = bench.capture_result(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(missing)])
    assert result.returncode != 0
    assert "bad\udcffname" in result.stderr
    row: dict[str, object] = {
        "source": str(missing),
        "excerpt_index": 1,
        "valid": False,
        "reason": result.stderr,
    }
    csv_path = tmp_path / "bench.csv"
    bench.write_csv(csv_path, [row])
    assert b"bad\xffname.mp4" in csv_path.read_bytes()
    with csv_path.open(encoding="utf-8", errors="surrogateescape", newline="") as stream:
        assert [os.fsencode(item["source"]) for item in csv.DictReader(stream)] == [
            os.fsencode(missing)
        ]
    before = csv_path.read_bytes()

    class Unwritable:
        def __str__(self) -> str:
            raise RuntimeError("synthetic CSV failure")

    with pytest.raises(RuntimeError, match="synthetic CSV failure"):
        bench.write_csv(csv_path, [row | {"reason": Unwritable()}])
    assert csv_path.read_bytes() == before
    assert not (tmp_path / ".bench.csv.tmp").exists()


@pytest.mark.slow
@pytest.mark.needs_media
@pytest.mark.linux_only
def test_serious_bench_non_utf8_name_end_to_end(
    tmp_path: Path, fast_presets: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = non_utf8_path(tmp_path / "input", b"bad\xffname.mp4")
    # libvmaf's SpEED features reject frames much smaller than 720p.
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1280x720:r=10:d=2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "10",
            str(source),
        ]
    )
    output = tmp_path / "bench"
    arguments = [
        "bench",
        str(source),
        "--category",
        "apartment-tour",
        "--excerpts",
        "1",
        "--excerpt-seconds",
        "1",
        "--quality-settings",
        "40",
        "--output-dir",
        str(output),
        "--presets",
        str(fast_presets),
        "--json",
    ]
    assert entry.main(arguments) == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["valid_count"] == 1, [row["reason"] for row in result["rows"]]
    assert b"bad\xffname.mp4" in (output / "bench.csv").read_bytes()
    assert not (output / ".bench.csv.tmp").exists()


def test_f3b_lock_conflict_hint(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out"
    plan = make_plan(text_sources(tmp_path), output, fast_presets, force=True)
    monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=lambda _: plan))
    with RunLock(output):
        with pytest.raises(Locked):
            RunLock(output).acquire()
        assert entry.main(["convert", "--force", "--json"]) == 1
    error = json.loads(capsys.readouterr().err.splitlines()[-1])["error"]
    assert error["kind"] == "conflict"
    assert "locked by run" in error["message"]
    assert "--force" not in error["hint"] and error["hint"].startswith("Wait for the run")
    assert entry.failure_guidance(Conflict("planned file exists"))[1].endswith(
        "use --force only for intended replacements."
    )
    recovery = ERROR_KINDS["conflict"]["recovery"]
    assert "wait for the run" in recovery and "does not clear it" in recovery


@pytest.mark.needs_media
def test_o5d_metadata_check_times(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4")
    exact = 1_700_000_000_123_456_700
    os.utime(source, ns=(exact, exact))
    record = run_action(source, tmp_path / "out", fast_presets, "copy-video")
    assert record["status"] == "completed", record.get("reason")
    metadata = next(check for check in record["checks"] if check["name"] == "Metadata")
    values = metadata["values"]
    assert not {key for key in values if key.endswith("_seconds")}
    assert values["source_mtime"] == "2023-11-14T22:13:20.123456700Z"
    assert RFC3339_NS.fullmatch(values["file_mtime"])
    assert text_ns(values["file_mtime"]) == Path(record["output_path"]).stat().st_mtime_ns
    first_frame = record["probe"]["first_frame"]
    assert set(first_frame) <= {*FRAME_KEYS, "duration_seconds"}
    assert {"pts", "pkt_dts", "duration", "best_effort_timestamp"}.isdisjoint(first_frame)
    assert first_frame["duration_seconds"] == pytest.approx(0.1)
    schema = document("schema", "convert")
    validate_schema(record["probe"], schema["output"]["properties"]["probe"])
    assert (
        "duration_seconds"
        in schema["output"]["properties"]["probe"]["properties"]["first_frame"]["properties"]
    )
    assert "file_mtime and source_mtime values" in schema["output_description"]


def test_i1d_include_25_fps_description(capsys: pytest.CaptureFixture[str]) -> None:
    flags = {flag["name"]: flag for flag in document("schema", "bench")["flags"]}
    description = flags["include-25-fps"]["description"]
    assert "Without it, the native variants already follow the preset's frame-rate cap" in (
        description
    )
    assert "uncapped" in description and "25 fps" in description and "is added" in description
    with pytest.raises(SystemExit):
        entry.main(["bench", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "variants follow the preset's frame-rate cap" in help_text
    assert "keep the source rate uncapped and a 25 fps set is added" in help_text


def test_d1_root_help_purpose(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        entry.main(["--help"])
    raw = capsys.readouterr().out
    # argparse prints usage, then the description paragraph, then the argument groups.
    purpose = " ".join(raw.split("\n\n")[1].split())
    assert purpose.startswith("Re-encode video recordings")
    for name in ("presets", "convert", "bench"):
        assert re.search(rf"\b{name}\b", purpose), name
    assert "every command defaults to JSON outside a terminal" in " ".join(raw.split())
    # The epilog claim holds for every command, introspection included.
    index = document("schema")
    assert index["format_defaults"]["non_tty"] == "json"
    for name in COMMANDS:
        defaults = COMMANDS[name].format_defaults or index["format_defaults"]
        assert defaults["non_tty"] == "json", name


@pytest.mark.needs_media
def test_d58_first_frame_after_leading_b_frames(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    cut = tmp_path / "input" / "cut.mp4"
    cut.parent.mkdir()
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x240:r=25:d=6",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-bf",
            "3",
            "-g",
            "50",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )
    # Input seeking with stream copy starts the cut mid-GOP: its first packets never display.
    _run(["ffmpeg", "-v", "error", "-ss", "1.3", "-i", str(source), "-c", "copy", str(cut)])
    assert not decoded_frames(cut, 1)
    frame = first_frame(cut)
    assert frame["interlaced_frame"] == 0 and frame["duration_seconds"] == pytest.approx(0.04)
    sources, _ = discover([str(cut)], tmp_path / "out")
    record = plan_source(sources[0], builtin_categories()["holiday"], "portable", ZoneInfo("UTC"))
    assert record["status"] == "planned", record.get("reason")
    assert record["failing_check"] is None


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param("unreadable", marks=pytest.mark.posix_only),
        "copy",
    ],
)
def test_r20_copy_file_failing_check(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source = text_sources(tmp_path, 1)
    path = source / "0.txt"
    if failure == "unreadable":
        if sys.platform != "win32" and os.geteuid() == 0:
            pytest.skip("root reads mode-000 files")
        path.chmod(0)
    else:

        def broken_copy(*_: object) -> None:
            raise OSError("synthetic copy failure")

        monkeypatch.setattr(encoding.shutil, "copyfile", broken_copy)
    try:
        records: list[Any] = list(make_plan(source, tmp_path / "out", fast_presets).records())
    finally:
        path.chmod(0o600)
    record, summary = records
    assert record["action"] == "copy-file" and record["status"] == "failed"
    assert record["failing_check"] == "CopyFile"
    assert [(c["name"], c["passed"]) for c in record["checks"]] == [("CopyFile", False)]
    assert summary["failures"][0]["failing_check"] == "CopyFile"
