"""Inspect random-access headers without decoding a second time."""

import re
import subprocess
from collections import deque
from pathlib import Path

from lastencode.processes import popen_text, tracked


def header_numbers(path: Path, field: str) -> list[int]:
    pattern = re.compile(rf"{field}\s+\S+\s+= (\d+)")
    numbers: list[int] = []
    tail: deque[str] = deque(maxlen=15)
    # trace_headers is verbose per frame. Stream it instead of buffering hours of trace text.
    with (
        popen_text(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "trace",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-c",
                "copy",
                "-bsf:v",
                "trace_headers",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
        ) as process,
        tracked(process),
    ):
        try:
            assert process.stderr is not None
            for line in process.stderr:
                tail.append(line)
                match = pattern.search(line)
                if match:
                    numbers.append(int(match[1]))
            if process.wait():
                raise ValueError("bitstream inspection failed: " + "".join(tail)[-2000:])
        except BaseException:
            process.kill()
            process.wait()
            raise
    return numbers


def random_access(path: Path, codec: str, expected: int) -> dict[str, object]:
    if codec == "hevc":
        # HEVC BLA (16-18) and CRA (21) are not the IDR required by R18.
        access = [n for n in header_numbers(path, "nal_unit_type") if 16 <= n <= 23]
        valid = len(access) == expected and set(access) <= {19, 20}
    elif codec == "av1":
        access = [n for n in header_numbers(path, "frame_type") if n == 0]
        valid = len(access) == expected
    else:
        raise ValueError(f"unsupported encoded codec for random access: {codec}")
    return {"random_access_types": access, "random_access_valid": valid}
