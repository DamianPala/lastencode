# Changelog

## [0.2.1] - 2026-10-23

### Fixed

- On Windows, a valid video no longer fails now and then with "ffprobe: no presented video packets; cannot determine video end"

## [0.2.0] - 2026-10-23

### Added

- Runs on macOS and Windows as well as Linux, tested on all three in CI; the README lists the differences (for example, `--trash-originals` works on Linux only), and on Windows the preset file defaults to `%APPDATA%\lastencode\presets.toml`
- `convert` without `--output-dir` writes each output next to its source as `<name>.lastencode.mp4`, with the manifest and lock in the input folder; sources that would not shrink are skipped, other files stay where they are, and the run stops if another run holds a lock above or inside that folder
- A single source file can now use a subfolder of its own folder as `--output-dir`
- The tool check before a run requires ffmpeg's zscale filter, which the colour check uses, and says how to install a build that has it (on macOS, `brew install ffmpeg-full`)

### Changed

- **BREAKING:** exiftool 13.43 or newer is required, because older versions lose Android capture tags (12.76) or the Android time-zone key `samsung.android.utc_offset` (13.42). Migration: where the system package is older (Ubuntu 24.04 ships 12.76), install the Perl distribution from exiftool.org and put it first on `PATH`
- Files written by an earlier lastencode run are never sources, also when named on the command line or under `--force`; the summary lists them with the excluded files
- Copied non-video files count as up to date when their modification time is within 2 seconds of the source's, so copies on NAS shares are no longer redone on every run
- Inputs skip more system folders, in any letter case (`$RECYCLE.BIN`, `System Volume Information`, `.Trashes`, `.Spotlight-V100`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100`), and never treat a run's `.lastencode.lock` as a source
- ffmpeg, ffprobe and exiftool are looked up only in the folders listed on `PATH`, never in the current folder

[0.2.1]: https://github.com/DamianPala/lastencode/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/DamianPala/lastencode/compare/v0.1.0...v0.2.0
