"""Slice 8: real same-mount moves and conservative retention before every original move."""

import copy
import errno
import io
import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest

import lastencode.consent as consent
import lastencode.encoding as encoding
import lastencode.trash as trash
import lastencode.trash_gate as gate
from lastencode.dates import ns_text, text_ns
from lastencode.errors import ConfirmationRequired
from lastencode.identity import sha256
from lastencode.manifest import NAME, append
from lastencode.plan_schema import convert_schema
from test_cli import cli, validate_schema
from test_copying import build_video
from test_runs import lines, make_plan, source_records, text_sources


def record_pair(tmp_path: Path) -> dict[str, Any]:
    source, output = tmp_path / "source.mp4", tmp_path / "output.mp4"
    source.write_bytes(b"synthetic original")
    output.write_bytes(b"synthetic verified output")
    return {
        "source_path": str(source),
        "output_path": str(output),
        "source_size_bytes": source.stat().st_size,
        "source_mtime": ns_text(source.stat().st_mtime_ns),
        "source_sha256": sha256(source),
        "output_sha256": sha256(output),
        "probe": {"streams": [{"index": 0, "codec_type": "video", "codec_name": "h264"}]},
        "checks": [{"name": "Synthetic", "passed": True}],
        "dropped_streams": [],
        "status": "completed",
        "action": "encode",
        "warnings": [],
    }


def test_home_move_info_and_collisions(tmp_path: Path) -> None:
    source = tmp_path / "clip with % ø.mp4"
    root = Path(os.environ["XDG_DATA_HOME"]) / "Trash"
    for number in range(3):
        source.write_bytes(f"fixture {number}".encode())
        destination = trash.move(source)
        assert destination.parent == root / "files"
        assert destination.read_bytes() == f"fixture {number}".encode()
        info = (root / "info" / f"{destination.name}.trashinfo").read_text().splitlines()
        assert info[0] == "[Trash Info]"
        assert unquote(info[1].removeprefix("Path=")) == str(source)
        datetime.strptime(info[2], "DeletionDate=%Y-%m-%dT%H:%M:%S")
        assert not source.exists()
    # Orphan files and orphan info entries independently reserve a name.
    source.write_bytes(b"last")
    (root / "files" / f"{source.name}.3").write_bytes(b"keep")
    (root / "info" / f"{source.name}.4.trashinfo").write_text("keep")
    assert trash.move(source).name == source.name + ".5"


@pytest.mark.parametrize("shared", ["missing", "sticky", "plain", "symlink", "file"])
def test_other_mount(tmp_path: Path, shared: str) -> None:
    top = tmp_path / "mount"
    top.mkdir()
    common = top / ".Trash"
    if shared in ("sticky", "plain"):
        common.mkdir(mode=0o1777 if shared == "sticky" else 0o777)
        common.chmod(0o1777 if shared == "sticky" else 0o777)
    elif shared == "symlink":
        common.symlink_to(tmp_path, target_is_directory=True)
    elif shared == "file":
        common.write_text("not a directory")
    source = top / "source.mp4"
    source.write_bytes(b"synthetic")
    destination = trash.move(source, top_for=lambda p: top if p.is_relative_to(top) else Path("/"))
    expected = common / str(os.getuid()) if shared == "sticky" else top / f".Trash-{os.getuid()}"
    assert destination.parent == expected / "files"
    assert stat.S_IMODE(expected.stat().st_mode) == 0o700
    assert destination.read_bytes() == b"synthetic"
    assert not source.exists()


def test_mount_top_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    top = tmp_path / "mount"
    source = top / "nested" / "clip.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic")
    real_stat = Path.stat

    def fake_stat(path: Path, **kwargs: Any) -> os.stat_result:
        values = list(real_stat(path, **kwargs))
        values[2] = 123 if path.is_relative_to(top) else 456
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", fake_stat)
    assert trash.mount_top(source) == top


@pytest.mark.parametrize("fault", [errno.EXDEV, errno.EACCES])
def test_rename_failure_keeps_original_cleans_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: int
) -> None:
    record = record_pair(tmp_path)

    def fail(*args: object) -> None:
        raise OSError(fault, "injected rename failure")

    monkeypatch.setattr(trash.os, "rename", fail)
    gate.trash_original(record)
    assert Path(record["source_path"]).exists()
    assert record["trash_outcome"]["status"] == "kept"
    assert record["warnings"]
    assert not list(Path(os.environ["XDG_DATA_HOME"]).rglob("*.trashinfo"))


