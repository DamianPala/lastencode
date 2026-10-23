"""Slice 7: durable identity, repeated runs, recovery and bounded concurrency."""

import copy
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import lastencode.jobs as jobs
from lastencode import __version__
from lastencode.commands.convert import Plan
from lastencode.errors import Conflict
from lastencode.identity import fingerprint, sha256, tag_payload
from lastencode.manifest import NAME, append, load
from lastencode.metadata import exiftool_tags
from lastencode.paths import discover
from lastencode.plan_schema import convert_schema
from lastencode.presets import load_categories
from lastencode.resume import clean_leftovers
from lastencode.run_lock import RunLock
from test_cli import cli, document, validate_schema
from test_copying import build_video


def make_plan(source: Path, output: Path, presets: Path, **options: Any) -> Plan:
    category = next(c for c in load_categories(str(presets)) if c.name == "apartment-tour")
    sources, ignored = discover([str(source)], output)
    return Plan(
        sources=sources,
        category=category,
        target="portable",
        zone=ZoneInfo("UTC"),
        output=output,
        ignored=ignored,
        dry_run=False,
        **options,
    )


def lines(output: Path) -> list[dict[str, Any]]:
    return [
        record
        for line in (output / NAME).read_text().splitlines()
        if (record := json.loads(line)).get("record_type") != "summary"
    ]


def source_records(plan: Plan) -> list[dict[str, Any]]:
    return [record for record in plan.records() if record["record_type"] == "source"]


def text_sources(tmp_path: Path, count: int = 3) -> Path:
    source = tmp_path / "input"
    source.mkdir()
    for n in range(count):
        (source / f"{n}.txt").write_text(f"synthetic {n}")
    return source


def test_r23_retries_only_failure_and_hashes_once(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.identity as identity

    source = text_sources(tmp_path)
    output = tmp_path / "output"
    real_encode = jobs.encode_source
    encodes: list[str] = []
    hashes: list[Path] = []
    real_hash = identity.sha256

    def hashed(path: Path) -> str:
        hashes.append(path)
        return real_hash(path)

    def fail_one(record: dict[str, object], *, jobs: int = 1) -> None:
        encodes.append(str(record["source_path"]))
        if str(record["source_path"]).endswith("1.txt"):
            record.update(status="failed", reason="injected", failing_check="CopyFile")
        else:
            real_encode(record, jobs=jobs)

    monkeypatch.setattr(identity, "sha256", hashed)
    monkeypatch.setattr(jobs, "encode_source", fail_one)
    first = make_plan(source, output, fast_presets)
    records = source_records(first)
    assert first.exit_code == 1
    assert len(records) == len(lines(output)) == len(hashes) == 3
    assert all(r["source_sha256"] for r in records)
    monkeypatch.setattr(jobs, "encode_source", real_encode)
    hashes.clear()
    second = make_plan(source, output, fast_presets)
    records = source_records(second)
    assert second.exit_code == 0
    assert [r["action"] for r in records] == ["skip", "copy-file", "skip"]
    assert hashes == [source / "1.txt"]
    assert len(lines(output)) == 6
    third = make_plan(source, output, fast_presets)
    all_records = list(third.records())
    assert all_records[-1]["skipped_count"] == 3
    assert all_records[-1]["actions"] == {"skip": 3}
    assert len(hashes) == 1


@pytest.mark.parametrize("video", [False, pytest.param(True, marks=pytest.mark.needs_media)])
def test_manifest_loss_recovers_and_force_reprocesses(
    tmp_path: Path, fast_presets: Path, video: bool
) -> None:
    source = (
        build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
        if video
        else text_sources(tmp_path, 1)
    )
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets))[0]
    assert first["status"] == "completed", first
    assert first["source_sha256"] == sha256(Path(first["source_path"]))
    assert first["output_sha256"] == sha256(Path(first["output_path"]))
    assert first["tool_version"] == __version__
    if video:
        tags = exiftool_tags(Path(first["output_path"]))
        raw = next(v for k, v in tags.items() if k.endswith(":LastEncode"))
        assert json.loads(str(raw)) == tag_payload(first)
    (output / NAME).unlink()
    recovered = source_records(make_plan(source, output, fast_presets))[0]
    assert recovered["status"] == "completed", recovered
    assert recovered["action"] == "skip" and recovered["recovered"] is True
    assert recovered["checks"][0]["status"] == "not-rerun"
    assert recovered["dropped_frame_share"] is None
    assert recovered["dropped_streams"] is None
    assert recovered["date_source"] is None
    again = source_records(make_plan(source, output, fast_presets))[0]
    assert again["action"] == "skip" and again["recovered"] is True
    forced = source_records(make_plan(source, output, fast_presets, force=True))[0]
    assert forced["status"] == "completed" and forced["action"] != "skip", forced
    assert forced["recovered"] is False
    for record in lines(output):
        validate_schema(record, convert_schema())


