"""Kernel-owned, nonblocking output-directory lock; never unlink its inode."""

import errno
import json
import os
import socket
from pathlib import Path
from types import TracebackType

from lastencode.errors import Locked
from lastencode.identity import now
from lastencode.platform_io import open_control, read_at


class RunLock:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.fd: int | None = None

    def __enter__(self) -> "RunLock":
        try:
            return self.acquire()
        except OSError as error:
            raise OSError(f"Acquire output lock in {self.output}: {error}") from error

    def acquire(self) -> "RunLock":
        self.output.mkdir(parents=True, exist_ok=True)
        fd = open_control(self.output / ".lastencode.lock", os.O_CREAT | os.O_RDWR)
        try:
            try:
                try_exclusive_lock(fd)
            except BlockingIOError as error:
                owner = read_at(fd, 4096, 0).decode(errors="replace")
                raise Locked(
                    f"Output folder locked by run {owner or '(owner unavailable)'}"
                ) from error
            # Unsupported locking fails closed. PID-only locks cannot safely arbitrate hosts.
            owner = {"host": socket.gethostname(), "pid": os.getpid(), "started_at": now()}
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, json.dumps(owner).encode())
            self.fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.fd is not None:
            unlock(self.fd)
            os.close(self.fd)
            self.fd = None


def probe_lock(output: Path) -> None:
    """Check an existing lock inode without creating a directory or changing its owner."""
    try:
        # Read access suffices for flock and for LockFile behind msvcrt.locking.
        fd = open_control(output / ".lastencode.lock", os.O_RDONLY)
    except FileNotFoundError:
        return
    acquired = False
    try:
        try:
            try_exclusive_lock(fd)
            acquired = True
        except BlockingIOError as error:
            owner = read_at(fd, 4096, 0).decode(errors="replace")
            raise Locked(f"Output folder locked by run {owner or '(owner unavailable)'}") from error
    finally:
        if acquired:
            unlock(fd)
        os.close(fd)


def try_exclusive_lock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 1 << 20, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EDEADLK, errno.EAGAIN):
                raise BlockingIOError(error.errno, str(error)) from error
            raise
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 1 << 20, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def probe_tree_locks(root: Path, *, include_root: bool = True, include_tree: bool = True) -> None:
    """Inspect only existing lock files, without altering their contents or ownership."""
    from lastencode.paths import is_system_clutter

    for parent in root.resolve().parents:
        probe_lock(parent)
    if include_root:
        probe_lock(root)
    # File inputs form a source tree of just those files (R8), so their siblings' folders
    # are neither walked nor allowed to fail the run.
    pending = [root] if include_tree else []
    seen: set[Path] = set()
    while pending:
        folder = pending.pop()
        resolved = folder.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        for child in folder.iterdir():
            if child.is_dir() and child.resolve() not in seen and not is_system_clutter(child):
                probe_lock(child)
                pending.append(child)
