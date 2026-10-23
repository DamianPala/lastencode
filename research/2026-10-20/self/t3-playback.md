# T3: Playback compatibility on ~2-year-old phones, gallery apps and desktop players (state 2026-10)

Researcher: Claude (self-run, WebSearch/WebFetch plus reading FFmpeg/libaom/SVT-AV1/x265/Immich source). Date: 2026-10-20.
Note on method: the shared web-search budget ran out while covering the coordinator's addendum (desktop/mpv/VVC). Those items rely on direct fetches of primary pages (mpv manual, Haruna docs, ffmpeg.org, Wikipedia hardware tables) and on encoder source code instead of extra searches.

## TL;DR

HEVC 8-bit Main in a real MP4 with `hvc1` is the only video format that plays natively everywhere in scope: every 2024-25 phone, Apple Photos, Google Photos, Immich and libmpv. AV1 fails on two common groups. The first is iPhones older than the 15 Pro (no hardware decoder, and iOS has no system software fallback) [1][2][3]. The second is most 2024-25 mid-range Android phones (Galaxy A55/A35/A56, Snapdragon 7-series below 7 Gen 4, Dimensity 7xxx), which fall back to dav1d in software [7][8][9][10][11][13].
For audio, use AAC-LC as the default. Opus in MP4 works on iOS 17+ and Android, but Apple does not document it and FFmpeg has open Opus-in-MP4 edit-list bugs [19][40].
For archive files that must scrub smoothly in Haruna/mpv, cap the keyframe interval at about 2-5 s. libaom's default (9999 frames, about 2,8 min at 60 fps) explains the slow seeks the user saw, because Haruna seeks in "exact" mode [24][46][47].

## Key Findings

### Q1. AV1 hardware decode on 2024 / early-2025 phones; software fallback

- **What**: Apple: the iPhone 16 tech specs list AV1 playback; the iPhone 15 specs list only HEVC, H.264 and ProRes [1][2]. AV1 hardware decode starts with the A17 Pro (iPhone 15 Pro/Pro Max) and covers the whole iPhone 16 family (A18/A18 Pro) and later [3][4][6]. Based on [3], "as of 2026, Apple has not introduced a system-wide AV1 software decoder", so an iPhone 15/14/13 cannot play AV1 in Photos or the native player at all. Safari 17 enabled AV1 only "on devices with hardware decoding support" [5].
- **What**: Android chips (fact):
  - Pixel 6 and later (Tensor G1-G4) decode AV1 in hardware [6].
  - Snapdragon 8 Gen 2 (2023) and 8/8s Gen 3 decode AV1. On the mid-range side only Snapdragon 7 Gen 4 (2025) does [6]. The Snapdragon 7 Gen 3 product brief lists H.264/H.265/VP9 decode with no AV1 [7], and the 7+ Gen 3 lacks AV1 decode [8].
  - Samsung's flagship Exynos 2x00 line (Galaxy S21 and later, S24 Exynos 2400) has AV1 [6]. The mid-range parts do not: the Exynos 1480 (Galaxy A55) lacks AV1 decode [9], the Exynos 1580 (Galaxy A56) has no AV1 decoder [10], and the Exynos 1380 (A35/A54) lists only HEVC/H.264/VP9 [10].
  - MediaTek: the Dimensity 8300 and the 1000/8000/9000 families have AV1 decode [6][12]; the Dimensity 7300 lists only H.264/HEVC/VP9 [11].
- **What**: Software fallback on Android (fact):
  - The Android 15 CDD requires every handheld to decode AV1 Main profile (8- and 10-bit) for third-party apps, so a software decoder always exists [13]. The hardware AV1 Main10 requirement in the CDD applies only to Media Performance Class devices [13].
  - AOSP added dav1d as `c2.android.av1-dav1d.decoder` in the swcodec Mainline module, and Google moved the default from libgav1 to dav1d via Play System Updates in 2024 [14][15].
  - Capacity: Meta (2023) found dav1d sustained 720p30 on "most" Android devices and 1080p30 only on some mid- and high-end models [16]. A 2022 SPIE study reached the same split: 720p30 on low-end, 1080p30 on mid/high-end with 4 threads [59, single-source, abstract only].
  - Battery: Meta reports an $80 phone playing software AV1 for 16-17 h [17], and a Reddit test cited by Ozer got 11 h 15 min of 720p AV1 on a Galaxy A14 [18]. Neither covers 1080p60 or 4K.