@pytest.mark.needs_media
def test_tag_identity_mismatch_equal_size_mtime(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    original = source_records(make_plan(source, output, fast_presets))[0]
    assert original["status"] == "completed"
    (output / NAME).unlink()
    stat = source.stat()
    # Change a byte in mdat; the container remains probeable, but identity must reject it.
    content = bytearray(source.read_bytes())
    index = content.index(b"mdat") + 8
    content[index] ^= 1
    source.write_bytes(content)
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    record = source_records(make_plan(source, output, fast_presets))[0]
    assert record["source_size_bytes"] == original["source_size_bytes"]
    assert record["source_mtime"] == original["source_mtime"]
    assert record["source_sha256"] != original["source_sha256"]
    assert record["status"] == "failed" and record["failing_check"] == "Conflict", record
    assert sha256(Path(original["output_path"])) == original["output_sha256"]
    assert "tag belonging to another source" in record["reason"]


@pytest.mark.parametrize("lose_manifest", [False, True])
@pytest.mark.needs_media
def test_changed_settings_do_not_skip(
    tmp_path: Path, fast_presets: Path, lose_manifest: bool
) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    before = source_records(make_plan(source, output, fast_presets))[0]
    if lose_manifest:
        (output / NAME).unlink()
    plan = make_plan(source, output, fast_presets, strip_location=True)
    after = source_records(plan)[0]
    assert after["settings_fingerprint"] != before["settings_fingerprint"]
    assert after["action"] != "skip", after
    assert after["status"] == "completed", after
    assert after["source_sha256"] == before["source_sha256"]


@pytest.mark.needs_media
def test_multiple_matching_paths_conflict(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mov", duration=0.5)
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets))[0]
    assert first["status"] == "completed", first
    other = next(
        path
        for path in (output / "clip.mp4", output / "clip.mov")
        if path != Path(first["output_path"])
    )
    other.write_bytes(Path(first["output_path"]).read_bytes())
    (output / NAME).unlink()
    record = source_records(make_plan(source, output, fast_presets))[0]
    assert record["status"] == "failed" and record["failing_check"] == "Conflict", record


