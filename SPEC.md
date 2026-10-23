# lastencode: spec

Revision 2026-10-23 · code v0.1.0 · format spec-writing 0.7

## Problem

Phone recordings, course recordings and calls take a lot of NAS space, so they get re-encoded now and then to save it. Ad-hoc ffmpeg runs tend to lose recording dates, leave file dates at the conversion day, drop frames, produce seek-unfriendly files and keep no record of what they did, and every run means hand-picking ffmpeg flags again. lastencode turns a folder of recordings into much smaller files at settings chosen by eye per kind of footage, keeps their dates and location, and checks each file's integrity before it counts as done.

## User

The user runs it rarely, mostly through an AI agent that picks the command from the tool's own listing of content categories and playback targets. The results are watched on a phone about two years old, on a Linux laptop with a player such as Haruna, and sometimes on other people's Windows PCs. A **category** is the kind of footage: apartment tour, dance lesson, webinar (which covers recorded sessions), call or holiday clip. A **target** is where the files must play: `portable` (phones and computers, the default), or `desktop` (computers only: smaller files for webinars and calls, at a quality the owner accepted in a blind comparison, and the same files as `portable` for camera footage).

## Goal

After this is built, the user can point lastencode at a folder, name the category and target, and get a mirrored folder of verified, smaller MP4 files, or such files next to the originals, plus a record of every file, on Linux, macOS or Windows. The build is accepted when the acceptance run in part 2 passes on a synthetic phone clip and a course recording excerpt, and the outputs play correctly on an Android phone and in Haruna, and the default test suite passes on Linux, macOS and Windows in CI. Whether it is worth using is judged later by the size saved on a set of course recordings at a quality the user accepts by eye.

## What it does

- **S1.** The user or agent lists categories and targets with their settings, and sees the per-file plan of a run without writing anything. (R1 to R4, R33)
- **S2.** The user converts files or folders for one category and one target into a separate folder that mirrors the source tree, where files that are not videos (PDFs, subtitles, photos) are copied as they are. When re-encoding would not make a file smaller, the mirror gets the original's streams unchanged instead, possibly under the original's extension. Without an output folder, each output lands next to its original as `<name>.lastencode.mp4`, and earlier outputs are never converted again. (R5 to R12e, R13b to R13d, R35 to R36; next to the originals: R5d, R6c to R6e)
- **S3.** Video that is already heavily compressed is copied unchanged and only its audio is re-encoded, because re-encoding it would cost quality for little size gain; a course or call recording above 25 fps is re-encoded anyway. (R13, R13a)
- **S4.** Each output keeps the recording date, file date and all audio tracks of its original, and its GPS location unless a preset or the run asks to strip it; when the recording date is missing, the tool takes the most trustworthy one it can find and records where it came from. (R14 to R17a)
- **S5.** Each output is checked right after encoding (a full decode, frames, timing, streams, colours and metadata; it does not score picture quality); a failed file never appears under its final name, and the run ends with a summary of what changed per file: action, settings, size before and after, location kept or stripped. (R18 to R21)
- **S6.** A repeated run converts only what is missing or failed, even when the record of earlier runs was lost, and every run appends to that record. (R22 to R25)
- **S7.** With an explicit flag, originals of verified outputs go to the trash on their own disk, on Linux only. (R26 to R26f)
- **S8.** The user benchmarks a category on short excerpts: several quality settings, targets and frame rates side by side, with sizes, quality scores and clips to compare by eye. (R27 to R32)

## What it does not do

- No target for older players: it differed from `portable` mostly in audio, and as HEVC it still needed a codec extension on a stock Windows PC, the case it was meant for. (D76)
- No H.266 (VVC) output and no hardware (GPU) encoding: VVC looked no better than x265 at equal size and was much slower. (D1, D71)
- No bundled ffmpeg: the user installs a recent build, and benchmark mode needs one with the newer VMAF models. (D12, D12a)
- No per-file search for the quality setting: each category has fixed settings, and the tool never changes them on its own; they come from the built-in table or the user's preset file. (R9b, R31)
- No network use and no media in the tool's own repository: no download of test footage, no upload, sharing or gallery-app integration, and the tests build synthetic clips. (R34)
- It never deletes a source, never writes into the source tree except outputs with their own `.lastencode` names and their manifest when no output folder is given, and never leaves an unchecked file under a final output name: originals only go to the trash, on request, after their output passed the check, and a failed work file is deleted. (R8, R19, R26)
- No interlaced video and no video with non-square pixels (old camcorders, some broadcast recordings): such a source fails with a reason, and nothing lands at its mirror path. (R36)

## How it works

A run first probes every source with ffprobe and builds a plan: encode the video, copy the video and re-encode only the audio, or skip. A **preset** is the settings for one category on one target, read from a built-in table that a user's preset file can change or extend. Encoding writes a work file, and the recording date, location and file date are copied from the original. The **fast check** then reads the work file back, decodes it fully and compares the colours of a few of its frames with the source's; only then does the file get its final name. A **manifest** (one line per file, appended to a file in the output folder, or in the input folder when no output folder is given) records source, output, settings, check results and versions.

Facts about the picture (colours, frame times, interlacing, pixel shape) come from the video itself rather than from the labels in the file's container, because those labels can contradict the video. When the container's colours or length disagree with the video, the run warns.

