# lastencode

lastencode re-encodes video recordings into smaller MP4 files, with fixed settings per kind of footage and playback target.
It keeps the recording date, file date and GPS location, checks every output before giving it its final name, and copies the video stream unchanged where re-encoding would not pay off.
`bench` compares encoding settings on short excerpts.

Version 0.2.1, experimental. Commands and presets may change before 1.0.

## Requirements

- Linux, macOS or Windows.
- The output filesystem must support platform file locks.
- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).
- ffmpeg and ffprobe 9.0 or newer with libx265, libsvtav1, libopus and the zscale filter (zimg).
- exiftool 13.43 or newer.

On Linux, put the ffmpeg 9 release-branch `gpl` binaries from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) on `PATH` and install exiftool 13.43 or newer.
The apt package may be too old; download the Perl distribution from [exiftool.org](https://exiftool.org/) and put its extracted directory on `PATH`.
On Windows, put the BtbN ffmpeg 9 release-branch `gpl` binaries on `PATH` and run `choco install exiftool` to provide `exiftool.exe`.
On macOS, run `brew install ffmpeg-full exiftool` and check that `ffmpeg -version` reports at least 9.0.
The keg-only `ffmpeg-full` formula needs `export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"` so its binaries take precedence.
`bench` also needs libvmaf and the xpsnr filter; its tests run on Linux only.

On Windows, local dates use the system's current time-zone rules; `--tz` uses the installed `tzdata` dependency.
`source_ctime` is creation time, so a rewrite preserving size and mtime can go unnoticed as a change until the hash check.
A hard kill can leave ffmpeg running and holding its work file until it finishes; no Job Object is used.
A source fails if its longest derived path exceeds 259 UTF-16 units.
Dot-prefixed work files remain visible in Explorer.

Output modification times match the source within 2 seconds; creation times are not preserved.
Manifest paths use native absolute spelling and belong to that machine's path mapping.

## Install

```sh
uv tool install git+https://github.com/DamianPala/lastencode@v0.2.1
```

Uninstall:

```sh
uv tool uninstall lastencode
```

## Quick start

List the presets, convert one file next to its source, then preview and run a conversion into an archive folder:

```sh
lastencode presets
lastencode convert recordings/clip.mp4 --category apartment-tour
lastencode convert recordings/clip.mp4 --category apartment-tour --target portable --output-dir archive --dry-run
lastencode convert recordings/clip.mp4 --category apartment-tour --target portable --output-dir archive
```

Without `--output-dir`, the output is `recordings/clip.lastencode.mp4`, non-videos stay put and no-gain sources are skipped.
With `--output-dir archive`, the output lands in `archive/clip.mp4`, next to `lastencode-manifest.jsonl` with one line per processed file and a final summary for each run.
A folder as the source gives a mirrored tree in the output folder, with files that are not videos copied as they are.
A repeated run converts only what is missing or failed.
Every command accepts `--json`; `lastencode schema --json` describes the commands, exit codes and error kinds.

## Categories and targets

`--target` is `portable` (phones and computers, the default) or `desktop` (computers only, with smaller files for webinars and calls).
A preset is the settings for one category on one target.

| Category | portable | desktop | Scale |
|---|---|---|---|
| apartment-tour | x265 10-bit, CRF 28, slow; Opus 48k | Same as portable | Native |
| dance-lesson | x265 10-bit, CRF 28, slow; Opus 64k | Same as portable | Short side 720 |
| webinar | x265 10-bit, CRF 28, slow; Opus 24k mono for dual-mono, otherwise 48k stereo | SVT-AV1 10-bit, CRF 50, preset 4; repeated frames dropped | Native |
| call | As webinar | As webinar, CRF 45 | Short side 360 |
| holiday | x265 10-bit, CRF 26, slow; Opus 64k | Same as portable | Native |

Webinars and calls are capped at 25 fps on both targets.
A TOML file at `$XDG_CONFIG_HOME/lastencode/presets.toml`, or one given with `--presets FILE`, can change any value or add a category; `lastencode presets` shows the effective values.
Without `XDG_CONFIG_HOME`, the default is `%APPDATA%\lastencode\presets.toml` on Windows and `~/.config/lastencode/presets.toml` elsewhere.
[SPEC.md](SPEC.md), requirement R9, has the full table.

## Safety and privacy

- With `--output-dir`, nothing is written in the source tree; a folder input needs an output folder outside it, and a single file may go to a subfolder of its own folder, but not to that folder itself.
  Without it, the source tree receives only `.lastencode.mp4` outputs, their work files, the manifest and the lock.
- `--dry-run` prints the plan and writes nothing.
- An output gets its final name only after it passes a check (full decode, frame count and timing, streams, colours, metadata); a failed file is deleted.
- `--force` converts again what an earlier run verified and replaces protected conflicting outputs after confirmation (use `--yes` without a terminal).
- Originals are never deleted.
- On Linux only, `--trash-originals` moves the originals of passing outputs to the freedesktop trash on their own disk, after asking; `--yes` confirms without a prompt.
- On macOS and Windows, `--trash-originals` fails with `invalid_input`, including with `--dry-run`.
- The tool makes no network requests.
- GPS location is kept unless you pass `--strip-location` or the preset says `strip`.

## Spec and tests

[SPEC.md](SPEC.md) is the binding contract: requirements, decisions with their reasons, and the acceptance run.
Tests generate synthetic clips with ffmpeg when they run; the repository holds no recordings.

## Maintenance

This is a solo project, maintained on a best-effort basis with no response-time promise.
Issues are welcome at the [issue tracker](https://github.com/DamianPala/lastencode/issues).
A useful bug report names the command you ran, the output of `lastencode --version`, the first line of `ffmpeg -version` and the JSON error from stderr; replace private paths and file names before posting.
Pull requests for bug fixes are welcome; open an issue first for anything larger.
Report security vulnerabilities through [GitHub private vulnerability reporting](https://github.com/DamianPala/lastencode/security/advisories/new).

Built with AI coding agents under my direction.

## Licence

MIT. See [LICENSE](LICENSE).
