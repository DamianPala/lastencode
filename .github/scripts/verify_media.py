"""Fail once with a clear capability error before the media test suite."""

import re
import subprocess
import sys


def capture(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout


def check_zscale():
    filters = capture(["ffmpeg", "-hide_banner", "-filters"])
    if not re.search(r"^\s*\S+\s+zscale\s", filters, re.MULTILINE):
        raise RuntimeError(
            "ffmpeg: required filter zscale is missing; install a zimg-enabled build"
        )
    print("filter: zscale", flush=True)


def check_exiftool():
    version = capture(["exiftool", "-ver"]).strip()
    print("exiftool " + version, flush=True)
    match = re.fullmatch(r"(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (13, 43):
        raise RuntimeError(f"exiftool: need version >= 13.43, found {version}")


def main():
    print(sys.version, flush=True)
    for name in ("ffmpeg", "ffprobe"):
        line = capture([name, "-version"]).splitlines()[0]
        print(line, flush=True)
        match = re.search(r"version\s+n?(\d+)\.(\d+)", line)
        if not match or tuple(map(int, match.groups())) < (9, 0):
            raise RuntimeError(f"{name}: need a numbered release >= 9.0, found {line}")
    check_exiftool()
    listing = capture(["ffmpeg", "-hide_banner", "-encoders"])
    for name in ("libx265", "libsvtav1", "libopus"):
        if not re.search(r"\b" + name + r"\b", listing):
            raise RuntimeError(f"ffmpeg: required encoder {name} is missing")
        print("encoder: " + name, flush=True)
    check_zscale()
    if "--bench" in sys.argv:
        listing = capture(["ffmpeg", "-hide_banner", "-filters"])
        for name in ("libvmaf", "xpsnr"):
            if not re.search(r"\b" + name + r"\b", listing):
                raise RuntimeError(f"ffmpeg: required bench filter {name} is missing")
            print("filter: " + name, flush=True)


if __name__ == "__main__":
    main()