@pytest.mark.parametrize(
    "change", ["size", "mtime", "hash", "output_hash", "failed", "copy", "symlink"]
)
def test_keep_rules(tmp_path: Path, change: str) -> None:
    record = record_pair(tmp_path)
    source = Path(record["source_path"])
    if change == "symlink":
        real = tmp_path / "real.mp4"
        source.rename(real)
        source.symlink_to(real)
    elif change == "size":
        source.write_bytes(b"longer synthetic replacement original")
    elif change == "mtime":
        os.utime(source, ns=(0, text_ns(record["source_mtime"]) + 1))
    elif change == "hash":
        source.write_bytes(b"x" * source.stat().st_size)
        os.utime(source, ns=(0, text_ns(record["source_mtime"])))
    elif change == "output_hash":
        output = Path(record["output_path"])
        output.write_bytes(b"x" * output.stat().st_size)
    elif change == "failed":
        record["status"] = "failed"
    else:
        record.update(action="skip", probe=None)
    gate.trash_original(record)
    assert source.exists()
    assert record["trash_outcome"]["status"] == "kept"
    assert bool(record["warnings"]) is (change in ("size", "mtime", "hash"))
    if change in ("size", "mtime", "hash"):
        assert "source changed" in record["trash_outcome"]["reason"]


@pytest.mark.parametrize(
    "kind,tag,kept",
    [
        ("subtitle", None, True),
        ("attachment", None, True),
        ("attachment", "tmcd", True),
        ("data", None, False),
        ("data", "tmcd", False),
    ],
)
def test_dropped_stream_rules(tmp_path: Path, kind: str, tag: str | None, kept: bool) -> None:
    record = record_pair(tmp_path)
    record["dropped_streams"] = [{"type": kind, "codec_tag": tag, "codec": "fixture"}]
    gate.trash_original(record)
    assert Path(record["source_path"]).exists() is kept
    assert record["trash_outcome"]["status"] == ("kept" if kept else "trashed")
    if kept:
        assert kind in record["warnings"][0]


def test_unsafe_trash_is_unavailable(tmp_path: Path) -> None:
    record = record_pair(tmp_path)
    data = Path(os.environ["XDG_DATA_HOME"])
    data.mkdir()
    (data / "Trash").symlink_to(tmp_path, target_is_directory=True)
    gate.trash_original(record)
    assert Path(record["source_path"]).exists()
    assert "Unsafe trash" in record["warnings"][0]


def test_acceptance_consent_and_move(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    args = (
        "convert",
        str(source),
        "--output-dir",
        str(output),
        "--category",
        "apartment-tour",
        "--presets",
        str(fast_presets),
        "--trash-originals",
        "--json",
    )
    refused = cli(*args)
    assert refused.returncode == 1
    assert json.loads(refused.stderr.splitlines()[-1])["error"]["kind"] == "confirmation_required"
    assert source.exists() and not output.exists()
    force_refused = cli(*args, "--force")
    assert force_refused.returncode == 1
    assert (
        json.loads(force_refused.stderr.splitlines()[-1])["error"]["kind"]
        == "confirmation_required"
    )
    assert source.exists() and not output.exists()
    dry = cli(*args, "--dry-run", "--yes")
    summary = json.loads(dry.stdout.splitlines()[-1])
    assert summary["requires_confirmation"] is True
    assert summary["trash_candidate_count"] == 1
    assert summary["trash_candidate_bytes"] == source.stat().st_size
    assert not output.exists()
    size = source.stat().st_size
    passed = cli(*args, "--yes")
    assert passed.returncode == 0, passed.stderr
    records = [json.loads(line) for line in passed.stdout.splitlines()]
    assert records[0]["trash_outcome"]["status"] == "trashed"
    assert not source.exists() and Path(records[0]["output_path"]).exists()
    assert records[-1]["trashed_bytes"] == size
    assert "emptied" in records[-1]["trash_space_note"]
    assert lines(output) == records[:-1]
    for record in records:
        validate_schema(record, convert_schema())


@pytest.mark.parametrize("tamper", [False, True])
def test_prior_verified_skip_rehashes_output(
    tmp_path: Path, fast_presets: Path, tamper: bool
) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets))[0]
    if tamper:
        path = Path(first["output_path"])
        path.write_bytes(b"x" * path.stat().st_size)
    second = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert second["action"] == "skip"
    assert source.exists() is tamper
    assert second["trash_outcome"]["status"] == ("kept" if tamper else "trashed")


