"""Kernel-owned, nonblocking output-directory lock; never unlink its inode."""

import fcntl
import json
import os
import socket
from pathlib import Path
from types import TracebackType

from lastencode.errors import Locked
from lastencode.identity import now


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
        fd = os.open(
            self.output / ".lastencode.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                owner = os.pread(fd, 4096, 0).decode(errors="replace")
                raise Locked(
                    f"Output folder locked by run {owner or '(owner unavailable)'}"
                ) from error
            # Unsupported locking fails closed. PID-only locks cannot safely arbitrate hosts.
            owner = {"host": socket.gethostname(), "pid": os.getpid(), "started_at": now()}
            os.ftruncate(fd, 0)
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
            os.close(self.fd)
            self.fd = None


def probe_lock(output: Path) -> None:
    """Check an existing lock inode without creating a directory or changing its owner."""
    try:
        fd = os.open(output / ".lastencode.lock", os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            owner = os.pread(fd, 4096, 0).decode(errors="replace")
            raise Locked(f"Output folder locked by run {owner or '(owner unavailable)'}") from error
    finally:
        os.close(fd)
