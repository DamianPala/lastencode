"""Cancel child processes of parallel jobs before waiting for their workers."""

import subprocess
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Control:
    cancelled: bool = False
    children: dict[int, Callable[[], None]] = field(default_factory=dict[int, Callable[[], None]])
    mutex: threading.Lock = field(default_factory=threading.Lock)

    def cancel(self) -> None:
        with self.mutex:
            self.cancelled = True
            for kill in self.children.values():
                kill()


CURRENT: ContextVar[Control | None] = ContextVar("lastencode_process_control", default=None)


def check_cancelled() -> None:
    control = CURRENT.get()
    if control is not None and control.cancelled:
        raise InterruptedError("Run interrupted")


@contextmanager
def use_control(control: Control) -> Generator[None]:
    token = CURRENT.set(control)
    try:
        yield
    finally:
        CURRENT.reset(token)


@contextmanager
def tracked[T: (str, bytes)](process: subprocess.Popen[T]) -> Generator[None]:
    control = CURRENT.get()
    try:
        if control is not None:
            with control.mutex:
                if control.cancelled:
                    process.kill()
                    raise InterruptedError("Run interrupted")
                control.children[process.pid] = process.kill
        yield
    finally:
        if control is not None:
            with control.mutex:
                control.children.pop(process.pid, None)


def popen_text(
    command: list[str],
    *,
    stdout: int | None = subprocess.PIPE,
    stderr: int | None = subprocess.PIPE,
    cwd: Path | None = None,
) -> subprocess.Popen[str]:
    """Open text pipes that decode like file names: tools echo paths that need not be UTF-8."""
    return subprocess.Popen(
        command, stdout=stdout, stderr=stderr, cwd=cwd, text=True, errors="surrogateescape"
    )


def run(
    command: list[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    timeout: float | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    if CURRENT.get() is None:
        return subprocess.run(
            command,
            capture_output=capture_output,
            text=text,
            check=check,
            timeout=timeout,
            cwd=cwd,
            errors="surrogateescape" if text else None,
        )
    check_cancelled()
    with popen_text(command, cwd=cwd) as process, tracked(process):
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        check_cancelled()
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def run_bytes(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    check_cancelled()
    with (
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process,
        tracked(process),
    ):
        stdout, stderr = process.communicate()
        check_cancelled()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
