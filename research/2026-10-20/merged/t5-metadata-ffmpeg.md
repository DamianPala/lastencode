# T5 merged: metadata preservation, ffmpeg builds and container pitfalls

Inputs: Report A `self/t5-metadata-ffmpeg.md` (Claude), Report B `codex/t5-metadata-ffmpeg.md` (Codex), notes from the January 2026 prototype, not published. Merge and verification pass: 2026-10-20.
Owner decisions applied: GPS is kept in every category, so A's GPS-strip recipe (A Q7) and the "write an offset date because stripped files show UTC" advice are dropped. Gallery apps are not targets, so the gallery date/location tables (both reports, Q2) are cut to one note. MP4 is the container for every category (consistent with merged T3).

## 1. Bottom line

- **Always pass `-map_metadata 0`.** On the automatic path, ffmpeg 7.1 and 8.0 copy the input's global metadata and then explicitly delete `creation_time`. An explicit global mapping skips that deletion. The MP4 muxer takes `mvhd`/`tkhd`/`mdhd` dates only from global `creation_time`. [verified in source]
- **ffmpeg alone does not keep GPS in Android or Apple form in MP4.** In MP4 mode the muxer writes the `location` key only as a 3GPP `loci` box in `moov/udta`. It writes `©xyz` only in MOV mode, and never writes Apple's `com.apple.quicktime.location.ISO6709` into `moov/meta`. So after the encode, an ExifTool step copies `Keys:all` plus `GPSCoordinates` into both `Keys` and `UserData` (`©xyz`), and ExifTool can write both. [verified]
- **Restore mtime last**, after ExifTool and before the rename: `os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))` from the source's `stat`. No ffmpeg flag does this. [both]
- **Always use `-fps_mode passthrough`.** With no `-r`, the default `auto` mode resolves to `vfr` for both MP4 and Matroska. `vfr` rounds frame times onto the encoder time base, which defaults to 1/framerate, and drops any frame that lands a tick behind. That rule, not the Matroska 1 ms grid, is what drops frames from VFR phone footage. [verified in source; conflict resolved]
- **Mux once, then add metadata once. No remux pass.** Drop `+genpts`, `-max_interleave_delta 0` and `-cues_to_front`. Keep `-movflags +faststart` and `-tag:v hvc1`. [both]
- **Set the keyframe interval explicitly and use closed GOPs on x265 (`open-gop=0`).** FFmpeg's libx265 wrapper flags CRA frames as keyframes. Mozilla fixed a freeze when seeking open-GOP HEVC in MKV, and noted that Apple's VideoToolbox can only start decoding at IDR frames. [verified; the effect on iPhone playback is inference]
- **Ubuntu 26.04 (8.0.1-3ubuntu2) and Debian (trixie 7.1.5, current packaging master) build ffmpeg without libvmaf.** Encode mode can use the distro ffmpeg. Benchmark mode needs BtbN `gpl`, Arch, or wader/static-ffmpeg. Probe capabilities, require ffmpeg 7.1 or newer, and record the build in the manifest. [verified]
- **Bake rotation** with the default autorotate and record it in the manifest. Matroska rotation is barely supported, and `-noautorotate` behaviour has changed between ffmpeg versions. [A only, owner-neutral]

## 2. Findings

### Q1. Metadata through ffmpeg 7.x/8.x, MP4 vs MKV, ExifTool, mtime

