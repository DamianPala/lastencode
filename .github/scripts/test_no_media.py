"""Hide preinstalled runner media tools and run only the tool-free test cases."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="lastencode-no-media-") as directory:
    # POSIX shebang stubs use env python3; no media executable can leak from the runner.
    if os.name != "nt":
        (Path(directory) / "python3").symlink_to(sys.executable)
    environment = dict(os.environ, PATH=directory)
    environment.pop("LASTENCODE_TEST_FFMPEG_DIR", None)
    print(sys.version, flush=True)
    for tool in ("ffmpeg", "ffprobe", "exiftool"):
        if shutil.which(tool, path=directory):
            raise RuntimeError(f"No-media isolation failed: {tool} is present")
        print(tool + ": absent (expected)", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "not needs_media and not slow", "-ra"],
        env=environment,
        check=False,
    )
    sys.exit(result.returncode)
