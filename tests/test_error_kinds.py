"""Slice 18: discoverable error meanings and authoritative exit statuses."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import lastencode.__main__ as entry
import lastencode.commands.bench as bench
import lastencode.commands.convert as convert
from lastencode.errors import ERROR_KINDS
from lastencode.jobs import Run
from lastencode.manifest import load
from lastencode.registry import COMMANDS
from lastencode.run_lock import RunLock
from lastencode.tools import check_tools
from test_runs import make_plan, text_sources

EXPECTED_CODES = {
    "confirmation_required": 1,
    "conflict": 1,
    "internal_error": 1,
    "interrupted": 1,
    "invalid_input": 2,
    "io_error": 1,
    "missing_tool": 3,
    "not_found": 1,
    "sources_failed": 1,
    "unreadable_source": 1,
}
SHARED_KINDS = {
    "invalid_input",
    "not_found",
    "conflict",
    "permission_denied",
    "unauthenticated",
    "timeout",
    "unavailable",
    "outcome_unknown",
    "interrupted",
    "cursor_unavailable",
    "confirmation_required",
    "operation_failed",
    "precondition_failed",
}


def test_d6_error_kinds_in_index(capsys: pytest.CaptureFixture[str]) -> None:
    assert entry.main(["schema"]) == 0
    index = json.loads(capsys.readouterr().out)
    assert index["schema_version"] == "1"
    assert list(index).index("error_kinds") == list(index).index("exit_codes") + 1
    assert index["error_kinds"] == ERROR_KINDS
    assert list(index["error_kinds"]) == sorted(ERROR_KINDS)
    assert set(ERROR_KINDS) == set(EXPECTED_CODES)
    for kind, definition in ERROR_KINDS.items():
        assert set(definition) == {"exit_code", "defined_by", "meaning", "recovery"}
        assert type(definition["exit_code"]) is int
        assert definition["exit_code"] == EXPECTED_CODES[kind]
        for field in ("defined_by", "meaning", "recovery"):
            assert isinstance(definition[field], str) and definition[field]
        assert definition["defined_by"] == (
            "cli-design-standard" if kind in SHARED_KINDS else "lastencode"
        )
    assert entry.main(["schema", "convert"]) == 0
    assert "error_kinds" not in json.loads(capsys.readouterr().out)


def quiet_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass external capability probes, leaving source and filesystem logic real."""
    monkeypatch.setattr(convert, "check_tools", lambda _: {"ffmpeg": "test"})
    monkeypatch.setattr(convert, "probe_encoder", lambda *a, **k: "test")
    monkeypatch.setattr(bench, "check_bench_tools", lambda _: None)
    monkeypatch.setattr(bench, "check_variant_encoders", lambda _: None)


def prepare_failure(
    kind: str,
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    plan: convert.Plan,
) -> tuple[list[str], convert.Plan]:
    source, output = tmp_path / "input", plan.output
    argv = ["convert", "--json"]
    if kind == "invalid_input":
        argv = ["presets", "--unknown"]
    elif kind == "not_found":

        def missing(_: object) -> object:
            return convert.run(
                entry.build_parser().parse_args(
                    [
                        "convert",
                        str(tmp_path / "absent"),
                        "--category",
                        "holiday",
                        "--output-dir",
                        str(output),
                    ]
                )
            )

        monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=missing))
    elif kind == "missing_tool":
        monkeypatch.setenv("PATH", str(tmp_path / "no-tools"))
        monkeypatch.setattr(convert, "check_tools", check_tools)
        monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=convert.run))
        argv = ["convert", str(source), "--category", "holiday", "--output-dir", str(output)]
    elif kind == "confirmation_required":
        plan.force = True
        output.mkdir()
        (output / "0.txt").write_text("protected foreign content")
    elif kind == "sources_failed":
        output.mkdir()
        (output / "0.txt").write_text("protected foreign content")
    elif kind == "unreadable_source":
        (source / "broken.mp4").write_bytes(b"synthetic invalid media")
        plan = make_plan(source, output, fast_presets)
    return argv, plan