**creation_time.**
- [conflict, resolved for A] A: `copy_meta()` deletes `creation_time`, `company_name`, `product_name`, `product_version` (and `duration` with `-t`) from the auto-copied global metadata; explicit `-map_metadata` bypasses this [1]. B: "`creation_time` is not generally dropped by design"; losses come from key layout or explicit mapping [2]. Source code for both release/7.1 and release/8.0 has the deletion inside `if (!metadata_global_manual && nb_input_files)`, and any `-map_metadata` with a global spec sets `metadata_global_manual = 1` and copies the dict as is [1]. The docs [2] describe the default copy but not the deletion, which explains B's reading. The prototype history matches A: no `-map_metadata`, `creation_time` lost in MP4 and MKV. [verified]
- Stream metadata is still auto-copied (`AV_DICT_DONT_OVERWRITE`) when only a global mapping is given [1]. Stream-level `creation_time` does not matter for MP4: `movenc` parses only global `creation_time` (`ff_parse_creation_time_metadata(s, &mov->time, 1)`) and uses it for movie, track and media headers [3]. [A; verified]
- Belt and braces (synthesis): read the source `format_tags.creation_time` with ffprobe and also pass `-metadata creation_time=<ISO8601Z>`, so the date does not depend on how the demuxer named the key. If the source has none (screen recordings), write none and rely on mtime. See open question 3.
- ffmpeg master has a new `-keep_metadata` option and a list of "stale on re-encode" keys. The `creation_time` deletion is unchanged there [A only, not in a release; not rechecked].

**GPS / location (where ffmpeg writes it, where Apple reads it).**
- Android `MediaMuxer.setLocation()` stores ISO 6709 in `udta` (`©xyz`), MP4 only [13]. ffmpeg demuxes it to `location` (and `location-eng`) [A; history confirms `location`/`location-eng` in prototype outputs].
- `movenc.c` (8.0) `mov_write_udta_tag()`: in MOV mode without `use_metadata_tags` → `©xyz` from `location`; in MP4 mode → iTunes `meta`/`ilst` (no location key in that list) plus `mov_write_loci_tag()` (3GPP `loci`, lat/lon as 16.16 fixed point, ≈1,7 m resolution) [3]. The only `meta` box ffmpeg writes for MOV/MP4 is inside `udta`; the top-level `moov/meta` call is in the AVIF path only [3]. [verified]
- `-movflags use_metadata_tags` writes every global key as an `mdta` key, but inside `moov/udta/meta`. ExifTool groups that as `MOV-Movie-UserData-Meta-Keys`, while iPhone input shows GPS under `MOV-Movie-Meta-Keys` (`moov/meta`). The trac reporter says Apple apps do not show the `udta` copy [11]. In MOV mode the flag also suppresses `©xyz` [3]. Do not use it. [A; verified in source and trac]
- Apple Photos reads GPS from `Keys:GPSCoordinates` in .mp4/.mov and from `UserData` `©xyz` only in .mov [12] [A only, ExifTool forum via search excerpts; unverified]. This matters only if someone imports a file into Photos, because galleries are not targets.
- ExifTool writability [6][7]: `Keys:GPSCoordinates` (`location.ISO6709`) yes, with the note "Google Photos may ignore this if the coordinates have more than 5 digits after the decimal". `ItemList:GPSCoordinates` (`©xyz`) is writable. `UserData:GPSCoordinates` (`©xyz`) is `string/`, meaning writable but "Avoided", so it is created only if the group is named (`-UserData:GPSCoordinates`). `UserData:LocationInformation` (`loci`) is `undef/`, raw and avoided, so don't rely on it. By default, new tags go to ItemList, then UserData, then Keys, so name the group explicitly. [verified]
- Android `com.android.*` keys (`version`, `manufacturer`, `model`, Samsung `utc_offset`) are writable Keys tags; `com.android.capture.fps` appears not writable [A, ExifTool docs]. B: not a portable namespace [B]. Neither drives anything for our targets; copy them for completeness via `-Keys:all`.