@pytest.mark.parametrize("passed", [False, True])
def test_recovered_later_skip_checks_fresh(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, passed: bool
) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    source_records(make_plan(source, output, fast_presets))
    (output / NAME).unlink()
    recovered = source_records(make_plan(source, output, fast_presets))[0]
    assert recovered["recovered"]
    calls = []

    def fresh(path: Path, record: dict[str, object]) -> bool:
        calls.append(path)
        record["checks"] = [{"name": "Fresh", "passed": passed}]
        return passed

    monkeypatch.setattr(gate, "fast_check", fresh)
    result = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert len(calls) == 1
    assert source.exists() is not passed
    assert result["trash_outcome"]["status"] == ("trashed" if passed else "kept")


def test_copy_file_never_trashed(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    for _ in range(2):
        result = source_records(
            make_plan(source, tmp_path / "out", fast_presets, trash_originals=True)
        )[0]
        assert result["trash_outcome"]["status"] == "kept"
        assert (source / "0.txt").exists()


def test_trashed_byte_copy_protected_even_after_failure(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captions = tmp_path / "captions.srt"
    captions.write_text("1\n00:00:00,000 --> 00:00:00,400\nSynthetic\n")
    source = build_video(tmp_path / "input" / "clip.mkv", duration=0.5, subtitle=captions)
    output = tmp_path / "out"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: True)
    first = source_records(make_plan(source, output, fast_presets, trash_originals=True, yes=True))[
        0
    ]
    assert first["checks"][0]["name"] == "ByteCopy"
    assert first["trash_outcome"]["status"] == "trashed"
    destination = Path(first["output_path"])
    original = destination.read_bytes()
    source.write_bytes(original)
    for _ in range(2):
        result = source_records(make_plan(source, output, fast_presets))[0]
        assert result["failing_check"] == "Conflict"
        assert destination.read_bytes() == original
    dry = make_plan(source, output, fast_presets)
    dry.dry_run = True
    assert source_records(dry)[0]["status"] == "failed"
    forced = source_records(make_plan(source, output, fast_presets, force=True, yes=True))[0]
    assert forced["status"] == "completed", forced


@pytest.mark.parametrize("enabled", [False, True])
def test_force_changed_path_trashes_owned_previous(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    captions = tmp_path / "captions.srt"
    captions.write_text("1\n00:00:00,000 --> 00:00:00,400\nSynthetic\n")
    source = build_video(tmp_path / "input" / "clip.mkv", duration=0.5, subtitle=captions)
    output = tmp_path / "out"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: True)
    first = source_records(make_plan(source, output, fast_presets))[0]
    old = Path(first["output_path"])
    assert old.suffix == ".mkv"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: False)
    plan = make_plan(source, output, fast_presets, force=True, trash_originals=enabled, yes=True)
    plan.dry_run = True
    dry = list(plan.records())[-1]
    expected_count = 2 if enabled else 0
    assert dry["trash_candidate_count"] == expected_count
    if enabled:
        assert dry["trash_candidate_bytes"] == source.stat().st_size + old.stat().st_size
    plan.dry_run = False
    records = list(plan.records())
    result: Any = records[0]
    summary: Any = records[-1]
    assert result["status"] == "completed", result
    assert Path(result["output_path"]).suffix == ".mp4"
    assert result["previous_output_trash"]["status"] == ("trashed" if enabled else "kept")
    assert old.exists() is not enabled
    assert source.exists() is not enabled
    assert "targets" not in summary and "requires_confirmation" not in summary
    if not enabled:
        assert any(str(old) in note and "--trash-originals" in note for note in summary["warnings"])


@pytest.mark.parametrize("last", ["failed", "Space", "Conflict"])
def test_last_manifest_failure_is_not_verified(tmp_path: Path, last: str) -> None:
    record = record_pair(tmp_path)
    prior = copy.deepcopy(record)
    prior.update(status="failed", failing_check=last)
    output = tmp_path / "manifest"
    output.mkdir()
    append(output, record)
    append(output, prior)
    from lastencode.manifest import load
    from lastencode.resume import manifest_skip

    assert manifest_skip(record, load(output)[record["source_path"]]) is False


