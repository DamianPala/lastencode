I’ll research the five requested angles separately, prioritizing current primary documentation and reproducer reports, then cross-check gallery behavior and ffmpeg/container claims before turning them into benchmark and design implications.

The metadata evidence is already showing a key interoperability split: container tags that ffprobe can see do not guarantee that a gallery app indexes them. I’m checking each app’s documented date/location fields separately and will distinguish documented behavior from app-specific behavior that needs a device test.

### TL;DR

FFmpeg copies some metadata by default, but that does not guarantee that a date, GPS coordinate, or rotation flag survives a re-encode in a form every gallery app will use. Preserve and verify those fields explicitly, and treat each app’s import behavior as a compatibility test. [1] [8] [10] [18] [19]

For builds and playback, probe capabilities rather than trusting the FFmpeg version string: distro packages vary, Matroska timestamp behavior alone does not explain whole-frame loss, and the reported remux corruption has no confirmed cause in the sources reviewed. [2] [13] [22] [26]

### Key Findings

#### 1. Metadata preservation across FFmpeg, MP4, and MKV

**What:** FFmpeg’s documented default is to copy global metadata from the first input and carry stream metadata with mapped streams. So `creation_time` is not generally dropped by design. It can still be lost when the date is stored under a different key or at a different metadata level, when explicit metadata mapping replaces the default, or when the output container cannot represent the source field in the same way. `-map_metadata 0` maps global metadata; after encoding, inspect the output rather than assuming the mapping worked. [1]

QuickTime has specific location metadata, including `com.apple.quicktime.location.ISO6709`. Android’s public `MediaMetadataRetriever` API recognizes ISO 6709 location in MP4/3GP under `@xyz`; it does not define a portable `com.android.*` video-tag namespace. Treat such tags as device- or app-specific unless testing confirms otherwise. [8] [10]

FFmpeg enables autorotation by default, so a re-encode ordinarily bakes the display rotation into the pixels. Keeping the original orientation metadata instead requires disabling autorotation and relying on the output muxer and player to preserve and honor the display matrix. For cross-app viewing, upright pixels are the safer default; preserving the matrix is useful when keeping the original raster matters, but it needs broader playback testing. [1]

File modification time is filesystem metadata, separate from video-container tags. ExifTool documents that metadata writes can affect file dates; a tool can restore mtime afterward, and Python provides `os.utime` for setting it. [11] [35]

MP4 and MKV store metadata differently. QuickTime/MP4 supports Apple and extensible metadata keys, while Matroska defines tags such as `DATE_RECORDED` and `RECORDING_LOCATION`; the latter is a place description, not a universally interoperable GPS coordinate field. ExifTool documents writable QuickTime tags for MOV/MP4; its Matroska support is not a general-purpose MKV tag-editing workflow. Use FFmpeg or MKVToolNix for MKV metadata changes, and verify the result with `ffprobe`. [9] [11] [12] [13] [37]

**Synthesis:** For MP4 archives, explicitly set the intended capture date, preserve the Apple creation-date key and ISO6709 location where needed, and set mtime after all metadata edits. Use ExifTool as a post-pass only for fields whose output it can write and whose representation you have verified. For MKV, preserve what the container can express, but do not assume gallery apps will interpret it like QuickTime metadata. [1] [8] [9] [11] [12]

**Evidence:** FFmpeg metadata mapping and rotation docs; Apple QuickTime metadata docs; Android API docs; ExifTool QuickTime and Matroska references; Matroska tag specification. [1] [8] [9] [10] [11] [12] [13]

**Confidence:** Medium. The container and API rules are documented, but field survival still depends on the input’s tag layout, FFmpeg build, output muxer, and target app.

#### 2. How gallery apps choose dates and locations

**What:** Google Photos allows users to change a photo or video’s date and location, but its public help does not specify a complete import-time priority order for container atoms. It also allows locations to come from camera data, manual edits, or estimates, so a location shown in Photos does not prove that a particular input atom was imported. [15] [16]

