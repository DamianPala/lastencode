"""Same-mount freedesktop trash, using rename only and exclusive info reservations."""

import os
import stat
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from lastencode.platform_io import open_control


def mount_top(path: Path) -> Path:
    current = path.absolute()
    device = current.stat().st_dev
    while current.parent != current and current.parent.stat().st_dev == device:
        current = current.parent
    return current


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != linux_uid():
        raise OSError(f"Unsafe trash directory: {path}")
    if info.st_mode & stat.S_IWOTH:
        raise OSError(f"World-writable trash directory: {path}")


def trash_root(source: Path, top_for: Callable[[Path], Path]) -> Path:
    top = top_for(source)
    if top == top_for(Path.home()):
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        if not data.is_absolute():
            raise OSError("XDG_DATA_HOME must be absolute")
        data.mkdir(parents=True, exist_ok=True)
        root = data / "Trash"
    else:
        shared = top / ".Trash"
        try:
            info = shared.lstat()
        except FileNotFoundError:
            info = None
        usable = info is not None and stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX
        root = shared / str(linux_uid()) if usable else top / f".Trash-{linux_uid()}"
    private_directory(root)
    private_directory(root / "files")
    private_directory(root / "info")
    return root


def move(
    source: Path,
    *,
    top_for: Callable[[Path], Path] = mount_top,
    before_move: Callable[[], None] | None = None,
    on_moved: Callable[[Path], None] | None = None,
) -> Path:
    source = source.absolute()
    root = trash_root(source, top_for)
    number = 0
    while True:
        name = source.name if number == 0 else f"{source.name}.{number}"
        number += 1
        destination = root / "files" / name
        info = root / "info" / f"{name}.trashinfo"
        if os.path.lexists(destination):
            continue
        try:
            fd = open_control(info, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(
                    "[Trash Info]\n"
                    f"Path={quote(str(source), safe='/')}\n"
                    f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
            # Never replace a pre-existing trashed file, including dangling symlinks.
            if os.path.lexists(destination):
                info.unlink()
                continue
            if before_move is not None:
                before_move()
            os.rename(source, destination)
            report_move(destination, on_moved)
            return destination
        except BaseException:
            # A signal can arrive after rename succeeded but before Python returned.
            # Keep restoration metadata whenever the destination already exists.
            cleanup_interrupted(destination, info, on_moved)
            raise


def report_move(destination: Path, on_moved: Callable[[Path], None] | None) -> None:
    if on_moved is not None:
        on_moved(destination)


def cleanup_interrupted(
    destination: Path, info: Path, on_moved: Callable[[Path], None] | None
) -> None:
    if os.path.lexists(destination):
        report_move(destination, on_moved)
    else:
        info.unlink(missing_ok=True)


def linux_uid() -> int:
    if sys.platform != "linux":
        raise OSError("Same-mount trash is supported on Linux only")
    return os.getuid()
