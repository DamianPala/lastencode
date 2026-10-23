"""Portable regressions for Slice 19, with synthetic media only."""

import errno
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import lastencode.commands.convert as convert
import lastencode.dates as dates
import lastencode.platform_io as platform_io
import lastencode.presets as presets
import lastencode.processes as processes
import lastencode.run_lock as locking
import lastencode.video as video
from lastencode.__main__ import build_parser
from lastencode.errors import InvalidInput, MissingTool
from lastencode.paths import SYSTEM_CLUTTER_DIRS, SYSTEM_CLUTTER_FILES, Source, discover
from lastencode.planning import inspect_source, space_summary, validate_path_length
from test_cli import cli
from test_copying import build_video


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_r26f_refuses_before_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, dry_run: bool
) -> None:
    def unexpected(*_: object) -> None:
        pytest.fail("tool check must not run")

    monkeypatch.setattr(convert, "check_tools", unexpected)
    monkeypatch.setattr(convert.sys, "platform", platform)
    args = build_parser().parse_args(
        [
            "convert",
            str(tmp_path / "missing"),
            "--category",
            "holiday",
            "--output-dir",
            str(tmp_path / "out"),
            "--trash-originals",
            *(["--dry-run"] if dry_run else []),
        ]
    )
    with pytest.raises(InvalidInput, match=platform):
        convert.run(args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", sorted(SYSTEM_CLUTTER_DIRS | SYSTEM_CLUTTER_FILES))
def test_r5c_case_insensitive_clutter(tmp_path: Path, name: str) -> None:
    source = tmp_path / "input"
    source.mkdir()
    path = source / name.swapcase()
    if name in SYSTEM_CLUTTER_DIRS:
        path.mkdir()
        (path / "must-not-copy.txt").touch()
    else:
        path.touch()
    (source / "keep.txt").touch()
    sources, ignored = discover([str(source)], tmp_path / "out")
    assert [s.path.name for s in sources] == ["keep.txt"]
    assert ignored == [str(path)]


@pytest.mark.needs_media
def test_f26_polish_filename_through_convert(tmp_path: Path, fast_presets: Path) -> None:
    source = build_video(tmp_path / "input" / "ą ę ł.mp4")
    result = cli(
        "convert",
        str(source),
        "--category",
        "holiday",
        "--presets",
        str(fast_presets),
        "--output-dir",
        str(tmp_path / "out"),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / source.name).is_file()
    assert "Metadata" in result.stdout


def test_f26_windows_argfile_is_utf8_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(processes.sys, "platform", "win32")
    command = ["exiftool", "-config", "config", '-Keys:LastEncode={"a":1}', "ą ę ł.mp4"]
    with processes.tool_arguments(command) as args:
        assert args[:5] == ["exiftool", "-config", "config", "-charset", "filename=utf8"]
        path = Path(args[-1])
        assert path.read_bytes() == '-Keys:LastEncode={"a":1}\ną ę ł.mp4\n'.encode()
    assert not path.exists()


def test_f2_cpu_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(video.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(video.os, "cpu_count", lambda: None)
    assert video.hardware_threads() == 1
    monkeypatch.setattr(video.os, "cpu_count", lambda: 8)
    assert video.hardware_threads() == 8


@pytest.mark.parametrize(
    "difference, matches", [(0, True), (100, True), (1_999_999_999, True), (2_000_000_000, False)]
)
def test_r5a_time_tolerance(difference: int, matches: bool) -> None:
    assert platform_io.same_file_time(0, difference) is matches
    assert platform_io.same_file_time(difference, 0) is matches


def test_f19_windows_path_length(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out" / ("x" * 180) / "clip.mp4"
    source = Source(tmp_path / "clip.mp4", tmp_path, output, output.with_suffix(".MOV"))
    monkeypatch.setattr(convert.sys, "platform", "win32")
    with pytest.raises(ValueError, match=r"length \d+ exceeds the 259"):
        validate_path_length(source)
    record = inspect_source(
        source, presets.builtin_categories()["holiday"], "portable", dates.local_zone("UTC")
    )
    assert record["status"] == "failed" and "259" in str(record["reason"])


def test_f20a_missing_drive_fails_instead_of_looping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "exists", lambda _: False)
    with pytest.raises(InvalidInput, match="drive or share not available"):
        space_summary([], Path("/unavailable"), [])


def test_f38_windows_config_and_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(presets.sys, "platform", "win32")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    path = tmp_path / "appdata" / "lastencode" / "presets.toml"
    path.parent.mkdir(parents=True)
    path.write_text("# appdata", encoding="utf-8")
    assert presets.read_user_file(None) == ({}, str(path.absolute()))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "missing"))
    assert presets.read_user_file(None) is None