Apple’s public PhotoKit model exposes an asset’s creation date and location, but Apple does not document which exact QuickTime atom its importer prioritizes. Apple’s QuickTime format does document the creation-date and ISO6709 location metadata keys, making those reasonable fields to test for Apple Photos compatibility. [8] [9] [17]

Immich is more inspectable: its current server code uses ExifTool and ffprobe metadata, and defines a list of date tags it checks for videos. That list includes QuickTime creation-date fields. Immich also supports XMP sidecars, which can carry dates and GPS coordinates. [18]

Synology’s published guidance identifies `Xmp.xmp.com.apple.quicktime.creationdate` and `Xmp.video.DateUTC` for video dates, and says it may fall back to upload or modification time when metadata is inadequate. Its help also says timeline ordering uses creation date. The detailed priority guidance is old, so test it against the current Synology Photos release. [19] [20]

Nextcloud Memories documents EXIF-based indexing and a server-time fallback when a photo lacks an EXIF date. Its public documentation does not establish a specific video-tag priority order. [21]

**Synthesis:** A practical cross-app candidate is to write a UTC container `creation_time`, an Apple QuickTime creation-date key with its timezone, and a QuickTime ISO6709 location, then set filesystem mtime to the intended date as a fallback. No single combination is documented to guarantee the same result in every gallery app; verify imports directly. [8] [9] [15] [17] [18] [19] [21]

**Evidence:** Google Photos help pages; Apple PhotoKit and QuickTime docs; current Immich source; Synology guidance; Memories docs. [8] [9] [15] [16] [17] [18] [19] [20] [21]

**Confidence:** Medium. Immich and Synology disclose useful behavior, but exact importer precedence remains undocumented for several apps, and the Synology priority guidance is dated.

#### 3. FFmpeg builds, versions, and feature detection

**What:** As of 2026-10-20, FFmpeg’s latest stable release is 9.0.2, released 2026-09-18. Distro packages can lag: the cited package pages list Arch FFmpeg 9.0.2, Debian Trixie FFmpeg 7.1.5, Ubuntu 26.04 FFmpeg 8.0.1, and Fedora 44’s `ffmpeg-free` 8.1.3. The Arch package lists dependencies for Opus, SVT-AV1, VMAF, and x265; its related package pages list SVT-AV1 4.2.0, x265 4.3, and VMAF 3.2.1. [4] [22] [23] [24] [25] [26] [27] [28]

Feature availability still depends on how a particular binary was built. Check `-buildconf`, available encoders and filters, and encoder-specific help for `libx265`, `libsvtav1`, and `libopus`; check for `libvmaf` and `xpsnr` before relying on them. FFmpeg’s filter docs describe current `libvmaf` options and `xpsnr`. [1] [3]

For compatibility with FFmpeg 7.x and 8.x, replace the deprecated `scale2ref` filter with the `scale=rw:rh` expressions shown in current docs. Older `libvmaf` examples using `model_path` are stale: that option was replaced by `model='path=…'`, and the old feature-toggle options were removed. FFmpeg 8.1’s changelog also lists EXIF metadata parsing. [3] [5] [6]

BtbN publishes third-party builds with different licensing and codec configurations. John Van Sickle’s site lists a 7.0.2 build from June 2024, which is old for a new 2026 workflow. Before redistributing any FFmpeg binary, record its build configuration and check the licensing for the enabled components. [29] [30] [31]

**Synthesis:** Make runtime feature checks the contract: require the encoders, muxers, and filters a selected profile needs, and record the FFmpeg version and build configuration in the manifest. A minimum version can still be useful, but the version string alone will not establish that a distro or static build has the required libraries. [1] [3] [22] [29]

**Evidence:** FFmpeg release and filter docs; official distro package pages; build projects’ documentation. [1] [3] [4] [22] [23] [24] [25] [26] [27] [28] [29] [30] [31]