@pytest.mark.parametrize("answer", ["yes\n", "n\n", ""])
def test_interactive_prompt_once(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    error = Terminal()
    monkeypatch.delenv("NO_INPUT", raising=False)
    monkeypatch.setattr(consent.sys, "stdin", Terminal(answer))
    monkeypatch.setattr(consent.sys, "stderr", error)
    preview = {
        "requires_confirmation": True,
        "trash_candidate_count": 3,
        "trash_candidate_bytes": 99,
    }
    if answer == "yes\n":
        consent.confirm(preview, yes=False, machine=False)
    else:
        with pytest.raises(ConfirmationRequired):
            consent.confirm(preview, yes=False, machine=False)
    assert error.getvalue().count("[y/N]") == 1
    assert "3 files (99 bytes)" in error.getvalue()


def test_change_after_info_creation_keeps_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = record_pair(tmp_path)
    source = Path(record["source_path"])
    real = trash.os.fsync

    def change(fd: int) -> None:
        real(fd)
        source.write_bytes(b"x" * source.stat().st_size)
        os.utime(source, ns=(0, text_ns(record["source_mtime"])))

    monkeypatch.setattr(trash.os, "fsync", change)
    gate.trash_original(record)
    assert source.exists()
    assert "changed before trash move" in record["warnings"][0]
    assert not list(Path(os.environ["XDG_DATA_HOME"]).rglob("*.trashinfo"))


def test_recovered_actual_fast_check_and_stream_inventory(
    tmp_path: Path, fast_presets: Path
) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    source_records(make_plan(source, output, fast_presets))
    (output / NAME).unlink()
    result = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert result["recovered"]
    assert result["trash_outcome"]["status"] == "trashed", result
    assert all(check["passed"] for check in result["checks"])


@pytest.mark.parametrize("foreign", [False, True])
def test_previous_output_requires_ownership_and_new_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, foreign: bool
) -> None:
    record = record_pair(tmp_path)
    old = tmp_path / "old.mp4"
    old.write_bytes(b"owned previous synthetic output")
    previous = {
        "output_path": str(old),
        "output_size_bytes": old.stat().st_size,
        "output_sha256": sha256(old),
    }
    monkeypatch.setattr(gate, "output_tag", lambda _: None)
    if foreign:
        old.write_bytes(b"unrelated")
    else:
        record["status"] = "failed"
    gate.trash_previous(record, previous, tmp_path)
    assert old.exists()
    assert record.get("previous_output_trash", {}).get("status") != "trashed"


def test_original_move_under_lock(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lastencode.errors import Conflict
    from lastencode.run_lock import RunLock

    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    real_move = gate.move
    calls = []

    def locked(path: Path, **kwargs: Any) -> Path:
        with pytest.raises(Conflict), RunLock(output):
            pytest.fail("move occurred without output lock")
        calls.append(path)
        return real_move(path, **kwargs)

    monkeypatch.setattr(gate, "move", locked)
    result = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert result["trash_outcome"]["status"] == "trashed"
    assert calls == [source]


def test_protection_follows_output_across_input_roots(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    original = source.read_bytes()
    output = tmp_path / "out"
    first = source_records(make_plan(source, output, fast_presets, trash_originals=True, yes=True))[
        0
    ]
    new = tmp_path / "different-input" / "clip.mp4"
    new.parent.mkdir()
    new.write_bytes(original)
    before = Path(first["output_path"]).read_bytes()
    # Other settings would normally permit replacing an output tagged for the same hash.
    result = source_records(make_plan(new, output, fast_presets, strip_location=True))[0]
    assert result["failing_check"] == "Conflict", result
    assert Path(first["output_path"]).read_bytes() == before


def test_machine_context_never_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    class Forbidden:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            pytest.fail("machine context prompted")

    monkeypatch.setattr(consent.sys, "stdin", Forbidden())
    with pytest.raises(ConfirmationRequired):
        consent.confirm(
            {
                "requires_confirmation": True,
                "trash_candidate_count": 1,
                "trash_candidate_bytes": 10,
            },
            yes=False,
            machine=True,
        )


def test_prior_skip_rehashes_source_same_size_and_time(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    first = source_records(make_plan(source, output, fast_presets))[0]
    original_stat = source.stat()
    data = bytearray(source.read_bytes())
    data[-1] ^= 1
    source.write_bytes(data)
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    result = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert result["action"] == "skip", result
    assert result["source_sha256"] == first["source_sha256"]
    assert source.exists() and result["trash_outcome"]["status"] == "kept"
    assert "source changed" in result["trash_outcome"]["reason"]


def test_recovered_missing_inventory_does_not_assume_policy_loss() -> None:
    source: dict[str, object] = {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "attachment", "codec_name": "ttf"},
            {"index": 2, "codec_type": "subtitle", "codec_name": "dvd_subtitle"},
        ]
    }
    assert gate.missing_streams(source, source) == []
    output: dict[str, object] = {"streams": [{"codec_type": "video", "codec_name": "hevc"}]}
    missing = gate.missing_streams(source, output)
    assert [s["type"] for s in missing] == ["attachment", "subtitle"]


@pytest.mark.parametrize(
    "planned,codec,expected",
    [
        ("encode", "av1", "encode"),
        ("encode", "h264", "no-gain"),
        ("copy-video", "h264", "copy-video"),
    ],
)
def test_recovered_fast_check_uses_frame_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    planned: str,
    codec: str,
    expected: str,
) -> None:
    record = record_pair(tmp_path)
    record.update(verification_action=planned, settings={"encoder": "libsvtav1"})
    monkeypatch.setattr(gate, "light_probe", lambda _: {"video_codec": codec, "streams": []})
    actions = []

    def checked(path: Path, context: dict[str, object]) -> bool:
        actions.append(context["action"])
        return True

    monkeypatch.setattr(gate, "fast_check", checked)
    assert gate.refresh_recovered(record, Path(record["output_path"]))
    assert actions == [expected]


