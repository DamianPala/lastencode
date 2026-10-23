"""Slice 20: synthetic next-to-source runs and read-only path safety."""

import json
import os
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from lastencode.commands.convert import Plan
from lastencode.errors import InvalidInput, Locked
from lastencode.manifest import NAME
from lastencode.paths import Source, discover, run_root, validate_paths
from lastencode.presets import load_categories
from lastencode.run_lock import RunLock, probe_tree_locks
from test_cli import cli, document, validate_schema
from test_copying import build_video


def next_plan(inputs: list[Path], presets: Path, **options: Any) -> Plan:
    root = run_root(list(map(str, inputs)))
    sources, ignored = discover(list(map(str, inputs)), None)
    category = next(c for c in load_categories(str(presets)) if c.name == "apartment-tour")
    return Plan(
        sources=sources,
        ignored=ignored,
        category=category,
        target="portable",
        zone=ZoneInfo("UTC"),
        output=root,
        next_to_source=True,
        folder_input=any(p.is_dir() for p in inputs),
        dry_run=False,
        **options,
    )


@pytest.mark.needs_media
def test_r6c_scenario_r8_allowed_files_and_recovery(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    root = tmp_path / "work"
    first = build_video(root / "clip.mp4", duration=0.5)
    second = build_video(root / "sub" / "b.mov", duration=0.5)
    # Exercise publication independently of fixture compression and encoder versions.
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
    before = {p.relative_to(root) for p in root.rglob("*")}
    initial = list(next_plan([root], fast_presets).records())
    assert all(r["status"] == "completed" for r in initial[:-1]), initial
    expected = {
        Path("clip.lastencode.mp4"),
        Path("sub/b.lastencode.mp4"),
        Path(NAME),
        Path(".lastencode.lock"),
    }
    assert {p.relative_to(root) for p in root.rglob("*")} - before == expected
    assert len((root / NAME).read_text().splitlines()) == 3
    repeat = list(next_plan([root], fast_presets).records())
    assert [r["action"] for r in repeat[:-1]] == ["skip", "skip"]
    assert {
        str(first.with_name("clip.lastencode.mp4")),
        str(second.with_name("b.lastencode.mp4")),
    } <= set(cast(list[str], repeat[-1]["ignored_paths"]))
    for record in repeat:
        validate_schema(record, document("schema", "convert")["output"])
    (root / NAME).unlink()
    recovered = list(next_plan([root], fast_presets).records())
    assert all(r["recovered"] for r in recovered[:-1])


@pytest.mark.needs_media
def test_r6c_no_gain_skip_keeps_original_and_previous_output(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    source = build_video(tmp_path / "work" / "clip.mp4", duration=0.5, location=True)
    original = source.read_bytes()
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: True)
    records = list(next_plan([source], fast_presets).records())
    record = records[0]
    assert (record["action"], record["reason"], record["status"]) == (
        "skip",
        "no-gain",
        "completed",
    )
    assert record["output_sha256"] is None
    assert record["gps_present"] is None
    assert record["dropped_streams"] == []
    assert records[-1]["gps_outputs"] == []
    assert source.read_bytes() == original
    assert not Path(str(record["output_path"])).exists()
    assert not list(source.parent.glob(".*.lastencode-part.*"))

    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
    passed = list(next_plan([source], fast_presets).records())[0]
    output = Path(str(passed["output_path"]))
    previous = output.read_bytes()
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: True)
    forced = list(
        next_plan([source], fast_presets, force=True, trash_originals=True, yes=True).records()
    )[0]
    assert forced["reason"] == "no-gain"
    assert source.read_bytes() == original
    assert output.read_bytes() == previous
    assert cast(dict[str, object], forced["trash_outcome"])["status"] == "kept"


@pytest.mark.needs_media
@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("mirror", [False, True])
def test_r5d_tagged_folder_named_and_force(
    tmp_path: Path,
    fast_presets: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    named: bool,
    force: bool,
    mirror: bool,
) -> None:
    import lastencode.encoding as encoding

    source = build_video(tmp_path / "work" / "clip.mp4", duration=0.5)
    monkeypatch.setattr(encoding, "not_smaller", lambda _encoded, _source: False)
    record = list(next_plan([source], fast_presets).records())[0]
    tagged = Path(str(record["output_path"]))
    assert tagged.exists(), record
    selected = tagged if named else source.parent
    mode = ("--output-dir", str(tmp_path / "archive")) if mirror else ()
    result = cli(
        "--presets",
        str(fast_presets),
        "convert",
        str(selected),
        "--category",
        "apartment-tour",
        "--json",
        "--dry-run",
        *(("--force",) if force else ()),
        *mode,
    )
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert str(tagged) in records[-1]["ignored_paths"]
    assert records[-1]["source_count"] == (0 if named else 1)
    if named:
        actual = cli(
            "--presets",
            str(fast_presets),
            "convert",
            str(tagged),
            "--category",
            "apartment-tour",
            "--force",
            "--json",
        )
        assert actual.returncode == 0, actual.stderr
        assert json.loads(actual.stdout)["source_count"] == 0


