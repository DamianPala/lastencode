"""Second conformance audit: observable failures, preview and timestamp identity."""

import io
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import lastencode.__main__ as entry
import lastencode.commands.bench as bench
from lastencode.dates import ns_text, text_ns
from lastencode.errors import MissingTool
from lastencode.identity import verify_source
from lastencode.manifest import NAME, load
from lastencode.registry import COMMANDS
from lastencode.run_lock import RunLock
from test_cli import document, validate_schema
from test_copying import build_video
from test_runs import make_plan, text_sources


@pytest.mark.parametrize("fail_last", [False, True])
def test_f1c_closed_pipe_finishes_work(tmp_path: Path, fast_presets: Path, fail_last: bool) -> None:
    source = text_sources(tmp_path)
    output = tmp_path / "out"
    script = tmp_path / "pipe.py"
    script.write_text(
        "import sys, time\n"
        "from dataclasses import replace\n"
        "from pathlib import Path\n"
        "import lastencode.__main__ as entry\n"
        "import lastencode.jobs as jobs\n"
        "from test_runs import make_plan\n"
        "plan = make_plan(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))\n"
        "original = jobs.encode_source\n"
        "def encode(record, **kwargs):\n"
        "    time.sleep(0.15)\n"
        "    if sys.argv[4] == 'True' and record['source_path'].endswith('2.txt'):\n"
        "        raise ValueError('synthetic source failure')\n"
        "    original(record, **kwargs)\n"
        "jobs.encode_source = encode\n"
        "entry.COMMANDS['convert'] = replace(entry.COMMANDS['convert'], run=lambda _: plan)\n"
        "sys.exit(entry.main(['convert', '--json']))\n"
    )
    with subprocess.Popen(
        [sys.executable, str(script), str(source), str(output), str(fast_presets), str(fail_last)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    ) as process:
        assert process.stdout is not None and process.stderr is not None
        first = json.loads(process.stdout.readline())
        assert first["source_path"].endswith("0.txt")
        process.stdout.close()
        errors = process.stderr.read().decode()
        assert process.wait(timeout=30) == int(fail_last), errors
    records = [json.loads(line) for line in (output / NAME).read_text().splitlines()]
    assert [r["record_type"] for r in records] == ["source"] * 3 + ["summary"]
    assert records[-1]["failed_count"] == int(fail_last)
    assert len(load(output)) == 3
    assert (output / "1.txt").read_text() == "synthetic 1"
    assert (output / "2.txt").exists() is not fail_last
    assert "Traceback" not in errors and "BrokenPipeError" not in errors


@pytest.mark.parametrize("command", ["convert", "bench"])
def test_f1d_unreadable_source_not_missing_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    source = tmp_path / "input" / "garbage.mp4"
    source.parent.mkdir()
    source.write_bytes(b"invalid synthetic media")
    monkeypatch.setattr("lastencode.commands.convert.check_tools", lambda _: {"ffmpeg": "test"})
    monkeypatch.setattr("lastencode.commands.convert.probe_encoder", lambda *a, **k: "test")
    monkeypatch.setattr(bench, "check_bench_tools", lambda _: None)
    monkeypatch.setattr(bench, "check_variant_encoders", lambda _: None)
    assert (
        entry.main(
            [command, str(source), "--category", "holiday", "--output-dir", str(tmp_path / "out")]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert json.loads(captured.err.splitlines()[-1])["error"]["kind"] == "unreadable_source"
    assert "Traceback" not in captured.err
    if command == "convert":
        assert json.loads(captured.out.splitlines()[0])["status"] == "failed"


@pytest.mark.parametrize("format_name", ["text", "ndjson"])
@pytest.mark.parametrize("suffix", [".txt", ".mp4"])
def test_f2b_non_utf8_name_no_traceback(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    format_name: str,
    suffix: str,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    raw_path = os.fsencode(source) + b"/clip-\x9b" + suffix.encode()
    if suffix == ".txt":
        Path(os.fsdecode(raw_path)).write_text("synthetic")
    else:
        build_video(Path(os.fsdecode(raw_path)), duration=0.5)
    plan = make_plan(source, tmp_path / "out", fast_presets)
    monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=lambda _: plan))
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    assert entry.main(["convert", "--format", format_name]) == 0
    stream.flush()
    rendered = buffer.getvalue().decode()
    assert "\\udc9b" in rendered
    if format_name == "ndjson":
        path = json.loads(rendered.splitlines()[0])["source_path"]
        assert os.fsencode(path) == raw_path
    manifest = json.loads((plan.output / NAME).read_text().splitlines()[0])
    assert os.fsencode(manifest["source_path"]) == raw_path


def test_f2b_internal_error_object(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_: object) -> object:
        raise RuntimeError("synthetic unexpected failure")

    monkeypatch.setitem(COMMANDS, "presets", replace(COMMANDS["presets"], run=broken))
    assert entry.main(["presets", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["kind"] == "internal_error"
    assert "Traceback" not in captured.err


def test_r4c_dry_run_skips_verified(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = text_sources(tmp_path)
    output = tmp_path / "out"
    list(make_plan(source, output, fast_presets).records())
    before = (output / NAME).read_bytes()

    def forbidden(*_: object) -> str:
        pytest.fail("preview must not hash")

    monkeypatch.setattr("lastencode.identity.sha256", forbidden)
    monkeypatch.setattr("lastencode.conflicts.sha256", forbidden)
    plan = make_plan(source, output, fast_presets)
    plan.dry_run = True
    records = list(plan.records())
    assert [r["action"] for r in records[:-1]] == ["skip"] * 3
    assert records[-1]["targets"] == [
        {"path": str(output / NAME), "effect": "append", "size_bytes": len(before)}
    ]
    assert records[-1]["changed"] is False
    assert (output / NAME).read_bytes() == before
    validate_schema(records[-1], document("schema", "convert")["output"])


def test_f1e_d7_command_success_refinements(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "every file" not in document("schema")["exit_codes"]["0"]
    assert "dry-run" in document("schema", "convert")["exit_codes"]["0"]
    assert "invalid rows" in document("schema", "bench")["exit_codes"]["0"]
    result = {"valid_count": 0, "invalid_count": 2, "rows": [{"valid": False}] * 2}
    monkeypatch.setitem(COMMANDS, "bench", replace(COMMANDS["bench"], run=lambda _: result))
    assert entry.main(["bench", "x", "--category", "holiday", "--output-dir", "out"]) == 0
    assert json.loads(capsys.readouterr().out) == result


def test_d1_output_descriptions_match() -> None:
    description = document("schema", "convert")["output_description"]
    assert "packet presentation times" in description and "otherwise it is unknown" in description
    assert "dry-run succeeds with planned failures" in description
    assert "nominal versus average" not in description


def test_h1a_bench_target_repeatable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_args: list[Any] = []
    monkeypatch.setitem(
        COMMANDS, "bench", replace(COMMANDS["bench"], run=lambda args: captured_args.append(args))
    )
    args = ["bench", "x", "--category", "holiday", "--output-dir", "out"]
    assert entry.main([*args, "--target", "portable", "--target", "desktop"]) == 0
    assert captured_args[0].target == ["portable", "desktop"]
    assert entry.main([*args, "--target", "deskto"]) == 2
    message = json.loads(capsys.readouterr().err)["error"]["message"]
    assert "deskto" in message and "desktop" in message and "--target" in message
    assert entry.main([*args, "--targets", "desktop"]) == 2
    capsys.readouterr()
    assert "repeat fails with conflict" in document("schema", "bench")["description"]


def test_o5d_rfc3339_times(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    path = source / "0.txt"
    exact = 1_700_000_000_123_456_789
    os.utime(path, ns=(exact, exact))
    output = tmp_path / "out"
    record = list(make_plan(source, output, fast_presets).records())[0]
    assert record["source_mtime"] == "2023-11-14T22:13:20.123456789Z"
    assert text_ns(record["source_ctime"]) == path.stat().st_ctime_ns
    assert not {"source_mtime_ns", "source_ctime_ns"} & record.keys()
    persisted = json.loads((output / NAME).read_text().splitlines()[0])
    assert persisted["source_mtime"] == record["source_mtime"]
    assert list(make_plan(source, output, fast_presets).records())[0]["action"] == "skip"
    (output / NAME).unlink()
    recovered = list(make_plan(source, output, fast_presets).records())[0]
    assert recovered["action"] == "skip" and recovered["recovered"] is True
    # A one-nanosecond change invalidates skip and source verification.
    os.utime(path, ns=(exact, exact + 1))
    with pytest.raises(ValueError, match="Source changed"):
        verify_source(record)
    assert list(make_plan(source, output, fast_presets).records())[0]["action"] != "skip"
    assert text_ns(ns_text(-1)) == -1


@pytest.mark.parametrize("error", [OSError("synthetic permission failure"), KeyboardInterrupt()])
def test_f3a_operation_and_cause(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: BaseException
) -> None:
    def fail(_: object) -> object:
        raise error

    monkeypatch.setitem(COMMANDS, "presets", replace(COMMANDS["presets"], run=fail))
    assert entry.main(["presets", "--json"]) == 1
    obj = json.loads(capsys.readouterr().err)["error"]
    assert "lastencode presets" in obj["message"]
    assert (
        "synthetic permission failure" in obj["message"]
        if isinstance(error, OSError)
        else ("SIGINT" in obj["message"])
    )


def test_f3a_lock_operation_context(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("synthetic")
    with pytest.raises(OSError, match="Acquire output lock"):
        with RunLock(blocker / "out"):
            pytest.fail("lock cannot be acquired")


def test_r27a_text_bench_preview_lists_files() -> None:
    result = {
        "dry_run": True,
        "variant_count": 1,
        "encode_count": 1,
        "excerpt_count": 1,
        "space_estimate_bytes": 123,
        "targets": [{"effect": "create", "path": "/synthetic/clip.mkv"}],
    }
    assert "create: /synthetic/clip.mkv" in bench.render_text(result)


def test_f1d_missing_tool_still_exit_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(_: object) -> object:
        raise MissingTool("ffprobe: unavailable")

    monkeypatch.setitem(COMMANDS, "presets", replace(COMMANDS["presets"], run=missing))
    assert entry.main(["presets"]) == 3
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["kind"] == "missing_tool" and error["hint"]