def test_interruption_after_rename_retains_restoration_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"synthetic")
    real = trash.os.rename

    def interrupted(original: Path, destination: Path) -> None:
        real(original, destination)
        raise KeyboardInterrupt

    monkeypatch.setattr(trash.os, "rename", interrupted)
    with pytest.raises(KeyboardInterrupt):
        trash.move(source)
    root = Path(os.environ["XDG_DATA_HOME"]) / "Trash"
    assert (root / "files" / source.name).read_bytes() == b"synthetic"
    assert (root / "info" / f"{source.name}.trashinfo").is_file()


def test_nanosecond_change_after_probe_does_not_reset_identity(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.planning as planning

    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    real_probe = planning.probe

    def changed(path: Path, *, packet_times: bool = False) -> dict[str, object]:
        result = real_probe(path, packet_times=packet_times)
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        return result

    monkeypatch.setattr(planning, "probe", changed)
    result = source_records(
        make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    )[0]
    assert result["status"] == "failed", result
    assert "Source changed after planning" in result["reason"]
    assert result["trash_outcome"]["status"] == "kept" and source.exists()


@pytest.mark.parametrize("mode", [0o775, 0o777])
@pytest.mark.parametrize("part", ["", "files", "info"])
def test_existing_home_trash_permissions(tmp_path: Path, mode: int, part: str) -> None:
    record = record_pair(tmp_path)
    root = Path(os.environ["XDG_DATA_HOME"]) / "Trash"
    for path in (root, root / "files", root / "info"):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    (root / part).chmod(mode)
    gate.trash_original(record)
    assert record["trash_outcome"]["status"] == ("trashed" if mode == 0o775 else "kept")
    if mode == 0o777:
        assert str(root / part) in record["trash_outcome"]["reason"]
        assert Path(record["source_path"]).exists()


def test_trash_directory_other_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "private"
    path.mkdir()
    monkeypatch.setattr(trash.os, "getuid", lambda: path.stat().st_uid + 1)
    with pytest.raises(OSError, match="Unsafe trash directory"):
        trash.private_directory(path)


def test_trash_hashes_once_immediately_before_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = record_pair(tmp_path)
    calls = []
    real_hash = gate.sha256

    def hashed(path: Path) -> str:
        assert list(Path(os.environ["XDG_DATA_HOME"]).rglob("*.trashinfo"))
        calls.append(str(path))
        return real_hash(path)

    monkeypatch.setattr(gate, "sha256", hashed)
    gate.trash_original(record)
    assert record["trash_outcome"]["status"] == "trashed"
    assert calls == [record["output_path"], record["source_path"]]


def test_recovered_mkv_byte_copy_uses_byte_verdict(tmp_path: Path, fast_presets: Path) -> None:
    import shutil

    source = build_video(tmp_path / "input" / "clip.mkv", duration=0.5)
    output = tmp_path / "out"
    plan = make_plan(source, output, fast_presets, trash_originals=True, yes=True)
    candidate = plan.sources[0].no_gain
    candidate.parent.mkdir(parents=True)
    shutil.copy2(source, candidate)
    result = source_records(plan)[0]
    assert result["recovered"]
    assert result["checks"][0]["name"] == "ByteCopy"
    assert result["trash_outcome"]["status"] == "trashed", result
    assert not source.exists()


def test_byte_verdict_only_for_matching_fresh_hash(tmp_path: Path) -> None:
    record = record_pair(tmp_path)
    fresh = [{"name": "Fresh", "passed": True}]
    record.update(recovered=True, checks=fresh)
    gate.verify_recovered(record, record["output_sha256"])
    assert record["checks"] == fresh
    gate.verify_recovered(record, record["source_sha256"])
    assert record["checks"][0]["name"] == "ByteCopy"


def test_interrupted_original_move_records_byte_copy_protection(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lastencode.manifest import load, protected_paths

    source = build_video(tmp_path / "input" / "clip.mkv", duration=0.5)
    original = source.read_bytes()
    output = tmp_path / "out"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: True)
    real_rename = trash.os.rename

    def interrupted(before: Path, after: Path) -> None:
        real_rename(before, after)
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(trash.os, "rename", interrupted)
        with pytest.raises(KeyboardInterrupt):
            source_records(make_plan(source, output, fast_presets, trash_originals=True, yes=True))
    recorded = lines(output)[-1]
    assert recorded["trash_outcome"]["status"] == "trashed"
    assert recorded["output_path"] in protected_paths(load(output))
    assert Path(recorded["trash_outcome"]["path"]).read_bytes() == original
    source.write_bytes(original)
    result = source_records(make_plan(source, output, fast_presets))[0]
    assert result["failing_check"] == "Conflict"


@pytest.mark.parametrize("tagged", [False, True])
def test_later_completed_line_releases_only_same_source_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tagged: bool
) -> None:
    import lastencode.manifest as manifest

    record = record_pair(tmp_path)
    output = tmp_path / "manifest"
    output.mkdir()
    destination = Path(record["output_path"])
    destination.write_bytes(Path(record["source_path"]).read_bytes())
    record["output_sha256"] = record["source_sha256"]
    tag = {"source_sha256": record["source_sha256"]} if tagged else None
    monkeypatch.setattr(manifest, "output_tag", lambda _: tag)
    record["trash_outcome"] = {"status": "trashed", "path": "synthetic-trash"}
    append(output, record)
    completed = dict(record, trash_outcome=None)
    append(output, dict(completed, source_path=str(tmp_path / "different-source.mp4")))
    assert manifest.protected_paths(manifest.load(output)) == [str(destination)]
    append(output, dict(completed, status="failed"))
    assert manifest.protected_paths(manifest.load(output)) == [str(destination)]
    append(output, completed)
    assert manifest.protected_paths(manifest.load(output)) == []