def test_f9_system_zone_resolves_each_instant(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    monkeypatch.setattr(dates.sys, "platform", "win32")
    monkeypatch.delenv("TZ", raising=False)
    zone = dates.local_zone(None)
    for instant in (datetime(2026, 1, 15, 12), datetime(2026, 7, 15, 12)):
        assert instant.replace(tzinfo=zone).utcoffset() == instant.astimezone().utcoffset()


@pytest.mark.parametrize("winerror,retries", [(32, 4), (33, 4), (5, 4), (2, 0)])
def test_f10_sharing_retry_bound(
    monkeypatch: pytest.MonkeyPatch, winerror: int, retries: int
) -> None:
    calls: list[int] = []
    delays: list[float] = []

    class SharingError(OSError):
        winerror: int

    error = SharingError("sharing violation")
    error.winerror = winerror

    def fail() -> None:
        calls.append(1)
        raise error

    monkeypatch.setattr(platform_io, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(platform_io.time, "sleep", delays.append)
    with pytest.raises(OSError):
        platform_io.retry_sharing(fail)
    assert len(calls) == retries + 1 and len(delays) == retries


def test_f4_windows_lock_does_not_lock_owner_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    calls: list[tuple[int, int, int]] = []

    def lock(fd: int, mode: int, size: int) -> None:
        calls.append((os.lseek(fd, 0, os.SEEK_CUR), mode, size))
        if mode == 1 and len(calls) == 3:
            raise OSError(errno.EACCES, "locked")

    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(locking=lock, LK_NBLCK=1, LK_UNLCK=2)
    )
    monkeypatch.setattr(
        locking, "os", SimpleNamespace(name="nt", lseek=os.lseek, SEEK_SET=os.SEEK_SET)
    )
    with (tmp_path / "lock").open("w+b") as stream:
        stream.write(b"owner")
        stream.flush()
        locking.try_exclusive_lock(stream.fileno())
        assert platform_io.read_at(stream.fileno(), 5, 0) == b"owner"
        locking.unlock(stream.fileno())
        with pytest.raises(BlockingIOError):
            locking.try_exclusive_lock(stream.fileno())
    assert calls == [(1 << 20, 1, 1), (1 << 20, 2, 1), (1 << 20, 1, 1)]


def test_f15_unicode_normalization_collision(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "é.txt").touch()
    (second / "e\u0301.txt").touch()
    with pytest.raises(InvalidInput, match="collision"):
        discover([str(first), str(second)], tmp_path / "out")


def test_r5a_rounded_output_skip_and_recovery(tmp_path: Path, fast_presets: Path) -> None:
    from lastencode.manifest import NAME
    from test_runs import make_plan, text_sources

    source = text_sources(tmp_path, 1)
    output = tmp_path / "out"
    original = source / "0.txt"
    exact = 1_700_000_000_123_456_700
    os.utime(original, ns=(exact, exact))
    first = list(make_plan(source, output, fast_presets).records())[0]
    assert first["status"] == "completed"
    copied = output / "0.txt"
    os.utime(copied, ns=(exact, exact - 100))
    assert list(make_plan(source, output, fast_presets).records())[0]["action"] == "skip"
    (output / NAME).unlink()
    recovered = list(make_plan(source, output, fast_presets).records())[0]
    assert recovered["action"] == "skip" and recovered["recovered"]


@pytest.mark.symlinks
def test_f14_existing_aliases_deduplicated(tmp_path: Path) -> None:
    from lastencode.consent import output_targets

    first, second = tmp_path / "clip.mp4", tmp_path / "CLIP.MP4"
    first.touch()
    if not second.exists():
        second.symlink_to(first)
    targets = output_targets(
        {
            "source_path": str(tmp_path / "source"),
            "output_path": str(first),
            "no_gain_path": str(second),
        },
        [],
        force=False,
        hash_copies=False,
    )
    assert len(targets) == 1
    assert len(platform_io.unique_paths([first, second])) == 1


@pytest.mark.parametrize("name", ["x" * 240, "🎬" * 100])
def test_f19_windows_bench_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    import lastencode.commands.bench as bench

    monkeypatch.setattr(bench.sys, "platform", "win32")
    path = str(tmp_path / name / "variant.mp4")
    with pytest.raises(InvalidInput, match=r"length \d+ exceeds the 259"):
        bench.validate_windows_paths(tmp_path, [], [], [{"path": path}])


@pytest.mark.parametrize("probe", [False, True])
def test_unlock_failure_closes_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: bool
) -> None:
    held = locking.RunLock(tmp_path)
    held.acquire()
    descriptor = held.fd
    assert descriptor is not None
    if probe:
        held.__exit__(None, None, None)
        opened: list[int] = []
        original = locking.open_control

        def remember(path: Path, flags: int) -> int:
            fd = original(path, flags)
            opened.append(fd)
            return fd

        monkeypatch.setattr(locking, "open_control", remember)

    def fail(_fd: int) -> None:
        raise OSError("unlock failed")

    monkeypatch.setattr(locking, "unlock", fail)
    with pytest.raises(OSError, match="unlock failed"):
        if probe:
            locking.probe_lock(tmp_path)
        else:
            held.__exit__(None, None, None)
    fd = opened[0] if probe else descriptor
    with pytest.raises(OSError):
        os.fstat(fd)
    assert held.fd is None


