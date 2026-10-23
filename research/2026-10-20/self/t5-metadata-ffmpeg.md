# T5: metadata preservation, ffmpeg builds and container pitfalls

Research date: 2026-10-20. Method: web search plus direct reading of ffmpeg, Immich and Nextcloud Memories source code.
Coverage note: the shared web-search budget ran out mid-thread. The angles were covered by direct fetches of primary sources (source code, official docs, package indexes) instead of more searches. The ExifTool forum and trac.ffmpeg.org were unreachable during the run (outage / bot wall), so forum-based claims rest on search-result excerpts and are marked as such.
Addendum from the coordinator (slow AV1 seeking in Haruna, colour range, GPS policy per category) is covered in Q4, Q6 and Q7.

## TL;DR

ffmpeg's CLI deletes `creation_time` from the auto-copied global metadata on purpose. The MP4 muxer takes `mvhd`/`tkhd`/`mdhd` times only from that global key, so `-map_metadata 0` (or an explicit `-metadata creation_time=...`) is mandatory, and copying stream metadata does not help [1][4].
GPS survives only partly: ffmpeg writes MP4 location as a 3GPP `loci` box or as `mdta` keys under `udta/meta`, and Apple apps read neither. The reliable pattern is ffmpeg for the encode, then ExifTool `-tagsFromFile` on MP4 for dates and GPS, then `touch`/`os.utime` for mtime. ExifTool cannot write MKV [4][5][11].
For smooth seeking everywhere, the biggest lever is an explicit keyframe interval (`-g`). libaom leaves it at its library default when `-g` is unset, which fits the slow Haruna seeks. Next come `-fps_mode passthrough` (no silent frame drops), MP4 with `+faststart`, and full-range handling decided explicitly per encoder [46][3][50].

## Key Findings

### Q1. Preserving metadata when re-encoding phone video (ffmpeg 7.x to 9.x)

**Why `creation_time` disappears.**
- **What**: Based on [1], `copy_meta()` in `fftools/ffmpeg_mux_init.c` copies global metadata from the first input by default and then deletes `creation_time`, `company_name`, `product_name` and `product_version` (plus `duration` when `-t` is used). Stream metadata is copied by default with `AV_DICT_DONT_OVERWRITE` and keeps `creation_time` [1]. The deletion only happens on the *automatic* path. With an explicit `-map_metadata`, the user takes over, and users report `creation_time` then survives [8][10].
- **What (muxer side)**: Based on [4], the MOV/MP4 muxer writes one `mov->time` into `mvhd` and copies it to every track (`mov->tracks[i].time = mov->time`), so `tkhd`/`mdhd` dates come from global metadata only. Stream-level `creation_time` is ignored for MP4. Synthesizing: `-map_metadata 0` (global) is the switch that matters, and `-map_metadata:s:v 0:s:v` alone will not fix MP4 dates.
- **What (git master, not yet released)**: ffmpeg master adds `-keep_metadata` and a table of "stale on re-encode" keys (`encoded_by`, `encoding_tool`, `vendor_id`, `iTunSMPB`, Matroska `_STATISTICS_*`, always `major_brand`/`compatible_brands`). The `creation_time` deletion is unchanged [2][3]. This code is not in `release/9.0` [1]. Treat it as the likely behaviour of the next major release.
- **Evidence**: [1][2][3][4][8][10]. **Confidence**: high (source code, two versions).

**Recommended ffmpeg flags (MP4 target).**
- Base: `-map 0:v:0 -map 0:a? -map_metadata 0 -movflags +faststart -tag:v hvc1` (source-grounded parts: [1][4][43]). Optionally add `-metadata creation_time=<ISO8601Z>` read from ffprobe, which makes the date independent of the input's metadata layout (synthesis).
- `-movflags use_metadata_tags` writes *all* global keys as `mdta` keys, but inside `moov/udta/meta`. Apple reads `moov/meta`, so Apple apps still ignore them (reported in ffmpeg 6.1.1, and the placement is unchanged in 9.0 code) [4][5][6]. In MOV mode, the flag also *suppresses* the classic `udta` atoms (`©xyz` etc.) [4]. Synthesis: do not use it as the GPS/date strategy. It is mainly useful for carrying `com.android.*` keys for inspection.

**GPS / location.**
- **What**: Android's `MediaMuxer.setLocation()` stores an ISO 6709 location in `udta`, MP4 only [13]. ExifTool shows it as `UserData:GPSCoordinates` (`©xyz`) [7]. ffmpeg demuxes it to a `location` key, and sometimes also `location-eng` [8]. On output, the 9.0 `movenc.c` writes `location` as `©xyz` only in MOV mode without `use_metadata_tags`. In MP4 mode it goes through `mov_write_loci_tag()` (3GPP `loci`, 16.16 fixed point) [4].
- **What (Apple)**: ExifTool forum replies say Photos.app reads GPS from `Keys:GPSCoordinates` in .mp4/.m4v/.mov and `UserData:GPSCoordinates` only from .mov, so Android-style `©xyz` in an MP4 is ignored by Apple Photos [7] [forum, via search excerpt]. ExifTool's tag docs add: "Google Photos may ignore this if the coordinates have more than 5 digits after the decimal" for the Keys ISO6709 tag [12].
- **Evidence**: [4][5][6][7][8][12][13]. **Confidence**: medium-high (code is certain, Apple behaviour is forum-reported).