def prepare_exception(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> list[str]:
    if kind in ("io_error", "internal_error", "interrupted"):
        error = {
            "io_error": OSError("synthetic disk failure"),
            "internal_error": RuntimeError("synthetic unexpected exception"),
            "interrupted": KeyboardInterrupt(),
        }[kind]

        def failed(_: object) -> object:
            raise error

        monkeypatch.setitem(COMMANDS, "presets", replace(COMMANDS["presets"], run=failed))
        argv = ["presets", "--json"]
    return argv


@pytest.mark.parametrize("kind", EXPECTED_CODES)
def test_f3_every_emitted_kind_is_listed(
    kind: str,
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiet_tools(monkeypatch)
    source = text_sources(tmp_path, 1)
    output = tmp_path / "out"
    plan = make_plan(source, output, fast_presets)
    monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=lambda _: plan))
    argv, plan = prepare_failure(kind, tmp_path, fast_presets, monkeypatch, plan)
    argv = prepare_exception(kind, monkeypatch, argv)
    if kind == "conflict":
        with RunLock(output):
            code = entry.main(argv)
    else:
        code = entry.main(argv)
    captured = capsys.readouterr()
    assert json.loads(captured.err.splitlines()[-1])["error"]["kind"] == kind
    assert code == ERROR_KINDS[kind]["exit_code"] == EXPECTED_CODES[kind]
    if kind in ("sources_failed", "unreadable_source"):
        summary = json.loads(captured.out.splitlines()[-1])
        assert summary["failures"]
        assert load(output)
        assert plan.exit_code == code


def test_f3_unknown_kind_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(KeyError, match="unlisted"):
        entry.emit_error("unlisted", "Must never emit this kind")
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("command", ["presets", "convert", "bench"])
@pytest.mark.parametrize("contents", [None, "broken = [", "[categories.holiday]\nunknown = true"])
def test_f3_invalid_preset_writes_nothing(
    tmp_path: Path,
    command: str,
    contents: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preset = tmp_path / "bad.toml"
    if contents is not None:
        preset.write_text(contents)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    argv = [command, "--presets", str(preset)]
    if command != "presets":
        argv.extend(["absent", "--category", "holiday", "--output-dir", str(tmp_path / "out")])
    assert entry.main(argv) == ERROR_KINDS["invalid_input"]["exit_code"]
    assert json.loads(capsys.readouterr().err)["error"]["kind"] == "invalid_input"
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("command", ["bench", "convert"])
def test_f3_unreadable_media_commands(
    tmp_path: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiet_tools(monkeypatch)
    source = tmp_path / "input" / "bad.mp4"
    source.parent.mkdir()
    source.write_bytes(b"synthetic invalid media")
    assert (
        entry.main(
            [
                command,
                str(source),
                "--category",
                "holiday",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        == ERROR_KINDS["unreadable_source"]["exit_code"]
    )
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["error"]["kind"] == (
        "unreadable_source"
    )


def test_f3_interrupted_keeps_verified_manifest(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = text_sources(tmp_path, 2)
    output = tmp_path / "out"
    plan = make_plan(source, output, fast_presets)
    original_emit = Run.emit

    def interrupted(self, record, previous=None):
        original_emit(self, record, previous)
        raise KeyboardInterrupt

    monkeypatch.setattr(Run, "emit", interrupted)
    monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=lambda _: plan))
    assert entry.main(["convert", "--json"]) == ERROR_KINDS["interrupted"]["exit_code"]
    assert json.loads(capsys.readouterr().err)["error"]["kind"] == "interrupted"
    records = load(output)
    assert len(records) == 1
    finished = records[str(source / "0.txt")]
    assert finished["status"] == "completed"
    assert finished["output_sha256"]
    assert (output / "0.txt").read_bytes() == (source / "0.txt").read_bytes()
    monkeypatch.setattr(Run, "emit", original_emit)
    resumed = list(make_plan(source, output, fast_presets).records())
    assert resumed[0]["action"] == "skip"
    assert resumed[-1]["failed_count"] == 0


@pytest.mark.parametrize("kind", ["invalid_input", "sources_failed", "unreadable_source"])
def test_f3_exit_status_derived_from_table(
    kind: str,
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiet_tools(monkeypatch)
    plan = make_plan(text_sources(tmp_path, 1), tmp_path / "out", fast_presets)
    argv, plan = prepare_failure(kind, tmp_path, fast_presets, monkeypatch, plan)
    monkeypatch.setitem(COMMANDS, "convert", replace(COMMANDS["convert"], run=lambda _: plan))
    monkeypatch.setitem(ERROR_KINDS, kind, ERROR_KINDS[kind] | {"exit_code": 9})
    assert entry.main(argv) == 9
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["error"]["kind"] == kind
    if kind != "invalid_input":
        assert plan.exit_code == 9