**Confidence:** High for the dated package-version snapshot and documented FFmpeg option changes; medium for feature availability across all packages because build variants differ.

#### 4. Timestamps, seeking, and playback pitfalls

**What:** Matroska’s default `TimestampScale` is one millisecond, but the specification permits other scales. A one-millisecond grid can introduce timestamp rounding; at 59.94 fps, that rounding is far short of a whole frame per frame, so it does not by itself explain a loss of four frames. The reported frame loss needs a reproducible input/output comparison. [13]

FFmpeg’s `-fps_mode passthrough` preserves input frame timestamps as far as the output muxer permits. CFR modes can duplicate or drop frames, so converting phone VFR footage to CFR should be an explicit choice. `-fflags +genpts` generates missing PTS when DTS is present; it is not a general timestamp-repair switch. [1] [2]

`-max_interleave_delta 0` can make FFmpeg buffer packets until each stream has supplied a packet, even when timestamps are far apart. Matroska normally writes Cues at the end; `cues_to_front` moves them forward, while MP4 `+faststart` moves the `moov` atom forward in a second pass. These options affect indexing and buffering; the docs do not establish them as generic fixes for corruption or timestamp errors. [2]

One relevant seeking issue was in Firefox’s Matroska handling of HEVC: the bug report attributes freezes on seek to the demuxer’s treatment of x265 CRA/open-GOP frames as keyframes. The bug was fixed for Firefox 158, while the report notes a separate macOS VideoToolbox limitation around starting from non-IDR frames. x265 documents open GOP as enabled by default. This is a player interoperability issue, not evidence that the encoded file is corrupt. [32] [33]

The Opus-in-ISO-BMFF specification defines pre-roll behavior for random access. That makes MP4 Opus a reasonable target for explicit device seeking tests; it does not establish that FFmpeg output is malformed. [34]

**Synthesis:** Keep VFR unless the profile intentionally changes frame cadence. Do not add `+genpts`, zero interleave delta, or front-loaded Cues as general “stability” flags. Test open-GOP versus closed-GOP output if random seeking matters, and test MP4/Opus on the actual phone players. The exact corruption reportedly seen after the combined remux flags remains unexplained by the documentation and bug reports reviewed here. [1] [2] [13] [32] [33] [34]

**Evidence:** FFmpeg timestamp and muxer docs; Matroska specification; Mozilla bug report; x265 and Opus docs. [1] [2] [13] [32] [33] [34]

**Confidence:** High for the documented option behavior and the Firefox bug; low for diagnosing the reported MKV corruption without a reproducer.

#### 5. Safe handling of originals and resumable runs

**What:** Python documents `os.replace` as an atomic replacement when it succeeds; the source and destination must be on the same filesystem for the atomic rename guarantee. [35]

**Synthesis:** Encode to a temporary path on the destination filesystem, finalize metadata there, validate it, and only then atomically rename it into place. A fast per-file check can use `ffprobe` JSON to verify streams, duration, tags, and orientation. If the user elects to delete the original, require a stronger decode check and a recorded output hash before moving it to trash. [35] [37]

Keep a manifest keyed by input hash and transform settings. Record the input and output hashes, profile, actual arguments, FFmpeg version/build configuration, metadata snapshot, source mtime, and verification results. Resume only when the input hash and transform fingerprint match and the existing output still passes validation. BagIt is an established reference for checksum manifests, though the project need not adopt its full directory format. [1] [35] [36] [37]

**Evidence:** Python filesystem docs, FFmpeg/ffprobe docs, BagIt specification. [1] [35] [36] [37]

**Confidence:** High for the filesystem guarantees; medium for the recommended workflow, which is a synthesis for this project.

### Perspectives