def test_r19b_exact_leftovers_only(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    output.mkdir()
    names = [
        ".0.lastencode-part.txt",
        ".0.lastencode-part.txt_exiftool_tmp",
        ".0.lastencode-part.faststart.txt",
    ]
    for name in names:
        (output / name).write_text("interrupted")
    unrelated = output / ".other.lastencode-part.txt"
    unrelated.write_text("not this source")
    record = source_records(make_plan(source, output, fast_presets))[0]
    assert record["status"] == "completed", record
    assert all(not (output / name).exists() for name in names)
    assert unrelated.read_text() == "not this source"
    assert (output / "0.txt").read_bytes() == (source / "0.txt").read_bytes()


def test_r19b_video_derived_names(tmp_path: Path) -> None:
    output = tmp_path / "x.mp4"
    work = tmp_path / ".x.lastencode-part.mp4"
    paths = [work, Path(str(work) + "_exiftool_tmp"), tmp_path / ".x.lastencode-part.faststart.mp4"]
    for path in paths:
        path.write_text("leftover")
    clean_leftovers({"output_path": str(output), "no_gain_path": str(output)})
    assert not any(path.exists() for path in paths)


def test_lock_second_process_no_writes_and_stale_takeover(tmp_path: Path) -> None:
    output = tmp_path / "output"
    with RunLock(output):
        owner = (output / ".lastencode.lock").read_bytes()
        code = "from pathlib import Path; from lastencode.run_lock import RunLock; "
        code += f"lock=RunLock(Path({str(output)!r})); lock.__enter__()"
        process = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert process.returncode != 0
        assert socket.gethostname() in process.stderr
        assert str(os.getpid()) in process.stderr
        assert json.loads(owner)["started_at"] in process.stderr
        assert (output / ".lastencode.lock").read_bytes() == owner
        assert list(output.iterdir()) == [output / ".lastencode.lock"]
    (output / ".lastencode.lock").write_text(
        json.dumps({"host": socket.gethostname(), "pid": 999_999_999, "started_at": "old"})
    )
    with RunLock(output):
        assert json.loads((output / ".lastencode.lock").read_text())["pid"] == os.getpid()


@pytest.mark.needs_media
def test_lock_cli_error_kind(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    with RunLock(output):
        before = {p.name: p.read_bytes() for p in output.iterdir()}
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
        )
        assert result.returncode == 1 and not result.stdout
        error = json.loads(result.stderr.splitlines()[-1])["error"]
        assert error["kind"] == "conflict"
        assert socket.gethostname() in error["message"] and str(os.getpid()) in error["message"]
        assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_lock_unsupported_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import errno

    import lastencode.run_lock as locking

    def unsupported(*args: object) -> None:
        raise OSError(errno.ENOTSUP, "No network locking")

    monkeypatch.setattr(locking, "try_exclusive_lock", unsupported)
    with pytest.raises(OSError, match="No network locking"):
        with RunLock(tmp_path / "output"):
            pytest.fail("Unprotected run")


def test_manifest_partial_tail_and_last_record(tmp_path: Path) -> None:
    record: dict[str, object] = {"source_path": "/synthetic", "status": "failed"}
    append(tmp_path, record)
    with (tmp_path / NAME).open("ab") as stream:
        stream.write(b'{"source_path":')
    assert load(tmp_path)["/synthetic"]["status"] == "failed"
    record["status"] = "completed"
    append(tmp_path, record)
    assert len(lines(tmp_path)) == 2
    assert load(tmp_path)["/synthetic"]["status"] == "completed"
    (tmp_path / NAME).write_text("invalid\n")
    with pytest.raises(Conflict, match="line 1"):
        load(tmp_path)


@pytest.mark.parametrize("video", [False, pytest.param(True, marks=pytest.mark.needs_media)])
def test_parallel_equals_serial_and_really_overlaps(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, video: bool
) -> None:
    source = tmp_path / "input" if video else text_sources(tmp_path)
    if video:
        for n in range(3):
            build_video(source / f"{n}.mp4", duration=0.5)
    first = source_records(make_plan(source, tmp_path / "serial", fast_presets, jobs=1))
    barrier = threading.Barrier(3)
    real_encode = jobs.encode_source

    def overlapping(record: dict[str, object], *, jobs: int = 1) -> None:
        barrier.wait(timeout=10)
        real_encode(record, jobs=jobs)

    monkeypatch.setattr(jobs, "encode_source", overlapping)
    parallel_output = tmp_path / "parallel"
    second = source_records(make_plan(source, parallel_output, fast_presets, jobs=3))
    assert all(r["status"] == "completed" for r in second)
    assert len(lines(parallel_output)) == 3
    keys = (
        "source_path",
        "settings",
        "settings_fingerprint",
        "source_sha256",
        "checks",
        "action",
        "status",
        "output_size_bytes",
    )
    assert {r["source_path"]: {key: r[key] for key in keys} for r in first} == {
        r["source_path"]: {key: r[key] for key in keys} for r in second
    }
    for record in lines(parallel_output):
        validate_schema(record, convert_schema())


def test_space_stops_new_jobs_reports_reservations(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = text_sources(tmp_path)
    # Each source is 11 bytes. One job fits, the next does not fit alongside it.
    monkeypatch.setattr(jobs, "free_space", lambda path: 30)
    records = source_records(make_plan(source, tmp_path / "output", fast_presets, jobs=3))
    completed = [r for r in records if r["status"] == "completed"]
    failures = [r for r in records if r["status"] == "failed"]
    assert len(completed) == 1 and len(failures) == 2
    assert all(r["failing_check"] == "Space" for r in failures)
    assert all(r["space_needed_bytes"] == 44 for r in failures)
    assert all("44 bytes" in r["reason"] for r in failures)
    assert (
        Path(completed[0]["output_path"]).read_bytes()
        == Path(completed[0]["source_path"]).read_bytes()
    )


def test_fingerprint_canonical_and_metadata_sensitive() -> None:
    record: dict[str, object] = {"settings": {"b": 2, "a": 1}, "location": "kept"}
    reordered = copy.deepcopy(record)
    reordered["settings"] = {"a": 1, "b": 2}
    assert fingerprint(record) == fingerprint(reordered)
    reordered["recording_date"] = "2026-10-21T00:00:00Z"
    assert fingerprint(record) != fingerprint(reordered)


@pytest.mark.parametrize("value", ["0", "-1", "one", "1.5"])
def test_jobs_usage_errors(tmp_path: Path, value: str) -> None:
    source = text_sources(tmp_path, 1)
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "output"),
        "--category",
        "apartment-tour",
        "--jobs",
        value,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr.splitlines()[-1])["error"]["kind"] == "invalid_input"
    assert not (tmp_path / "output").exists()