def test_conflicting_preview_matches_real_consent(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "out"
    plan = make_plan(source, output, fast_presets, trash_originals=True)
    candidate = plan.sources[0].output
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"foreign output")
    plan.dry_run = True
    dry = list(plan.records())[-1]
    assert dry["trash_candidate_count"] == 0
    assert dry["requires_confirmation"] is False
    plan.dry_run = False
    # No consent is needed when the preview has no possible destructive effect.
    records = list(plan.records())
    assert records[0]["status"] == "failed"
    assert source.exists()
    assert "targets" not in records[-1] and "requires_confirmation" not in records[-1]


def test_force_preview_counts_possible_fallback_path_change(tmp_path: Path) -> None:
    record = record_pair(tmp_path)
    record["no_gain_path"] = str(tmp_path / "output.mkv")
    previous = {record["source_path"]: {"output_path": record["output_path"]}}
    result = consent.preview([record], True, previous=previous, force=True)
    assert result["trash_candidate_count"] == 2
    assert result["trash_candidate_bytes"] == (
        Path(record["source_path"]).stat().st_size + Path(record["output_path"]).stat().st_size
    )


def test_original_outside_consent_preview_stays(tmp_path: Path) -> None:
    record = record_pair(tmp_path)
    gate.trash_original(record, allowed_paths=set())
    assert Path(record["source_path"]).exists()
    assert record["trash_outcome"]["status"] == "kept"
    assert "consent preview" in record["trash_outcome"]["reason"]
    assert not record["warnings"]


def test_previous_output_outside_consent_preview_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = record_pair(tmp_path)
    old = tmp_path / "old.mp4"
    old.write_bytes(b"synthetic previous output")
    previous: dict[str, object] = {"output_path": str(old), "output_sha256": sha256(old)}
    monkeypatch.setattr(gate, "output_tag", lambda _: None)
    gate.trash_previous(record, previous, tmp_path, allowed_paths=set())
    assert old.exists()
    assert record["previous_output_trash"]["status"] == "kept"
    assert "consent preview" in record["previous_output_trash"]["reason"]
    assert not record["warnings"]
