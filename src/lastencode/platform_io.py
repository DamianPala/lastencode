"""Small filesystem operations with explicit Windows compatibility."""

import errno
import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path


def open_control(path: Path, flags: int) -> int:
    # Windows has no O_NOFOLLOW. The precheck narrows, but cannot close, its race.
    if path.is_symlink():
        raise OSError(errno.ELOOP, f"Control file must not be a symlink: {path}")
    return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)


def read_at(fd: int, size: int, offset: int) -> bytes:
    os.lseek(fd, offset, os.SEEK_SET)
    return os.read(fd, size)


def retry_sharing(operation: Callable[[], None]) -> None:
    for attempt in range(5):
        try:
            operation()
            return
        except OSError as error:
            if (
                os.name != "nt"
                or getattr(error, "winerror", None) not in (5, 32, 33)
                or attempt == 4
            ):
                raise
            time.sleep(0.1 * (attempt + 1))


def replace_retry(source: Path, destination: Path) -> None:
    retry_sharing(lambda: os.replace(source, destination))


def unlink_retry(path: Path, *, missing_ok: bool = False) -> None:
    retry_sharing(lambda: path.unlink(missing_ok=missing_ok))


def same_file_time(left: int, right: int) -> bool:
    return abs(left - right) < 2_000_000_000


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    """Keep planned spelling, but collapse existing aliases of one file."""
    result: list[Path] = []
    for path in sorted(set(paths)):
        if not any(path.exists() and prior.exists() and path.samefile(prior) for prior in result):
            result.append(path)
    return result