- **Synthesizing across sources**: a Galaxy A55/A35-class phone (still the volume seller of 2024) will play 1080p30 AV1 in software, probably play 1080p60 marginally, and most likely stutter on 4K. Nobody has published 1080p60 or 4K software-decode numbers for these chips, so this has to be measured.
- **Evidence**: [1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16][17][18]
- **Confidence**: high for the Apple split and the flagship/mid-range Android split; medium for individual mid-range chips (the Exynos 1480 rests on Android Authority's read of Samsung specs); low for 1080p60/4K software playback and battery cost.

### Q2. HEVC Main vs Main10, `hvc1` vs `hev1`, full vs limited range

- **What**: Main vs Main10.
  - The Android CDD requires HEVC Main profile decode up to UHD on handhelds (or VP9 instead) and does not mandate Main10 [13].
  - The Exynos 1380 spec lists "HEVC 10bit" decode [10]. Apple's HLS spec allows up to Main10 Level 5.1, and recommends at most Main10 L4.0 "for maximum compatibility" [20].
  - Immich transcodes 10-bit HEVC even when HEVC is an accepted codec, "because some clients can't play it" [28].
- **Synthesizing**: the sources are 8-bit, so 8-bit Main is the zero-risk choice. Main10 gains a little efficiency and less banding but triggers Immich transcodes. Main10 is still reasonable for the "recent devices" profile.
- **What**: `hvc1` vs `hev1`.
  - FFmpeg's MP4 muxer writes `hev1` by default. It has done so since 2014, because FFmpeg could not guarantee that parameter sets appear only in the sample entry [21]. The current `movenc.c` still lists `hev1` first for HEVC [23].
  - `hvc1` must be requested with `-tag:v hvc1`; this was added in 2017 "because QuickTime and other Apple software require hvc1" [22].
  - Apple's HLS spec says to use `hvc1` and marks `hev1` "use not recommended" [20].
  - The user confirmed that MP4 + HEVC `hvc1` + Opus plays in the iOS 18 native player (project history).
- **What**: Full range.
  - Both FFmpeg wrappers signal full range in the bitstream. `libx265` sets the VUI `video_full_range_flag` when `color_range=pc` or the input is `yuvj420p` [23], and `libsvtav1` sets `color_range` from `avctx->color_range` [23].
  - libaom has history: FFmpeg ticket #8455 reported that `yuvj420p` input was silently converted to limited range [44, single-source].
  - Voukoder users found that SVT-AV1's "full" flag only tagged the stream while the pixels were still limited. A filter-graph conversion caused this, and `scale=out_range=full` fixed it [45].
  - Player bugs on record are old: Firefox rendered full-range H.264 as limited in 2015 [43, stale], and QuickTime/Preview washed out full-range screen recordings in 2018 (per a forum thread found in search) [stale, not separately cited].
- **Synthesizing**: Android phones already record and play `yuvj420p` HEVC/H.264 in their own galleries, so full-range playback is routine on the target phones. The real risk is an accidental range conversion in the filter graph, which shows up as a contrast shift. The tool should either keep full range end to end and verify the output flag with ffprobe, or convert explicitly to limited range (`scale=in_range=pc:out_range=tv`), ideally into 10-bit so no levels are lost. I found no 2025-26 reports of full-range HEVC or AV1 playing wrong on iOS 17/18 or Android 14/15.
- **Evidence**: [10][13][20][21][22][23][28][43][44][45]
- **Confidence**: high for hvc1; medium for Main10 risk; low/medium for current full-range player behaviour (old sources only).

### Q3. Containers and audio

- **What**: MP4 vs MKV.
  - Google Photos accepts both .mp4 and .mkv [30]. The Android CDD lists Matroska for Opus/VP8 and decode-only for AAC/MP3 [13].
  - Synology Photos lists only MOV and MP4 for native playback; MKV and AV1 do not appear in the Photos or Image Assistant specs [32][33].
  - The user's own test showed that MKV does not open in the iOS native player (project history).
  - Immich's default accepted containers are `mov,ogg,webm` (MP4 counts as the mov family). Files in other containers are remuxed to MP4 for playback [27][Immich docs-commit mirror in search, not cited].
  - Desktop libmpv players (Haruna/mpv) and VLC play both containers. This is general knowledge and was not re-sourced.
- **What**: Opus in MP4.
  - An Apple Media Engineer wrote: "Opus audio is only supported beginning in iOS 17, and only in MP4 files … you should also supply AAC". Opus is not listed in Apple's Tech Specs or Authoring Guidelines [19].
  - WebKit announced Opus in MP4/WebM for Safari 17 on macOS (1-2 channels) [5]. A Jellyfin report puts iOS direct play at 17.4+, mono/stereo only [57, single-source].
  - Android decodes Opus in MP4 ("decode only") [13]. Chrome and Firefox support Opus, with MP4 among its containers [42].
  - Earlier failures: Safari/iMovie on Mac played Opus-in-MP4 without sound [41], and Opus-in-MP4 files failed to save to Photos on some iOS versions (not confirmed).
- **What**: FFmpeg Opus-in-MP4 bugs. FFmpeg writes `Opus` + `dOps` [23]. Trac #9177 says Opus-in-MP4 end trimming (edit list) is not applied correctly [40, single-source, ticket page blocked]. Trac #11031 says CMAF output without edit lists does not skip priming samples [search result, not opened].
- **What**: Apple Photos import of Opus-in-MP4 is undocumented. No source either way.
- **Evidence**: [5][13][19][27][30][32][33][40][41][42][57]
- **Confidence**: high that AAC-LC in MP4 is universally safe; medium that Opus in MP4 plays on iOS 17+/Android; low for Apple Photos and Synology handling of Opus.

### Q4. Gallery and sync behaviour (accept/transcode/reject; date and location)

- **Google Photos**:
  - Accepts .mp4/.mkv up to 10 GB and "10-bit HDR videos" [30].
  - In "Storage saver" mode, videos above 1080p are "resized to high-definition 1080p" and some information may be lost. "Original quality" keeps files unchanged [31].
  - No official statement on AV1 uploads exists. A 2021 report said "AV1 support is coming to Photos" (stale, found in search, not cited).
  - Date precedence for MP4 is not documented. Community reports say Google uses QuickTime CreateDate (UTC) and can shift by the timezone offset [exiftool forum threads seen in search, forum down when fetched].
- **Apple Photos**:
  - A Dec 2025 report says an SVT-AV1 MP4 played in Files and nPlayer on an iPhone 17 Pro (iOS 26) but could not be saved to Photos [36, single-source]. Treat AV1 as not importable into the iOS Photos library until tested.
  - USB/PC imports may be converted to H.264 unless "Keep Originals" is set [37].
  - Location: FFmpeg writes GPS where Apple's apps do not show it (inside `udta/meta/keys`), even with `-movflags use_metadata_tags -map_metadata 0` (trac #4209, reproduced, still open) [38]. Android-style `©xyz` was lost in trac #6193 [39].
- **Immich**:
  - Default `transcode: required`, `acceptedVideoCodecs: ["h264"]`, `targetVideoCodec: h264`, `targetResolution: 720`, `acceptedAudioCodecs: aac, mp3, opus` [27]. Under the defaults, every HEVC or AV1 upload gets an extra H.264 720p playback copy. The original is kept and the server CPU does the work.
  - 10-bit HEVC is transcoded even when HEVC is accepted [28].
  - Date precedence: SubSecDateTimeOriginal > SubSecCreateDate > DateTimeOriginal > CreationDate > CreateDate > MediaCreateDate > … > file mtime/birthtime [29]. GPS comes from ExifTool `GPSLatitude/GPSLongitude` [29].
- **Synology Photos (DSM 7.2.2+)**:
  - Server-side HEVC/H.264 transcoding was removed in Aug 2024 [34].
  - HEVC MP4/MOV added via SMB, File Station or web upload gets previews only through the desktop Synology Image Assistant. Files backed up by the Synology mobile app are unaffected [33][35].
  - AV1 and MKV are not listed as supported at all [32][33].
- **What (source-level fact)**: FFmpeg's MP4 muxer (MP4 mode) writes location as a 3GPP `loci` box, not `©xyz`. MOV mode writes `©xyz`, and `use_metadata_tags` writes mdta keys [23]. It writes `creation_time` into `mvhd` when the metadata key is present [23].
- **Synthesizing**: re-encoded files will often land in galleries with the right date (mvhd CreateDate survives if `creation_time` is mapped) but no location. A post-encode `exiftool -TagsFromFile src` step for QuickTime CreateDate/CreationDate and Keys/UserData GPSCoordinates is the dependable fix, verified per file. Without it, Immich falls back to mtime, so mtime must be restored too.
- **Evidence**: [23][27][28][29][30][31][32][33][34][35][36][37][38][39]
- **Confidence**: high for Immich and Synology behaviour; medium for Apple Photos/AV1 (single report); low for Google Photos AV1 handling and date precedence (undocumented).

### Q5. Synthesis: recommended combinations

- **"Plays on a 2-year-old phone without fuss" (default)**: HEVC 8-bit Main (libx265), real MP4 (`.mp4`), `-tag:v hvc1`, AAC-LC stereo (128-160 kbit/s at 48 kHz), `+faststart`, keyframe interval of 2-5 s. Metadata copied with exiftool afterwards.
  - Why: hvc1 is required for Apple [20][22]; HEVC Main is mandatory on Android [13]; AAC is the only audio Apple documents and HLS mandates [19][20]; Synology plays MP4 [32]; Immich accepts AAC [27].
  - Opus in MP4 is acceptable for iOS 17+/Android viewing (user-verified on iOS 18). Treat it as an option, not the default, because of the Apple Photos and Synology unknowns and the FFmpeg edit-list bugs [19][40].
- **"Smallest file, recent devices only"**: AV1 (SVT-AV1, 10-bit Main), MP4 (`av01`), Opus or AAC, keyframe interval ≤5 s.
  - Plays in hardware on iPhone 15 Pro/16+, Pixel 6+, Galaxy S21+/S24/S25, Snapdragon 8 Gen 2+, Dimensity 8000/9000 [3][6].
  - Excluded: iPhone 15 and older non-Pro models entirely [2][3], and the iOS Photos library per one report [36]. On mid-range Android it plays only in software [9][10][11][16].
  - Synology Photos and Google Photos support is undocumented [30][32].
- **Confidence**: medium-high for the default; medium for the AV1 profile's device list; low for AV1 gallery behaviour.

### Addendum A. Desktop: Haruna/libmpv seek performance, keyframe interval, AMD iGPU AV1 decode

- **What (fact)**: Haruna's seek setting uses mpv's "exact" seek mode [47]. mpv's own default `--hr-seek=default` uses precise seeks only for absolute seeks, not for arrow keys [46]. A precise seek "has to decode all video … from the start" of the GOP [58], i.e. from the previous keyframe. mpv defaults to `--hwdec=no` (software decode). Haruna's docs advise `auto-safe`/`auto` [46][47].
- **What (fact)**: Default maximum keyframe intervals:
  - libaom: `kf_max_dist` 9999 frames. The FFmpeg wrapper leaves it unchanged unless `-g` is given (`"g", "-1"`) [23][24].
  - SVT-AV1: about 5 s (`--keyint -2`) [25].
  - x265: 250 frames [26], i.e. ~4 s at 60 fps and ~8 s at 30 fps.
- **Synthesizing**: the slow arrow-right seeks with libaom are explained by exact seeking in software through up to 9999 frames between keyframes; scene-cut keyframes are rare in handheld footage. Each seek costs (frames since last keyframe) / (decode fps). With a 2 s GOP that is about 60-120 frames, which a 16-core CPU decodes in a fraction of a second. With a 2-min GOP it is thousands of frames. All three likely causes (sparse keyframes, exact seek, software decode) multiply, but the GOP length dominates.
- **Size cost**: I found no measured BD-rate for 2 s vs 5 s vs 10 s GOPs on AV1 or x265. One illustrative model (not a measurement) puts the saving from stretching beyond 2 s at about 3% [56]. Synthesizing: expect low single-digit percent between 2 s and 5 s on static content (webinars, talking heads). This is worth measuring per category in benchmark mode. SVT-AV1 `--fast-decode 1/2` additionally cuts decoder work [25]; Meta cites about 25% fewer cycles for about 3-5% quality loss [Meta/Ronca coverage in search, not cited].
- **AMD iGPU**: Raphael's iGPU (Ryzen 7000 desktop, incl. 7950X3D) uses VCN 3.1.2. Rembrandt is VCN 3.1.1 and Phoenix VCN 4.0, and AV1 decode arrived with VCN 3.0 [48]. Notebookcheck lists AV1/VP9/HEVC/H.264 8/10-bit decode for the Ryzen 7000 iGPU [52]. Mesa has had VA-API AV1 decode on AMD since 21.3 [51]. A Mesa 24 regression caused stalls in 2160p AV1 VA-API decode on Phoenix [50, single-source, may be fixed]. Intel has decoded AV1 since Tiger Lake (11th gen) and VVC since Lunar Lake [49].
- **Synthesizing**: most laptops from 2021 onwards (Intel 11th gen+, Ryzen 6000+) can decode AV1 in hardware via VA-API, but only if the player enables hwdec. Haruna/mpv default to software.
- **Confidence**: high on defaults (source code and manuals); medium on the AMD VCN mapping (Wikipedia + Notebookcheck); low on size cost (no measurement found).

### Addendum B. VVC in ffmpeg/libmpv (brief)

- **What**: FFmpeg 7.0 (2024-04-05) added a native VVC decoder as experimental; FFmpeg 7.1 (2024-09-30) declared it stable; 8.0 (2025-08-22) added IBC/ACT/palette support. The latest release is 8.1 (2026-03-16) [53]. Ubuntu 24.04 ships ffmpeg 6.1.1, which has no native VVC decoder [54]. A May 2025 ticket shows the native decoder failing mid-stream on a file that vvdec decodes [55].
- **Synthesizing**: a VVC file failing in Haruna on another laptop is expected if that laptop's libmpv links ffmpeg < 7.1 (e.g. Ubuntu 24.04 or an older Flatpak runtime). Container support for VVC in MKV is a second unverified risk. VVC is not viable for the playback targets in 2026.
- **Confidence**: high on FFmpeg versions; medium on the diagnosis.

## Perspectives

- **AV1 on mid-range Android: "fine" vs "battery and stutter risk".** Meta and Ozer argue that software AV1 is cheap enough, citing 16-17 h playback and 11 h on a Galaxy A14 [17][18]. YouTube's AV1 rollout drew complaints about battery life and performance on phones without hardware decode [18]. Both camps measured 720p streaming bitrates, not 1080p60/4K archive files at high bitrates, so neither settles this project's case.
- **Opus in MP4 on Apple.** It works in practice on iOS 17+ (the Apple engineer's answer and the user's own test) [19]. Apple still does not list it in specs and recommends AAC alongside it [19]. These views differ on risk tolerance, not on the facts.
- **Full range: keep vs convert.** Keeping full range preserves the source's levels and is what the phones themselves produce. Converting to limited range is the traditional safe default for players that ignore range flags [44][45]. Current evidence of player breakage is old.

## Practical Implications

1. Default preset: libx265 8-bit Main, `.mp4`, `-tag:v hvc1`, AAC-LC, `-movflags +faststart`, explicit `-g` (≈2-5 s × fps) and `-keyint_min`. Opus as an opt-in audio choice.
2. AV1 preset family: SVT-AV1 (never libaom without `-g`), explicit `-g`, consider `-svtav1-params fast-decode=1`, 10-bit. Label it "recent devices only" and warn about iPhone ≤15 non-Pro, the iOS Photos import uncertainty, Synology and mid-range Android.
3. Always set the keyframe interval explicitly. Expose "scrub-friendly" (2 s) vs "max compression" (5-10 s) settings and measure the size delta in benchmark mode.
4. After each encode, copy metadata with exiftool from the source:
   - `-TagsFromFile src "-QuickTime:CreateDate" "-QuickTime:CreationDate" "-Keys:GPSCoordinates" "-UserData:GPSCoordinates"`, or equivalent; validate the exact tag names in testing.
   - Restore mtime.
   - Verify with ffprobe/exiftool as part of the fast per-file check.
5. Fast check additions: assert codec tag `hvc1` (or `av01`), container MP4 brand, `color_range` matching intent, pix_fmt bit depth, keyframe spacing (ffprobe `-skip_frame nokey` sample), audio codec, presence of creation date and GPS.
6. Document per-gallery behaviour in the README:
   - Immich makes an H.264 720p copy unless the admin accepts HEVC/AV1 and disables transcoding for 8-bit.
   - Synology needs Image Assistant for HEVC files arriving over SMB.
   - Google Photos "Storage saver" re-encodes anything above 1080p.

Benchmark-matrix candidates:

| Axis | Values |
|---|---|
| Codec/profile | x265 Main 8-bit; x265 Main10; SVT-AV1 10-bit (preset 2-6) |
| Keyframe interval | 2 s, 5 s, 10 s (size delta plus mpv exact-seek latency) |
| SVT-AV1 fast-decode | 0, 1, 2 |
| Audio | AAC-LC 128k; Opus 64-96k |
| Range | full kept; limited (8-bit); limited (10-bit) |

## Sources

1. [iPhone 16 - Tech Specs](https://support.apple.com/en-us/121029) - primary; lists HEVC, H.264, AV1 playback.
2. [iPhone 15 - Tech Specs](https://support.apple.com/en-us/111831) - primary; HEVC, H.264, ProRes, no AV1.
3. [Bitmovin: Apple AV1 support](https://bitmovin.com/blog/apple-av1-support) - secondary; A17 Pro/M3+ hardware, no iOS software fallback "as of 2026".
4. [MDN: Web video codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Video_codecs) - secondary reference; AV1/HEVC browser support.
5. [WebKit Features in Safari 17.0](https://webkit.org/blog/14445/webkit-features-in-safari-17-0/) - primary; AV1 only with hardware decoding; Opus in MP4/WebM on macOS.
6. [Wikipedia: AV1 (hardware support)](https://en.wikipedia.org/wiki/AV1) - secondary; SoC table (Snapdragon 8 Gen 2+, 7 Gen 4, Tensor, Exynos 2x00, Dimensity 1000/8000/9000, A17 Pro/A18).
7. [Qualcomm Snapdragon 7 Gen 3 product brief](https://docs.qualcomm.com/doc/87-73943-1/87-73943-1_REV_D_Snapdragon_7__Gen_3_Mobile_Platform_Product_Brief.pdf) - primary; decode H.264/H.265/VP9, no AV1 (via search excerpt).
8. [Notebookcheck: Snapdragon 7+ Gen 3 announced](https://www.notebookcheck.net/Qualcomm-announces-Snapdragon-7-Plus-Gen-3-chipset-with-OnePlus-Realme-and-Sharp-smartphones-teased.815601.0.html) - secondary; no AV1 decode.
9. [Android Authority: Exynos 1480](https://www.androidauthority.com/p-3429457/) - secondary; "AV1 decoding isn't supported".
10. [Gizmochina: Exynos 1580](https://www.gizmochina.com/2024/10/24/samsung-unveils-exynos-1580-processor-with-upgraded-cpu-and-gpu/4/) and [Nepalitelecom: Exynos 1380](https://nepalitelecom.com/samsung-exynos-1380-processor-unveiled) - secondary; no AV1 decoder; 1380 decodes HEVC 10-bit/H.264/VP9.
11. [MediaTek Dimensity 7300](https://www.mediatek.com/products/smartphones/mediatek-dimensity-7300) - primary; playback H.264/HEVC/VP9.
12. [MediaTek Dimensity 8300](https://www.mediatek.com/products/smartphones/mediatek-dimensity-8300) - primary; 4K AV1 decode.
13. [Android 15 Compatibility Definition](https://source.android.com/docs/compatibility/15/android-15-cdd) - primary; AV1/HEVC/Opus/AAC/container requirements.
14. [AOSP frameworks/av commit (e/OS mirror): add dav1d decoder](https://gitlab.e.foundation/e/os/android_frameworks_av/-/commit/bb68e9ae9b1154894faaba7df5be76d193dbd319) - primary; `c2.android.av1-dav1d.decoder`.
15. [Landian: Google enhances Android with dav1d](https://landian.news/article/1831.html) - secondary; dav1d default, rollout to Android 11-14.
16. [Meta Engineering: AV1 for Reels (2023-02-21)](https://engineering.fb.com/2023/02/21/video-engineering/av1-codec-facebook-instagram-reels/) - primary; dav1d 720p30 most devices, 1080p30 some; iOS profiles.
17. [Streaming Media: How Meta deploys and benchmarks AV1 on Android (2025-04)](https://www.streamingmedia.com/Articles/Editorial/Short-Cuts/How-Meta-Deploys-and-Benchmarks-AV1-on-Android-169002.aspx) - secondary; 16-17 h battery on $80 phone.
18. [Streaming Learning Center: Tesla rolls back YouTube AV1](https://streaminglearningcenter.com/codecs/tesla-rolls-back-youtube-from-av1-to-vp9.html) - secondary; Galaxy A14 11 h 15 min 720p AV1; YouTube battery complaints.
19. [Apple Developer Forums: Does iOS HLS support Opus? (Media Engineer answer, 2024)](https://developer.apple.com/forums/thread/759210) - primary-ish; Opus iOS 17+, MP4 only, supply AAC.
20. [Apple HLS Authoring Specification](https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html) - primary; hvc1 over hev1, HEVC profile limits, AAC required.
21. [FFmpeg cvslog 2014: movenc use 'hev1' tag](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2014-March/074855.html) - primary.
22. [FFmpeg cvslog 2017: allow alternative hvc1 tag](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2017-July/108220.html) - primary.
23. FFmpeg master source, read 2026-10-20: [movenc.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c), [libx265.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/libx265.c), [libsvtav1.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/libsvtav1.c), [libaomenc.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/libaomenc.c) - primary; tag order, range signalling, loci/©xyz writing, `-g -1` defaults.
24. [libaom av1_cx_iface.c](https://aomedia.googlesource.com/aom/+/refs/heads/main/av1/av1_cx_iface.c) - primary; default `kf_max_dist` 9999.
25. [SVT-AV1 Docs/Parameters.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/Parameters.md) - primary; keyint default ~5 s, fast-decode.
26. [x265 CLI docs](https://x265.readthedocs.io/en/master/cli.html) - primary; keyint default 250.
27. [Immich config file docs](https://docs.immich.app/install/config-file/) - primary; ffmpeg defaults.
28. [Immich issue #15402](https://github.com/immich-app/immich/issues/15402) - primary; 10-bit HEVC always transcoded.
29. [Immich metadata.service.ts](https://github.com/immich-app/immich/blob/main/server/src/services/metadata.service.ts) - primary; date tag precedence, GPS.
30. [Google Photos Help: file types](https://support.google.com/photos/answer/6193313?hl=en) - primary.
31. [Google Photos Help: backup quality](https://support.google.com/photos/answer/6220791?hl=en) - primary; Storage saver resizes >1080p.
32. [Synology Photos spec, DSM 7.3](https://www.synology.com/en-global/dsm/7.3/software_spec/synology_photos) - primary.
33. [Synology Image Assistant spec](https://www.synology.com/en-global/dsm/7.3/software_spec/image_assistant) - primary.
34. [Synology: end of HEVC/AVC/VC-1 transcoding (2024-08-26)](https://www.synology.com/en-global/products/status/eol-video-codec-support) - primary.
35. [SynoForum: no video thumbnail preview](https://www.synoforum.com/threads/no-video-thumbnail-preview.14636/post-72780) - secondary; mobile-app uploads unaffected.
36. [Apple Community: transcoded AV1 cannot be saved to Photos (2025-12)](https://discussions.apple.com/thread/256212244) - secondary, single report.
37. [Apple: Using HEIF or HEVC media on Apple devices](https://support.apple.com/116944) - primary.
38. [FFmpeg trac #4209 comment (2024-04)](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-April/069027.html) - primary; GPS written where Apple apps don't show it.
39. [FFmpeg trac #6193: GPS lost after encoding](https://ffmpeg.org/pipermail/ffmpeg-trac/2017-March/039085.html) - primary (2017, possibly stale).
40. [FFmpeg trac #9177: Opus in MP4 end trimming](https://trac.ffmpeg.org/ticket/9177) - primary; seen via search excerpt only (page blocked by Anubis).
41. [3CX community: Opus recordings no audio in Safari/iMovie](https://www.3cx.com/community/threads/web-conference-recording-playback-issue.121940/latest) - secondary.
42. [MDN: Web audio codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Audio_codecs) - secondary reference.
43. [Mozilla bug 1229304: full-range video rendered limited](https://bugzilla.mozilla.org/show_bug.cgi?id=1229304) - primary, 2015, stale.
44. [FFmpeg trac #8455: libaom-av1 yuvj420p range](https://ffmpeg.org/pipermail/ffmpeg-trac/2021-August/059588.html) - primary; seen via search excerpt.
45. [Voukoder forum: SVT-AV1 full color range](https://www.voukoder.org/forum/thread/1193-svt-av1-full-color-range-is-not-implemented-in-voukoder/) - secondary.
46. [mpv manual (stable)](https://mpv.io/manual/stable/) - primary; hr-seek, hwdec defaults.
47. [Haruna handbook (index.docbook)](https://lxr.kde.org/source/multimedia/haruna/doc/index.docbook) - primary; exact seek mode, hwdec advice.
48. [Wikipedia: Video Core Next](https://en.wikipedia.org/wiki/Video_Core_Next) - secondary; Raphael VCN 3.1.2; AV1 from VCN 3.0.
49. [Wikipedia: Intel Quick Sync Video](https://en.wikipedia.org/wiki/Intel_Quick_Sync_Video) - secondary; AV1 decode from Tiger Lake; VVC Lunar Lake.
50. [Mesa issue #11221: AV1 VA-API stutter on Phoenix with Mesa 24](https://gitlab.freedesktop.org/mesa/mesa/-/issues/11221) - primary, single report.
51. [Phoronix: VA-API AV1 decode lands in Mesa 21.3](https://www.phoronix.com/news/VA-API-AV1-In-Gallium3D) - secondary.
52. [Notebookcheck: Radeon Graphics (Ryzen 7000)](https://www.notebookcheck.com/Radeon-Graphics-Ryzen-7000-vs-Radeon-680M_11422_11124.247532.0.html) - secondary; AV1 decode 8/10-bit.
53. [ffmpeg.org news](https://ffmpeg.org/) - primary; VVC decoder 7.0 experimental, 7.1 stable; 8.1 released 2026-03-16.
54. [Ubuntu packages: ffmpeg in noble](https://packages.ubuntu.com/noble/ffmpeg) - primary; 6.1.1.
55. [FFmpeg trac #11601: VVC decode fails after few frames (2025-05)](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-May/073672.html) - primary.
56. [BlazingCDN: keyframe/GOP size explainer](https://blog.blazingcdn.com/en-us/what-is-a-keyframe-gop-size-and-keyframe-interval) - secondary; illustrative model only.
57. [Jellyfin forum: Opus in MP4 on iOS 17.4+](https://forum.jellyfin.org/printthread.php?tid=10247) - secondary, single report.
58. [mpv issue #1823 (precise seek explanation)](https://github.com/mpv-player/mpv/issues/1823) - primary-ish.
59. [SPIE 2022: Benchmarking and analysis of AV1 software decoding on Android devices](https://astronomicaltelescopes.spiedigitallibrary.org/conference-proceedings-of-spie/12226/122260T/Benchmarking-and-analysis-of-AV1-software-decoding-on-Android-devices/10.1117/12.2633692.full) - primary; abstract seen via search only, page did not render.

## Gaps (what the benchmark should measure)

1. **Software AV1 on mid-range Android**:
   - Play 1080p30, 1080p60 and 4K30 SVT-AV1 files at archive bitrates on a Galaxy A55/A35-class phone, in the Samsung Gallery, Google Photos and Immich apps.
   - Count dropped frames and measure battery drain per hour against the same content in HEVC.
2. **iOS Photos import of AV1** on an iPhone 16 (iOS 18/26): save to library, play and AirDrop. This settles the single report in [36]. Also test an iPhone 15 (A16) to confirm AV1 fails there.
3. **Opus in MP4 in Apple Photos**: import on iOS and macOS, sound present, A/V sync. Also check end-trimming and duration against AAC with FFmpeg 8.x (trac #9177).
4. **Galleries vs metadata**: upload the same re-encode (with and without the exiftool copy step) to Google Photos, Apple Photos, Immich and Synology. Record shown date, time zone and location. The undocumented tags are `loci` vs `©xyz` vs Keys GPSCoordinates.
5. **Google Photos with AV1 and MKV**: accepted, playable on web and Android, and transcoded or not. No documentation was found.
6. **Full-range output**: encode full range kept vs converted to limited range (8- and 10-bit). Check levels on an iPhone, Android, Chrome/Firefox web views (Immich/Google Photos) and mpv with a test chart.
7. **Keyframe interval**:
   - Size delta at 2/5/10 s per content category at equal VMAF.
   - Exact-seek latency in mpv/Haruna with `hwdec=no` vs `vaapi` on the 7950X3D iGPU and a typical laptop.
   - Effect of SVT-AV1 `fast-decode`.
8. **VA-API AV1 on Raphael**: confirm `vainfo` lists `VAProfileAV1Profile0` on the current Mesa, and check for the Mesa 24-era 4K stall [50].
9. **Search-budget gap**: no extra searching was possible for Galaxy S25/Snapdragon 8 Elite, Dimensity 7400/8400 or Snapdragon 7s Gen 3 AV1 status, or for VVC in Matroska. Verify these if they matter.
