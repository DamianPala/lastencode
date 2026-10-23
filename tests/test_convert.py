"""Planning contract, safety, dates and subprocess boundaries, using synthetic media only."""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from lastencode.dates import recording_date
from lastencode.paths import discover
from lastencode.presets import builtin_categories
from lastencode.tools import supported_version
from test_cli import assert_invalid, cli, document, validate_schema


@pytest.fixture(autouse=True)
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def arguments(source: Path, output: Path, *extra: str) -> tuple[str, ...]:
    return (
        "convert",
        str(source),
        "--output-dir",
        str(output),
        *(("--category", "apartment-tour") if "--category" not in extra else ()),
        "--dry-run",
        *extra,
    )


def plan(source: Path, output: Path, *extra: str) -> list[dict[str, Any]]:
    result = cli(*arguments(source, output, *extra))
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def listing(root: Path) -> list[tuple[str, int, int]]:
    return sorted(
        (str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*")
    )


def test_phone_plan_writes_nothing(phone_clip: Path, tmp_path: Path) -> None:
    root = tmp_path
    source = root / "input" / phone_clip.name
    source.parent.mkdir()
    shutil.copyfile(phone_clip, source)
    before = listing(root)
    records = plan(source, root / "phone-output")
    assert records[0]["action"] == "encode"
    assert records[0]["probe"]["bit_depth"] == 8
    assert records[0]["probe"]["color_range"] == "pc"
    assert records[0]["probe"]["rotation"] == -90
    assert records[0]["date_source"] == "creation_time"
    assert listing(root) == before
    assert not (root / "phone-output").exists()


def test_bad_category_precedes_missing_paths() -> None:
    result = cli("convert", "--category", "nope", "--json")
    assert_invalid(result, "valid categories")
    assert "apartment-tour" in result.stderr


@pytest.mark.parametrize(
    "extra, problem",
    [
        (("--tz", "Bad/Zone"), "--tz"),
        (("--target", "nope"), "valid targets"),
    ],
)
def test_bad_flags(tmp_path: Path, extra: tuple[str, ...], problem: str) -> None:
    source = tmp_path / "source.txt"
    source.touch()
    assert_invalid(cli(*arguments(source, tmp_path / "../out", *extra)), problem)


def test_empty_conversion(tmp_path: Path) -> None:
    args = list(arguments(tmp_path, tmp_path / "../out"))
    args.remove("--dry-run")
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["completed_count"] == 0


def test_old_tool_first(
    tmp_path: Path, old_ffmpeg_stub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(old_ffmpeg_stub) + os.pathsep + os.environ["PATH"])
    result = cli(*arguments(tmp_path, tmp_path / "../out"))
    assert result.returncode == 3
    assert result.stdout == ""
    assert "ffmpeg" in json.loads(result.stderr)["error"]["message"]


@pytest.mark.parametrize(
    "version, accepted",
    [
        ("7.1", False),
        ("7.0", False),
        ("6.1", False),
        ("8.0.1-3ubuntu2", False),
        ("n9.0.2-27-gabc", True),
        ("N-12345-gabc", False),
        ("unknown", False),
    ],
)
def test_version_rule(version: str, accepted: bool) -> None:
    assert supported_version("ffmpeg version " + version) is accepted


@pytest.mark.parametrize("kind", ["inside", "same", "extensions", "case", "symlink"])
def test_unsafe_paths(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "a.mov").touch()
    output = tmp_path / "out"
    selected = source
    if kind == "inside":
        output = source / "nested"
    elif kind == "same":
        selected = source / "a.mov"
        output = source
    elif kind == "extensions":
        (source / "a.mp4").touch()
    elif kind == "case":
        (source / "A.MOV").touch()
    else:
        output.mkdir()
        selected = tmp_path / "alias"
        selected.symlink_to(output, target_is_directory=True)
    before = listing(tmp_path)
    result = cli(*arguments(selected, output))
    assert_invalid(result, "output")
    assert str(selected) in result.stderr or str(source / "a.mov") in result.stderr
    assert listing(tmp_path) == before


def test_mirror_discovery_ignores_hidden_and_loop(tmp_path: Path) -> None:
    source = tmp_path / "input"
    nested = source / ".hidden" / "nested"
    nested.mkdir(parents=True)
    (nested / "slides.PDF").write_text("text")
    (source / "lastencode-manifest.jsonl").touch()
    (nested / ".clip.lastencode-part.mp4").touch()
    (nested / "loop").symlink_to(source, target_is_directory=True)
    records = plan(source, tmp_path / "out")
    assert len(records) == 2
    assert records[0]["action"] == "copy-file"
    assert records[0]["output_path"] == str(tmp_path / "out/.hidden/nested/slides.PDF")
    assert len(records[-1]["ignored_paths"]) == 2
    assert records[-1]["space_needed_bytes"] == 12


def test_system_clutter_is_skipped_and_counted(tmp_path: Path, low_clip: Path) -> None:
    source = low_clip.parent
    folder_names = (
        "@eaDir",
        "#recycle",
        "#snapshot",
        ".SynologyWorkingDirectory",
        ".Trash-1000",
    )
    file_names = (".DS_Store", "._desktop.ini", "Thumbs.db", "desktop.ini")
    for name in folder_names:
        clutter = source / name
        clutter.mkdir()
        (clutter / "hidden.mp4").touch()
    for name in file_names:
        (source / name).touch()
    records = plan(source, tmp_path / "out")
    assert [record["action"] for record in records[:-1]] == ["copy-video"]
    assert records[-1]["system_clutter_count"] == len(folder_names) + len(file_names)
    assert len(records[-1]["ignored_paths"]) == len(folder_names) + len(file_names)
    result = cli(
        "convert",
        str(source),
        "--output-dir",
        str(tmp_path / "run-output"),
        "--category",
        "apartment-tour",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    run_records = [json.loads(line) for line in result.stdout.splitlines()]
    assert run_records[-1]["system_clutter_count"] == len(folder_names) + len(file_names)


def test_strip_location_flag_is_declared_in_schema(tmp_path: Path) -> None:
    schema = document("schema", "convert")
    flags = {flag["name"]: flag for flag in schema["flags"]}
    assert flags["strip-location"]["type"] == "boolean"
    source = tmp_path / "in" / "source.txt"
    source.parent.mkdir()
    source.touch()
    record = plan(source, tmp_path / "out", "--strip-location")[0]
    assert record["location"] == "stripped"


def test_folder_alias_into_output(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    (source / "alias").symlink_to(output, target_is_directory=True)
    with pytest.raises(ValueError, match="output folder"):
        discover([str(source)], output)


def test_file_symlink_keeps_given_path(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    original = tmp_path / "original.txt"
    original.write_text("hello")
    (source / "alias.txt").symlink_to(original)
    record = plan(source, tmp_path / "out")[0]
    assert record["source_path"] == str(source / "alias.txt")
    assert record["output_path"] == str(tmp_path / "out/alias.txt")


@pytest.fixture
def low_clip(tmp_path: Path) -> Path:
    path = tmp_path / "input" / "low.mp4"
    path.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=64x64:r=10:d=1",
            "-c:v",
            "libx264",
            "-crf",
            "40",
            "-color_trc",
            "bt709",
            str(path),
        ],
        check=True,
    )
    return path


def test_low_video_copy_and_never(low_clip: Path, tmp_path: Path) -> None:
    assert plan(low_clip, tmp_path / "out")[0]["action"] == "copy-video"
    result = cli(
        "convert",
        str(low_clip),
        "--output-dir",
        str(tmp_path / "out"),
        "--category",
        "webinar",
        "--target",
        "desktop",
        "--dry-run",
    )
    if result.returncode == 3:
        error = json.loads(result.stderr)["error"]
        if error["kind"] == "missing_tool" and "rejected encoder parameters" in error["message"]:
            pytest.skip(error["message"])
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout.splitlines()[0])
    assert record["action"] == "encode"
    assert "May not shrink" in record["no_gain_note"]


def test_unreadable_continues(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "bad.mp4").write_bytes(b"garbage")
    (source / "good.txt").write_text("yes")
    result = cli(*arguments(source, tmp_path / "out"))
    assert result.returncode == 0
    assert result.stderr == ""
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]["action"] == "failure"
    assert "ffprobe" in records[0]["reason"]
    assert records[1]["action"] == "copy-file"
    assert records[2]["failed_count"] == 1