**Rotation.** Autorotate is on by default. It rotates pixels and drops the display matrix. With `-noautorotate`, matrix propagation to MP4 changed between 7.0 and 7.1 (trac #11649). Matroska writes rotation as `ProjectionPoseRoll`, which players historically ignore [34][33][39][37] [A only]. Both reports favour baking, and B says it "needs broader playback testing" for the matrix route [both]. Scale filters must target the short side after rotation.

**MP4 vs MKV.**

| Item | MP4 (ffmpeg 8.0, `-map_metadata 0`) | MKV (ffmpeg 8.0) |
|---|---|---|
| Date | `mvhd`/`tkhd`/`mdhd` from global `creation_time` [3] | Segment `DateUTC` from global `creation_time` [4]. RFC 9559 defines DateUTC as when the Segment "was created by the muxing application" [10], so storing capture time there is an ffmpeg convention. `creation_time` is never written as a tag [4] |
| GPS | `loci` only [3]; `©xyz`/Keys via ExifTool [6] | Generic SimpleTag `LOCATION` (key uppercased, ISO 6709 string) [4]. Matroska's standard `RECORDING_LOCATION` is "US, Texas, Austin"-style text, with no coordinates field in the spec [9] |
| Post-edit | ExifTool read/write [6][40] | ExifTool read-only: every Matroska tag is `Writable: no` [8]; `mkvpropedit` not checked |
| Readers | ffprobe, ExifTool, Apple (Keys) | ExifTool reads `DateUTC` as `DateTimeOriginal` and `DATE_RECORDED` likewise [8]; ffprobe/mpv expose tags. No player or phone that uses them was found [unverified] |

(c) answered: MKV has no standard GPS element. Its date is a muxing date that ffmpeg and ExifTool happen to round-trip. No player in the target set uses either for anything. [verified for spec and ExifTool; reader survey not exhaustive]

**mtime.** ffmpeg creates a new file; `-map_metadata` does not touch filesystem times [both]. ExifTool also rewrites the file and changes its mtime unless `-P` is given [B], so set mtime after the ExifTool step. Use `os.utime(path, ns=(atime_ns, mtime_ns))` [28]. `rename()` keeps mtime.

### Q2. Gallery apps (de-scoped)

Both reports covered Immich, Memories, Synology, Google Photos and Apple Photos. Galleries are not targets now. One finding still matters for the pipeline: Immich and Memories fall back to file mtime, and Synology's own KB names mtime as a fallback too [44][45][46] [both]. So restoring mtime is cheap insurance for any future import. `Keys:CreationDate` with a `+HH:MM` offset is what Apple software uses for local time [A, forum]. Copy it from the source when present (iPhone files have it, Android files usually don't). Don't synthesize it (open question 2).

### Q3. ffmpeg builds and how the tool should require ffmpeg

- Upstream: 9.0.2 (2026-09-18), 8.1.3, 8.0.3, 7.1.5 [both, 41].
- (e) **libvmaf absent in Debian/Ubuntu** [verified]: Debian's packaging `debian/rules` (salsa master) enables libdav1d, libopus, libx265 and libsvtav1 (per-arch) and has no `--enable-libvmaf` [18]. The Ubuntu 26.04 source package `ffmpeg_8.0.1-3ubuntu2.debian.tar.xz` has no `vmaf` in `debian/rules` or `debian/control` [17]. The `libavfilter11` (resolute) dependency list has no libvmaf [17]. Debian trixie `libavfilter10` 7.1.5-0+deb13u1 and forky `libavfilter11` 8.1.2-2 pages do not mention vmaf [19]. This matches the history: Ubuntu 26.04 `ffmpeg` has `vmafmotion` but no `libvmaf`.
- [conflict, minor] Fedora `ffmpeg-free` on F44: A 8.1.2, B 8.1.3 → **8.1.3-1.fc44** [21, verified]. `-free` has no x265 [A].
- [conflict, minor] Debian forky ffmpeg: A says 9.0.2; the forky `libavfilter11` page shows 8.1.2-2 "and others" [19]. A probably saw sid or experimental. Not pursued.
- x265 4.3: A flagged it single-source; B cites Arch. Arch `x265 4.3-1` [20, verified]. SVT-AV1 in Ubuntu 26.04 is 2.3.0 vs upstream 4.2.0 [A].
- Static builds [both]: BtbN (daily master + release branches, `gpl`/`lgpl`/`nonfree`, glibc 2.28, libvmaf + SVT-AV1 + x265 + opus + dav1d; retention 14 dailies + monthly for 2 years) [22]; wader/static-ffmpeg 9.0.2-1 with libvmaf [23]; johnvansickle's newest is 7.0.2 (June 2024), too old [24].
- Requirement policy [both, synthesis]: discover `--ffmpeg PATH` > `$VIDEOCONVERT_FFMPEG` > `PATH`. Probe `-encoders` (libx265, libsvtav1, libopus, aac), `-filters` (libvmaf, xpsnr), `-h encoder=libsvtav1` and `-buildconf`, and fail fast with a hint ("benchmark needs libvmaf: BtbN gpl"). Require ffmpeg 7.1 or newer, because of YUV range negotiation replacing YUVJ and `scale` taking a reference input with `scale2ref` deprecated [25]. libvmaf takes `model=version=…`/`model=path=…`, and `model_path` was removed [B: 42; history hit the same error].

