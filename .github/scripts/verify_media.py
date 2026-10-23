"""Fail once with a clear capability error before the media test suite."""

import re
import subprocess
import sys


def capture(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout


def main():
    print(sys.version, flush=True)
    for name in ("ffmpeg", "ffprobe"):
        line = capture([name, "-version"]).splitlines()[0]
        print(line, flush=True)
        match = re.search(r"version\s+n?(\d+)\.(\d+)", line)
        if not match or tuple(map(int, match.groups())) < (9, 0):
            raise RuntimeError(f"{name}: need a numbered release >= 9.0, found {line}")
    print("exiftool " + capture(["exiftool", "-ver"]).strip(), flush=True)
    listing = capture(["ffmpeg", "-hide_banner", "-encoders"])
    for name in ("libx265", "libsvtav1", "libopus"):
        if not re.search(r"\b" + name + r"\b", listing):
            raise RuntimeError(f"ffmpeg: required encoder {name} is missing")
        print("encoder: " + name, flush=True)
    if "--bench" in sys.argv:
        listing = capture(["ffmpeg", "-hide_banner", "-filters"])
        for name in ("libvmaf", "xpsnr"):
            if not re.search(r"\b" + name + r"\b", listing):
                raise RuntimeError(f"ffmpeg: required bench filter {name} is missing")
            print("filter: " + name, flush=True)


if __name__ == "__main__":
    main()