def test_no_video_is_failure(tmp_path: Path) -> None:
    source = tmp_path / "audio.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=0.1", "-c:a", "aac", str(source)],
        check=True,
    )
    result = cli(*arguments(source, tmp_path / "../out"))
    assert result.returncode == 0
    assert "no video stream" in json.loads(result.stdout.splitlines()[0])["reason"]


@pytest.mark.parametrize(
    "creation, keys, name, expected_source, expected",
    [
        (
            "2026-01-01T01:00:00Z",
            "2026:02:01 02:00:00+02:00",
            "20260915_143012.mp4",
            "creation_time",
            "2026-01-01T01:00:00Z",
        ),
        (
            "2026-03-01T10:11:12.000000Z;2026-03-01T10:11:12.345Z",
            None,
            "20260915_143012.mp4",
            "creation_time",
            "2026-03-01T10:11:12Z",
        ),
        (
            None,
            "2026:02:01 02:00:00+02:00",
            "20260915_143012.mp4",
            "Keys:CreationDate",
            "2026-02-01T00:00:00Z",
        ),
        (None, None, "20260915_143012.mp4", "filename", "2026-09-15T12:30:12Z"),
        (None, None, "VID20260915143012.mp4", "filename", "2026-09-15T12:30:12Z"),
        (None, None, "VID_20260915_143012.mp4", "filename", "2026-09-15T12:30:12Z"),
        (None, None, "2026-09-15.mp4", "filename", "2026-09-14T22:00:00Z"),
        (None, None, "unknown.mp4", "mtime", "1970-01-01T00:00:00Z"),
        ("invalid", "bad", "20260230_143012.mp4", "mtime", "1970-01-01T00:00:00Z"),
        (None, None, "20261025_023000.mp4", "filename", "2026-10-25T00:30:00Z"),
        (None, None, "20260329_023000.mp4", "filename", "2026-03-29T01:30:00Z"),
    ],
)
def test_date_order(
    creation: str | None, keys: str | None, name: str, expected_source: str, expected: str
) -> None:
    assert recording_date(creation, keys, name, 0, ZoneInfo("Europe/Warsaw")) == (
        expected,
        expected_source,
    )