### Q4. Stutter, frame drops, seeking

**(d) Frame drops with `fps_mode` [conflict, resolved].**
- A blamed rounding to the "encoder/muxer time base" in `vfr` mode. B said the 1 ms Matroska grid "does not by itself explain a loss of four frames".
- Source check [verified]:
  - In `ffmpeg_mux_init.c` (8.0), `auto` resolves to CFR if `-r`/`-fpsmax` is set. Otherwise it uses `vfr` when the muxer has `AVFMT_VARIABLE_FPS`, and both `mp4` (`movenc.c`) and `matroska` have that flag [1][3][4].
  - In `ffmpeg_filter.c` (7.1 and 8.0), the output time base defaults to `av_inv_q(framerate)` unless `-enc_time_base` is set. The docs agree: "For video - use 1/framerate" [5][2].
  - In `video_sync_process()`, `VSYNC_VFR` drops a frame when `delta <= -0.6` ticks. `VSYNC_PASSTHROUGH` never drops [5].
- So phone VFR jitter, rounded onto a 1/59,94 s grid, can make a frame land a tick behind, and the frame is dropped before the muxer. The Matroska 1 ms `TimestampScale` [4] only rounds times afterwards; that is the legal 16/17 ms alternation in history, not the cause of drops. One 34 ms gap in the MKV output is a single dropped frame.
- History says the MP4 outputs did not lose frames under the same default, which is not explained (they may have had different flags). Reproduce in the benchmark.
- Fix [both]: `-fps_mode passthrough -enc_time_base demux`, with an explicit `fps=N` filter only in presets that reduce frame rate. Verify with packet counts.

**Remux flags [both].** `-max_interleave_delta 0` buffers until every stream has a packet. `-cues_to_front` rewrites the file. `+genpts` only fills in missing PTS [26]. Neither report found a bug that explains the one corrupt MKV. Both say: don't use these as general "stability" flags. A adds: no second write pass at all. Adopted.

**Keyframes / open GOP.**
- Without `-g`, libaom's own default applies (the T3 merge says 9999 frames). SVT-AV1 uses about 5 s, and x265 uses `keyint` 250 with open GOP on [A: 35, 36; 16].
- FFmpeg's libx265 wrapper marks CRA/BLA/IDR as keyframes [15, verified]. In MP4, CRA frames therefore become sync samples.
- Mozilla bug 2006226: HEVC in MKV froze after a seek because the demuxer treated only IDR frames as keyframes. It was fixed in Firefox 158, and the assignee notes VideoToolbox "can only start from IDR frames" [14, verified; B only].
- Synthesis: `open-gop=0` costs little and removes a class of seek failures on Apple decoders. Measure the size cost.

**Opus in MP4.** Pre-skip is signalled through the edit list, and ffmpeg's `use_editlist=auto` handles it [A: 32]. Keep the defaults. T3 notes trac #9177 (end trimming); check the duration in verify.

### Q5. Originals, atomic writes, manifest [both; A more concrete]

`os.replace` is atomic only within one filesystem [28]. fsync the file before the rename and fsync the directory after it. Delete leftover partials on start. Key the manifest on the source hash plus a preset fingerprint. Trash originals only after a passing verify and an explicit opt-in. The freedesktop trash spec forbids silent deletion when trashing fails [30]. Fall back to a `_quarantine/` folder on NAS mounts. BagIt is a reference for checksum manifests [43] [B].

## 3. Per-file pipeline (concrete)

Encode in a local work directory, then publish to the NAS. Writing over SMB/NFS during `+faststart`'s second pass is slow and harder to make atomic.

