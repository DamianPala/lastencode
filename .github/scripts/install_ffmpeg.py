"""Install the unique n9.0 GPL asset from a pinned BtbN release date in CI."""

import fnmatch
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path


def github_json(url):
    headers = {"Accept": "application/vnd.github+json"}
    # Unauthenticated API calls share a 60/hour limit per runner IP.
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main():
    prefix = "autobuild-" + os.environ["BTBN_RELEASE_DATE"] + "-"
    base = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases"
    # Resolve the exact timestamp from the pinned date rather than guessing a tag.
    releases = github_json(base + "?per_page=100")
    matches = [release for release in releases if release["tag_name"].startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one BtbN release for {prefix}, found {len(matches)}. "
            "Check BTBN_RELEASE_DATE at the top of this job (dated releases may expire)."
        )
    release = matches[0]
    key = "BTBN_WINDOWS_ASSET" if sys.platform == "win32" else "BTBN_LINUX_ASSET"
    pattern = os.environ[key]
    assets = [asset for asset in release["assets"] if fnmatch.fnmatchcase(asset["name"], pattern)]
    if len(assets) != 1:
        available = ", ".join(asset["name"] for asset in release["assets"])
        raise RuntimeError(
            f"Expected one asset matching {key}={pattern!r}; found {len(assets)}. "
            f"Release {release['tag_name']} has: {available}"
        )
    asset = assets[0]
    print(f"Downloading {release['tag_name']}/{asset['name']}", flush=True)
    root = Path(os.environ["RUNNER_TEMP"]) / "lastencode-ffmpeg"
    root.mkdir()
    archive = root / asset["name"]
    urllib.request.urlretrieve(asset["browser_download_url"], archive)
    shutil.unpack_archive(archive, root)
    executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bins = list(root.glob(f"*/bin/{executable}"))
    if len(bins) != 1:
        raise RuntimeError(f"Expected one */bin/{executable} in {archive}; found {bins}")
    directory = bins[0].parent
    with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as stream:
        stream.write(str(directory) + "\n")
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
        stream.write(f"LASTENCODE_TEST_FFMPEG_DIR={directory}\n")


if __name__ == "__main__":
    main()