def test_tz_cli(low_clip: Path, tmp_path: Path) -> None:
    renamed = low_clip.with_name("20260915_143012.mp4")
    low_clip.rename(renamed)
    record = plan(renamed, tmp_path / "out", "--tz", "Europe/Warsaw")[0]
    assert record["recording_date"] == "2026-09-15T12:30:12Z"
    assert record["date_source"] == "filename"


@pytest.mark.parametrize(
    "target, key, value",
    [
        ("portable", "speed_preset", '"4"'),
        ("desktop", "speed_preset", '"slow"'),
        ("portable", "quality_crf", "52"),
        ("desktop", "quality_crf", "0"),
    ],
)
def test_encoder_setting_sanity(tmp_path: Path, target: str, key: str, value: str) -> None:
    # Desktop cases use webinar, the built-in SVT-AV1 category, to keep AV1 ranges covered.
    category = "webinar" if target == "desktop" else "apartment-tour"
    overlay = tmp_path / "presets.toml"
    overlay.write_text(f"[categories.{category}.{target}]\n{key} = {value}\n")
    extra = ("--presets", str(overlay), "--target", target, "--category", category)
    result = cli(*arguments(tmp_path, tmp_path / "../out", *extra))
    assert_invalid(result, f"{category}.{target}.{key}")
    assert value.strip('"') in result.stderr


def test_human_presets_absence_and_booleans() -> None:
    result = cli("presets", "--format", "text")
    assert result.returncode == 0
    assert "None" not in result.stdout and "False" not in result.stdout
    assert "Base: -" in result.stdout and "no [builtin]" in result.stdout


def test_ndjson_text_and_schema(low_clip: Path, tmp_path: Path) -> None:
    records = plan(low_clip, tmp_path / "out", "--format", "ndjson")
    schema = document("schema", "convert")["output"]
    for record in records:
        validate_schema(record, schema)
    text = cli(*arguments(low_clip, tmp_path / "out", "--format", "text"))
    assert text.returncode == 0
    assert "copy-video:" in text.stdout
    assert "space_needed_bytes" in text.stdout


def test_mtime_is_utc(tmp_path: Path) -> None:
    source = tmp_path / "data.txt"
    source.write_text("hello")
    os.utime(source, (100, 100))
    record = plan(source, tmp_path / "../out")[0]
    assert datetime.fromisoformat(record["source_mtime"]).astimezone(UTC).timestamp() == 100