MP4 offers a strong starting point for phone and native-player compatibility, along with QuickTime metadata conventions that Apple software understands. MKV offers flexible tagging and indexing, but gallery-app interpretation is less predictable and the user’s own iOS test found MKV did not open in the native player. Those tradeoffs support using MP4 for mobile-facing archives and retaining MKV only where its features are useful and tested. [8] [9] [12] [19]

Baking rotation into pixels reduces dependence on player behavior. Keeping the display matrix preserves the original raster orientation and avoids a pixel rotation, but depends on each reader honoring it. The right choice is a profile-level policy, followed by checks that the encoded pixels and output display matrix agree. [1]

Open GOPs can improve compression behavior, while closed GOPs can make random access more reliable in some players. The Firefox report demonstrates a real demuxer issue, but does not establish that all target players need closed GOPs. Test both settings against the intended devices before choosing a default. [32] [33]

### Practical Implications

For the benchmark matrix, include:

- MP4 with HEVC tagged for Apple playback, and MKV as a separate compatibility case. Record whether each target app imports the date and location, honors orientation, and seeks cleanly. [8] [9] [12] [19]
- Metadata cases with `creation_time`, Apple QuickTime creation date, ISO6709 GPS, preserved source mtime, and missing metadata. Include a VFR source and a rotated phone clip. [1] [8] [10] [13] [35]
- VFR passthrough versus deliberate CFR, and x265 open GOP versus closed GOP. Measure decoded frame count, timestamps, audio sync, and random-seek behavior. [1] [32] [33]
- Runtime probes for `libx265`, `libsvtav1`, `libopus`, `libvmaf`, and `xpsnr`, with the detected build configuration recorded alongside each result. [1] [3]

For the application, make the fast check structural and metadata-aware on every file. Require a full decode check before optional original deletion, then store output hashes and verification status in the manifest. [35] [36] [37]

### Sources