**Android / Apple keys.** ExifTool lists `com.android.version`, `com.android.manufacturer`, `com.android.model` and `samsung.android.utc_offset` as writable Keys tags. `com.android.capture.fps` appears not writable [12]. Synthesis: none of these drive gallery dates. `capture.fps` matters only for slow-motion clips, which are out of scope.

**Rotation / display matrix.**
- **What**: `-autorotate` is on by default [3]. Since its introduction, autorotation rotates the pixels and drops the rotation side data from the output, except on stream copy [17]. With `-noautorotate`, ffmpeg 7.1 started carrying a display matrix to MP4 where 7.0 did not (ticket #11649, now fixed) [18], so behaviour has moved between versions. MP4 writes a `tkhd` matrix from `AV_PKT_DATA_DISPLAYMATRIX` [4]. MKV writes it as `ProjectionPoseRoll` (ffmpeg muxer support since the 2023 patch series), and only for orthogonal rotations or flips [14][15]. Player support for Matroska roll was historically poor: in 2019 no player honoured it, and MPC-BE added it in 2021 [16].
- **Pros/cons (synthesis)**: baking costs nothing in quality, because we re-encode anyway. It is correct in every player and gallery, and works the same in MP4 and MKV. The downside is that the coded size becomes portrait (for example 1080x1920), so downscale expressions must target the short side (`scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'`). Keeping the matrix keeps the stored frame landscape, but depends on every consumer honouring it. That is fine in MP4, but risky in MKV and has changed across ffmpeg versions [16][18]. **Recommendation: bake rotation (default autorotate), and record `rotation_baked: <deg>` in the manifest.**
- **Evidence**: [3][4][14][15][16][17][18]. **Confidence**: medium-high.

**File mtime.** ffmpeg writes a new file, so filesystem times are "now", and `-map_metadata 0` does not change that [9]. Restore it after the encode with `touch -r src dst` [10], or in Python with `os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))`, which the Python docs call "the best way to preserve exact times" [53].

**MP4 vs MKV: what survives (source-grounded where cited).**

| Item | MP4 (ffmpeg 9.0, `-map_metadata 0`) | MKV (ffmpeg 9.0) |
|---|---|---|
| Creation date | `mvhd`/`tkhd`/`mdhd` from global `creation_time` [4] | Segment `DateUTC` from global `creation_time`; `creation_time` is *not* written as a tag [14] |
| GPS | `loci` box (MP4 mode), `©xyz` only in MOV mode [4] | Written as a generic tag (`location` is not on the skip list) [14]; no reader evidence found |
| Rotation | `tkhd` matrix if kept [4] | `ProjectionPoseRoll`, weak player support [14][16] |
| Post-edit with ExifTool | Read/write [11] | Read only [11] |

**When to use ExifTool after ffmpeg.** Use it on MP4/MOV to copy the original's dates and GPS into the places gallery apps read, for example `exiftool -tagsFromFile SRC -api QuickTimeUTC=1 "-Keys:all" "-UserData:all" "-ItemList:all" "-QuickTime:CreateDate" "-Keys:GPSCoordinates<GPSCoordinates" -overwrite_original DST`. Users report that a plain `-all:all` copy restored GPS but left track/media dates stale [23-forum]. QuickTime integer dates (`CreateDate`, `Track*Date`, `Media*Date`) are UTC by spec and cannot carry a timezone. `Keys:CreationDate` is a string and should carry an offset, and Apple Photos shows wrong dates when it lacks one [23]. ExifTool 13.59 (2026-05-27) is current. MKV/WebM are read-only [11].
**Confidence**: medium (the tool facts are primary, the exact copy recipe needs testing).

### Q2. How gallery apps decide date and location

| App | Date source (in order) | TZ / location | Source quality |
|---|---|---|---|
| **Immich** | `SubSecDateTimeOriginal`, `SubSecCreateDate`, `DateTimeOriginal`, `CreationDate`, `CreateDate`, `MediaCreateDate`, `DateTimeCreated`, `GPSDateTime`, ... then `min(fileCreatedAt, birthtime/mtime)` [19] | exiftool-vendored with `defaultVideosToUTC: true`, `geoTz` from GPS, `inferTimezoneFromDatestamps` [20]; GPS from composite `GPSLatitude`/`GPSLongitude` [19] | primary (code) |
| **Nextcloud Memories** | Videos: `ContentCreateDate` ?? `CreationDate` (then the generic `DateTimeOriginal`/`CreateDate` chain); fallback file mtime [21] | ExifTool runs with `-api QuickTimeUTC=1`; TZ from `OffsetTimeOriginal`/`OffsetTime`/`LocationTZID`, else UTC [21] | primary (code) |
| **Apple Photos** | `Keys:CreationDate` overrides the QuickTime UTC date when present [22-forum][23] | GPS from `Keys:GPSCoordinates` (mp4/mov), `UserData` only in .mov [7] | forum |
| **Synology Photos** | Reported to prefer XMP `com.apple.quicktime.creationdate`, then XMP video `DateUTC`, else file modification time; Android videos lacking those land at the mtime [24]; Pixel videos showed upload time [25] | not documented | forum, single-source [single-source] |
| **Google Photos** | Forum users say it sorts by `CreateDate`; may shift by TZ inferred from GPS [26] | `Keys` ISO6709 with >5 decimals may be ignored [12] | forum, weak |

- Synthesizing across sources: a re-encoded MP4 lands on the right date everywhere if it has (a) correct `mvhd`/`tkhd`/`mdhd` UTC times (from `-map_metadata 0`), (b) `Keys:CreationDate` with a `+HH:MM` offset (via ExifTool), and (c) file mtime equal to the capture time (a fallback for Synology and Immich). For location: `Keys:GPSCoordinates` plus `UserData:GPSCoordinates` (`©xyz`) covers Apple, Immich (via ExifTool composite) and others.
- Important side effect: Immich turns the UTC video date into local time using the GPS position [20]. **Stripping GPS (client apartment tours) makes Immich show UTC times** unless an offset-bearing `Keys:CreationDate` exists. Memories falls back to UTC in the same case [21]. So when stripping location, write `Keys:CreationDate` with an offset.
- **Confidence**: high for Immich/Memories, medium for Apple, low for Synology/Google.

### Q3. ffmpeg builds in 2026

**Upstream releases.** 9.0.2 "Lei" (2026-09-18, branch cut from master 2026-06-26), 8.1.3 (2026-09-21), 8.0.3 (2026-06-18), 7.1.5 (2026-06-20) [27]. 8.1 shipped 2026-03-16 [28][58]. The 9.0 changelog has no metadata-CLI changes relevant here. 9.0.2 hardens `mov` keys-atom parsing [29].

**Distro packages (checked 2026-10-20).**

| Distro | ffmpeg | libvmaf | SVT-AV1 | x265 |
|---|---|---|---|---|
| Ubuntu 24.04 | 6.1.1 | no | 1.7.0 | 3.5 |
| Ubuntu 25.10 | 7.1.1 | no | 2.3.0 | 4.1 |
| Ubuntu 26.04 LTS | 8.0.1 | no | 2.3.0 | 4.1 |
| Ubuntu "stonking" (dev) | 8.1.2 | no (Debian rules) | 4.1.0 | 4.2 |
| Debian 13 trixie | 7.1.5 | **no** | 2.3.0 | n/c |
| Debian forky/sid | 9.0.2 | **no** | 4.2.0 | n/c |
| Arch | 9.0.2 | **yes** (`vmaf` dep) | yes (4.2.0) | yes |
| Fedora `ffmpeg-free` | 8.1.2 (F44) | probably (rebuilt for vmaf 3.1.0) | n/c | **no** (patent-stripped) |
| RPM Fusion `ffmpeg` | full build | n/c | n/c | yes |

Sources: Ubuntu [31], Debian [32]; the Debian `debian/rules` enables libsvtav1, libx265, libopus, libdav1d and libaom but has no `--enable-libvmaf` [33]; Arch [34]; Fedora [35]. "n/c" = not checked.
- Synthesizing: no Debian/Ubuntu ffmpeg has libvmaf, and Ubuntu 26.04's SVT-AV1 2.3.0 is two majors behind upstream 4.2.0 (2026-07-14) [40]. x265 upstream is 4.2 (2026-04-19) [39]. A 4.3 (2026-07-31) is listed by one aggregator [57] [single-source]. libvmaf upstream reached 3.1.0 and 3.2.0 per packagers [41].

**Static builds.**
- **BtbN/FFmpeg-Builds**: daily autobuilds of master plus release branches 4.4 to 9.0. Variants: `gpl` (has x264/x265), `lgpl` (no x264/x265), `nonfree` (+fdk-aac), and shared variants. Linux targets glibc 2.28. The last 14 dailies are kept, plus the monthly last build for 2 years, plus a floating `latest` tag. The build scripts include `vmaf`, `svtav1`, `x265`, `libopus`, `dav1d`, `aom` [36]. The repo is MIT; the binaries carry GPL obligations [36].
- **mwader/static-ffmpeg**: Docker image (amd64/arm64), currently 9.0.2-1. Hardened static PIE, includes libvmaf, SVT-AV1, x265 (multilib), opus and dav1d, and ships a `versions.json`. No hardware acceleration [37].
- **johnvansickle.com**: unreachable during research. The latest release build seen in mirrors is 7.0.2, and a community post says maintenance dwindled [38] [low confidence]. Synthesis: do not depend on it.

**How the tool should require ffmpeg (synthesis, grounded in the facts above).**
1. Discover `ffmpeg`/`ffprobe` via `--ffmpeg PATH` > `$VIDEOCONVERT_FFMPEG` > `PATH`.
2. Capability-probe, don't version-guess: `ffmpeg -hide_banner -encoders` (libx265, libsvtav1, libopus), `-filters` (libvmaf, xpsnr), `-h encoder=libsvtav1` (check that `svtav1-params` exists), and `-buildconf`. Fail fast with an actionable message ("libvmaf missing: benchmark mode needs a build with --enable-libvmaf, e.g. BtbN gpl").
3. Minimum version: **ffmpeg ≥ 7.1**. Reasons: YUV colour-range negotiation that obsoletes YUVJ, `scale` with a reference input, and `scale2ref` deprecated (all in 7.1) [30]. `-fps_mode`/`-enc_time_base` are needed and documented in current docs [3].
4. Encode mode works with the distro ffmpeg; benchmark mode needs libvmaf, so document BtbN/Arch/static-ffmpeg. Record the `ffmpeg -version` first line, `-buildconf` hash, and encoder library versions in the manifest.
- libvmaf filter API today: `model=version=vmaf_v0.6.1` (default), `feature=name=psnr|name=ciede`, `log_fmt` (xml/json/csv/sub), `pool`, `n_threads`, `n_subsample`, plus framesync options. The docs' own multi-container example normalizes both inputs with `settb=AVTB,setpts=PTS-STARTPTS` [42]. `xpsnr` is a built-in filter (it got a fix in 9.0.1) [29][42].

### Q4. Stutter, freezes, non-seekable output: causes and settings

**(a) Keyframe interval: most likely cause of the slow Haruna seeks (coordinator addendum).**
- **What**: In ffmpeg's libaom wrapper, `-g` defaults to -1, and then `kf_max_dist` is *not set*, leaving libaom's library default [46]. I could not fetch that default value (believed to be very large, "9999 frames"; unverified, see Gaps). A Cinelerra-GG user's libaom AV1 file "would not seek", and setting `g=30`/`keyint_min=30` fixed it [50]. SVT-AV1's default `keyint` is -2 = "~5 seconds" and is only applied by ffmpeg when `-g` > 1 [44][47]. x265's default `keyint` is 250 frames (4,2 s at 60 fps, 8,3 s at 30 fps) with `open-gop` enabled by default [48]. mpv's precise seeks decode from the previous keyframe, so they slow down as the keyframe distance grows [51].
- Synthesizing: seconds-per-seek in libmpv is what a multi-second-to-unbounded GOP with heavy AV1 decoding produces. Container timestamps are a secondary suspect.
- **Set in the archiver**: always pass `-g` explicitly as `round(fps_nominal * K)` with K = 2 s for high-motion categories and 4-5 s for static/screen content. Also pass `-keyint_min` (x265: `min-keyint`; scenecut stays on). For x265, consider `no-open-gop=1` for robust seeking after a cut (low cost; synthesis, not measured). For SVT-AV1, keep the default closed GOP (`irefresh-type=2`) [47].
- **Fast verifier** (no decoding): `ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 FILE`, then compute the max gap between packets whose flags contain `K`; fail if it exceeds 1,5 × the target [56] (ffprobe options; the `K` flag semantics are standard ffprobe output, but this check needs a test). A cross-check that decodes only keyframes: `ffprobe -skip_frame nokey -select_streams v:0 -show_entries frame=pts_time -of csv FILE`.
- **Confidence**: medium (wrapper behaviour is primary, the libaom default value and the Haruna diagnosis are inferred).

**(b) Frame drops with VFR sources (`-fps_mode`).**
- **What**: `-fps_mode auto` (default) "chooses between cfr and vfr depending on muxer capabilities". `vfr` drops frames "so as to prevent 2 frames from having the same timestamp" [3]. Matroska has a fixed 1 ms `TimestampScale` in ffmpeg's muxer (`put_ebml_uint(... TIMECODESCALE, 1000000)`) [14].
- Synthesizing: phone VFR timestamps rounded to the encoder/muxer time base can collide, and `vfr` mode silently drops one of the pair. This explains the prototype's 4/3601 lost frames at 59,94 fps in MKV. The 1 ms grid also explains the "1 ms timestamp grid" note: at 59,94 fps frame spacing alternates 16/17 ms, which is legal, not a bug.
- **Set**: `-fps_mode passthrough` (keeps every frame with its demuxer timestamp [3]) plus `-enc_time_base demux` [3], unless a category deliberately changes fps (talking heads at 25 fps → then `fps=25` in the filtergraph, explicit). Verify the frame count: output `nb_read_packets` = input (± deliberate change).
- **Confidence**: medium (mechanism is documented, attribution to the prototype's drops is inference).

**(c) Remux flags from the prototype.**
- `-max_interleave_delta 0` means "continue buffering packets until it has a packet for each stream" (default 10 s) [43]. Synthesis: harmless for normal A/V, but with a missing or ending audio stream it can buffer to EOF. Don't use it by default.
- `-cues_to_front 1` rewrites the file to move Cues to the front ("shifting the main data") [43]. `reserve_index_space` (~50 kB per hour) avoids the shift [43]. Synthesis: front cues matter for HTTP streaming, not for local playback. The second write pass adds risk, and the prototype's one corrupt MKV came from exactly this kind of post-encode remux. **Recommendation: no post-encode remux. Mux once, directly from the encode.**
- `+genpts` only matters for inputs lacking PTS. Phone MP4s have PTS (synthesis). Drop it.
- MP4 `+faststart` moves `moov` to the front and "will not work in various situations such as fragmented output" [43]. Keep it for MP4 (gallery uploads and phone players), and don't fragment.
- **Opus in MP4**: priming/pre-skip is signalled by an edit list (`elst` `media_time` = pre-skip), and `PreSkip` in `dOps` is informative [52]. ffmpeg `use_editlist` defaults to `auto` [43]. Synthesis: the prototype's iOS test passed, so keep the defaults and do not pass `-use_editlist 0`.

**(d) HEVC in MKV.** I found no 2024-2026 primary source on HEVC-in-MKV seeking bugs (search budget ran out). Synthesis: x265's default open GOP (CRA frames flagged as keyframes) is the plausible mechanism for seek glitches in some players, so `no-open-gop` plus MP4 avoids it. Gap, needs testing.

**Recommended archive container (synthesis):** MP4 (`hvc1`, Opus or AAC, `+faststart`) for everything that a phone or gallery should open. iOS native players do not open MKV (prototype finding). MKV only for screen recordings if a feature truly requires it, but nothing in T5 requires it, and MKV loses ExifTool editability [11].

### Q5. Safe handling of originals

- **Atomic writes**: encode to `DST.partial` (or `.tmp-<uuid>`) in the *same directory*. `os.replace` is atomic only within one filesystem and "may fail if src and dst are on different filesystems" [53]. Before renaming, `f.flush()` and `os.fsync()` the file [53] (also fsync the directory, POSIX practice; synthesis). Resumability falls out of this: a run that dies leaves only `.partial` files, which are deleted on the next start, and finished files are skipped via the manifest.
- **Verify-then-trash**: (1) fast verify: ffprobe the duration (±1 frame), stream count/codecs, frame count vs source under passthrough, max keyframe gap, `color_range`, metadata presence (`creation_time`, GPS policy), and a decode of N short segments with `-xerror`; (2) record the result; (3) only then, on explicit opt-in, move the original to trash, never delete it outright. Freedesktop Trash 1.0: `$XDG_DATA_HOME/Trash`, or `$topdir/.Trash-$uid` on other volumes. Each item needs a `.trashinfo` with `Path` and `DeletionDate`, and an implementation that can't trash must "not erase the file without confirmation" [55]. On a NAS/SMB mount, a per-volume trash may be impossible, so fall back to a tool-managed `_quarantine/` directory (synthesis).
- **Manifest** (JSON Lines or SQLite next to the outputs; synthesis): source path, size, mtime_ns, a content hash (`hashlib.file_digest(f, "blake2b")`, Python ≥ 3.11 [54]), output path and hash, preset name + full ffmpeg argv, ffmpeg version line + `-buildconf` hash, encoder library versions, tool version, verify results (fast metrics; VMAF if benchmarked), metadata actions (GPS kept/stripped, rotation baked), and status (`encoded`/`verified`/`original_trashed`). A later run keys on the source hash, so moved or renamed files aren't re-encoded.
- **Confidence**: high for the OS primitives, synthesis for the workflow.

### Q6. Colour range (coordinator addendum)

- **What**: ffmpeg 7.1 introduced "YUV colorspace negotiation for codecs and filters, obsoleting the YUVJ pixel format" [30]. Per-encoder behaviour in 9.0:
  - **libx265** accepts `yuvj420p`. Full range is signalled when `color_range` is JPEG/pc, or, if unspecified, when the pix_fmt is `yuvj*` [45]. x265's own `range` is a VUI signal ("Default undefined (not signaled)") [48].
  - **libsvtav1** accepts only `yuv420p`/`yuv420p10`. It sets `param->color_range = (color_range == JPEG)`, and an unspecified range is treated as limited for YUV [44]. SVT-AV1 `--color-range` default is 0 = studio [47].
  - **libaom** has no `yuvj` support. Unspecified or MPEG range maps to `AOM_CR_STUDIO_RANGE`, JPEG to full [46]. Ticket #8455 documents that `yuvj420p` → libaom silently became `yuv420p` and "damages brightness range"; the suggested workaround is explicit `out_range=pc` plus `-color_range pc` [49].
- Synthesizing: the prototype's libaom file tagged `tv` is the expected result when range is not explicit. Either swscale converted the levels to limited (a true conversion, small levels loss, correct tag), or the frames stayed full but were tagged limited (a mis-tag: washed-out/clipped picture). Which one happened depends on the ffmpeg version (pre/post 7.1 negotiation). Check by measuring the luma range (see Gaps).
- **Retag vs convert**: *retagging* changes only the flag (output `-color_range`, or a bitstream-metadata filter) and is right only when the flag was wrong. *Converting* remaps pixel values (`scale=in_range=pc:out_range=tv`) and is right when changing the target range. Synthesis.
- **Recommendation**: keep full range end-to-end, because phone sources are full range and the target players/galleries already play these phone files. Use the filter chain `scale=...:in_range=pc:out_range=pc,format=yuv420p` (or `yuv420p10le`) with output `-color_range pc` and explicit `-colorspace bt709 -color_primaries bt709 -color_trc bt709` (or bt601/bt470bg if the source says so). For SVT-AV1 also pass `svtav1-params color-range=1`, and for x265 `x265-params range=full` (belt and braces). Fast verify: `ffprobe -show_entries stream=color_range,color_space,color_primaries,color_transfer` must equal the source.
- **Confidence**: medium-high (wrapper code is primary, the recommendation is synthesis).

### Q7. GPS policy: strip location only, keep date and rotation (coordinator addendum)

- **ffmpeg (MP4 and MKV)**: keep `-map_metadata 0` and delete only the location keys: `-metadata location= -metadata location-eng= -metadata com.apple.quicktime.location.ISO6709=`. `-metadata` overrides `-map_metadata`, and an empty value deletes the key [3]. The keys come from the demuxer's `location` mapping [8]. `creation_time` stays (MP4 `mvhd`, MKV `DateUTC`) [4][14]. Rotation is unaffected, because it is side data, not a metadata key [4][14].
- **ExifTool (MP4 only)**: after the copy step, delete `Keys:GPSCoordinates`, `UserData:GPSCoordinates`, `ItemList:GPSCoordinates`, the 3GPP `LocationInformation` (`loci`) and any XMP GPS. Then audit with `exiftool -a -G1 -s "-*GPS*" "-*Location*" FILE` (expect empty) [7][12]. For MKV, ExifTool can only audit (read-only) [11]. Post-hoc MKV tag removal needs MKVToolNix (`mkvpropedit`), which was not researched here.
- **Side effect**: without GPS, Immich and Memories show UTC unless `Keys:CreationDate` carries an offset [20][21], so write it for stripped files.
- Also note that GPS can hide in `udta` vendor boxes (Samsung/Xiaomi) that ffmpeg doesn't map [7]. Synthesis: for the strip policy, the safe default is *not* copying unknown `udta` content (ffmpeg doesn't) and auditing with ExifTool.
- **Confidence**: medium (the mechanism is documented, the end-to-end recipe needs a test file).

## Perspectives

- **Keep rotation as metadata vs bake.** The pro-metadata view (lossless orientation, original dimensions) rests on MP4 `tkhd` support, which is universal [4]. The pro-bake view rests on MKV roll support being weak [16] and ffmpeg's matrix propagation changing between 7.0 and 7.1 [18]. Since we re-encode anyway, baking has no quality cost. I lean bake, but this is a judgment call.
- **`use_metadata_tags`**: some guides treat it as "copy all metadata". The ffmpeg trac evidence shows it lands in a location Apple ignores [5][6]. Useful for completeness, not for compatibility.
- **Full vs limited range in archives**: full range keeps all code values of the phone source, while limited is the broadcast norm and tolerant of players that ignore the flag. The sources here don't settle player behaviour for AV1 full range on phones (see T3).
- **Front cues / faststart**: needed for streaming, irrelevant for local playback. The remux cost and risk of `cues_to_front` is my inference, not a documented bug.

## Practical Implications

Benchmark matrix / design candidates:
1. **Metadata pipeline (all presets):** ffmpeg `-map_metadata 0` (+ `-metadata location= -metadata location-eng=` only when the category strips GPS) → ExifTool `-tagsFromFile` for Keys/UserData dates and GPS (MP4) → `os.utime(ns=...)` from the source → verify with ffprobe + ExifTool.
2. **Container:** MP4 for all six categories. Drop MKV output unless a test shows a reason.
3. **GOP:** explicit `-g` per category (2 s motion / 5 s static) for every encoder. Add a benchmark column "max keyframe gap (s)" and "mpv seek latency" (see Gaps).
4. **Timing:** `-fps_mode passthrough -enc_time_base demux`, with an explicit `fps=` only in presets that reduce fps. Verify frame counts.
5. **Range:** explicit `in_range/out_range/-color_range` plus encoder params. Verify by tag equality + luma min/max.
6. **Rotation:** default autorotate (bake). Short-side-aware scale expression.
7. **ffmpeg:** require ≥ 7.1; probe capabilities; benchmark mode requires libvmaf (BtbN `gpl` or Arch/static-ffmpeg); record build info in the manifest.
8. **Originals:** `.partial` + fsync + `os.replace`; manifest with blake2b hashes; trash only after verify, per the freedesktop spec, with a quarantine-directory fallback.

## Sources

1. [FFmpeg `fftools/ffmpeg_mux_init.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/fftools/ffmpeg_mux_init.c) - `copy_meta()` default copy and `creation_time` deletion. Primary.
2. [FFmpeg `fftools/ffmpeg_mux_init.c` (master)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/fftools/ffmpeg_mux_init.c) - `reenc_delete_keys`, `-keep_metadata`. Primary.
3. [ffmpeg documentation (git)](https://ffmpeg.org/ffmpeg.html) - `-map_metadata`, `-metadata`, `-keep_metadata`, `-autorotate`, `-fps_mode`, `-enc_time_base`. Primary.
4. [FFmpeg `libavformat/movenc.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavformat/movenc.c) - mvhd/tkhd time, display matrix, `©xyz`/`loci`, mdta keys. Primary.
5. [FFmpeg trac #4209 comment, April 2024](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-April/069027.html) - `use_metadata_tags` output lands in UserData-Meta-Keys; Apple ignores it (ffmpeg 6.1.1). Primary (bug tracker).
6. [FFmpeg trac #4209 comment, March 2023](https://ffmpeg.org/pipermail/ffmpeg-trac/2023-March/065438.html) - `moov/udta/meta` vs `moov/meta`. Primary (bug tracker).
7. [ExifTool forum: macOS Photos ignores GPS on mp4](https://exiftool.org/forum/index.php?msg=82839) and [GPS in mp4/mov](https://exiftool.org/forum/index.php?msg=41874) - Photos reads Keys GPS; Android `©xyz` in UserData. Secondary (forum; read via search excerpts, forum offline).
8. [FFmpeg-user: Copy all metadata fields? (2020)](https://ffmpeg.org/pipermail/ffmpeg-user/2020-March/047583.html) - `-map_metadata 0` keeps `creation_time`; `©xyz` → `location`/`location-eng`. Secondary.
9. [FFmpeg-user: How to keep the original creation date? (2023)](https://ffmpeg.org/pipermail/ffmpeg-user/2023-June/056575.html) - filesystem times not preserved. Secondary.
10. [linux-tips: reducing video size preserving metadata and timestamp](https://linux-tips.com/t/reducing-video-size-with-preserving-metadata-and-timestamp/705) - `-map_metadata 0` + `touch -r`. Secondary.
11. [ExifTool home: supported file types](https://exiftool.org/) - MP4/MOV R/W, MKV/WebM read-only; v13.59 (2026-05-27). Primary.
12. [ExifTool QuickTime tag names](https://exiftool.org/TagNames/QuickTime.html) - Keys/ItemList writability, Android keys, QuickTimeUTC, Google Photos 5-decimal note. Primary.
13. [Android `MediaMuxer` reference](https://developer.android.com/reference/android/media/MediaMuxer) - `setLocation()` ISO 6709 in `udta`, MP4 only. Primary.
14. [FFmpeg `libavformat/matroskaenc.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavformat/matroskaenc.c) - 1 ms TimestampScale, DateUTC, skipped tags, ProjectionPoseRoll. Primary.
15. [FFmpeg-devel: matroskaenc support rotations (Aug 2023)](https://ffmpeg.org/pipermail/ffmpeg-devel/2023-August/313041.html) - rotation write support. Primary.
16. [Doom9: Matroska playback / rotation](https://forum.doom9.org/archive/index.php/t-176503.html) - player support for ProjectionPoseRoll (2019/2021, possibly stale). Secondary.
17. [FFmpeg-cvslog: autorotate option (2015)](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2015-May/089218.html) - rotation side data not copied when autorotating. Primary (old but still the design).
18. [FFmpeg trac #11649](https://trac.ffmpeg.org/ticket/11649) ([list mirror](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-June/073945.html)) - 7.1 display-matrix regression with `-noautorotate`. Primary.
19. [Immich `metadata.service.ts`](https://raw.githubusercontent.com/immich-app/immich/main/server/src/services/metadata.service.ts) - date tag order, mtime fallback, GPS tags. Primary.
20. [Immich `metadata.repository.ts`](https://raw.githubusercontent.com/immich-app/immich/main/server/src/repositories/metadata.repository.ts) - `defaultVideosToUTC`, `geoTz`. Primary.
21. [Nextcloud Memories `lib/Exif.php`](https://raw.githubusercontent.com/pulsejet/memories/master/lib/Exif.php) - video date order, QuickTimeUTC, mtime fallback. Primary.
22. [Nextcloud forum: Memories video time metadata](https://help.nextcloud.com/t/solved-memories-weird-behavior-with-video-time-metadata/199364) - UTC convention; Keys date overrides in Apple apps. Secondary.
23. ExifTool forum threads on QuickTime dates/time zones: [CreationDate without timezone](https://exiftool.org/forum/index.php?msg=64363), [Apple Photos MP4 date](https://exiftool.org/forum/index.php?msg=56781), [Date and timezone in videos](https://exiftool.org/forum/index.php?msg=52414), [copying dates to re-encoded video](https://exiftool.org/forum/index.php?msg=77890). Secondary (via search excerpts).
24. [ExifTool forum: Synology Photos video date tags](https://exiftool.org/forum/index.php?msg=86976) - XMP creationdate / DateUTC priority. Secondary, single-source.
25. [SynoForum: wrong date/time for videos](https://www.synoforum.com/threads/wrong-date-time-for-videos-despite-correct-exif-data.6807/latest) - Pixel videos show upload time. Secondary.
26. ExifTool forum on Google Photos: [Canon S120](https://exiftool.org/forum/index.php?msg=81590), [Panasonic ZS100](https://exiftool.org/forum/index.php?msg=47875) - CreateDate, GPS-based TZ guess. Secondary, weak.
27. [FFmpeg download page](https://ffmpeg.org/download.html) - 9.0.2 / 8.1.3 / 8.0.3 / 7.1.5 dates; BtbN link. Primary.
28. [FFmpeg news](https://ffmpeg.org/index.html#news) - 8.0 and 8.1 announcements. Primary.
29. [FFmpeg Changelog (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/Changelog) - 9.0, 9.0.1, 9.0.2 entries. Primary.
30. [FFmpeg Changelog (release/7.1)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/7.1/Changelog) - YUVJ obsoleted by range negotiation; scale ref input; scale2ref deprecated. Primary.
31. Ubuntu packages: [ffmpeg](https://packages.ubuntu.com/search?keywords=ffmpeg&searchon=names&exact=1), [svt-av1](https://packages.ubuntu.com/search?keywords=svt-av1&searchon=sourcenames&exact=1), [x265](https://packages.ubuntu.com/search?keywords=x265&searchon=sourcenames&exact=1). Primary.
32. Debian packages: [ffmpeg](https://packages.debian.org/search?keywords=ffmpeg&searchon=sourcenames&exact=1&suite=all&section=all), [svt-av1](https://packages.debian.org/search?keywords=svt-av1&searchon=sourcenames&exact=1&suite=all&section=all). Primary.
33. [Debian ffmpeg `debian/rules`](https://salsa.debian.org/multimedia-team/ffmpeg/-/raw/debian/master/debian/rules) - enabled libs, no libvmaf. Primary.
34. [Arch Linux ffmpeg package](https://archlinux.org/packages/extra/x86_64/ffmpeg/) - 9.0.2, depends on vmaf/svt-av1/x265. Primary.
35. [Fedora ffmpeg-free packages](https://packages.fedoraproject.org/pkgs/ffmpeg/ffmpeg-free-devel/fedora-44-updates.html) and [LinuxCapable Fedora guide](https://linuxcapable.com/install-ffmpeg-on-fedora-linux) - 8.1.2, no x265 in -free. Mixed.
36. [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) and [scripts.d](https://github.com/BtbN/FFmpeg-Builds/tree/master/scripts.d) - variants, retention, included libs. Primary.
37. [wader/static-ffmpeg](https://github.com/wader/static-ffmpeg) - Docker static builds 9.0.2-1 with libvmaf. Primary.
38. [Roon community: johnvansickle builds maintenance](https://community.roonlabs.com/t/broken-codecs-link/43269) and [mirror listing 7.0.2](https://github.com/MotionquestAI/ffmpeg-static-build). Secondary, weak.
39. [x265-devel: New Release v4.2 (April 2026)](https://mailman.videolan.org/pipermail/x265-devel/2026-April/014533.html). Primary.
40. [SVT-AV1 v4.2.0 release (2026-07-14)](https://newreleases.io/project/gitlab/AOMediaCodec/SVT-AV1/release/v4.2.0). Secondary mirror of a primary release note.
41. [Gentoo libvmaf](https://packages.gentoo.org/packages/media-libs/libvmaf) - upstream 3.1.0/3.2.0 available. Secondary.
42. [ffmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) - libvmaf options/examples, xpsnr, libvmaf_cuda. Primary.
43. [ffmpeg formats documentation](https://ffmpeg.org/ffmpeg-formats.html) - max_interleave_delta, avoid_negative_ts, cues_to_front, reserve_index_space, movflags, use_editlist. Primary.
44. [FFmpeg `libavcodec/libsvtav1.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavcodec/libsvtav1.c) - range, `-g` mapping, pix_fmts. Primary.
45. [FFmpeg `libavcodec/libx265.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavcodec/libx265.c) - range from yuvj/color_range, keyint. Primary.
46. [FFmpeg `libavcodec/libaomenc.c` (release/9.0)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavcodec/libaomenc.c) - range mapping, `kf_max_dist` untouched without `-g`, no yuvj. Primary.
47. [SVT-AV1 `Docs/Parameters.md`](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Parameters.md) - keyint -2 ≈ 5 s, color-range default studio, irefresh-type. Primary.
48. [x265 CLI documentation](https://x265.readthedocs.io/en/master/cli.html) - keyint 250, open-gop on, scenecut 40, range not signalled by default. Primary.
49. [FFmpeg trac #8455 (2021)](https://ffmpeg.org/pipermail/ffmpeg-trac/2021-August/059563.html) - libaom yuvj420p range damage, workaround. Primary (bug tracker).
50. [Cinelerra-GG list: AV1 seek fails (Aug 2024)](https://lists.cinelerra-gg.org/pipermail/cin/2024-August/008509.html) - libaom AV1 non-seekable, fixed by g=30. Secondary.
51. [mpv issue #1823](https://github.com/mpv-player/mpv/issues/1823) - precise seeks decode from the previous keyframe. Secondary (developer comment).
52. [Encapsulation of Opus in ISOBMFF](https://opus-codec.org/docs/opus_in_isobmff.html) - PreSkip informative, edit list does trimming (v0.6.8, 2016, stable). Primary.
53. [Python `os` docs](https://docs.python.org/3/library/os.html) - `os.replace` atomicity, `os.fsync`, `os.utime(ns=)`. Primary.
54. [Python `hashlib` docs](https://docs.python.org/3/library/hashlib.html) - `file_digest` (3.11), blake2b. Primary.
55. [Freedesktop Trash specification 1.0](https://specifications.freedesktop.org/trash/latest/) - trash dirs, `.trashinfo`, cross-filesystem rules. Primary.
56. [ffprobe documentation](https://ffmpeg.org/ffprobe.html) - show_entries, show_packets, read_intervals, count_packets. Primary.
57. [VideoHelp x265 version history](https://www.videohelp.com/software/x265-Encoder/version-history) - x265 4.3 (2026-07-31). Secondary, single-source.
58. [UbuntuHandbook: FFmpeg 8.1.2](https://ubuntuhandbook.org/index.php/2026/06/ffmpeg-8-1-2-over-hundred-fixes/) - 8.1.x point releases. Secondary.

## Gaps (what to measure in the benchmark)

1. **libaom default `kf_max_dist`**: not confirmed (aomedia source not readable in this run). Measure: encode 60 s with libaom without `-g` and record the max keyframe gap. Then measure mpv/Haruna seek latency (e.g. `mpv --no-config --hr-seek=yes` with scripted seeks, timing `playback-restart`) vs `-g` = 2 s / 5 s for x265, SVT-AV1 and libaom.
2. **Gallery acceptance matrix**: build 6 synthetic MP4 variants (with/without `Keys:CreationDate`+offset, with/without `©xyz`/Keys GPS, mtime correct/now) and import them into Google Photos, Apple Photos (iOS 18+), Immich, Synology Photos and Memories. Record the shown date/time and location. Google and Synology behaviour is mostly forum-level.
3. **MKV readers**: does ExifTool/Immich read Matroska `DateUTC` and a `LOCATION` tag? Test before allowing MKV for any category.
4. **`-noautorotate` in 8.x/9.x**: does the display matrix reach MP4 output on re-encode? Matters only if the "keep matrix" option is offered.
5. **Colour range**: for each encoder, compare source vs output `color_range` tag *and* luma statistics (`signalstats` YMIN/YMAX or a histogram on a frame with true blacks/whites). That tells a correct conversion apart from a mis-tag. Check AV1 full-range playback on the target phones (ties into T3).
6. **Frame drops**: confirm that `-fps_mode passthrough` gives an identical packet count on VFR phone sources for MP4 and MKV, and that `auto` drops frames (reproduce the 4/3601 case).
7. **HEVC open-GOP seeking**: compare seek correctness in MKV vs MP4 with `open-gop` on and off; no current primary source found.
8. **The "one corrupt MKV after remux"**: no matching bug found. Avoiding the second remux pass removes the risk; reproduce only if MKV stays in scope.
9. **johnvansickle builds**: site unreachable; status unverified.
10. **GPS strip completeness**: run the strip recipe on Samsung/Xiaomi/Pixel/iPhone samples and audit with `exiftool -a -G1 -s -ee` for leftover vendor boxes.