1. **Probe source** (and store the JSON in the manifest):
   `ffprobe -v error -show_format -show_streams -of json SRC`
   `ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets,avg_frame_rate,r_frame_rate -of json SRC`
   `exiftool -j -a -G1 -s -n -api QuickTimeUTC=1 SRC`. Keep `creation_time`, GPS, rotation, `color_range` and `st_mtime_ns`.
2. **Encode** to `WORK/<stem>.partial.mp4`. Encoder and colour flags come from T2/T3; the metadata and timing flags are fixed here:
   ```
   ffmpeg -hide_banner -nostdin -n -i SRC \
     -map 0:v:0 -map 0:a:0? -map_metadata 0 [-metadata creation_time=<src UTC ISO8601>] \
     -fps_mode passthrough -enc_time_base demux \
     -vf "<scale short-side>,<fps=N only if preset decimates>,format=yuv420p" \
     -c:v libx265 -preset slow -crf <C> -g <round(fps*K)> \
       -x265-params "open-gop=0:min-keyint=<…>:<preset params>" -tag:v hvc1 \
     -c:a libopus -b:a <B> -ac <src ≤2>      # fallback: -c:a aac -b:a <B>
     -movflags +faststart -f mp4 WORK/<stem>.partial.mp4
   ```
   Autorotate stays on (default). No second ffmpeg pass.
3. **Metadata step** (in place on the partial, only if SRC is MP4/MOV):
   ```
   exiftool -q -m -overwrite_original -api QuickTimeUTC=1 -tagsFromFile SRC \
     "-Keys:all" "-Keys:GPSCoordinates<GPSCoordinates" "-UserData:GPSCoordinates<GPSCoordinates" \
     WORK/<stem>.partial.mp4
   ```
   This copies `Keys:CreationDate` (with offset) and Android/Apple keys when the source has them. GPS ends up in `loci` (ffmpeg), Keys (`moov/meta`) and `©xyz`. If the source has no GPS, the redirects write nothing. For screen-recording MKV sources, skip this step.
4. **Fast verify** on the work file (any failure means status `failed`, the partial is kept for inspection, and the original is untouched):
   - Full parse and decode: `ffmpeg -v error -xerror -i OUT -map 0 -f null -`. Decoding is far cheaper than the x265 encode.
   - Streams and codecs as expected. Duration within one frame of the source. Video packet count equal to the source (passthrough), or within ±1 % of `dur × N` for decimating presets.
   - Max keyframe gap ≤ 1,5 × target: `ffprobe -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0`.
   - `color_range`/`color_space`/primaries/transfer as the preset intends.
   - `creation_time` equals the source to the second (`format_tags`). GPS present if and only if the source had it, with lat/lon within 1e-4 (`exiftool -n -GPSLatitude -GPSLongitude`). No rotation side data, and coded dimensions equal the source's displayed dimensions.
   - `moov` before `mdat`: read the top-level box headers in Python. ExifTool rewrites the file, so check this after step 3.