def test_R35_non_capped_probe_reads_only_picture_and_tail(
    low_clip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.probe as probing
    from lastencode.planning import plan_source

    calls: list[list[str]] = []
    import lastencode.check_media as packets

    original_scan = packets.scan
    scans: list[Path] = []

    def scan(path: Path, *, read_intervals: str | None = None) -> packets.Media:
        assert read_intervals is not None
        scans.append(path)
        return original_scan(path, read_intervals=read_intervals)

    monkeypatch.setattr(packets, "scan", scan)
    original = probing.capture

    def capture(command: list[str]) -> str:
        calls.append(command)
        return original(command)

    monkeypatch.setattr(probing, "capture", capture)
    sources, _ = discover([str(low_clip)], tmp_path / "out")
    record = plan_source(
        sources[0], builtin_categories()["apartment-tour"], "portable", ZoneInfo("UTC")
    )
    assert record["action"] == "copy-video"
    frame_probes = [c for c in calls if c[0] == "ffprobe"]
    assert len(frame_probes) == 2
    assert sum("-show_frames" in command for command in frame_probes) == 1
    assert scans == [low_clip]


def test_existing_unowned_output_conflicts(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "data.txt").write_text("original")
    output = tmp_path / "out"
    output.mkdir()
    (output / "data.txt").write_text("unrelated")
    before = listing(tmp_path)
    result = cli(*arguments(source, output))
    assert result.returncode == 0
    record = json.loads(result.stdout.splitlines()[0])
    assert record["action"] == "failure" and "conflict" in record["reason"]
    assert listing(tmp_path) == before


def test_matching_byte_copy_still_plans_copy(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "data.txt").write_text("original")
    output = tmp_path / "out"
    output.mkdir()
    shutil.copyfile(source / "data.txt", output / "data.txt")
    assert plan(source, output)[0]["action"] == "copy-file"


def test_output_symlink_cannot_enter_source(tmp_path: Path) -> None:
    source = tmp_path / "input"
    (source / "sub").mkdir(parents=True)
    (source / "sub/file.txt").write_text("source")
    output = tmp_path / "output"
    output.mkdir()
    (output / "sub").symlink_to(source / "sub", target_is_directory=True)
    before = listing(tmp_path)
    assert_invalid(cli(*arguments(source, output)), "source tree")
    assert listing(tmp_path) == before


def test_no_gain_collision_across_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a.mov").touch()
    (second / "a.MOV").touch()
    result = cli("convert", str(first), str(second), *arguments(first, tmp_path / "out")[2:])
    assert_invalid(result, "collision")
    assert str(first / "a.mov") in result.stderr
    assert str(second / "a.MOV") in result.stderr


@pytest.mark.parametrize("missing", ["ffprobe", "exiftool", "libopus", "libx265"])
def test_missing_tools_and_encoders(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import lastencode.tools as tooling
    from lastencode.errors import MissingTool

    def which(name: str) -> str | None:
        return None if name == missing else "/fake/" + name

    def capture(command: list[str]) -> str:
        if command[-1] == "-version":
            return f"{command[0]} version 9.0"
        if command[-1] == "-encoders":
            return "\n".join(
                f" V..... {name}" for name in ("libx265", "libopus", "aac") if name != missing
            )
        return "13.50"

    monkeypatch.setattr(tooling.shutil, "which", which)
    monkeypatch.setattr(tooling, "capture", capture)
    target = "portable"
    with pytest.raises(MissingTool, match=missing):
        tooling.check_tools(builtin_categories()["apartment-tour"].settings[target])


def test_date_keys_from_exiftool_wins(low_clip: Path, tmp_path: Path) -> None:
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-Keys:CreationDate=2026:02:03 12:30:00+02:00",
            str(low_clip),
        ],
        check=True,
        capture_output=True,
    )
    record = plan(low_clip, tmp_path / "out")[0]
    assert record["date_source"] == "Keys:CreationDate"
    assert record["recording_date"] == "2026-02-03T10:30:00Z"


def test_summary_space_math(low_clip: Path, tmp_path: Path) -> None:
    (low_clip.parent / "notes.txt").write_text("notes")
    records = plan(low_clip.parent, tmp_path / "not-created" / "deep")
    sizes = [r["source_size_bytes"] for r in records[:-1]]
    assert records[-1]["space_needed_bytes"] == sum(sizes) + 2 * max(sizes)
    assert records[-1]["space_available_bytes"] > 0
    assert records[-1]["space_checked_path"] == str(tmp_path)


def test_case_insensitive_video_extension(low_clip: Path, tmp_path: Path) -> None:
    renamed = low_clip.with_suffix(".MP4")
    low_clip.rename(renamed)
    record = plan(renamed, tmp_path / "out")[0]
    assert record["action"] == "copy-video"
    assert record["output_path"].endswith("low.mp4")
    assert record["no_gain_path"].endswith("low.MP4")


def test_machine_zone_retains_dst(monkeypatch: pytest.MonkeyPatch) -> None:
    from lastencode.dates import local_zone

    monkeypatch.setenv("TZ", "Europe/Warsaw")
    assert recording_date(None, None, "20260915_143012.mp4", 0, local_zone(None)) == (
        "2026-09-15T12:30:12Z",
        "filename",
    )


@pytest.mark.parametrize("option", ["--target", "--tonemap-hdr"])
def test_r2_r12c_removed_options_write_nothing(
    phone_clip: Path, tmp_path: Path, option: str
) -> None:
    output = tmp_path / "out"
    before = listing(tmp_path)
    extra = [option, "compat"] if option == "--target" else [option]
    result = cli(
        "convert",
        str(phone_clip),
        "--category",
        "apartment-tour",
        "--output-dir",
        str(output),
        "--json",
        *extra,
    )
    assert_invalid(result, "compat" if option == "--target" else "unrecognized arguments")
    if option == "--target":
        assert "portable" in result.stderr and "desktop" in result.stderr
    assert listing(tmp_path) == before
    assert not output.exists()
