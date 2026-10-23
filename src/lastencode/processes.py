"""Cancel child processes of parallel jobs before waiting for their workers."""

import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from lastencode.executables import resolved_command


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
        resolved_command(command),
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
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
    with tool_arguments(command) as arguments:
        return run_resolved(
            arguments,
            capture_output=capture_output,
            text=text,
            check=check,
            timeout=timeout,
            cwd=cwd,
        )


def run_resolved(
    command: list[str],
    *,
    capture_output: bool,
    text: bool,
    check: bool,
    timeout: float | None,
    cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    command = resolved_command(command)
    if CURRENT.get() is None:
        return subprocess.run(
            command,
            capture_output=capture_output,
            text=text,
            check=check,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8" if text else None,
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
        subprocess.Popen(
            resolved_command(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ) as process,
        tracked(process),
    ):
        stdout, stderr = process.communicate()
        check_cancelled()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


@contextmanager
def tool_arguments(command: list[str]) -> Generator[list[str]]:
    if sys.platform != "win32" or command[0] != "exiftool":
        yield command
        return
    # Close before ExifTool opens it: Windows denies reopening a NamedTemporaryFile.
    with tempfile.TemporaryDirectory(prefix="lastencode-args-") as directory:
        path = Path(directory) / "arguments.txt"
        arguments = command[1:]
        # -config must be the first option and is not supported inside an argfile.
        config: list[str] = []
        if arguments[:1] == ["-config"]:
            config, arguments = arguments[:2], arguments[2:]
        if any("\n" in arg or "\r" in arg for arg in arguments):
            raise ValueError("ExifTool arguments must not contain line breaks on Windows")
        path.write_text("\n".join(arguments) + "\n", encoding="utf-8", newline="\n")
        yield ["exiftool", *config, "-charset", "filename=utf8", "-@", str(path)]
