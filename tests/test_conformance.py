"""Slice 15 regressions for the CLI Design Standard contract."""

import json
import threading
from pathlib import Path
from typing import Any

import pytest

import lastencode.commands.bench as bench
import lastencode.conflicts as conflicts
import lastencode.jobs as jobs
from lastencode.__main__ import build_parser, main
from lastencode.errors import ConfirmationRequired
from lastencode.identity import sha256
from lastencode.manifest import append
from lastencode.run_lock import probe_lock, try_exclusive_lock, unlock
from test_cli import assert_invalid, cli, document, validate_schema
from test_runs import make_plan, text_sources


def test_r26b_force_replace_needs_confirmation(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "0.txt"
    existing.write_text("precious foreign file")
    plan = make_plan(source, output, fast_presets, force=True)
    plan.machine = True
    with pytest.raises(ConfirmationRequired, match="--yes"):
        list(plan.records())
    assert existing.read_text() == "precious foreign file"
    assert sorted(p.name for p in output.iterdir()) == ["0.txt"]
    plan.dry_run = True
    summary = list(plan.records())[-1]
    assert summary["requires_confirmation"] is True
    assert summary["targets"] == [
        {"path": str(existing), "size_bytes": existing.stat().st_size, "effect": "replace"},
        {"path": str(output / "lastencode-manifest.jsonl"), "size_bytes": None, "effect": "create"},
    ]
    plan.dry_run, plan.yes = False, True
    assert list(plan.records())[0]["status"] == "completed"
    assert existing.read_text() == "synthetic 0"


@pytest.mark.parametrize("protected", ["foreign-tag", "trashed-original", "same-source"])
def test_r6b_confirmation_scope(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, protected: str
) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    output.mkdir()
    path = output / "0.txt"
    path.write_text("old encoded output")
    source_path = source / "0.txt"
    tag = {"source_sha256": sha256(source_path) if protected == "same-source" else "other"}
    monkeypatch.setattr(conflicts, "output_tag", lambda _: tag)
    if protected == "trashed-original":
        append(
            output,
            {
                "source_path": str(source_path),
                "output_path": str(path),
                "trash_outcome": {"status": "trashed"},
            },
        )
    plan = make_plan(source, output, fast_presets, force=True)
    records: list[dict[str, object]] = [
        {
            "source_path": str(source_path),
            "output_path": str(path),
            "no_gain_path": str(path),
            "status": "planned",
        }
    ]
    assert plan.trash_preview(records)["requires_confirmation"] is (protected != "same-source")
    if protected == "same-source":
        assert list(plan.records())[0]["status"] == "completed"
    else:
        with pytest.raises(ConfirmationRequired):
            list(plan.records())
        assert path.read_text() == "old encoded output"


@pytest.fixture
def bench_args(phone_clip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(bench, "check_bench_tools", lambda _: None)
    monkeypatch.setattr(bench, "check_variant_encoders", lambda _: None)
    return [
        "bench",
        str(phone_clip),
        "--category",
        "apartment-tour",
        "--output-dir",
        str(tmp_path / "bench"),
        "--excerpts",
        "1",
        "--excerpt-seconds",
        "1",
        "--quality-settings",
        "28",
        "--json",
    ]


@pytest.mark.parametrize("folder", ["csv", "excerpts", "variants", "side-by-side"])
@pytest.mark.needs_media
@pytest.mark.linux_only
def test_r27b_bench_conflict_exit_1(
    bench_args: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str], folder: str
) -> None:
    assert main([*bench_args, "--dry-run"]) == 0
    planned = json.loads(capsys.readouterr().out)
    paths = [Path(t["path"]) for t in planned["targets"]]
    existing = paths[0] if folder == "csv" else next(p for p in paths if p.parent.name == folder)
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("precious previous result")
    for extra in ([], ["--dry-run"]):
        assert main([*bench_args, *extra]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        error = json.loads(captured.err)["error"]
        assert error["kind"] == "conflict"
        assert str(existing) in error["message"]
        assert existing.read_text() == "precious previous result"
    assert main([*bench_args, "--force", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["requires_confirmation"] is False


@pytest.mark.needs_media
@pytest.mark.linux_only
def test_r27a_bench_preview_targets_and_changed(
    bench_args: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*bench_args, "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    validate_schema(result, document("schema", "bench")["output"])
    assert result["changed"] is False and result["requires_confirmation"] is False
    assert len(result["targets"]) == 4
    assert {t["effect"] for t in result["targets"]} == {"create"}
    assert result["csv_path"] in [t["path"] for t in result["targets"]]
    assert len(result["excerpt_paths"]) == 1
    assert not (tmp_path / "bench").exists()


def test_r4b_dry_run_planned_failure_succeeds(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "out"
    output.mkdir()
    (output / "0.txt").write_text("foreign")
    plan = make_plan(source, output, fast_presets)
    plan.dry_run = True
    records = list(plan.records())
    assert records[0]["status"] == "failed"
    assert plan.exit_code == 0
    assert not (output / ".lastencode.lock").exists()


def test_r4c_create_targets(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "out"
    plan = make_plan(source, output, fast_presets)
    plan.dry_run = True
    summary = list(plan.records())[-1]
    assert summary["changed"] is False and summary["requires_confirmation"] is False
    assert summary["targets"] == [
        {"path": str(output / "0.txt"), "size_bytes": None, "effect": "create"},
        {"path": str(output / "lastencode-manifest.jsonl"), "size_bytes": None, "effect": "create"},
    ]
    assert not output.exists()


def walk_schema(schema: dict[str, Any]) -> None:
    if not schema:
        return
    assert "type" in schema
    assert set(schema) <= {
        "type",
        "enum",
        "properties",
        "required",
        "items",
        "description",
        "title",
    }
    for child in schema.get("properties", {}).values():
        walk_schema(child)
    if "items" in schema:
        walk_schema(schema["items"])


def test_o4a_schemas_use_subset_only() -> None:
    from lastencode.registry import COMMANDS

    walk_schema(COMMANDS["schema"].output)
    index = document("schema")
    for command in index["commands"]:
        walk_schema(document("schema", command["name"])["output"])


def test_i1a_repeatable_bench_values() -> None:
    args = build_parser().parse_args(
        [
            "bench",
            "--target",
            "portable",
            "--target",
            "desktop",
            "--quality-settings",
            "26",
            "--quality-settings",
            "28",
            "--category",
            "webinar",
            "--output-dir",
            "out",
            "source.mp4",
        ]
    )
    assert args.target == ["portable", "desktop"]
    assert args.quality_settings == [26, 28]
    assert args.sources == ["source.mp4"]
    flags = {f["name"]: f for f in document("schema", "bench")["flags"]}
    for name in ("target", "quality-settings"):
        assert flags[name]["repeatable"] is True
        assert flags[name]["type"] in ("string", "integer")
        assert "items" not in flags[name]


@pytest.mark.parametrize(
    "args",
    [
        ("convert", "--output-dir", "a", "--output-dir", "b"),
        ("convert", "--category", "holiday", "--category", "webinar"),
        ("--presets", "a", "presets", "--presets", "b"),
        ("bench", "--excerpts", "1", "--excerpts=2"),
        ("convert", "--force", "--force"),
    ],
)
def test_i6a_repeated_flag_is_usage_error(args: tuple[str, ...]) -> None:
    assert_invalid(cli(*args), "once")


@pytest.mark.parametrize("dry_run", [True, False])
def test_r3b_lock_precedes_confirmation(tmp_path: Path, fast_presets: Path, dry_run: bool) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "out"
    output.mkdir()
    (output / "0.txt").write_text("protected foreign file")
    lock = output / ".lastencode.lock"
    lock.write_text("synthetic lock owner")
    plan = make_plan(source, output, fast_presets, force=True)
    plan.dry_run = dry_run
    with lock.open("r+b") as held:
        try_exclusive_lock(held.fileno())
        from lastencode.errors import Conflict

        with pytest.raises(Conflict, match="locked"):
            list(plan.records())
        unlock(held.fileno())
    assert lock.read_text() == "synthetic lock owner"
    probe_lock(output)
    assert lock.read_text() == "synthetic lock owner"
    assert (output / "0.txt").read_text() == "protected foreign file"


def test_i1d_descriptions_state_rules() -> None:
    flags = {f["name"]: f["description"] for f in document("schema", "bench")["flags"]}
    assert "presets" in flags["category"]
    assert "0-51" in flags["quality-settings"] and "1-63" in flags["quality-settings"]
    assert "Positive" in flags["excerpts"] and "Positive" in flags["excerpt-seconds"]
    flags = {f["name"]: f["description"] for f in document("schema", "convert")["flags"]}
    assert "--trash-originals" in flags["force"] and "other paths" in flags["force"]


def test_d3b_help_and_exit_3_description() -> None:
    help_text = cli("convert", "--help").stdout
    assert "[--output-dir DIR]" in help_text and "[--category" not in help_text
    assert "Files or recursive folders" in help_text
    assert "portable (default) or desktop" in help_text
    assert "TTY" in help_text and "NDJSON otherwise" in help_text
    assert "Video files or folders" in cli("bench", "--help").stdout
    exit_3 = document("schema")["exit_codes"]["3"]
    for word in ("missing", "unusable", "old", "encoder", "filter", "model"):
        assert word in exit_3


def test_d7_format_defaults_only_when_different() -> None:
    for command in ("convert", "bench", "presets"):
        assert "format_defaults" not in document("schema", command)


def test_d5e_schema_schema_is_unknown() -> None:
    assert_invalid(cli("schema", "schema"), "unknown command path")


def test_r4_stream_order_with_jobs(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = text_sources(tmp_path, 3)
    output = tmp_path / "out"
    later_finished = threading.Event()
    real_encode = jobs.encode_source

    def encode(record: dict[str, object], *, jobs: int = 1) -> None:
        if str(record["source_path"]).endswith("0.txt"):
            assert later_finished.wait(timeout=10)
        real_encode(record, jobs=jobs)

    real_emit = jobs.Run.emit

    def emit(self: jobs.Run, record: dict[str, object], previous: Any = None) -> dict[str, object]:
        result = real_emit(self, record, previous)
        if str(record["source_path"]).endswith("1.txt"):
            later_finished.set()
        return result

    monkeypatch.setattr(jobs, "encode_source", encode)
    monkeypatch.setattr(jobs.Run, "emit", emit)
    records = list(make_plan(source, output, fast_presets, jobs=2).records())
    assert later_finished.is_set()
    assert [Path(str(r["source_path"])).name for r in records[:-1]] == ["0.txt", "1.txt", "2.txt"]
    assert records[-1]["record_type"] == "summary"


def test_r4_interrupt_publishes_held_records(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    later_finished = threading.Event()
    real_encode, real_emit = jobs.encode_source, jobs.Run.emit

    def encode(record: dict[str, object], *, jobs: int = 1) -> None:
        if str(record["source_path"]).endswith("0.txt"):
            assert later_finished.wait(timeout=10)
            raise KeyboardInterrupt
        real_encode(record, jobs=jobs)

    def emit(self: jobs.Run, record: dict[str, object], previous: Any = None) -> dict[str, object]:
        result = real_emit(self, record, previous)
        later_finished.set()
        return result

    monkeypatch.setattr(jobs, "encode_source", encode)
    monkeypatch.setattr(jobs.Run, "emit", emit)
    plan = make_plan(text_sources(tmp_path, 2), tmp_path / "out", fast_presets, jobs=2)
    published: list[dict[str, object]] = []
    with pytest.raises(KeyboardInterrupt):
        published.extend(plan.records())
    assert [Path(str(r["source_path"])).name for r in published] == ["1.txt"]


@pytest.mark.needs_media
@pytest.mark.linux_only
def test_r27b_frame_rate_reference_is_a_target(
    bench_args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*bench_args, "--include-25-fps", "--dry-run"]) == 0
    paths = [Path(t["path"]) for t in json.loads(capsys.readouterr().out)["targets"]]
    reference = next(p for p in paths if p.name.endswith("-25fps.mkv"))
    reference.parent.mkdir(parents=True)
    reference.write_text("previous reference")
    assert main([*bench_args, "--include-25-fps", "--dry-run"]) == 1
    assert str(reference) in json.loads(capsys.readouterr().err)["error"]["message"]


def test_i6d_missing_input_is_named(tmp_path: Path) -> None:
    result = cli("convert", "--category", "holiday", "--output-dir", "out")
    assert_invalid(result, "requires SOURCE")
    assert "--output-dir" not in json.loads(result.stderr)["error"]["message"]
    result = cli("convert", str(tmp_path / "missing.mp4"), "--category", "holiday")
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"]["kind"] == "not_found"


@pytest.mark.needs_media
def test_f3c_missing_source_not_found_exit_1(tmp_path: Path) -> None:
    result = cli(
        "convert",
        str(tmp_path / "missing.mp4"),
        "--category",
        "holiday",
        "--output-dir",
        str(tmp_path / "out"),
        "--dry-run",
    )
    assert result.returncode == 1
    assert json.loads(result.stderr)["error"]["kind"] == "not_found"
    assert not (tmp_path / "out").exists()


@pytest.mark.needs_media
@pytest.mark.linux_only
def test_r5a_bench_success_reports_writes_and_force_needs_no_yes(
    bench_args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    for extra in ([], ["--force"]):
        assert main([*bench_args, *extra]) == 0
        result = json.loads(capsys.readouterr().out)
        validate_schema(result, document("schema", "bench")["output"])
        assert result["changed"] is True
        assert result["requires_confirmation"] is False
        assert {t["effect"] for t in result["targets"]} == ({"replace"} if extra else {"create"})
        assert all(Path(t["path"]).is_file() for t in result["targets"])
        assert all(row["valid"] for row in result["rows"])


@pytest.mark.needs_media
@pytest.mark.linux_only
def test_r27b_conflict_names_all_existing_targets(
    bench_args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*bench_args, "--dry-run"]) == 0
    targets = json.loads(capsys.readouterr().out)["targets"]
    for item in targets:
        path = Path(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("previous result")
    assert main([*bench_args, "--dry-run"]) == 1
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["kind"] == "conflict"
    assert all(item["path"] in error["message"] for item in targets)
    assert all(Path(item["path"]).read_text() == "previous result" for item in targets)