def test_r5d_unreadable_tag_is_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import lastencode.conflicts as conflicts
    from lastencode.errors import MissingTool

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"unreadable synthetic input")

    def unreadable(_command: list[str]) -> str:
        raise MissingTool("tag reader failed")

    monkeypatch.setattr(conflicts, "capture", unreadable)
    sources, ignored = discover([str(source)], None)
    assert [s.path for s in sources] == [source]
    assert ignored == []


def test_r6d_non_videos_stay_put_r5b_lock_excluded(tmp_path: Path, fast_presets: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    note = root / "notes.txt"
    note.write_text("unchanged")
    (root / ".lastencode.lock").touch()
    sources, ignored = discover([str(root)], None)
    assert sources == []
    assert ignored == [str(root / ".lastencode.lock")]
    records = list(next_plan([root], fast_presets).records())
    assert records[-1]["failed_count"] == records[-1]["source_count"] == 0
    assert note.read_text() == "unchanged"
    assert {p.name for p in root.iterdir()} == {"notes.txt", ".lastencode.lock", NAME}


@pytest.mark.parametrize("folder", [True, False])
def test_r6e_root_one_folder_or_files(tmp_path: Path, folder: bool) -> None:
    root = tmp_path / "work"
    root.mkdir()
    files = [root / "a.mp4", root / "b.mov"]
    for path in files:
        path.touch()
    assert run_root([str(root)] if folder else list(map(str, files))) == root


def test_r6e_files_in_one_folder_any_letter_case(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    first, second = root / "a.mp4", tmp_path / "WORK" / "b.mov"
    first.touch()
    if not second.parent.exists():
        pytest.skip("file system distinguishes letter case")
    second.touch()
    assert run_root([str(first), str(second)]) == root


def test_r6e_several_folders_refused_before_change(tmp_path: Path) -> None:
    first = tmp_path / "a.mp4"
    first.touch()
    second = tmp_path / "sub" / "b.mov"
    second.parent.mkdir()
    second.touch()
    before = list(tmp_path.rglob("*"))
    result = cli("convert", str(first), str(second), "--category", "apartment-tour", "--json")
    assert result.returncode == 2, result.stderr
    assert "one folder" in result.stderr
    assert list(tmp_path.rglob("*")) == before


@pytest.mark.posix_only
def test_r6e_unwritable_root_refused(tmp_path: Path) -> None:
    root = tmp_path / "readonly"
    root.mkdir()
    root.chmod(0o555)
    try:
        if os.access(root, os.W_OK):
            pytest.skip("chmod does not prevent writes for this user/filesystem")
        with pytest.raises(InvalidInput, match="not writable"):
            run_root([str(root)])
        assert list(root.iterdir()) == []
    finally:
        root.chmod(0o755)


def test_r7_single_file_subfolder_allowed_own_folder_refused(tmp_path: Path) -> None:
    source = tmp_path / "clip.txt"
    source.touch()
    sources, _ = discover([str(source)], tmp_path / "archive")
    assert sources[0].output == tmp_path / "archive" / source.name
    with pytest.raises(InvalidInput, match="own folder"):
        discover([str(source)], tmp_path)


def test_r7_output_equals_source_refused(tmp_path: Path) -> None:
    first, second = tmp_path / "clip.mov", tmp_path / "clip.lastencode.mp4"
    first.touch()
    second.touch()
    sources = [
        Source(first, tmp_path, second, second, True),
        Source(second, tmp_path, tmp_path / "other.mp4", tmp_path / "other.mp4", True),
    ]
    with pytest.raises(InvalidInput, match="overlaps source"):
        validate_paths(sources, tmp_path, set())


def test_r7_inside_folder_hint(tmp_path: Path) -> None:
    with pytest.raises(InvalidInput, match="choose an output folder outside it"):
        discover([str(tmp_path)], tmp_path / "archive")


@pytest.mark.parametrize("above", [True, False])
def test_r25a_nested_held_lock_above_and_below(tmp_path: Path, above: bool) -> None:
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    locked = tmp_path if above else child
    with RunLock(locked):
        before = (locked / ".lastencode.lock").read_bytes()
        with pytest.raises(Locked, match="pid"):
            probe_tree_locks(root)
        assert (locked / ".lastencode.lock").read_bytes() == before
        assert not (root / ".lastencode.lock").exists()


@pytest.mark.needs_media
def test_r3_r26b_next_to_source_preview(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "work" / "clip.mp4", duration=0.5)
    before = {p: p.stat().st_mtime_ns for p in source.parent.iterdir()}
    result = cli(
        "--presets",
        str(fast_presets),
        "convert",
        str(source),
        "--category",
        "apartment-tour",
        "--dry-run",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    record, summary = [json.loads(line) for line in result.stdout.splitlines()]
    output = str(source.with_name("clip.lastencode.mp4"))
    assert record["output_path"] == record["no_gain_path"] == output
    assert {t["path"] for t in summary["targets"]} == {output, str(source.parent / NAME)}
    assert "skip" in record["no_gain_note"]
    assert {p: p.stat().st_mtime_ns for p in source.parent.iterdir()} == before
    flags = {f["name"]: f for f in document("schema", "convert")["flags"]}
    assert flags["output-dir"]["required"] is False
    assert "Optional" in flags["output-dir"]["description"]


@pytest.mark.needs_media
def test_r8_mirror_single_file_subfolder_preserves_source(
    tmp_path: Path, fast_presets: Path
) -> None:
    source = build_video(tmp_path / "work" / "clip.mp4", duration=0.5)
    original = (source.read_bytes(), source.stat().st_mtime_ns)
    output = source.parent / "archive"
    result = cli(
        "--presets",
        str(fast_presets),
        "convert",
        str(source),
        "--category",
        "apartment-tour",
        "--output-dir",
        str(output),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    assert (source.read_bytes(), source.stat().st_mtime_ns) == original
    assert {p.name for p in source.parent.iterdir()} == {source.name, "archive"}
    assert (output / "clip.mp4").exists()
    assert (output / NAME).exists()


@pytest.mark.parametrize("above", [True, False])
def test_r25a_lock_fails_before_consent_or_root_changes(
    tmp_path: Path, fast_presets: Path, above: bool
) -> None:
    root = tmp_path / "work"
    child = root / "nested"
    child.mkdir(parents=True)
    with RunLock(tmp_path if above else child):
        plan = next_plan([root], fast_presets, trash_originals=True)
        with pytest.raises(Locked, match="pid"):
            list(plan.records())
        assert not (root / NAME).exists()
        assert not (root / ".lastencode.lock").exists()


def test_r25a_file_input_ignores_sibling_folders(tmp_path: Path, fast_presets: Path) -> None:
    root = tmp_path / "work"
    child = root / "nested"
    child.mkdir(parents=True)
    clip = root / "clip.mp4"
    clip.touch()
    with RunLock(child):
        next_plan([clip], fast_presets).check_locks()
        with pytest.raises(Locked, match="pid"):
            next_plan([root], fast_presets).check_locks()
    with RunLock(tmp_path):
        with pytest.raises(Locked, match="pid"):
            next_plan([clip], fast_presets).check_locks()


@pytest.mark.symlinks
def test_r6e_files_in_one_folder_through_alias(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    first, second = root / "a.mp4", alias / "b.mov"
    first.touch()
    second.touch()
    assert run_root([str(first), str(second)]) == root
    sources, _ = discover([str(first), str(second)], None)
    assert {s.output.resolve() for s in sources} == {
        root / "a.lastencode.mp4",
        root / "b.lastencode.mp4",
    }


@pytest.mark.needs_media
def test_r6c_r6a_r26b_untagged_copy_requires_force_and_consent(
    tmp_path: Path, fast_presets: Path
) -> None:
    import shutil

    from lastencode.errors import ConfirmationRequired

    source = build_video(tmp_path / "work" / "clip.mp4", duration=0.5)
    output = source.with_name("clip.lastencode.mp4")
    shutil.copy2(source, output)
    original = output.read_bytes()
    regular = next_plan([source], fast_presets)
    records = list(regular.records())
    assert records[0]["status"] == "failed"
    assert "conflict" in str(records[0]["reason"])
    assert regular.exit_code == 1
    forced = next_plan([source], fast_presets, force=True, machine=True)
    with pytest.raises(ConfirmationRequired):
        list(forced.records())
    assert output.read_bytes() == original
    dry = next_plan([source], fast_presets, force=True)
    dry.dry_run = True
    summary = list(dry.records())[-1]
    assert summary["requires_confirmation"] is True
    assert {
        t["path"]
        for t in cast(list[dict[str, object]], summary["targets"])
        if t["effect"] == "replace"
    } == {str(output)}