1. [FFmpeg command-line documentation](https://ffmpeg.org/ffmpeg.html) — Primary: metadata mapping, rotation, build configuration, and frame-rate modes.
2. [FFmpeg format and muxer documentation](https://ffmpeg.org/ffmpeg-formats.html) — Primary: timestamp flags, interleaving, Matroska Cues, and MP4 `faststart`.
3. [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html) — Primary: `libvmaf`, `xpsnr`, and current scaling expressions.
4. [FFmpeg downloads and releases](https://ffmpeg.org/download.html) — Primary: latest stable release and upstream distribution guidance.
5. [FFmpeg development log: `scale2ref` deprecation](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2024-May/142854.html) — Primary: change history.
6. [FFmpeg development log: `libvmaf` option changes](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2023-October/139233.html) — Primary: option migration and removals.
7. [FFmpeg changelog](https://github.com/FFmpeg/FFmpeg/blob/master/Changelog) — Primary: release-level feature changes, including EXIF parsing.
8. [Apple QuickTime location metadata](https://developer.apple.com/documentation/quicktime-file-format/location_metadata) — Primary: ISO6709 location key.
9. [Apple QuickTime metadata atoms and types](https://developer.apple.com/documentation/quicktime-file-format/metadata_atoms_and_types) — Primary: QuickTime metadata key formats.
10. [Android `MediaMetadataRetriever`](https://developer.android.com/reference/android/media/MediaMetadataRetriever) — Primary: Android’s exposed location, date, and rotation metadata.
11. [ExifTool QuickTime tags](https://exiftool.org/TagNames/QuickTime.html) — Primary tool documentation: readable and writable QuickTime metadata.
12. [Matroska tagging specification](https://www.matroska.org/technical/tagging.html) — Primary: standardized Matroska tags.
13. [RFC 9559: Matroska media container](https://datatracker.ietf.org/doc/rfc9559/) — Primary standard: timestamp scale and container timing.
14. [ExifTool Matroska tags](https://exiftool.org/TagNames/Matroska.html) — Primary tool documentation: Matroska tag support.
15. [Google Photos: change date and time](https://support.google.com/photos/answer/6128850/?co=GENIE.Platform%3DAndroid&hl=en) — Primary: user-visible date editing behavior.
16. [Google Photos: add or change a location](https://support.google.com/photos/answer/6153599?hl=en-en) — Primary: location sources and editing.
17. [Apple PhotoKit `PHAsset.creationDate`](https://developer.apple.com/documentation/photos/phasset/creationdate) — Primary: asset creation date and location model.
18. [Immich metadata service](https://github.com/immich-app/immich/blob/main/server/src/services/metadata.service.ts) — Primary project source: current video metadata extraction and date selection.
19. [Synology Photos: incorrect dates](https://kb.synology.com/en-us/DSM/tutorial/What_can_I_do_if_Synology_Photos_shows_incorrect_dates_of_my_photos) — Primary: documented video date tags and fallback behavior.
20. [Synology Photos help](https://kb.synology.com/en-nz/DSM/help/SynologyPhotos/managing_photos?version=7) — Primary: timeline sorting and modification-time fallback.
21. [Nextcloud Memories configuration](https://github.com/pulsejet/memories/blob/master/docs/config.md) — Primary project docs: metadata indexing and fallback behavior.
22. [Arch Linux FFmpeg package](https://archlinux.org/packages/extra/x86_64/ffmpeg/) — Primary distro package page: current version and dependencies.
23. [Arch Linux SVT-AV1 package](https://archlinux.org/packages/extra/x86_64/svt-av1/) — Primary distro package page: encoder version.
24. [Arch Linux x265 package](https://security.archlinux.org/package/x265) — Primary distro package page: x265 version.
25. [Arch Linux VMAF package](https://archlinux.org/packages/extra/x86_64/vmaf/) — Primary distro package page: VMAF version.
26. [Debian Trixie FFmpeg package](https://packages.debian.org/trixie/ffmpeg) — Primary distro package page: Debian stable version.
27. [Ubuntu FFmpeg package](https://packages.ubuntu.com/resolute/ffmpeg) — Primary distro package page: Ubuntu 26.04 version.
28. [Fedora 44 `ffmpeg-free`](https://packages.fedoraproject.org/pkgs/ffmpeg/ffmpeg-free/fedora-44-updates.html) — Primary distro package page: Fedora build version.
29. [BtbN FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds) — Primary project documentation: third-party build variants.
30. [John Van Sickle static builds](https://johnvansickle.com/ffmpeg/) — Primary build page: available static build and release date.
31. [FFmpeg legal information](https://ffmpeg.org/legal.html) — Primary: build and redistribution licensing guidance.
32. [Mozilla bug 2006226](https://bugzilla.mozilla.org/show_bug.cgi?id=2006226) — Primary issue tracker: HEVC Matroska seeking and CRA-frame handling.
33. [x265 CLI documentation](https://x265.readthedocs.io/en/master/cli.html) — Primary: GOP and encoder options.
34. [Opus in ISO Base Media File Format](https://opus-codec.org/docs/opus_in_isobmff.html) — Primary specification: Opus initialization and preroll.
35. [Python `os` documentation](https://docs.python.org/3/library/os.html#os.replace) — Primary: atomic replacement and filesystem timestamp APIs.
36. [BagIt File Packaging Format, RFC 8493](https://www.rfc-editor.org/rfc/rfc8493) — Primary standard: checksum manifests for packaged files.
37. [FFprobe documentation](https://ffmpeg.org/ffprobe.html) — Primary: structured media inspection.

### Gaps

The exact import priority for Apple Photos and Google Photos is not publicly specified, and the Synology date-priority page is old. Android’s public API does not settle how individual camera vendors use private tags. Resolve these with direct imports on the target phones and current gallery releases. [10] [15] [16] [17] [19] [20]

The reported four-frame loss and intermittent remux corruption need a reproducible sample. Measure input/output frame timestamps and decoded frame count, then isolate `fps_mode`, `genpts`, interleave settings, and Cues placement one at a time. [1] [2] [13]