5. **mtime**: `os.utime(OUT, ns=(src.st_atime_ns, src.st_mtime_ns))`, then `fsync`.
6. **Publish atomically**: copy to `DESTDIR/.<stem>.<runid>.partial` (dot prefix also keeps sync tools away from it), fsync it, compare its BLAKE2b with the work file, `os.utime` again, `os.replace` to `DESTDIR/<stem>.mp4`, fsync `DESTDIR`, and re-stat to confirm size and mtime. Never overwrite an existing file without a manifest match.
7. **Manifest** (JSON Lines next to the output root, one fsync'd line per state change):
   `src_path, src_size, src_mtime_ns, src_blake2b, src_probe` (codec, wxh, fps, range, rotation, `creation_time`, has_gps), `out_path, out_size, out_blake2b, preset_name, preset_fingerprint` (hash of the argv minus paths), `ffmpeg_argv, exiftool_argv, ffmpeg_version_line, ffmpeg_buildconf_sha256, lib_versions` (x265/svtav1/opus/vmaf from `-version`/`-buildconf`), `exiftool_version, tool_version, verify` (each check plus its value), `metadata_actions` (`creation_time_source`, `gps_copied`, `rotation_baked_deg`), `status` (`encoded|verified|published|original_trashed|failed`), `timestamps`.
   On resume, skip a source whose `(src_blake2b, preset_fingerprint)` is `published` and whose output still matches size and hash. Delete stale `*.partial` files that no manifest line owns.
8. **Originals** (opt-in only, after `published`): move to trash (freedesktop spec) or `_quarantine/`, and record `original_trashed`.

## 4. Verification log

| # | Claim | Result | How |
|---|---|---|---|
| a | ffmpeg removes `creation_time` unless `-map_metadata` is explicit | **True** for 7.1 and 8.0: deletion only in the default-copy branch; global `-map_metadata` sets `metadata_global_manual` | read `copy_meta()`/`copy_metadata()` [1]; docs [2] silent |
| b1 | MP4 muxer location output | `loci` in `moov/udta` (MP4); `©xyz` only in MOV without `use_metadata_tags`; `mdta` keys only inside `udta/meta`; no `moov/meta` for MP4/MOV | `movenc.c` 8.0 [3] |
| b2 | Apple reads `moov/meta` Keys; ffmpeg's go to `udta/meta` | Consistent: trac shows iPhone input GPS under `MOV-Movie-Meta-Keys`, ffmpeg output under `MOV-Movie-UserData-Meta-Keys`, "Apple's apps do not display" | trac #4209 [11]; Apple doc page did not render (JS) |
| b3 | ExifTool can write each | Keys GPS yes; ItemList `©xyz` yes; UserData `©xyz` yes but avoided (name the group); `loci` raw/avoided | ExifTool QuickTime tag table + legend [6][7] |
| c | MKV date/location tags and readers | Only `DateUTC` (muxing date per RFC) + free-form tags; `RECORDING_LOCATION` is text; ExifTool reads, cannot write | `matroskaenc.c` [4], RFC 9559 [10], tagging spec [9], ExifTool Matroska [8] |
| d | default `fps_mode` drops colliding frames | `auto`→`vfr` for mp4 and matroska; enc tb = 1/framerate; drop when `delta <= -0.6`; the drop happens before the muxer, so the 1 ms grid is not the cause | `ffmpeg_mux_init.c`, `ffmpeg_filter.c` 7.1/8.0 [1][5], docs [2] |
| e | Ubuntu 26.04 / Debian lack libvmaf | True: no `--enable-libvmaf` in Debian rules or Ubuntu 8.0.1-3ubuntu2 packaging; no vmaf dep in libavfilter pages | [17][18][19] |
| f | Fedora F44 ffmpeg-free version | 8.1.3-1.fc44 (B right) | [21] |
| g | x265 4.3 exists | Arch 4.3-1 | [20] |
| h | libx265 wrapper flags CRA as keyframe | True (`is_keyframe()` incl. CRA, BLA) | `libx265.c` 8.0 [15] |
| i | Firefox HEVC-in-MKV seek freeze (B) | True, fixed in 158; VideoToolbox IDR-only note | bug 2006226 [14] |
| - | Apple Photos GPS reading rule | [unverified] forum only; irrelevant for current targets | [12] |
| - | libaom default `kf_max_dist` | not rechecked here (T3 merge cites 9999) | - |

## 5. Benchmark candidates

- **Frame-drop reproduction**: the same VFR 59,94 phone clip × {MP4, MKV} × {`auto`, `passthrough` + `enc_time_base demux`}. Record input/output packet counts, the max PTS gap and the "drop" counter on ffmpeg's last stats line. Expect drops only with `auto`.
- **Metadata round-trip matrix**: Android (Samsung, Pixel) and iPhone source clips × the pipeline. Check `creation_time`, Keys/`©xyz`/`loci` GPS, `Keys:CreationDate`, mtime and `moov` position after ExifTool. Spot-check that GPS shows in Haruna (mpv `metadata`), the iPhone Files info panel and an Android file manager.
- **GOP / seek**: x265 `open-gop` 1 vs 0 × `-g` {2 s, 5 s}. Record size delta at matched VMAF, max keyframe gap, mpv seek latency (`--hr-seek=yes`, scripted seeks) and a manual scrub test on the iPhone and an Android phone.
- **Decimation presets** (webinars): `fps=24`/`25` vs `mpdecimate` as filters with `passthrough`. Check that packet counts match the expected count.
- **Verify cost**: wall time of a full `-f null` decode vs encode time per category, to confirm the "fast" check stays cheap.
- **ExifTool step on files over 4 GB** (4K tours): confirm the in-place write works and keeps faststart.

## 6. Open questions for the owner

1. **Output placement**: a mirrored output tree next to the archive, or the converted file next to the original (`VID.mp4` → name collision when the original is also MP4)? Also, should the trash on the NAS be Synology's `#recycle` share bin or a tool `_quarantine/`?
2. **Android local-time date**: Android files carry a UTC `creation_time` and usually no offset. Should the tool derive an offset (from the file name's local time or Samsung `utc_offset`) and write `Keys:CreationDate`? This only matters for Apple Photos imports.
3. **Sources without `creation_time`** (screen recordings): leave the container date empty and keep only mtime, or write `creation_time` from mtime?

## 7. Sources

1. [FFmpeg `fftools/ffmpeg_mux_init.c` release/7.1](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/7.1/fftools/ffmpeg_mux_init.c) and [release/8.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/8.0/fftools/ffmpeg_mux_init.c) - `copy_meta()`, fps_mode auto. Primary.
2. [ffmpeg documentation](https://ffmpeg.org/ffmpeg.html) - `-map_metadata`, `-fps_mode`, `-enc_time_base`, `-autorotate`. Primary.
3. [FFmpeg `libavformat/movenc.c` release/8.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/8.0/libavformat/movenc.c) - udta/loci/©xyz/mdta, mvhd time, muxer flags. Primary.
4. [FFmpeg `libavformat/matroskaenc.c` release/8.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/8.0/libavformat/matroskaenc.c) - TimestampScale, DateUTC, tag skip list. Primary.
5. [FFmpeg `fftools/ffmpeg_filter.c` release/8.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/8.0/fftools/ffmpeg_filter.c) (and release/7.1) - `choose_out_timebase()`, `video_sync_process()`. Primary.
6. [ExifTool QuickTime tags](https://exiftool.org/TagNames/QuickTime.html) - writability, write-location order, Google Photos note. Primary.
7. [ExifTool tag-name legend](https://exiftool.org/TagNames/index.html) - meaning of `/` (avoided). Primary.
8. [ExifTool Matroska tags](https://exiftool.org/TagNames/Matroska.html) - all tags read-only; DateUTC → DateTimeOriginal. Primary.
9. [Matroska tagging specification](https://www.matroska.org/technical/tagging.html) - DATE_RECORDED, RECORDING_LOCATION. Primary.
10. [RFC 9559 Matroska](https://www.rfc-editor.org/rfc/rfc9559.txt) - DateUTC definition. Primary.
11. [FFmpeg trac #4209 comment (2024-04)](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-April/069027.html) - use_metadata_tags lands in UserData-Meta-Keys. Primary (tracker).
12. [ExifTool forum: Photos ignores GPS on mp4](https://exiftool.org/forum/index.php?msg=82839), [GPS in mp4/mov](https://exiftool.org/forum/index.php?msg=41874). Secondary.
13. [Android MediaMuxer](https://developer.android.com/reference/android/media/MediaMuxer) - `setLocation()`. Primary.
14. [Mozilla bug 2006226](https://bugzilla.mozilla.org/show_bug.cgi?id=2006226) - HEVC MKV seek freeze, CRA handling. Primary.
15. [FFmpeg `libavcodec/libx265.c` release/8.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/8.0/libavcodec/libx265.c) - `is_keyframe()`. Primary.
16. [x265 CLI documentation](https://x265.readthedocs.io/en/master/cli.html) - keyint, open-gop. Primary.
17. Ubuntu 26.04: [ffmpeg](https://packages.ubuntu.com/resolute/ffmpeg), [libavfilter11](https://packages.ubuntu.com/resolute/libavfilter11), [source debian.tar.xz](http://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/ffmpeg_8.0.1-3ubuntu2.debian.tar.xz). Primary.
18. [Debian ffmpeg `debian/rules`](https://salsa.debian.org/multimedia-team/ffmpeg/-/raw/debian/master/debian/rules). Primary.
19. Debian: [trixie libavfilter10](https://packages.debian.org/trixie/libavfilter10), [forky libavfilter11](https://packages.debian.org/forky/libavfilter11), [trixie ffmpeg](https://packages.debian.org/trixie/ffmpeg). Primary.
20. Arch: [ffmpeg](https://archlinux.org/packages/extra/x86_64/ffmpeg/), [x265](https://archlinux.org/packages/extra/x86_64/x265/). Primary.
21. [Fedora ffmpeg-free](https://packages.fedoraproject.org/pkgs/ffmpeg/ffmpeg-free/). Primary.
22. [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds). Primary.
23. [wader/static-ffmpeg](https://github.com/wader/static-ffmpeg). Primary.
24. [John Van Sickle static builds](https://johnvansickle.com/ffmpeg/). Primary.
25. [FFmpeg Changelog release/7.1](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/7.1/Changelog) - YUVJ obsoleted, scale ref input, scale2ref deprecated. Primary.
26. [ffmpeg formats documentation](https://ffmpeg.org/ffmpeg-formats.html) - max_interleave_delta, cues_to_front, movflags, use_editlist. Primary.
27. [ffmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) - libvmaf, xpsnr. Primary.
28. [Python `os`](https://docs.python.org/3/library/os.html) - `os.replace`, `os.fsync`, `os.utime(ns=)`. Primary.
29. [Python `hashlib`](https://docs.python.org/3/library/hashlib.html) - `file_digest`, blake2b. Primary.
30. [Freedesktop Trash spec](https://specifications.freedesktop.org/trash/latest/). Primary.
31. [ffprobe documentation](https://ffmpeg.org/ffprobe.html). Primary.
32. [Opus in ISOBMFF](https://opus-codec.org/docs/opus_in_isobmff.html) - pre-skip via edit list. Primary.
33. [FFmpeg trac #11649](https://trac.ffmpeg.org/ticket/11649) - `-noautorotate` display matrix in 7.1. Primary.
34. [FFmpeg-cvslog: autorotate (2015)](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2015-May/089218.html). Primary.
35. [FFmpeg `libavcodec/libaomenc.c` release/9.0](https://raw.githubusercontent.com/FFmpeg/FFmpeg/release/9.0/libavcodec/libaomenc.c) - `kf_max_dist` untouched without `-g`. Primary.
36. [SVT-AV1 Parameters.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Parameters.md) - keyint default. Primary.
37. [Doom9: Matroska rotation playback](https://forum.doom9.org/archive/index.php/t-176503.html). Secondary, possibly stale.
38. [mpv issue #1823](https://github.com/mpv-player/mpv/issues/1823) - exact seeks decode from previous keyframe. Secondary.
39. [FFmpeg-devel: matroskaenc rotation (2023)](https://ffmpeg.org/pipermail/ffmpeg-devel/2023-August/313041.html). Primary.
40. [ExifTool home](https://exiftool.org/) - MP4/MOV R/W, MKV read-only. Primary.
41. [FFmpeg download page](https://ffmpeg.org/download.html) - release versions. Primary.
42. [FFmpeg-cvslog: libvmaf option changes (2023-10)](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2023-October/139233.html). Primary.
43. [BagIt, RFC 8493](https://www.rfc-editor.org/rfc/rfc8493). Primary.
44. [Immich `metadata.service.ts`](https://raw.githubusercontent.com/immich-app/immich/main/server/src/services/metadata.service.ts) - date tag order, mtime fallback. Primary.
45. [Nextcloud Memories `lib/Exif.php`](https://raw.githubusercontent.com/pulsejet/memories/master/lib/Exif.php) - video date order, mtime fallback. Primary.
46. [Synology Photos: incorrect dates](https://kb.synology.com/en-us/DSM/tutorial/What_can_I_do_if_Synology_Photos_shows_incorrect_dates_of_my_photos) - video date tags, mtime fallback. Primary (dated).
