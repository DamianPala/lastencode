"""Shared pytest fixtures for synthetic command and media inputs."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from fixture_builders import (
    build_old_ffmpeg_stub,
    build_phone_clip,
    build_sixty_fps_clip,
    build_still_clip,
)


@pytest.fixture(scope="session", autouse=True)
def test_ffmpeg_path():
    """Use an explicitly selected ffmpeg build for every test and subprocess."""
    original = os.environ["PATH"]
    directory = os.environ.get("LASTENCODE_TEST_FFMPEG_DIR")
    if directory:
        os.environ["PATH"] = directory + os.pathsep + original
    yield
    os.environ["PATH"] = original


@pytest.fixture(scope="session")
def phone_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a synthetic variable-frame-rate phone clip for this test session."""
    return build_phone_clip(tmp_path_factory.mktemp("phone-clip"))


@pytest.fixture(scope="session")
def still_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a synthetic still clip for this test session."""
    return build_still_clip(tmp_path_factory.mktemp("still-clip"))


@pytest.fixture(scope="session")
def sixty_fps_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create the synthetic 20-second 60 fps flash-and-beep clip."""
    return build_sixty_fps_clip(tmp_path_factory.mktemp("sixty-fps-clip"))


@pytest.fixture(scope="session")
def old_ffmpeg_stub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create an old ffmpeg stub for this test session."""
    return build_old_ffmpeg_stub(tmp_path_factory.mktemp("old-ffmpeg"))


@pytest.fixture
def fast_presets(tmp_path: Path) -> Path:
    path = tmp_path / "fast.toml"
    path.write_text(
        "\n".join(
            f'[categories.{category}.{target}]\nspeed_preset = "{speed}"\n'
            for category in ("apartment-tour", "webinar", "dance-lesson")
            for target, speed in (
                ("portable", "ultrafast"),
                ("desktop", "12" if category == "webinar" else "ultrafast"),
            )
        )
    )
    return path


@pytest.fixture(autouse=True)
def isolated_trash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test or CLI subprocess may address the user's home trash."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    directory = os.environ.get("LASTENCODE_TEST_FFMPEG_DIR")
    path = os.pathsep.join(filter(None, (directory, os.environ.get("PATH", ""))))
    missing = [
        name for name in ("ffmpeg", "ffprobe", "exiftool") if not shutil.which(name, path=path)
    ]
    base = config.getoption("basetemp")
    symlinks, case_sensitive = filesystem_capabilities(Path(base) if base else None)
    unavailable = {
        "needs_media": (bool(missing), "missing media tools: " + ", ".join(missing)),
        "linux_only": (
            sys.platform != "linux",
            "requires Linux (trash, non-UTF-8 names or benchmark coverage)",
        ),
        "posix_only": (os.name == "nt", "requires POSIX signals, permissions or executable stubs"),
        "symlinks": (not symlinks, "filesystem or user permissions do not support symlinks"),
        "case_sensitive_fs": (not case_sensitive, "filesystem is case-insensitive"),
    }
    for item in items:
        for marker, (skip, reason) in unavailable.items():
            if skip and item.get_closest_marker(marker):
                item.add_marker(pytest.mark.skip(reason=reason))


def filesystem_capabilities(base: Path | None) -> tuple[bool, bool]:
    # Honour --basetemp; otherwise both probes and fixtures use the system temp filesystem.
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lastencode-fs-", dir=base) as directory:
        path = Path(directory)
        target = path / "A"
        target.touch()
        case_sensitive = not (path / "a").exists()
        try:
            (path / "link").symlink_to(target)
        except (OSError, NotImplementedError):
            return False, case_sensitive
        return True, case_sensitive