The benchmark cuts a few short excerpts from given sources, encodes each excerpt with each variant, scores every variant against its excerpt with quality metrics (VMAF, Netflix's quality score, among them), and writes a table plus side-by-side clips. The command line follows the CLI Design Standard, so an agent can discover commands, read JSON and recover from errors in a predictable way, at the price of a few extra flags such as `--yes` for trashing originals (D23).

## Key decisions

- **Two-axis presets, category and target:** the agent or user says where files must play, and the tool picks codec, bit depth and audio; the price is two settings sets to maintain per category. (D5, D5a)
- **Default target aims at recent phones and computers:** HEVC 10-bit in MP4 with Opus audio, at a slow, thorough encoder setting; the price is that Windows PCs may need VLC or a codec extension. These settings should convert Full HD in at most twice its length on a reference 16-core desktop PC; a measurement there after the build checks this, outside the acceptance run. (D3, D4, D6, D22, D67, D72, D84)
- **Fixed settings per category, judged by eye and by VMAF:** every file of a category gets the same settings, picked in blind comparisons where the owner's ranking matched VMAF; a higher quality setting looked better only on still crops and made files much larger, and a per-file search would save a little more space for much longer runs. (D7, D18, D65, D69, D74, D75)
- **Originals stay untouched, output goes to a mirror folder or next to them:** this costs double disk space until the user trashes originals with an explicit flag and empties the trash; without an output folder, the folders of the originals also hold the outputs and the record. (D8, D9, D90)
- **Linux, macOS and Windows, tested only in CI:** the default test suite runs on GitHub Actions for all three; the price is that the trash works only on Linux, so elsewhere originals stay until the user removes them. (D91, D92)
- **Low-bitrate video is copied, not re-encoded:** this keeps quality on already compressed recordings and gives up the extra video savings; copies keep the source's keyframe spacing and rotation tag. (D11, D24)
- **Desktop squeezes only course and call recordings:** camera footage keeps its portable settings on desktop, because AV1 made apartment-tour files the same size or up to 6 % larger at the portable output's average quality, 8 to 25 % smaller only when matched on the weakest frames, and lost a blind comparison. Course and call recordings on desktop are always re-encoded with AV1 at a strong compression level picked in a blind comparison, and frames that repeat the previous one are dropped; on a course recording this halved the video with text intact. The price: faces look slightly smoother, small screen changes can show up to a second late (one that is gone within that second may not show at all), and video editors need such a file converted to a fixed frame rate first. Course and call recordings also keep at most 25 frames per second on every target, so one above 25 fps is always re-encoded, even when it is already heavily compressed. (D36, D37, D39, D57, D70)

## Open

Nothing blocks the gate.

---

Part 2 is for the builder and the maintainer.

## Requirements

### Terms

- **`<scratch>`**: one directory for generated fixtures, stubs and outputs of checks, outside the project and outside any real archive.
- Relative paths such as `research/2026-10-20/...` resolve against the project folder of this spec.
- **source**: an input video file; **output**: the MP4 the tool writes for one source; **work file**: the output before it passed the fast check.
- **target**: where outputs must play, `portable` or `desktop`; the preset table (R9) gives each target's settings.
- **reference machine**: a desktop PC with a 16-core, 32-thread AMD Ryzen 9 7950X, against which the speed target (R9e) is set.
- **variant**: one encoding of a benchmark excerpt with one combination of preset, quality setting, target and frame rate.
- **phone clip**: a synthetic fixture built in `<scratch>` by a script in the repo's test helpers: 20 s of ffmpeg `testsrc2` at 1920x1080 and variable frame rate around 30 fps, H.264 at about 7 Mb/s, `yuvj420p` full range, its H.264 header signalling BT.601 (`bt470bg` primaries and matrix, `smpte170m` transfer) and full range while its MP4 `colr` box says BT.2020 and limited range, as a Samsung phone writes, a -90° rotation in the display matrix, AAC stereo audio, `creation_time` and GPS written with exiftool.
- **course excerpt**: the first 5 minutes of a real online-course screen recording (H.264 at 0,2 to 0,4 Mb/s and 25 fps, AAC at about 128 kb/s (from: `research/2026-10-20/synthesis.md`; `research/spikes.md`)), cut with stream copy into `<scratch>`; it never goes into the repo.
- **still clip**: a synthetic fixture built in `<scratch>` by a script in the repo's test helpers: 60 s of a grey still at 1280x720 and 25 fps with a full-frame white frame at 3, 10, 17,4, 31 and 52 s, and a 40 ms 1 kHz beep at the same instants, H.264 lossless with FLAC audio in MKV (`research/spikes.md`).
- **60 fps clip**: a synthetic fixture built in `<scratch>` by a script in the repo's test helpers: 20 s of a grey still at 1280x720 and 60 fps with a full-frame white flash lasting 3 frames (50 ms) at 3, 10,4 and 17 s, and a 40 ms 1 kHz beep at each flash start, H.264 lossless with FLAC audio in MKV.
- **old ffmpeg stub**: a script named `ffmpeg` in `<scratch>` that prints a version line of 6.1 and exits 0, put first on `PATH`.
- **colour description of a source**: its colour range, primaries, transfer and matrix as the decoder reports them for its first decoded frame, which come from the video stream's own header (the VUI of H.264 and HEVC, the sequence header of AV1); the container's `colr` box counts only for a property the stream leaves unspecified (D61). Its **colour range** is the range of that description.
- **Android capture tags**: the `com.android.*` QuickTime keys an Android phone writes (version, manufacturer, model, Samsung's UTC offset) (from: `research/2026-10-20/merged/t5-metadata-ffmpeg.md`).
- **VMAF desktop and phone models**: libvmaf's `vmaf_v1.0.16_3d0h` and `vmaf_v1.0.16_5d0h`; **XPSNR**: ffmpeg's perceptual PSNR filter; **BtbN `gpl`**: the static ffmpeg builds from github.com/BtbN/FFmpeg-Builds that include libvmaf.
- **`<le>`**: the command prefix `lastencode`, run from the installed tool.

### Repository

- **R34:** The repository holds no recordings or other media; tests build synthetic fixtures with scripts at test time, and media files are ignored by git (D34).
  - *cmd* `git check-ignore tests/clip.mp4` prints `tests/clip.mp4` and exits 0

### Command line

- **R33:** The command line conforms to CLI Design Standard 0.2.0-draft.12, the maintainer's versioned standard for agent-facing command lines (discovery through `schema`, JSON output, error objects, exit codes, confirmation), which builders receive with this spec, and claims it in `<le> schema` under `conformance` (D23). Where the standard and this spec disagree on the interface (flags, output format, errors, exit codes, confirmation), the standard wins; on encoding, metadata and checks, this spec wins.
  - *cmd* `<le> schema` prints JSON whose `conformance` names standard version 0.2.0-draft.12 (expected)
  - *scenario* given `convert --category nope --json`, when it runs, then stderr's last line is a JSON object with `error.kind` `invalid_input` listing the valid categories, and the exit code is 2
- **R33a:** `<le> schema` lists every `error.kind` the tool can emit under `error_kinds`, each with its exit code, whether the standard or the tool defines it, what it means and how to recover, including whether repeating the command helps; the exit code of every error comes from that list (D87).
  - *test* `tests/test_error_kinds.py` triggers each kind and checks its `error.kind` and exit code against the list

### Platforms

- **R37:** The tool runs on Linux, macOS and Windows with Python 3.12 or newer and ffmpeg, ffprobe and exiftool on `PATH`; every requirement holds on each, except where R26f or R37a names the difference (D91).
  - **R37a:** On Windows: the machine's time zone comes from the system's current rules (R14a), and `--tz` works through the `tzdata` package; `source_ctime` is the file's creation time, so a rewrite that keeps size and modification time goes unnoticed until the hash check; a hard kill can leave a running ffmpeg holding its work file until it ends; and a source whose longest derived path (work file or tool temp file) would exceed 259 characters fails with a reason that names the length (D93).
  - **R37b:** CI installs ffmpeg 9.0 or newer with libx265, libsvtav1 and libopus, and exiftool, on the GitHub Actions runners `ubuntu-latest`, `macos-latest` and `windows-latest`, and the default test suite passes on each. Only tests that need a feature a platform lacks (the trash, non-UTF-8 names, POSIX signals, shell-script stubs, symlinks, a case-sensitive file system) are skipped there, each with its reason; `bench` tests (R27 to R32) run on Linux only (D91).
  - *cmd* the workflow in `.github/workflows/` runs on all three runners and its run on the release commit is green (expected)

### Listing and planning

- **R1:** `presets` lists every category and target with a one-line description of when to choose the category, the effective encoder, quality setting, bit depth, scale, audio codec and bitrate, keyframe interval, copy-video threshold, frame-rate cap, repeated-frame dropping and location policy (D17).
  - *cmd* `<le> presets --json` prints one JSON document with 5 categories and 2 targets (expected)
- **R2:** `convert` and `bench` need `--category`; the target defaults to `portable` (D5a). An unknown category or target is a usage error that names the valid values (D76).
  - *scenario* given `convert --category apartment-tour --target compat` on the phone clip, when it runs, then it fails with a usage error naming `portable` and `desktop`, writes nothing and exits 2 (expected)
- **R3:** `convert --dry-run` prints the plan for each source (action encode, copy-video, copy-file or skip; output path; settings; recording date and its source; the no-gain fallback where an encode might not shrink the file) and the free space the run needs, and writes no file (D17).
  - *scenario* given the phone clip and category apartment-tour, when `convert --dry-run` runs, then `<scratch>` holds no new file and the plan says encode
- **R4:** Every command accepts `--json`. `presets` and `bench` then print one JSON document; `convert` prints one JSON record per source per line (NDJSON), in the plan's source order whatever `--jobs` is, and one summary record, using the manifest's field names (manifest, R22). Logs and progress go to stderr (D17).

### Converting

- **R5:** Sources are files or folders, read recursively. Files with the extensions mp4, mkv, mov, m4v, avi, webm, ts, mpg and mpeg, in any letter case, are sources.
  - **R5a:** With an output folder, every other file in an input folder is copied unchanged to its mirror path with its modification time, recorded in the manifest as `copy-file` with its hash, and never trashed (D33). It passes when size and hash equal the source's, is skipped when the mirror holds a file with the same size and a modification time within 2 s of the source's (D94), and is copied again under `--force`; none of the video checks apply to it.
  - **R5b:** Files named `lastencode-manifest.jsonl`, `.lastencode.lock` or `.*.lastencode-part.*` in an input folder are neither sources nor copied, and the summary lists them.
  - **R5c:** System clutter of NAS and desktop systems is neither a source nor copied: folders `@eaDir`, `#recycle`, `#snapshot`, `.SynologyWorkingDirectory`, `.Trash-*`, `$RECYCLE.BIN`, `System Volume Information`, `.Trashes`, `.Spotlight-V100`, `.fseventsd`, `.TemporaryItems` and `.DocumentRevisions-V100`, and files `.DS_Store`, `._*`, `Thumbs.db` and `desktop.ini`, matched in any letter case; the summary gives their count (D51).
  - **R5d:** A video file that carries a `lastencode` tag (R23a) is an earlier output: it is neither a source nor copied, also under `--force` and when it is named on the command line, and the summary lists it with the excluded files of the excluded-files rule (R5b); a run left with no source exits 0. A file whose tag cannot be read is an ordinary source (D89).
    - *scenario* given an input folder holding `clip.mp4` and a tagged `clip.lastencode.mp4`, when `convert` runs with or without `--force`, then only `clip.mp4` is a source and the summary lists `clip.lastencode.mp4` as excluded (expected)
- **R6:** With `--output-dir DIR`, each output lands at that folder plus the source's path relative to the given input folder, with the extension `.mp4` (a no-gain copy may keep its own, as the no-gain rule R13b says); a source given as a single file lands directly in it (D8).
  - **R6a:** A file already at an output path that carries no `lastencode` tag and is not a matching no-gain copy is left alone, and that source fails with `conflict`; `--force` replaces it after confirmation (R26b). Any replaced output stays in place until its replacement has passed the fast check.
  - **R6b:** A file at an output path whose `lastencode` tag names a source hash other than the current source's is left alone too, with or without a manifest line, and that source fails with `conflict`; `--force` replaces it after confirmation (R26b). A tag naming the current source's hash with other settings is replaced as usual. `--dry-run`, which hashes nothing, plans `conflict` when the tag's source size or modification time differ from the source's. An output whose original the manifest records as trashed is never replaced without `--force` and confirmation, tagged or not (D53).
  - **R6c:** Without `--output-dir`, each output lands in its source's own folder as `<stem>.lastencode.mp4`, and a source whose output would not be smaller is skipped with the reason `no-gain` instead of copied, so every output carries the `lastencode` tag (R13b, R23a) (D90).
    - *scenario* given `work/clip.mp4` and `work/sub/b.mov`, when `convert work` runs without `--output-dir`, then the outputs are `work/clip.lastencode.mp4` and `work/sub/b.lastencode.mp4`, `work/lastencode-manifest.jsonl` has a line per source, and a repeated run skips both sources and excludes both outputs as earlier outputs (R5d) (expected)
  - **R6d:** Without `--output-dir`, files that are not videos stay as they are and are neither copied nor failures (D90).
  - **R6e:** Without `--output-dir`, the inputs are one folder, or files in one folder; that folder is the run's root and holds the manifest and the lock (R22, R25a). Inputs in more than one folder, or a root the tool cannot write to, are a usage error before any change (D90).
- **R7:** The plan fixes every path an output may take, including the no-gain path with the source's own extension. The run stops before encoding with a usage error that names the paths when two sources may map to the same path, when an output path is another source's path (so `--force` never replaces a source), or when a given output folder lies inside an input folder given as a folder; the last error suggests an output folder outside it. For a source given as a single file, `--output-dir` may be any folder except the file's own folder, subfolders of it included (D88). Paths are compared after resolving symbolic links, and on a file system that ignores letter case, without it.
  - *scenario* given `work/clip.mp4`, when `convert work/clip.mp4 --output-dir work/archive` runs, then the output is `work/archive/clip.mp4`; with `--output-dir work` it fails with a usage error and writes nothing (expected)
- **R8:** The source tree is the input folders given as folders and the files given as files. With an output folder, the tool writes nothing in the source tree; the only change there is the trash move (D8). Without one, it writes there only the outputs named by the next-to-source rule (R6c), their work files, the manifest and the lock (D90).
- **R35:** The source facts that drive a decision or a check come from the video, and a container label counts only where the video carries none (D62): the colour description, the field order and the sample aspect ratio (R36) from the first decoded frame, which is the first frame the decoder returns even when a stream-copied cut opens with packets it drops (D86), and the frame rate from the presentation times of the video packets, never from the container's nominal or average rate fields (R10a, R10b).
  - **R35a:** When the container's colour values differ from the colour description, or the container's duration (ffprobe `format.duration`) differs by more than 0,5 s from the end of the last video packet (its presentation time plus its duration), the plan's and the manifest's warnings list and the summary name the property and both values; the run goes ahead (D62).
- **R36:** A source whose decoded video is interlaced, or whose pixels are not square (sample aspect ratio other than 1:1), fails before any encode or copy, with a reason naming the property and its value; nothing is written at its mirror paths (D64).
  - *scenario* given a 2 s synthetic interlaced clip and a 2 s clip with sample aspect ratio 16:15, when each is converted, then each fails with its reason, no output exists for it, and the exit code is 1 (expected)
- **R9:** Encoding follows the preset table below; the table and every built-in value in it bind (D1, D2, D3, D4, D5, D6, D7, D22, D35, D37, D39, D44, D45, D55, D57, D60, D65, D70, D72, D74, D75, D76, D81, D82).

  | Category | portable: x265 10-bit, Opus | desktop: SVT-AV1 10-bit, Opus, where not as portable | Keyframe max | Scale | Copy-video below |
  |---|---|---|---|---|---|
  | apartment-tour | CRF 28, slow, Opus 48k | as portable | 2 s | native | 1,5 Mb/s |
  | dance-lesson | CRF 28, slow, aq-mode 3, aq-strength 1.1, default deblocking, Opus 64k | as portable | 2 s | short side 720 | 1,0 Mb/s |
  | webinar | CRF 28, slow, Opus 24k mono for a dual-mono source, otherwise Opus 48k stereo | CRF 50, preset 4, `tune=1:enable-variance-boost=1:ac-bias=1.0:tf-strength=1:sharpness=1:enable-qm=1:qm-min=2:scm=1`, repeated frames dropped | 5 s | native | 0,3 Mb/s; never on desktop |
  | call | CRF 28, slow, audio as webinar | as webinar, but CRF 45 | 5 s | short side 360 | 0,3 Mb/s; never on desktop |
  | holiday | CRF 26, slow, Opus 64k | as portable | 2 s | native | 1,5 Mb/s |

  Webinar and call cap the frame rate at 25 fps on every target (R10b, D57); the other categories keep the source's rate. Desktop audio follows the portable column.
  - *scenario* given no preset file, when `presets --json` runs, then every category's effective values on both targets equal this table's (expected)
  - **R9e:** On the reference machine with `--jobs 1`, the portable preset of every category should encode a 1920x1080 30 fps source in at most 2 times its duration, and a source with a higher pixel rate (width times height times frame rate) in at most that multiple scaled by its pixel rate over that of 1920x1080 at 30 fps. This speed target is checked by a measurement on the reference machine and is not a condition of acceptance (D67, D84).
  - **R9a:** Scale shrinks only: a source whose short side is at or below the target keeps its size, and orientation decides which side is short.
  - **R9b:** A user preset file in TOML (`$XDG_CONFIG_HOME/lastencode/presets.toml`; when that variable is unset, `~/.config/lastencode/presets.toml` on Linux and macOS and `%APPDATA%\lastencode\presets.toml` on Windows; or the file given by `--presets FILE`) can change any value of the built-in table and add categories. It holds one table per category (`[categories.<name>]`, with `base` and `location`) and one per category and target (`[categories.<name>.<target>]`); its keys, values and units are those of `presets --json`. A new category names an existing one as `base` and inherits every value it does not set; an unknown key or a value of the wrong type is an error. `presets` shows each effective value and whether it comes from the built-in table or the file; an invalid file (unknown key, wrong type, unknown category base or target) is a usage error before any work, and one with a table for an unknown target, such as `compat`, names the valid targets; an encoder parameter in it that the encoder rejects falls under the tool check (R24) (D27, D76, D93).
    - *scenario* given a preset file with a `[categories.webinar.compat]` table, when `presets` runs, then it fails with a usage error naming `portable` and `desktop` and exits 2 (expected)
- **R10:** Every frame of the source reaches the output with its timing: the output's video frame count equals the source's, and each frame's presentation time, counted from the first frame, stays within 2 ms of the source's, except in a benchmark variant that changes frame rate, for a source above a frame-rate cap (R10b, D57) and where repeated frames are dropped (R10a).
  - *scenario* given the phone clip with variable frame rate, when it is converted, then frame counts of source and output are equal
  - **R10a:** In encoded video of a preset with repeated-frame dropping on (webinar and call on desktop in the built-in table), a frame that differs from the last kept frame by less than the default thresholds of ffmpeg's `mpdecimate` filter is dropped, as long as the kept frames lie no more than 1 s apart, or as far apart as the source's own frames where those lie further; each kept frame keeps its source presentation time within 2 ms (within the cap's tolerance when the frame rate is capped, R10b), and a change too small to cross the thresholds shows with the next kept frame, or not at all when it is gone by then (D36). The setting is a preset value that `presets` lists and the preset file can change (R1, R9b).
    - *scenario* given the still clip, when it is converted as webinar for desktop, then every white frame appears at its source time, every beep starts within 2 ms of its white frame, no two kept frames lie more than 1 s apart, and no two keyframes more than 6 s apart (expected)
  - **R10b:** A preset can cap the frame rate (webinar and call in the built-in table: 25 fps). A source is above the cap when some half-open 1 s window `[t, t+1 s)` of its presentation times holds more frames than the cap plus one; otherwise it is within the cap and keeps every frame (R10). In encoded video of a source above the cap, every half-open 1 s window holds at most the cap's number of frames, and every such window inside the video at least one fewer than the cap; each output frame, presented at time t counted from the first frame, shows a source frame that is on screen at some moment within half the capped frame interval of t (20 ms at 25 fps): its presentation time is at most t plus that half interval, and the next source frame's is above t minus it, so inside a source gap longer than the capped interval the previous frame repeats. With repeated-frame dropping on, the output meets the dropping rule (R10a) with the capped frames in place of the source's frames, and the lower bound does not apply. The cap is a preset value, a number of frames per second or `native`, that `presets` lists and the preset file can change (R1, R9b) (D57).
    - *scenario* given the 60 fps clip, when it is converted as webinar for portable, then no 1 s window holds more than 25 frames, every white flash shows and starts no more than 40 ms after its source start, and every beep starts within 40 ms of its flash's first output frame (expected)
- **R11:** No two consecutive keyframes in an encoded output lie further apart than the preset's keyframe interval (in an output with repeated frames dropped, the interval plus 1 s, or plus the source's own longest frame gap where that is longer; repeated-frame dropping, R10a, D36), and every keyframe is a point a player can start decoding from (closed GOP).
- **R12:** Encoded outputs are upright with no rotation tag (D20).
  - **R12a:** Encoded outputs use the limited range and are tagged so (D30, D76). A source whose stream header and container disagree is converted from the stream header's range (D61).
    - *scenario* given a clip whose HEVC header signals full range while its MP4 `colr` box says limited, when it is converted for portable, then the output's luma lies within the limited range and its decoded image matches the source's in black and white level (expected)
  - **R12b:** Outputs have their index at the start of the file.
  - **R12d:** Every encoded output carries the source's primaries, transfer and matrix, with the range the range rule (R12a) gives, and states the same values in its video stream's header and in its container (D61).
    - *scenario* given the phone clip, when it is converted as apartment-tour for portable and as webinar for desktop, then the output's stream header and its `colr` box both say `bt470bg` primaries and matrix and `smpte170m` transfer, and the Colour check passes (expected)
  - **R12e:** An output that carries the source's video stream unchanged (copy-video, R13, or a repackaged no-gain copy, R13b) states in its container no colour value that contradicts that stream's header; the container either repeats the header's values or states none for them (D61).
  - **R12c:** An HDR source (PQ or HLG transfer in its colour description) keeps its transfer, primaries and HDR metadata on every target; the tool never tone-maps (D77).
    - *scenario* given `convert` with the option `--tonemap-hdr`, when it runs, then it fails with a usage error for an unknown option, writes nothing and exits 2 (expected)
- **R13:** When the source video is H.264 or HEVC and its bitrate is below the preset's copy-video threshold, the output carries the source video stream unchanged and only the audio is re-encoded; the plan and manifest say `copy-video` (D11, D39, D81).
  - *scenario* given the course excerpt, category webinar and a preset file that raises webinar's portable copy-video threshold to 0,5 Mb/s, when converted, then the output video stream is bit-identical to the source's and the audio is Opus
  - **R13a:** Copied video keeps the source's keyframe spacing, rotation tag, bit depth, colour range and HDR signalling, so the repeated-frame, keyframe, upright and colour-range rules (R10a, R11, R12, R12a) do not apply to it (D24, D76). A source above a preset's frame-rate cap (R10b) is encoded, never video-copied (D57). The no-gain fallback (R13b, R13c) is separate.
- **R13b:** When the output is not smaller than its source, the mirror gets the source's streams unchanged instead, and the plan and manifest say `no-gain` (D25). An MP4 or MOV source is copied under its own extension, a source of another container is repackaged into MP4 when its streams fit MP4, and both then get the same metadata step as any output and pass the fast check without its Keyframes row. A source that cannot be repackaged is copied byte for byte under its own extension and passes when its size and hash equal the source's; when the run must strip its location or write a date it lacks, it fails instead.
  - **R13c:** The no-gain fallback applies to every source: scale, rotation, codec, the frame-rate cap and repeated-frame dropping are not requirements a copy must meet, so a no-gain copy keeps the source's (D57, D76).
  - **R13d:** When a `--force` run with `--trash-originals` puts a source's output at a different planned path than before, the previous output goes to the trash once the new one has passed; without `--trash-originals` the previous output stays and the summary names it (D54).
    - *scenario* given a MOV source whose earlier output is `clip.mp4`, when a `--force --trash-originals --yes` run gives a no-gain copy `clip.mov` that passes, then `clip.mp4` is in the trash; the same run without `--trash-originals` leaves `clip.mp4` in place and the summary names it

### Metadata

Each rule compares the output with its source after the run.

- **R14:** The output's recording date (`creation_time`, and with it the MP4 movie, track and media header dates) is the most trustworthy date available, in this order: the source's `creation_time`; the source's `Keys:CreationDate`; a timestamp in the file name (patterns `YYYYMMDD_hhmmss`, `VIDYYYYMMDDhhmmss`, `VID_YYYYMMDD_hhmmss`, `YYYY-MM-DD`); the source's file date (D16). When the source has `Keys:CreationDate`, the output has the same value.
  - **R14a:** A file-name timestamp is read as local time in the time zone of the machine running the tool, or in the IANA zone given by `--tz`; a pattern without a time of day means 00:00. The manifest's date source names the rule of R14 that gave the date (D43).
    - *scenario* given a clip without `creation_time` named `20260915_143012.mp4`, when it is converted with `--tz Europe/Warsaw`, then the output's `creation_time` is `2026-09-15T12:30:12Z` and its manifest line gives the file name as date source (expected)
- **R15:** When the source carries GPS coordinates and location is kept, exiftool reads the same coordinates from the output, both as `Keys:GPSCoordinates` and as `UserData:GPSCoordinates` (`©xyz`) (D10).
  - **R15a:** Location is kept unless the preset's location policy says `strip` or the run passes `--strip-location`; every built-in category keeps it. A stripped output carries no GPS in any box exiftool reads (including the 3GPP `loci` box and XMP), a byte search of the file for the source's coordinates finds nothing, and the summary lists each output that still carries GPS (D10).
- **R16:** The output's file modification time equals the source's, to the second.
- **R17:** The audio and video language and the Android capture tags of the source survive in the output.
  - **R17a:** Every audio stream of the source reaches the output, re-encoded per the preset; text subtitle streams and chapters are kept. Any stream the output cannot keep is named in the manifest and the summary.

### Fast check

This group applies to every work file.

- **R18:** The work file passes only when all of these hold; the table binds, with the dropped-frame limits of repeated-frame dropping (R10a, D36).

  | Check | Pass when |
  |---|---|
  | Probe | ffprobe reads the work file and finds a video stream |
  | Decode | a full decode reports no error |
  | Streams | video present; as many audio streams as the source; the text subtitle streams and chapters the stream rule (R17a) keeps |
  | Frames | frame count and frame times as the frame rules (R10, R10a, R10b) require |
  | Duration | the file's duration within 0,5 s of the source's; with repeated frames dropped (R10a), the video stream ends no more than 1 s, or the source's own longest frame gap where that is longer, before the source's video |
  | Keyframes | encoded video only: every keyframe is a random-access point (an IDR frame in HEVC, a key frame in AV1), and no gap in presentation time, including the one from the last keyframe to the end, exceeds the preset's interval by more than 10 % (with repeated frames dropped: by more than 1 s, or the source's own longest frame gap where that is longer) |
  | Colour tags | the output's colour description and its container's colour values are those the colour rules (R12a, R12d, R12e) require |
  | Colour | encoded video only: at 5 times spread over the video, the source frame and the output frame shown at that time, each converted to RGB from the colour values its own decoder attaches to the frame (not from the tool's probe) and scaled to 64 px wide, differ in the mean of each RGB channel by no more than 3 of 255 (guess) (D63) |
  | Metadata | date, GPS and file time as the metadata rules (R14 to R16) require |
  | Layout | MP4 index before the media data |

- **R19:** Only a passing work file is renamed to its final name; a failing one is deleted, and a run killed with SIGKILL leaves no file under a final name that has not passed. A previous output being replaced stays unchanged until then.
  - *scenario* given a first conversion killed with SIGKILL during encoding, when the output folder is listed, then no final-name file exists for the interrupted source
  - *scenario* given a `--force` replacement killed with SIGKILL during encoding, when the output folder is listed, then the previous output is still there unchanged
  - **R19a:** A work file is hidden, named `.<name>.lastencode-part.<ext>` in its output's folder, and becomes the output by a plain rename within that folder, never by a hard link or a copy (D29).
  - **R19b:** Before a source is processed, a leftover work file of that source from an interrupted run is deleted.
- **R20:** A failed file does not stop the run; the summary lists each failure with the failing check.
  - **R20a:** The run ends with a summary, as text or within the JSON output, holding per file: action, effective settings (encoder, quality, resolution and frame-rate change, share of dropped repeated frames, audio), size before and after, location kept or stripped, date source and trash outcome; and in total: files per action, bytes before and after.
- **R21:** Exit codes: 0 when the command completed (for a real `convert`, every file passed or was skipped; a dry run and a bench with invalid rows, R28a, also end with 0), 1 when a real `convert` had at least one failed file or a command could not proceed (a conflict, a missing or unreadable source), 2 for a usage error, 3 when a required tool is missing or unusable as the tool check (R24) defines it; `schema` lists 3 under `exit_codes`.

### Runs, tools and the record

- **R22:** Each processed source appends one JSON line to `lastencode-manifest.jsonl` in the output folder, or without one in the run's root (R6e), with: source path, size, modification time and SHA-256 hash; output path, size and SHA-256 hash; category; target; effective settings; share of dropped repeated frames; action; date source; location kept or stripped; dropped streams; each check result; trash outcome; tool, ffmpeg and encoder versions; start and end time. A completed run then appends its summary record, which skip and recovery ignore. Sizes are in bytes and times in ISO 8601 UTC, the source's modification and change times with a nanosecond fraction; a field without a value (a failed file has no output size) is null; the field names and types are published in `schema` as the output of `convert` (D46).
- **R23:** A source whose manifest line shows a passed check with the same settings and the same source size and modification time, and whose output still exists with the recorded size, is skipped; `--force` converts it again.
  - *scenario* given a run in which one of three sources failed, when the run is repeated, then only that source is encoded
  - **R23a:** Each output except a byte-for-byte copy carries a `lastencode` tag (the QuickTime key `LastEncode`, written after the last ffmpeg step) with the tool version, a fingerprint of the effective settings, and the source's size, modification time and SHA-256 hash. When the manifest has no line for a source whose output exists at one of its planned paths, the source is skipped if the tag matches, the source's hash included (or, for a byte-for-byte copy, the hashes of source and output are equal and the copy still meets the run's location and date rules), and its manifest line is rebuilt from the output and marked `recovered`, with fields that cannot be read from the output set to null and its checks marked `not-rerun`. Otherwise, or when more than one planned path holds a matching output, the conflict rules for existing files apply (R6a, R6b) (D31, D46).
  - **R23b:** `--force` turns off every skip, including the recovery from tags.
- **R24:** Before a run, the tool checks that the ffmpeg and ffprobe on `PATH` are at least version 9.0 (D59), that the target's encoders exist and accept every parameter of the effective preset, and that exiftool exists; a missing piece exits 3 and names it, with the rejected parameters and the encoder's version (D12, D12a, D52).
  - **R24a:** Each running job reserves twice its source's size in the folder its output goes to, and a job starts only while the free space covers all reservations; otherwise the run stops with the space it needs, and outputs finished so far stay valid. Running out of space anyway fails that file like any failed check.
- **R25:** `--jobs N` runs N files at once; each source gets an output that passes the same checks with the same settings as with one job, and the manifest holds the same set of lines apart from their order and times.
  - **R25b:** Each x265 encoder runs with a thread pool of the hardware threads available to the process divided by the number of jobs, rounded down and at least 1; SVT-AV1 gets no thread setting and keeps its own default (D83).
    - *scenario* given a machine with 16 hardware threads and two sources, when they are converted as webinar for portable with `--jobs 4`, then each x265 encoder runs with a pool of 4 threads (expected)
  - **R25c:** The thread count is not part of the effective settings, the manifest or the `lastencode` tag's fingerprint, so a rerun with another `--jobs` skips verified sources (R23, R23a) and meets the parallel-jobs rule (R25) (D85).
    - *scenario* given two sources converted with `--jobs 4`, when the run is repeated with `--jobs 1`, then both sources are skipped (expected)
  - **R25a:** A `convert` run holds a lock, the file `.lastencode.lock`, on its output folder, or without one on its root (R6e); a second run on the same folder exits before touching any file, with an error that names the first run. Without an output folder, a run also stops so when a lock held by another run lies in a folder above its root or inside its tree (D48).

### Originals

- **R26:** With `--trash-originals`, each source whose output passed the fast check goes, on Linux (R26f), to the freedesktop trash on the source's own mount (`.Trash-<uid>` at the mount's top, or the home trash when the source is on the home mount) after the rename, so no file is copied across disks (D9, D26).
  - **R26a:** A source with a failed output, or a skipped output that does not meet the earlier-run rule (R26c), stays. When no trash is available, the source stays and the summary warns. A source whose output lacks any of its streams other than data and timecode tracks (bitmap subtitles, for example) stays, and the summary names the stream (D47).
  - **R26b:** A run that would trash an original or a previous output, or replace a file the conflict rules (R6a, R6b) protect, asks for confirmation before any of these changes; without a terminal it needs `--yes`. `--dry-run` lists every file the run would create, replace, append to (the manifest) or trash and reports whether the run would need confirmation; a check that fails before any change (a locked output folder, R25a) fails first, without asking. This follows the CLI standard (R33, D23).
    - *scenario* given an output folder holding a file without a `lastencode` tag at the phone clip's output path, when `convert --force --json` runs without a terminal and without `--yes`, then it fails with `confirmation_required`, the file is unchanged, and `--dry-run` lists that file as replaced (expected)
  - **R26c:** `--trash-originals` also trashes a source skipped because an earlier run verified it, when its output's hash still equals the recorded one; a source with a `recovered` line goes only after its output passes the fast check again (D26).
  - **R26d:** Right before a source goes to the trash, its size and modification time must still equal those at probing, and its SHA-256 hash the one recorded for its output in the manifest or the `lastencode` tag; otherwise it stays and the summary says it changed (D46).
  - **R26e:** The summary reports the bytes moved to the trash separately and says that the space is freed only when the trash is emptied.
  - **R26f:** On macOS and Windows, `--trash-originals`, with or without `--dry-run`, fails with `invalid_input` naming the platform before any change (D92).
    - *scenario* given the platform reported as Windows, when `convert --trash-originals` runs on the phone clip, then it exits 2 with `invalid_input` naming Windows and writes nothing (expected)

### Benchmark

- **R27:** `bench --output-dir DIR` cuts excerpts of the given length (default 20 s, 3 per source, spread over the source) at the exact times, re-encoded losslessly as FFV1 in Matroska, where every frame is a keyframe, and encodes each excerpt with each variant, dropping repeated frames where the preset does (R10a): the preset, a list of quality settings, a list of targets, and optionally native and 25 fps (D15, D28, D40, D57). It writes only inside that folder.
  - **R27b:** When any file `bench` would write already exists in the output folder, `bench` without `--force` fails with `conflict` (exit 1), naming those files, before cutting any excerpt; `--force` replaces them.
    - *scenario* given a folder holding a `bench.csv`, when `bench` runs into it without `--force`, then it exits 1 with `conflict` and the folder is unchanged (expected)
  - **R27a:** By default the variants are the preset's own target at three quality settings (the preset's CRF and 2 below and above it) at the preset's own frame rate (its cap where it has one, R10b); `bench --dry-run` prints the number of variants, the space they need and the files it would write.
- **R28:** For each variant and excerpt, `bench.csv` holds: size, bitrate, encode time and encode time as a multiple of the excerpt's duration, VMAF desktop model mean and 5th percentile, VMAF phone model mean and 5th percentile, and XPSNR (D15, D41, D67, D69).
  - **R28f:** Variants are encoded one at a time, each with all hardware threads, so the time multiple compares with the single job of the speed target (R9e).
  - **R28d:** Before scoring, the variant is decoded to the excerpt's orientation, pixel format and colour range (the range of its colour description, D61) and, when its size differs, scaled to the excerpt's size with bicubic scaling; the row records that scaling.
  - **R28a:** Metrics compare the same frames: when frame counts differ, or a variant fails to encode, the row is marked invalid instead of scored.
  - **R28b:** A variant with a changed frame rate is scored against the excerpt passed through the same frame-rate change, and the row says so.
  - **R28e:** A variant with dropped repeated frames (R10a) is scored with each kept frame repeated until the next one on the excerpt's frame times, as a player shows it, and the row gives the share of dropped frames; the equal-frames rule (R28a) applies after that expansion (D36, D42).
- **R29:** For each excerpt and variant, a side-by-side clip (excerpt left, variant right) with a keyframe every second lets the user compare by eye and seek freely (D28).
- **R30:** Benchmark mode needs ffmpeg with libvmaf carrying the VMAF v1 models (from: `research/2026-10-20/merged/t4-measurement.md`) and the xpsnr filter; without them it exits 3 (D12a).
  - *scenario* given ffmpeg with libvmaf and xpsnr, when `bench` runs on the phone clip, then it exits 0, every valid row of `bench.csv` holds a number in each column the metrics rule (R28) names, and no column holds another metric (expected)
- **R31:** The benchmark never changes the preset table; picking new values is the maintainer's choice (D7).
- **R32:** `bench` prints the table sorted by size, with each metric's column.

## Decisions

| ID | Decision | Why | Date |
|---|---|---|---|
| D1 | Software encoding only (R9) | (not recorded) | 2026-10-20 |
| D2 | Quality before encode time, within reason (R9) | Longer runs are acceptable for better quality, without going to extremes. | 2026-10-20 |
| D3 | MP4 container for all encoded outputs (R9) | The iPhone's native player did not open MKV in a test (from: `research/2026-10-20/merged/t3-playback.md`). | 2026-10-20 |
| D4 | Opus audio on every target (R9) | Opus is widely supported; it played in an iOS 18 test (from: notes from the January 2026 prototype, not published). | 2026-10-20 |
| D5 | Presets on two axes, category and target (R9) | The user or agent may say "only on the computer, take the best and ignore phones". | 2026-10-20 |
| D5a | `portable` is the default target (R2) | A phone without extra apps is the first place files must play. | 2026-10-20 |
| D6 | 10-bit HEVC in the portable target (R9) | (not recorded) | 2026-10-20 |
| D7 | Fixed quality setting per category, picked by eye; the tool never changes the built-in values on its own (R9, R31) | The values were chosen by eye; changes need comparisons. | 2026-10-20 |
| D8 | Outputs in a separate mirrored folder; sources untouched (R6, R8) | (not recorded) | 2026-10-20 |
| D9 | Originals only to the trash, only with a flag, only after a pass (R26) | Originals stay by default, and the trash is the only way out. | 2026-10-20 |
| D10 | GPS kept by default; a preset or a run can strip it, and the summary shows where it stayed (R15, R15a) | The archive keeps location, while copies for other people may need it removed. | 2026-10-20 |
| D11 | Video below a per-preset bitrate is copied, only audio re-encoded (R13) | (not recorded) | 2026-10-20 |
| D12 | ffmpeg not bundled (R24) | The user installs the needed version. | 2026-10-20 |
| D12a | Minimum ffmpeg version required, newer VMAF models for the benchmark (R24, R30) | (not recorded) | 2026-10-20 |
| D13 | MIT licence | (not recorded) | 2026-10-20 |
| D14 | Python, installed as a uv tool | (not recorded) | 2026-10-20 |
| D15 | Benchmark on short excerpts with fast metrics (R27, R28) | (not recorded) | 2026-10-20 |
| D16 | Recording date as true as possible (R14) | Dates in the archive should reflect when a recording was made. | 2026-10-20 |
| D17 | Agent-first interface: listing, dry-run, JSON (R1, R3, R4) | The tool is mostly driven by an agent that picks commands. | 2026-10-20 |
| D18 | v1 leaves out per-file quality search, public test footage, AV1 for phones and slow metrics | A fairly quick build without excess scope. | 2026-10-20 |
| D20 | Rotation applied to the pixels (R12) | (not recorded) | 2026-10-20 |
| D22 | x265 as the portable encoder (R9) | At equal VMAF, x265's look was preferred to AV1's on a real clip (from: notes from the January 2026 prototype, not published). | 2026-10-20 |
| D23 | The command line follows CLI Design Standard 0.2.0-draft.12 (R33, R26b) | The maintainer's agent-facing CLIs share this standard. | 2026-10-20 |
| D24 | Copied video keeps the source's keyframes, rotation, bit depth, range and HDR (R13a) | A copy cannot change them, and players honour the rotation tag. | 2026-10-20 |
| D25 | When re-encoding gives no gain, the mirror gets the source's streams unchanged (R13b) | A complete mirror is more intuitive than one with gaps. | 2026-10-20 |
| D26 | Originals go to the trash on their own mount, including ones verified in earlier runs (R26, R26c) | A move to the home trash from a NAS would copy the archive over the network. | 2026-10-20 |
| D27 | A user preset file changes or extends the built-in table (R9b) | Changing a preset should not need a change in the repository. | 2026-10-20 |
| D28 | Benchmark excerpts and side-by-side clips get exact cuts and a keyframe every second (R27, R29) | Test clips must be seekable, and a stream-copy cut snaps to the source's sparse keyframes. | 2026-10-20 |
| D29 | Work files are hidden and become the output by a plain rename (R19a) | A sync client then uploads only the finished file, once (Synology Drive test, `research/spikes.md`), and hard links do not sync. | 2026-10-20 |
| D30 | 10-bit outputs use the limited colour range (R12a) | 10-bit limited range holds more levels than an 8-bit full-range source, and players read limited range reliably. | 2026-10-20 |
| D31 | A lost manifest is rebuilt from tags in the outputs instead of converting again (R23a) | Earlier conversions should not be thrown away because a record file went missing. | 2026-10-20 |
| D33 | Files that are not videos are copied into the mirror (R5a) | The mirror should be a complete copy of the folder, course materials included. | 2026-10-20 |
| D34 | No media in the repository; synthetic fixtures only (R34) | Real recordings are private and must never be published with the code. | 2026-10-20 |
| D35 | Webinar and call audio from a dual-mono source is Opus 24k mono (R9) | These recordings are speech, and mono already sounded fine to the user at 16k (measured: `research/spikes.md`). | 2026-10-20 |
| D36 | Webinar and call recordings on desktop drop repeated frames, keeping at least one frame per second (R10a, R11, R18, R28e) | On one course recording 22 to 37 % of frames repeat, and dropping them saved 12,5 % of video on one excerpt with sound in sync (measured: `research/spikes.md`, eight excerpts and the dropped-frame test). | 2026-10-20 |
| D37 | Webinar and call on desktop use SVT-AV1 at CRF 50, preset 4, tune 1 with the listed screen-content and psy settings (R9) | On one course recording this halved the video with text intact, and CRF 50 is where the user's blind rating put the limit for faces (measured: `research/spikes.md`, eight excerpts and two blind ratings). | 2026-10-20 |
| D39 | Webinar and call video is never copied on desktop (R9, R13) | AV1 shrank even the quietest parts of a course recording, and the no-gain fallback still catches a file that does not shrink (measured: `research/spikes.md`, eight excerpts, -9 % to -62 %). | 2026-10-20 |
| D40 | Benchmark excerpts are FFV1 in Matroska (R27) | It matched lossless x264 in size and was the fastest on noisy 1080p, with every frame a keyframe (measured: `research/spikes.md`, two synthetic 20 s clips). | 2026-10-20 |
| D41 | The benchmark table gives the 5th percentile for the VMAF phone model too (R28) | The worst frames, not the mean, separated the settings on the course recording (measured: `research/spikes.md`). | 2026-10-20 |
| D42 | Dropped-frame variants are scored as a player shows them, each kept frame held until the next (R28e) | The metrics should judge what the viewer sees. | 2026-10-20 |
| D43 | File-name dates are read in the machine's time zone unless `--tz` names another (R14a) | Phone file names hold local time without a zone, while container dates are UTC. | 2026-10-20 |
| D44 | Dance lessons use the encoder's default deblocking instead of -1:-1 (R9) | A weaker deblocking filter leaves more visible blocks in fast motion. | 2026-10-20 |
| D45 | Dance lessons keep Opus 64k (R9) | The sound serves to follow the beat and the teacher from a phone microphone in a hall, not to listen to music. | 2026-10-20 |
| D46 | A source is matched by its SHA-256 hash before recovery and before trash (R22, R23a, R26d) | Size and modification time alone could send a different original to the trash. | 2026-10-20 |
| D47 | A source whose output lost a stream is not trashed; data and timecode tracks excepted (R26a) | A note in the summary comes too late once the original is gone. | 2026-10-20 |
| D48 | One `convert` run per output folder (R25a) | A second run could delete the first run's work files as leftovers. | 2026-10-20 |
| D50 | Acceptance includes the desktop webinar preset on the still clip and the project's default test suite (Acceptance) | The desktop course preset and the archive safety rules are the main real uses. | 2026-10-20 |
| D51 | NAS and desktop-system clutter is skipped, not mirrored (R5c) | Thumbnail and index folders belong to the system that made them, which rebuilds them. | 2026-10-20 |
| D52 | An encoder that rejects a preset parameter stops the run (R24) | SVT-AV1 2.3 ignored three of the webinar settings and still exited cleanly, so the output would silently differ from the preset (measured: `research/2026-10-22/preset-tests.md`, 2026-10-20). | 2026-10-20 |
| D53 | An output tagged for a different source is a conflict, not replaced (R6b) | Once its original is in the trash, that output can be the only copy of the recording, and a new file reusing the name (a reset camera counter) would overwrite it. | 2026-10-21 |
| D54 | The previous output of a moved output goes to the trash only with `--trash-originals` (R13d) | `--force` alone asks no consent, and moving a file the call did not name needs the same consent as moving an original. | 2026-10-21 |
| D55 | Recorded sessions use the webinar category; there is no separate session category (R9) | Recorded sessions are practically the same use case as webinars. | 2026-10-21 |
| D57 | Webinars and calls are capped at 25 fps on every target, sources within it keep their rate, a source above it is encoded rather than video-copied, repeated-frame dropping stays, and the benchmark can still compare 25 fps with native (R9, R10, R10b, R13a, R13c, R27) | The owner wants the fewest frames that still look smooth, and on a course excerpt 15 fps looked visibly worse than 25 fps (measured: `research/spikes.md`). | 2026-10-21 |
| D59 | ffmpeg 9.0 is the minimum version (R24) | The acceptance ran only on 9.0.2 (from: `research/spikes.md`), and older versions may treat a source's colour range differently (guess). | 2026-10-21 |
| D60 | Calls are scaled to short side 360 on every target, and on desktop use the webinar settings with CRF 45 (R9) | A call shows mostly faces from webcams; the prototype's talking-head preset used CRF 42 at short side 360 (from: notes from the January 2026 prototype, not published), and the owner wants slightly smaller files than that. | 2026-10-21 |
| D61 | A source's whole colour description (range, primaries, transfer, matrix) comes from its video stream, and outputs state it the same in stream and container, or for copied video at least not against the stream (R12a, R12d, R12e, R28d) | Samsung phones label BT.601 full-range video in the MP4 `colr` box as BT.2020 or BT.709 limited, and a portable output of a real 4K apartment clip that followed the box came out visibly oversaturated (measured: `research/2026-10-22/preset-tests.md`, Samsung phone clips from 2022 and 2023, 2026-10-21). | 2026-10-21 |
| D62 | Picture facts that drive a decision come from the decoded video; the container only fills gaps, and disagreements about colours and length are warned (R35, R35a) | Containers already lied about colours, and the owner wants every such fact checked against the real video rather than assumed. | 2026-10-21 |
| D63 | The fast check compares the colours of source and output as a player shows them (R18) | The checks passed an output whose colours were visibly wrong, because they looked only at the file's labels. | 2026-10-21 |
| D64 | Interlaced sources and sources with non-square pixels fail with a reason (R36) | The tool has no deinterlacing or aspect correction, so such an output would show combing or a squeezed picture; the owner asked at least for a refusal with a warning. | 2026-10-21 |
| D65 | Holiday clips on portable use CRF 26 (R9) | The owner wants holiday clips at a higher quality than the CRF 28 of the other camera categories. | 2026-10-21 |
| D67 | Portable encoding of Full HD 30 fps should take at most 2 times real time on the reference machine with one job, and the bench reports encode time as a multiple of real time (R9e, R28) | Conversions will run on the reference machine, and the portable preset took about 15 times real time on 4K excerpts on an 8-thread virtual machine (measured: `research/2026-10-22/preset-tests.md`, two 20 s 4K excerpts, 2026-10-22). | 2026-10-22 |
| D69 | Preset choices are judged by VMAF v1, desktop model mean and 5th percentile with the phone model alongside; XPSNR stays in the benchmark only as a check that the measurement is sound, and SSIMULACRA2 is dropped (R28) | In a blind test at equal file size the owner ranked x265 and VVC above SVT-AV1 as VMAF did, while SSIMULACRA2 and XPSNR ranked x265 last (measured: `research/2026-10-22/preset-tests.md`, one 1080p60 apartment excerpt, three crops, 2026-10-22). | 2026-10-22 |
| D70 | Apartment tours, dance lessons and holiday clips use their portable settings on desktop (R9) | AV1 on desktop did not give a size gain worth a second encoder for camera footage: at portable VMAF, SVT-AV1 preset 4 changed apartment file size by 0 to +6 % on the mean and -8 % to -25 % on the 5th percentile, and it lost the blind comparison at equal file size (D69) (measured: `research/2026-10-22/preset-tests.md`, two 20 s 4K apartment excerpts and their 1080p downscales, 2026-10-22). The owner applies the same to dance and holiday clips without a run of their own. | 2026-10-22 |
| D71 | No H.266 (VVC) target or preset | At equal size the owner rated VVC about equal to x265, and it encoded 1,4 to 6,6 times slower (measured: `research/2026-10-22/preset-tests.md`, three excerpts, 2026-10-22). | 2026-10-22 |
| D72 | The x265 presets stay at `slow` (R9) | `slower` and `veryslow` gave larger files at a lower VMAF in 3 to 6 times the time (measured: `research/2026-10-22/preset-tests.md`, three 1080p excerpts, 2026-10-22). | 2026-10-22 |
| D74 | Dance lessons keep aq-mode 3 with aq-strength 1.1 (R9) | At equal file size the owner saw no difference between aq-mode 1, 2, 3 and 4, and VMAF differed by at most 0,4, so the existing setting stays (measured: `research/2026-10-22/preset-tests.md`, one 20 s 720p dance excerpt, 2026-10-22). | 2026-10-22 |
| D75 | Apartment tours and dance lessons stay at portable CRF 28 (R9) | In a blind test the owner ranked CRF 24 above 26 above 28 on still crops but saw almost no difference in normal playback, while CRF 26 and 24 made the file 53 % and 122 % larger (measured: `research/2026-10-22/preset-tests.md`, one 20 s 4K phone apartment excerpt, four crops, 2026-10-22). | 2026-10-22 |
| D76 | No `compat` target (R2, R9, R9b, R12a, R13a, R13c) | With the portable video settings it differed from `portable` mostly in audio, and as HEVC it still needed a codec extension on a stock Windows PC, the case it was meant for (from: `research/2026-10-20/merged/t3-playback.md`). | 2026-10-22 |
| D77 | HDR is kept on every target and the tool has no tone mapping (R12c) | Tone mapping served only the target for older players, which the tool does not have (D76). | 2026-10-22 |
| D81 | Webinar and call copy video on portable below 0,3 Mb/s (R9, R13) | (not recorded) | 2026-10-22 |
| D82 | Webinar and call use portable CRF 28 (R9) | In a blind test the owner ranked x265 CRF 26 best and the desktop AV1 output last on 3 of 4 crop sets, and chose CRF 28 because it is about 18 % smaller than CRF 26 (measured: `research/2026-10-22/preset-tests.md`, nine 20 s excerpts of one course recording, also scaled to short side 360 as a call stand-in, 2026-10-22). | 2026-10-22 |
| D83 | x265 threads are split evenly across `--jobs`; SVT-AV1 keeps its own default (R25b) | x265 fixed at 12 threads per job (from: the code before v0.1.0) left most of the reference machine idle with one job, which works against the speed target (R9e). | 2026-10-22 |
| D84 | The speed target is checked by a later measurement on the reference machine, which also compares `--jobs` 1, 2 and 4, and is not a condition of acceptance (R9e) | The owner set it as a target to check on the reference machine, not a gate for the build. | 2026-10-22 |
| D85 | The encoder thread count stays out of the effective settings and the settings fingerprint (R25c) | A rerun with another `--jobs` must still skip verified sources and match a one-job run. | 2026-10-22 |
| D86 | A source whose first packets do not decode is read from the first frame the decoder returns, not refused (R35) | A valid 15-minute stream-copied cut of a course recording, opening on a leading B frame, was refused as unreadable. | 2026-10-22 |
| D87 | Error kinds are listed in `schema`, not in the README or this spec (R33a) | Agents read the contract from the tool, and one list in the code cannot drift from the exit codes it drives. | 2026-10-23 |
| D88 | A single-file source may write to a subfolder of its own folder (R7) | `work/clip.mp4` into `work/archive` is the natural layout and cannot feed outputs back into the run; the owner found the refusal surprising. | 2026-10-23 |
| D89 | Files carrying a `lastencode` tag are never sources (R5d) | Outputs inside a folder converted later must not be encoded a second time. | 2026-10-23 |
| D90 | Without `--output-dir`, outputs land next to their sources as `<stem>.lastencode.mp4` (R6c, R6d, R6e, R8) | The owner finds a run without an output folder the intuitive default; it narrows D8, and the suffix keeps each output beside its original without ever taking its name. | 2026-10-23 |
| D91 | Linux, macOS and Windows, tested only on GitHub Actions runners (R37) | A public tool should run on the common desktop systems, and CI is the only macOS and Windows test environment available. | 2026-10-23 |
| D92 | The trash works only on Linux (R26f) | The freedesktop trash is a same-disk rename; the other systems' trash needs their own APIs or a new dependency, and refusing is safer than deleting. | 2026-10-23 |
| D93 | Windows differences are documented, not worked around (R37a, R9b) | Each workaround (a time-zone library, re-hashing for tamper checks, process job objects, long-path handling) costs a dependency or slow code for a rare case; failing a too-long path with a reason is deterministic. | 2026-10-23 |
| D94 | Modification times of a source and its output match within 2 s (R5a) | File systems store times at different precision (NTFS and SMB 100 ns, ext4 and APFS 1 ns), so an exact match fails for every copy on a NAS share. | 2026-10-23 |

### Builder decides

- The default for `--jobs`, as long as the parallel-jobs rule (R25) holds.
- How excerpts are spread over a source, and fewer excerpts when a source is shorter than their total length, within the excerpt rule (R27).
- The names of the benchmark's variant options, following the CLI standard's naming rules, and the text layout of human-readable output.
- How `bench --dry-run` estimates space, as long as the estimate is not below what the run uses.
- How the version check (R24) reads builds without a release number.
- How the side-by-side clip is encoded, as long as it plays in Haruna.
- How a dual-mono source is detected, as long as a stereo AAC track carrying the same voice in both channels counts as one.

## Risks

- Encoder versions change sizes and looks between upgrades; the manifest records them (R22), so a changed result can be traced to a version.
- x265 output bytes can differ with thread count, so outputs of parallel runs are compared by checks, not by bytes (R25).

## Acceptance

The maintainer runs it, because the course excerpt is real footage, on a Linux machine with ffmpeg 9.0 or newer whose SVT-AV1 accepts every webinar desktop parameter (SVT-AV1 4.2 in BtbN 9.0.2 does (measured: `research/spikes.md`)), a BtbN `gpl` build for `bench` and exiftool. Fixtures are the phone clip, the course excerpt, the still clip and the old ffmpeg stub in `<scratch>`; both `HOME` and `XDG_DATA_HOME` point into `<scratch>`, so the home trash lies on the fixtures' mount wherever `<scratch>` is mounted, and the reviewer confirms the trash lands there and in no `.Trash*` folder at a mount top before item 8. Pass means every item below passes (D50); the speed target (R9e) is not part of it (D84).

1. `presets --json` lists 5 categories and 2 targets with every column the listing rule (R1) names; `schema` claims standard 0.2.0-draft.12 (R33); `convert --category apartment-tour --target compat` exits 2 and names the valid targets (R2).
2. `convert --dry-run` on both fixtures writes no file and prints a plan (R3).
3. `convert` of the phone clip as apartment-tour for portable passes the fast check. The reviewer's own ffprobe and exiftool reads then show equal frame count, date, both GPS forms and file time, no rotation tag, the expected colour range, and BT.601 colours in both the stream header and the `colr` box; the summary warns that the source's container colours disagree (R9, R10, R11, R12, R12a, R12b, R12d, R14 to R18, R35, R35a).
4. `convert` of the course excerpt as webinar, with a preset file that raises webinar's portable copy-video threshold to 0,5 Mb/s, gives `copy-video` with a bit-identical video stream (R13, R9b).
5. A second run with the same options as items 3 and 4 skips both fixtures; after deleting the manifest a third run still skips them and rebuilds the manifest; `--force` converts them again (R23 to R23b).
6. Killing a first conversion with SIGKILL during encoding leaves no final-name file for that source, and killing a `--force` replacement leaves the previous output unchanged (R19).
7. The old ffmpeg stub on `PATH` makes `convert` exit 3 (R24).
8. `--trash-originals --yes` moves the fixture sources to the trash only after their outputs passed; without `--yes` and without a terminal it stops before encoding (R26 to R26b).
9. `bench` on the phone clip as apartment-tour with 5 s excerpts, three quality settings and the 25 fps option writes `bench.csv` in which every native and 25 fps row is valid and holds a number in each column the metrics rule (R28) names, the encode-time multiple included, and one side-by-side clip per excerpt and variant (R27 to R29).
10. A person plays the portable outputs in the built-in player of an Android phone about two years old and in Haruna next to the originals, and seeks in Haruna without stalls; fail if any does not play or seek, or its colours differ visibly from the original; where a player shows the original from its container's wrong labels, the reference is a frame of the original converted from its colour description.
11. `convert` of the still clip as webinar for desktop meets the repeated-frame scenario (R10a), passes the fast check with its dropped-frame limits (R11, R18), and the summary gives the share of dropped frames (R20a) (D50).
12. `convert` of the phone clip as webinar for desktop passes the fast check. The reviewer's own ffprobe reads then show AV1 video with no more than 25 frames in any 1 s window, no rotation tag, the limited range, and BT.601 colours in both the stream header and the `colr` box (R9, R10b, R12, R12a, R12d).
13. The default test suite (`uv run pytest`) passes. Besides the tests named with requirement IDs, these files cover: `tests/test_convert.py` R5, R5c, R7, R14 and R14a; `tests/test_copying.py` R5a and R13b; `tests/test_fast_check.py` R19a; `tests/test_bench.py` R27a and R30; `tests/test_encoding.py` R12c, R15a, R17a and R20; `tests/test_runs.py` R22, R23a, R23b, R24a, R25 and R25a; `tests/test_trash.py` R13d, R26a, R26c and R26d; `tests/test_conformance.py`, `tests/test_conformance2.py` and `tests/test_conformance3.py` the CLI standard's clauses under R33, named with the clause IDs, and `tests/test_error_kinds.py` R33a (D50). The suite also passes in CI on all three platforms (R37), and tests named with their IDs cover R5d, R6c to R6e, R7's single-file and case rules, and R26f.
14. `convert` of the phone clip, copied into an empty folder of `<scratch>`, without `--output-dir` meets the next-to-source scenario (R6c): its output and manifest lie next to it, a repeated run skips it and excludes its output (R5d), and the folder holds nothing else new (R8).

### Unverified

- Dropping repeated frames on real footage (R10a) and its benchmark scoring (R28e): item 11 covers only the synthetic still clip, and no check proves that only repeats were dropped or that such files seek well. Next check: a bench run of the still clip as webinar, and a person seeking inside a still stretch of a desktop webinar output in Haruna.
- Frame-rate cap on real footage (R10b): the tests use synthetic clips only. Next check: convert one real 50 to 60 fps screen recording as webinar and watch it for judder.
- The trash on a NAS share and in a synced folder (R19a, R26): tests simulate a second mount, and one manual sync-client test covers the rename (`research/spikes.md`), not the trash. Next check: trash an original in a synced folder on a NAS share and watch the sync client's log.
- Android capture tags surviving (R17): the phone clip carries none. Next check: convert a short real Android phone clip and compare its tag lists with exiftool, metadata only.
- Speed target (R9e): no test or acceptance item measures it. Next check: a 20 s 1080p30 and a 4K30 excerpt with each portable preset on the reference machine, with `--jobs` 1, 2 and 4.
- macOS and Windows beyond CI (R37): no person plays an output or runs the tool on those systems, and CI runners may lack tools a test needs. Next check: a run of the quick start on a Windows PC and a Mac, and the CI log's list of skipped tests.
- Excluded files, output layout, the source tree, exit codes and preset safety (R5b, R6, R8, R21, R31): no acceptance item or ID-named test covers them. Next check: builder tests named with these IDs on a small folder tree in `<scratch>`.
- JSON output, the run summary, the trash report and the benchmark table (R4, R20a, R26e, R32): no item parses them or reads the summary's per-file fields and trash bytes. Next check: parse the stdout of items 1, 3, 8 and 9 with `--json`.