def test_windows_tool_lookup_does_not_search_implicit_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lastencode.executables as executables

    folder = tmp_path / "bin"
    folder.mkdir()
    candidate = str(folder / "ffmpeg")
    calls: list[str] = []

    def windows_which(name: str, *, path: str) -> str | None:
        calls.append(name)
        # Simulate Windows' implicit current-directory match for a bare tool name.
        return str(tmp_path / "ffmpeg.exe") if name == "ffmpeg" else None

    monkeypatch.setattr(executables.shutil, "which", windows_which)
    with pytest.raises(MissingTool, match="required on PATH"):
        executables.resolve_tool("ffmpeg", str(folder), ".EXE")
    assert calls == [candidate]


@pytest.mark.parametrize("denied", [False, True])
def test_r6e_windows_write_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, denied: bool
) -> None:
    import lastencode.paths as paths

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(paths.sys, "platform", "win32")
    if denied:

        def refuse(**_kwargs: object) -> None:
            raise PermissionError("ACL denies file creation")

        monkeypatch.setattr(paths.tempfile, "NamedTemporaryFile", refuse)
        with pytest.raises(InvalidInput, match="not writable.*--output-dir"):
            paths.run_root([str(root)])
    else:
        assert paths.run_root([str(root)]) == root
    assert list(root.iterdir()) == []


def test_f19_windows_non_bmp_path_length(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / ("🎬" * 80) / "clip.mp4"
    source = Source(tmp_path / "clip.mp4", tmp_path, output, output)
    monkeypatch.setattr(convert.sys, "platform", "win32")
    # Each emoji counts as two UTF-16 units, even on a Linux test host.
    with pytest.raises(ValueError, match="259 UTF-16 unit"):
        validate_path_length(source)


@pytest.mark.parametrize("version", ["12.76", "13.42", "13.43", "13.44", "13.55", "invalid"])
def test_r24_exiftool_minimum(version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import lastencode.tools as tooling
    from lastencode.errors import MissingTool

    def capture(command: list[str]) -> str:
        if command[-1] == "-version":
            return f"{command[0]} version 9.0\r\n"
        if command[-1] == "-encoders":
            return " V.... libx265\r\n A.... libopus\r\n"
        if command[-1] == "-filters":
            return " .. zscale V->V\r\n"
        return version + "\r\n"

    monkeypatch.setattr(tooling, "find_tool", lambda name: "/tools/" + name)
    monkeypatch.setattr(tooling, "capture", capture)
    settings = presets.builtin_categories()["holiday"].settings["portable"]
    if version in {"12.76", "13.42", "invalid"}:
        with pytest.raises(MissingTool, match=r"exiftool: need version >= 13.43.*found " + version):
            tooling.check_tools(settings)
    else:
        assert tooling.check_tools(settings)["exiftool"] == version


@pytest.mark.parametrize("packets", [[], [{"stream_index": 0, "flags": "D"}]])
def test_r12d_empty_video_scan_has_clear_reason(packets: list[dict[str, object]]) -> None:
    from lastencode.check_media import Media

    media = Media({"streams": [{"index": 0, "codec_type": "video"}], "packets": packets})
    with pytest.raises(ValueError, match="ffprobe: no presented video packets"):
        _ = media.end


@pytest.mark.needs_media
def test_lavfi_signalstats_uses_safe_alias(tmp_path: Path) -> None:
    from fixture_builders import signalstats

    source = build_video(tmp_path / "with spaces and 'quotes'" / "clip.mp4")
    assert signalstats(source).strip()


def test_r12d_scan_accepts_crlf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import subprocess

    import lastencode.check_media as checking

    document = {
        "streams": [{"index": 0, "codec_type": "video"}],
        "packets": [{"stream_index": 0, "pts_time": "0.0", "duration_time": "0.04"}],
    }
    raw = json.dumps(document, indent=2).replace("\n", "\r\n")
    monkeypatch.setattr(
        checking, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, raw, "")
    )
    media = checking.scan(tmp_path / "clip.mp4")
    assert media.times == [0.0]
    assert media.end == 0.04


@pytest.mark.parametrize("missing", ["zscale", "exiftool-version"])
def test_r24_missing_capability_is_exit_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    import json

    import lastencode.tools as tooling
    from lastencode.__main__ import main

    def capture(command: list[str]) -> str:
        if command[-1] == "-version":
            return f"{command[0]} version 9.0"
        if command[-1] == "-encoders":
            return " V.... libx265\n A.... libopus"
        if command[-1] == "-filters":
            return " .. zscale V->V" if missing != "zscale" else " .. scale V->V"
        return "12.76"

    monkeypatch.setattr(tooling, "find_tool", lambda name: "/tools/" + name)
    monkeypatch.setattr(tooling, "capture", capture)
    assert main(["convert", str(tmp_path), "--category", "holiday", "--json"]) == 3
    error = json.loads(capsys.readouterr().err.splitlines()[-1])["error"]
    assert error["kind"] == "missing_tool"
    assert ("zscale" if missing == "zscale" else "13.43") in error["message"]