@pytest.mark.needs_media
def test_real_cli_manifest_schema_versions(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
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
    )
    assert result.returncode == 0, result.stderr
    schema = document("schema", "convert")
    assert schema["stream"] is True and schema["effects"] == "non_idempotent"
    stdout = [json.loads(line) for line in result.stdout.splitlines()]
    for record in stdout + lines(output):
        validate_schema(record, schema["output"])
    assert lines(output) == stdout[:-1]
    record = stdout[0]
    assert record["source_sha256"] and record["output_sha256"]
    assert record["ffmpeg_version"].startswith("ffmpeg version")
    assert record["encoder_version"] and record["started_at"].endswith("Z")
    assert record["ended_at"] >= record["started_at"]
    assert record["trash_outcome"] is None


def test_dry_run_no_hash_no_lock_no_write(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.conflicts as conflicts
    import lastencode.identity as identity

    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    plan = make_plan(source, output, fast_presets)
    plan.dry_run = True

    def forbidden(*args: object) -> str:
        pytest.fail("Dry run read source content")

    monkeypatch.setattr(identity, "sha256", forbidden)
    monkeypatch.setattr(conflicts, "same_bytes", forbidden)
    records = list(plan.records())
    assert records[0]["source_sha256"] is None
    assert records[-1]["changed"] is False
    assert not output.exists()


@pytest.mark.needs_media
def test_byte_copy_recovery_obeys_location_and_date(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    subtitle = tmp_path / "captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,400\nSynthetic\n")
    source = build_video(tmp_path / "input" / "clip.mkv", duration=0.5, subtitle=subtitle)
    output = tmp_path / "output"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: True)
    plan = make_plan(source, output, fast_presets)
    first = source_records(plan)[0]
    assert first["status"] == "completed", first
    assert first["checks"][0]["name"] == "ByteCopy", first
    assert first["source_sha256"] == first["output_sha256"]
    (output / NAME).unlink()
    recovered = source_records(make_plan(source, output, fast_presets))[0]
    assert recovered["action"] == "skip" and recovered["recovered"] is True, recovered
    (output / NAME).unlink()
    blocked = source_records(make_plan(source, output, fast_presets, strip_location=True))[0]
    assert blocked["status"] == "failed" and blocked["failing_check"] == "Conflict", blocked


def test_skip_needs_no_space(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    assert source_records(make_plan(source, output, fast_presets))[0]["status"] == "completed"
    monkeypatch.setattr(jobs, "free_space", lambda _: 0)
    repeated = source_records(make_plan(source, output, fast_presets))[0]
    assert repeated["action"] == "skip" and repeated["status"] == "completed"


def test_disk_full_is_file_failure_and_keeps_previous(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    import lastencode.encoding as encoding

    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    output.mkdir()
    final = output / "0.txt"
    final.write_text("old output")

    def full(*args: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(encoding.shutil, "copyfile", full)
    plan = make_plan(source, output, fast_presets, force=True, yes=True)
    record = source_records(plan)[0]
    assert record["status"] == "failed" and plan.exit_code == 1
    assert "No space left" in record["reason"]
    assert final.read_text() == "old output"
    assert not list(output.glob(".*.lastencode-part.*"))
    assert len(lines(output)) == 1


def test_source_change_during_hash_is_rejected(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.identity as identity

    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    real = identity.sha256

    def changed(path: Path) -> str:
        result = real(path)
        path.write_text("different content")
        return result

    monkeypatch.setattr(identity, "sha256", changed)
    record = source_records(make_plan(source, output, fast_presets))[0]
    assert record["status"] == "failed" and "changed while hashing" in record["reason"]
    assert record["source_sha256"] is None
    assert not (output / "0.txt").exists()


@pytest.mark.needs_media
def test_untagged_conflict_and_force_publish(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    output.mkdir()
    final = output / "clip.mp4"
    final.write_bytes(b"unrelated output without metadata")
    refused = source_records(make_plan(source, output, fast_presets))[0]
    assert refused["status"] == "failed" and refused["failing_check"] == "Conflict", refused
    assert final.read_bytes() == b"unrelated output without metadata"
    forced = source_records(make_plan(source, output, fast_presets, force=True, yes=True))[0]
    assert forced["status"] == "completed", forced
    assert forced["action"] != "skip"
    assert all(check["passed"] for check in forced["checks"])
    assert sha256(final) == forced["output_sha256"]


@pytest.mark.parametrize("name", [".lastencode.lock", NAME])
@pytest.mark.symlinks
def test_control_symlinks_never_write_target(tmp_path: Path, name: str) -> None:
    output = tmp_path / "output"
    output.mkdir()
    original = tmp_path / "original.txt"
    original.write_text("untouched")
    (output / name).symlink_to(original)
    with pytest.raises(OSError):
        if name == NAME:
            append(output, {"source_path": "/synthetic"})
        else:
            with RunLock(output):
                pytest.fail("followed lock symlink")
    assert original.read_text() == "untouched"


def test_source_cannot_replace_lock_inode(tmp_path: Path, fast_presets: Path) -> None:
    source = text_sources(tmp_path, 1) / ".lastencode.lock"
    source.write_text("synthetic")
    with pytest.raises(ValueError, match="reserved for the run lock"):
        make_plan(source, tmp_path / "output", fast_presets, force=True)


@pytest.mark.needs_media
@pytest.mark.posix_only
def test_source_changed_after_check_never_publishes(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.encoding as encoding

    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    output.mkdir()
    final = output / "clip.mp4"
    final.write_bytes(b"old output")
    real_check = encoding.fast_check

    def change_after_check(work: Path, record: dict[str, object]) -> bool:
        passed = real_check(work, record)
        if passed:
            stat = source.stat()
            data = bytearray(source.read_bytes())
            data[-1] ^= 1
            source.write_bytes(data)
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        return passed

    monkeypatch.setattr(encoding, "fast_check", change_after_check)
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: False)
    record = source_records(make_plan(source, output, fast_presets, force=True, yes=True))[0]
    assert record["status"] == "failed" and "Source changed during processing" in record["reason"]
    assert final.read_bytes() == b"old output"
    assert record["output_size_bytes"] is None and record["output_sha256"] is None


def test_r6a_identical_copy_after_failed_line_is_not_conflict(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    assert source_records(make_plan(source, output, fast_presets))[0]["status"] == "completed"
    real_space = jobs.free_space
    monkeypatch.setattr(jobs, "free_space", lambda _: 0)
    failed = source_records(make_plan(source, output, fast_presets, force=True))[0]
    assert failed["failing_check"] == "Space"
    monkeypatch.setattr(jobs, "free_space", real_space)
    again = source_records(make_plan(source, output, fast_presets))[0]
    assert again["status"] == "completed" and again["failing_check"] is None, again


@pytest.mark.parametrize("lose_manifest", [False, True])
@pytest.mark.needs_media
def test_r6b_foreign_tag_conflict_and_force(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, lose_manifest: bool
) -> None:
    import lastencode.conflicts as conflicts
    import lastencode.identity as identity

    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets))[0]
    assert first["status"] == "completed", first
    destination = Path(first["output_path"])
    original = destination.read_bytes()
    if lose_manifest:
        (output / NAME).unlink()
    source.unlink()
    build_video(source, duration=1.0)
    assert source.stat().st_size != first["source_size_bytes"]
    before = {p: p.read_bytes() for p in output.iterdir()}

    def forbidden(*args: object) -> str:
        pytest.fail("Dry run hashed content")

    with monkeypatch.context() as patch:
        patch.setattr(identity, "sha256", forbidden)
        patch.setattr(conflicts, "sha256", forbidden)
        patch.setattr(conflicts, "same_bytes", forbidden)
        dry = make_plan(source, output, fast_presets)
        dry.dry_run = True
        planned = source_records(dry)[0]
    assert planned["status"] == "failed" and "conflict" in planned["reason"], planned
    assert str(destination) in planned["reason"]
    assert {p: p.read_bytes() for p in output.iterdir()} == before
    blocked = source_records(make_plan(source, output, fast_presets))[0]
    assert blocked["failing_check"] == "Conflict", blocked
    assert "tag belonging to another source" in blocked["reason"]
    assert str(destination) in blocked["reason"]
    assert destination.read_bytes() == original
    forced = source_records(make_plan(source, output, fast_presets, force=True, yes=True))[0]
    assert forced["status"] == "completed" and forced["action"] != "skip", forced
    assert forced["source_sha256"] != first["source_sha256"]
    assert destination.read_bytes() != original


@pytest.mark.needs_media
def test_r6b_dry_run_changed_settings_encodes_without_hashing(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.conflicts as conflicts
    import lastencode.identity as identity

    source = build_video(tmp_path / "input" / "clip.mp4", duration=0.5)
    output = tmp_path / "output"
    assert source_records(make_plan(source, output, fast_presets))[0]["status"] == "completed"
    before = {p: p.read_bytes() for p in output.iterdir()}

    def forbidden(*args: object) -> str:
        pytest.fail("Dry run hashed content")

    monkeypatch.setattr(identity, "sha256", forbidden)
    monkeypatch.setattr(conflicts, "sha256", forbidden)
    monkeypatch.setattr(conflicts, "same_bytes", forbidden)
    dry = make_plan(source, output, fast_presets, strip_location=True)
    dry.dry_run = True
    record = source_records(dry)[0]
    assert record["status"] == "planned" and record["action"] in ("encode", "copy-video")
    assert {p: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("last_line", ["passed", "missing", "failed", "different_hash"])
def test_r6a_older_byte_copy_needs_last_manifest_hash(
    tmp_path: Path, fast_presets: Path, last_line: str
) -> None:
    source = text_sources(tmp_path, 1)
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets))[0]
    destination = Path(first["output_path"])
    original = destination.read_bytes()
    (source / "0.txt").write_text("a new source version")
    previous: dict[str, object] = dict(first)
    if last_line == "missing":
        (output / NAME).unlink()
    elif last_line == "failed":
        previous.update(status="failed", output_sha256=None)
        append(output, previous)
    elif last_line == "different_hash":
        previous["output_sha256"] = "0" * 64
        append(output, previous)
    record = source_records(make_plan(source, output, fast_presets))[0]
    if last_line == "passed":
        assert record["status"] == "completed", record
        assert destination.read_bytes() == (source / "0.txt").read_bytes()
    else:
        assert record["failing_check"] == "Conflict", record
        assert destination.read_bytes() == original


def build_data_mov(tmp_path: Path) -> Path:
    base = build_video(tmp_path / "base.mp4", duration=0.5)
    payload = tmp_path / "metadata.bin"
    payload.write_bytes(b"synthetic timed metadata")
    source = tmp_path / "input" / "clip.mov"
    source.parent.mkdir()
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(base),
            "-f",
            "data",
            "-i",
            str(payload),
            "-map",
            "0",
            "-map",
            "1:0",
            "-c",
            "copy",
            "-tag:d",
            "gpmd",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("ffmpeg cannot mux a bin_data/gpmd track into MOV: " + result.stderr.strip())
    return source


@pytest.mark.parametrize("strip_location", [False, True])
@pytest.mark.needs_media
def test_no_gain_data_stream_location_policy(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, strip_location: bool
) -> None:
    import lastencode.encoding as encoding
    from lastencode.probe import probe, stream_list

    source = build_data_mov(tmp_path)
    streams = stream_list(probe(source)["streams"])
    data = next(s for s in streams if s["codec_type"] == "data")
    assert data.get("codec_tag_string") != "tmcd"
    monkeypatch.setattr(encoding, "not_smaller", lambda *_: True)
    record = source_records(
        make_plan(source, tmp_path / "output", fast_presets, strip_location=strip_location)
    )[0]
    assert record["status"] == "completed" and record["action"] == "no-gain", record
    output_streams = stream_list(probe(Path(record["output_path"]))["streams"])
    assert any(s["codec_type"] == "data" for s in output_streams) is not strip_location
    if strip_location:
        assert len(record["dropped_streams"]) == 1
        dropped = record["dropped_streams"][0]
        assert dropped["source_stream_index"] == data["index"]
        assert dropped["type"] == "data"
        assert "location stripping" in dropped["reason"]
    else:
        assert record["dropped_streams"] == []
        assert [s["codec_type"] for s in output_streams] == [s["codec_type"] for s in streams]


@pytest.mark.needs_media
def test_r25b_pools_per_job_settings_and_fingerprint(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.video as video
    from lastencode.encoding import encoding_command
    from lastencode.planning import inspect_source

    monkeypatch.setattr(video, "hardware_threads", lambda: 16)
    source = build_video(tmp_path / "input" / "tiny.mp4", duration=0.5)
    plan = make_plan(source, tmp_path / "output", fast_presets)
    record = plan.sources[0]

    planned = inspect_source(record, plan.category, plan.target, plan.zone)
    planned["action"] = "encode"
    original = copy.deepcopy(planned)
    for count, expected in [(4, 4), (1, 16), (32, 1), (3, 5)]:
        command = encoding_command(planned, tmp_path / "work.mp4", jobs=count)
        params = command[command.index("-x265-params") + 1]
        assert f"pools={expected}" in params.split(":")
        assert "frame-threads=2" in params.split(":")
        assert planned["settings"] == original["settings"]
        assert fingerprint(planned) == fingerprint(original)
    av1 = next(c for c in load_categories(str(fast_presets)) if c.name == "webinar")
    params = video.encoder_parameters(
        Path("."), {}, {k: v.value for k, v in av1.settings["desktop"].items()}
    )
    assert not any(key in params for key in ["pools=", "frame-threads=", "lp="])


@pytest.mark.parametrize("lose_manifest", [False, True])
@pytest.mark.needs_media
def test_r25c_other_jobs_skip_verified_sources(
    tmp_path: Path, fast_presets: Path, monkeypatch: pytest.MonkeyPatch, lose_manifest: bool
) -> None:
    import lastencode.video as video
    from lastencode.conflicts import output_tag

    monkeypatch.setattr(video, "hardware_threads", lambda: 16)
    fast_presets.write_text(
        fast_presets.read_text().replace(
            'speed_preset = "ultrafast"',
            'speed_preset = "ultrafast"\ncopy_video_below_bps = 0',
            1,
        )
    )
    source = build_video(tmp_path / "input" / "tiny.mp4", duration=0.5)
    output = tmp_path / "output"
    first = source_records(make_plan(source, output, fast_presets, jobs=4))[0]
    assert first["status"] == "completed", first
    tag = output_tag(Path(first["output_path"]))
    assert tag and tag["settings_fingerprint"] == first["settings_fingerprint"]
    if lose_manifest:
        (output / NAME).unlink()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Verified source was encoded again after changing --jobs")

    monkeypatch.setattr(jobs, "encode_source", forbidden)
    second = source_records(make_plan(source, output, fast_presets, jobs=1))[0]
    assert second["action"] == "skip", second
    assert second["settings"] == first["settings"]
    assert second["settings_fingerprint"] == first["settings_fingerprint"]
    assert lines(output)[-1]["settings"] == first["settings"]
    assert "pools=" not in json.dumps(lines(output))
