# T3 merged: playback on phones, Haruna (libmpv) and Windows PCs (state 2026-10)

Inputs: Report A `self/t3-playback.md` (Claude), Report B `codex/t3-playback.md` (Codex), project history. Merge and verification pass: 2026-10-20.
Scope change applied: gallery apps (Google/Apple/Synology Photos, Immich) are no longer targets, so the gallery-ingest findings of both reports are dropped except where they touch phone playback. New target: Windows PCs owned by other people, which neither report covered; it was researched in this pass.

## 1. Bottom line

- **Default: MP4 + HEVC Main 8-bit (`-tag:v hvc1`) + AAC-LC.** It plays natively on every ~2-year-old iPhone and Android phone and in Haruna. On Windows it needs the HEVC Video Extensions (0,99 USD in the Store, or a free OEM copy preinstalled on many retail PCs); without it, VLC is the fallback. [both + verified]
- **No codec except H.264 plays on a stock Windows PC with zero installs.** Microsoft's list of codecs that ship with Windows says H.265 and AV1 come only "with the install of the corresponding optional codec pack". If "other people's Windows PCs, no installs" is a hard requirement, shared categories need H.264 + AAC. [verified]
- **Opus (the owner's default) is fine on phones and Haruna, and unproven on Windows.** iOS 17+ plays Opus only in MP4 (Apple engineer, plus the owner's iOS 18 test). Android lists Opus in MP4 and MKV. Microsoft's inbox codec table has no Opus row at all. The Windows Media Player app is documented for `.opus`/Ogg only; Opus inside MP4/MKV there is undocumented. Test on one Windows 11 PC before shipping Opus in categories other people watch. [verified, Windows part unverified]
- **AV1 is not a "plays everywhere" codec.** iPhone 15/15 Plus and older have no AV1 decoder and iOS has no system software fallback. iPhone 15 Pro and all iPhone 16/17 models decode it in hardware. Mid-range 2024 Android phones decode in software: Meta (2025) says "up to 1080p @60fps but with suboptimal user experience". One iOS 26 report says AV1 MP4s cannot be saved to Photos even on an iPhone 17 Pro. [verified]
- **MKV is out for phones.** The iOS native player does not open it (owner's test). Windows and Haruna play MKV fine, but MP4 covers every target, and the prototype's MKV outputs had the 1 ms timestamp grid and one corrupt remux. [both + history]
- **Haruna: set the keyframe interval explicitly (≈2-5 s).** Haruna seeks in mpv's "exact" mode and mpv decodes in software by default, so long GOPs (libaom default 9999 frames) cause the slow seeks the owner saw. Defaults: libaom 9999 frames, SVT-AV1 ~5 s, x265 250 frames [25][26][27][28][29]. [A only]
- **VLC is the universal fallback on Windows** (bundled HEVC, dav1d AV1, Opus; VLC 3.0.21 fixed "Opus in MP4 behaviour"). [verified]

## 2. Findings

### Q1. AV1 hardware decode on phones; software fallback

- iPhone: hardware AV1 starts with the A17 Pro. Apple's iPhone 15 Pro spec page lists "HEVC, H.264, AV1, and ProRes"; iPhone 16 (A18) lists "HEVC, H.264, and AV1"; iPhone 15 lists no AV1 [11][12][13]. Meta's 2025 table: A17 Pro and A18 = iPhone 15 Pro/Pro Max, iPhone 16 (all models, incl. 16e), iPhone 17 (all) [14]. [both + verified]
- iOS has no system-wide AV1 software decoder, so iPhone 15 non-Pro and older cannot play AV1 in the native player or Files; Safari 17 enabled AV1 only "on devices with hardware decoding support" [15][35]. Apps that bundle dav1d (VLC, nPlayer) can still play it. [A only for the "no fallback" claim; Safari part both]
- AV1 and the iOS Photos library: one Apple Community post (2025-12-15, iPhone 17 Pro, iOS 26, SVT-AV1 `.mp4`) says the file plays in Files and nPlayer but "can't be saved to Photos". The only reply (a community user, not Apple) says "AV1 is not a supported format to be saved to Photos on iPhone". No Apple documentation either way [16]. [A only; verified the post exists and what it says; claim itself unverified]
- Android flagships: Tensor (Pixel 6+), Snapdragon 8 Gen 2+, Exynos 2100/2200/2400 (Galaxy S21+ Exynos variants), Dimensity 9000-class decode AV1 in hardware [14][37]. [both + verified in Meta 2025 Table 2]
- Android mid-range: no AV1 hardware on Snapdragon 7+ Gen 3 [30], Exynos 1480 (Galaxy A55) [31], Exynos 1580 (A56) and 1380 (A35/A54) [32], Dimensity 7300 [33]; Snapdragon 7 Gen 4 has it [14]. Meta 2025: AV1 hardware "may reach some - but not all - mid-tier SoCs by 2026" [14]. [both for Snapdragon 7-series; A only for the Exynos/Dimensity parts]
- Software decode capacity: [conflict, resolved] A cites Meta 2023 (dav1d 720p30 on "most" devices, 1080p30 only on some mid/high-end) [34]; B cites Meta 2025 (mid-tier "up to 1080p60"). The 2025 white paper says: "modern mid-tier devices can decode AV1 in SW up to 1080p @60fps but with suboptimal user experience including increased battery drain and less responsive application performance" [14]. The newer source wins on capability; both agree on the battery/UX cost. All numbers are streaming bitrates, not archive bitrates; 4K software decode on mid-range is unmeasured. [verified]
- Android always has an AV1 decoder for apps (software dav1d in the swcodec module; Android 14+ makes AV1 mandatory) [18][20]. [both]

### Q2. HEVC profile, `hvc1`, colour range

- Use HEVC **Main 8-bit**: the Android CDD mandates HEVC Main decode, not Main10; sources are 8-bit anyway [20]. [both]
- `hvc1` is required for Apple: FFmpeg writes `hev1` by default and added `-tag:v hvc1` "because QuickTime and other Apple software require hvc1"; Apple's HLS spec marks `hev1` "use not recommended" [21][22][23]. [both; B notes HLS guidance is not proof for local files, the owner's iOS 18 test is]
- Full range: both FFmpeg wrappers (libx265, libsvtav1) signal full range when the input is `yuvj420p`/`color_range pc`; the real risk is an accidental range conversion in the filter graph. No 2025-26 reports of full-range HEVC playing wrong on iOS/Android [23]. [A only; B agrees there is no evidence of widespread failure]
- Windows full-range handling in Media Player was not researched. [gap]

### Q3. Containers and audio (phones, Haruna, Windows)

Phones:
- iOS: MKV does not open in the native player; real MP4 + `hvc1` + Opus plays on iOS 18 (owner's test, history). [both]
- iOS Opus: Apple Media Engineer (Jul 2024): "Opus audio is only supported beginning in iOS 17, and only in MP4 files … you should also supply AAC … Opus is not listed as a supported codec in either the Guidelines or the Tech Specs" [17]. A Jellyfin report puts reliable direct play at iOS 17.4+, mono/stereo [36]. [A; verified the Apple quote]
- Android Opus: the platform formats table lists Opus decode from Android 5.0 with containers Ogg, MPEG-4 (.mp4) and Matroska (.mkv) [18]. ExoPlayer (used by most Android players) uses the platform decoders by default [19]. [verified] [conflict, minor] B says Android documents Opus in MP4 "from Android 10"; on the page Android 10+ is the encoder column, decode is 5.0+ [18]. Moot for 2024 phones.
- Google Photos / Samsung Gallery as viewers of Opus-in-MP4 files: no source found either way. [unverified, test on device]

Haruna (libmpv):
- Plays MP4 and MKV with HEVC, AV1 (dav1d) and Opus/AAC through FFmpeg; mpv default `--hwdec=no` [25][26]. [both, general knowledge plus manuals]

Windows 10/11 (new in this pass):
- Inbox codec table (Microsoft Learn, updated 2026-05): MKV container decode is listed for H.264, H.265, VP9, AV1; H.264 and AAC-LC in MP4 are built in; "H.265 and AV1 are available with the install of the corresponding optional codec pack". The audio table has no Opus or Vorbis row [1]. [verified]
- HEVC Video Extensions: 0,99 USD, publisher Microsoft, "for devices that don't have hardware support for HEVC videos, software support is provided" [2]. A free variant "HEVC Video Extensions from Device Manufacturer" exists (price 0) and is what OEMs (Dell, HP, Lenovo…) preinstall; it is not searchable in the Store and reports say it is unavailable in some markets [3][6]. [verified via Store API, availability by region unverified]
- Is HEVC preinstalled on a clean Windows 11? [conflict] Windows Latest (2025-07-16) says the free version was "exclusively for OEMs … to pre-install" and a clean install lacks it [6]; a second Windows Latest article the same day lists "HEIF, HEVC, AV1, VP9…" among media extensions that appear in Installed apps on 24H2 media, without saying the HEVC decoder is functional [7]. Treat a random Windows PC as "HEVC maybe": OEM laptops usually yes, self-built/clean installs often no. [unverified]
- AV1 Video Extension: free, publisher "Microsoft Windows" [4]; reported as shipped with Windows 11 24H2 install media as a dependency of Photos and Media Player [7]. On Windows 10 it is a free Store install. [verified price; preinstall single-source]
- Web Media Extensions (free, often preinstalled) adds only Ogg, Vorbis and Theora [5]. [verified]
- Opus: Windows has had an Opus decoder since the Windows 10 Anniversary Update (Edge 14 played Opus in WebM by default) [9], and the Media Player app (Windows 11, and Windows 10 since 2023) lists Opus for `.opus`/Ogg files [8]. Nothing documents Opus inside MP4 or MKV in Media Player or Films & TV, and Microsoft's own codec table omits Opus [1]. [verified sources; actual MP4/MKV behaviour unverified]
- Films & TV (Windows 10) and Media Player use the same Media Foundation codecs, so the extension rules above apply to both [8]. [verified for Media Player]
- VLC 3.0.x bundles its own decoders: dav1d AV1 decoder, Opus, HEVC; 3.0.21 "Fix Opus in MP4 behaviour" [10]. VLC is the no-admin-rights-needed fix for every gap above. [verified]

FFmpeg Opus-in-MP4 caveat: trac #9177 reports end trimming (edit list) not applied correctly for Opus in MP4 [24]. Effect is a few ms of extra audio at the end at most; check duration in the fast verify. [A only, ticket page blocked]

### Q4. Gallery behaviour

Out of scope after the owner's decision. Two leftovers that still touch phone use: (a) AV1 may not be savable into iOS Photos (Q1), relevant only if someone saves a NAS file to their camera roll; (b) GPS/creation_time placement is handled in thread T5.

### Q5. Synthesis: recommendation table

Target set: iPhone ~2 years old (iPhone 15/15 Plus and iPhone 16 family, iOS 17-26), Android 2024 phones (flagship and mid-range), Haruna/libmpv, Windows 10/11 Media Player or Films & TV.

| Container | Video | Audio | iPhone 15 / older | iPhone 15 Pro, 16, 17 | Android 2024 | Haruna | Windows, nothing installed | Windows + HEVC ext. | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| MP4 | H.264 High 8-bit | AAC-LC | yes | yes | yes | yes | yes | yes | Plays everywhere; noticeably larger than HEVC (size gap to be measured, see T2) |
| MP4 `hvc1` | HEVC Main 8-bit | AAC-LC | yes | yes | yes | yes | no (VLC) | yes | **Recommended default** |
| MP4 `hvc1` | HEVC Main 8-bit | Opus | iOS 17+ yes | yes | yes (docs) | yes | no (VLC) | unverified | Owner's default; OK for phones + Haruna, test Windows |
| MKV | HEVC | Opus/AAC | no | no | yes (docs) | yes | no (VLC) | AAC yes, Opus unverified | Not recommended |
| MP4 | AV1 (SVT-AV1) | AAC/Opus | no | yes (not savable to Photos?) | flagship HW; mid-range SW, battery cost | yes | yes if AV1 ext. present (likely on Win11 24H2) | same | Only for owner-only categories, if no older iPhones |

Reading the table: no row is "yes" in every column except H.264. HEVC + AAC fails only on Windows PCs without the extension, where the fix is 0,99 USD or VLC. Opus adds one more unknown on Windows and saves ~64 kbit/s versus AAC 128k (~0,5 MB per minute). That is a few percent of a 1080p file and up to ~20% of a 300 kbit/s webinar file (synthesis, not measured).

Suggested split (synthesis): AAC for categories other people watch on Windows (apartment tours, holiday clips, dance); Opus allowed for owner-only low-bitrate categories (webinars, sessions, Zoom calls), where it saves the most. If the Windows test shows Opus-in-MP4 plays in Media Player, Opus can be the default everywhere.

## 3. Verification log

| # | Claim | Result | Source |
|---|---|---|---|
| 1 | Windows ships H.265/AV1 decoders | No: both "available with the install of the corresponding optional codec pack"; MKV decode listed for H.264/H.265/AV1; no Opus row | [1] fetched |
| 2 | HEVC Video Extensions paid? | 0,99 USD (Store API, updated 2026-10-09); OEM variant price 0 | [2][3] Store API JSON fetched |
| 3 | HEVC preinstalled on clean Win11 | Conflicting secondary sources; OEM PCs usually have the free variant | [6][7] fetched; unverified |
| 4 | AV1 Video Extension free / preinstalled | Free (Store API); preinstall on 24H2 media per one article | [4] fetched, [7] single-source |
| 5 | Web Media Extensions content | Ogg, Vorbis, Theora only | [5] Store API |
| 6 | Opus in Windows Media Player | `.opus` (Ogg) listed; MP4/MKV Opus undocumented; Windows Opus decoder since 1607 via Edge | [8][9] fetched; MP4/MKV unverified |
| 7 | VLC covers HEVC/AV1/Opus on Windows | dav1d decoder, Opus updates, "Fix Opus in MP4 behaviour" in 3.0.21 | [10] NEWS file fetched |
| 8 | AV1 HW only A17 Pro+ | iPhone 15 Pro spec lists AV1; iPhone 15 does not; iPhone 16 does; Meta table agrees | [11][12][13][14] fetched |
| 9 | AV1 cannot be saved to iOS Photos | One user report (iOS 26, iPhone 17 Pro); reply from a non-Apple user; no Apple doc | [16] fetched; claim unverified |
| 10 | Mid-tier Android SW AV1 1080p30 vs 1080p60 (A vs B) | Meta 2025: up to 1080p60 with battery and responsiveness cost | [14] PDF read |
| 11 | Opus on iOS: version, container | iOS 17+, MP4 only, not in Apple specs, supply AAC | [17] fetched |
| 12 | Opus in MP4 on Android | Platform table: decode Android 5.0+, containers Ogg/MP4/MKV; B's "Android 10" is the encoder column | [18] fetched |
| 13 | Google Photos / Samsung Gallery play Opus-in-MP4 | No source found | unverified |
| 14 | ExoPlayer decodes via platform | Yes, platform decoders by default | [19] fetched |
| 15 | FFmpeg Opus-in-MP4 trimming bug #9177 | Not re-checked (Anubis block in A's pass) | [24] unverified |

## 4. Benchmark candidates (playback part)

- Encodes for the device test, from one 60 s 1080p60 phone clip and one 4K30 clip:
  - `libx265 -preset slow -crf <T2> -pix_fmt yuv420p -tag:v hvc1 -g <2-5 s × fps> -keyint_min <fps>` + `-c:a aac -b:a 128k` → `.mp4`, `-movflags +faststart`.
  - Same video + `-c:a libopus -b:a 64k` (and 96k) → `.mp4`.
  - `libsvtav1 -preset 4 -crf <T2> -g <…> -svtav1-params fast-decode=1` + AAC → `.mp4`.
  - `libx264 -preset slow -crf <T2>` + AAC → `.mp4` as the compatibility reference.
- Device checklist (plays, audio present, seek, A/V sync after seek, duration matches source):
  - iPhone 15 or older non-Pro (expect AV1 to fail), iPhone 16-class (also "Save to Photos" for AV1).
  - Galaxy A5x-class (AV1 software: dropped frames, battery %/h vs HEVC) and a flagship (S24/Pixel).
  - Haruna on the 7950X3D and on a typical laptop: exact-seek latency at GOP 2/5/10 s, `hwdec=no` vs `vaapi`.
  - Windows 11 PC: Media Player with no extras, with HEVC Video Extensions, with VLC; same for Films & TV on Windows 10 if available.
- Size cost of the compatibility choices per category: AAC 128k vs Opus 64k share of file size; GOP 2 s vs 5 s at equal VMAF.
- Fast per-file checks: `codec_tag_string=hvc1`, major brand `isom`/`mp42` (not Matroska under `.mp4`, the January bug), audio codec matches preset, keyframe spacing ≤ target, audio duration within ~50 ms of video.

## 5. Open questions for the owner

1. Windows viewers: is "install the 0,99 USD HEVC extension or VLC" acceptable for other people's PCs, or must shared categories play with zero installs (then H.264 + AAC for those categories, at a size cost)?
2. Opus vs AAC per category: keep Opus as the global default only if the Windows Media Player test passes, otherwise AAC for categories others watch and Opus for owner-only ones. OK?
3. Do any viewers still use an iPhone 15/15 Plus or older? If yes, AV1 is ruled out for every category they might open.
4. Will anyone save NAS videos into the iPhone camera roll? If yes, AV1 is ruled out regardless of device (single report, to be confirmed in the device test).

## 6. Sources

1. [Microsoft Learn: Supported codecs (Windows apps), updated 2026-05](https://learn.microsoft.com/en-us/windows/uwp/audio-video-camera/supported-codecs) - primary.
2. [Microsoft Store: HEVC Video Extensions (9NMZLZ57R3T7)](https://apps.microsoft.com/detail/9nmzlz57r3t7) - primary; price read via Store API.
3. [Microsoft Store: HEVC Video Extensions from Device Manufacturer (9N4WGH0Z6VHQ)](https://apps.microsoft.com/detail/9n4wgh0z6vhq) - primary.
4. [Microsoft Store: AV1 Video Extension (9MVZQVXJBQ9V)](https://apps.microsoft.com/detail/9mvzqvxjbq9v) - primary.
5. [Microsoft Store: Web Media Extensions (9N5TDP8VCMHS)](https://apps.microsoft.com/detail/9n5tdp8vcmhs) - primary.
6. [Windows Latest: Can you get HEVC codec for free on Windows 11 (2025-07-16)](https://windowslatest.com/2025/07/16/can-you-get-hevc-codec-for-free-on-windows-11) - secondary.
7. [Windows Latest: Windows 11 24H2 installs 36 inbox apps (2025-07-16)](https://windowslatest.com/2025/07/16/microsoft-windows-11-24h2-installs-36-inbox-apps-now-fully-up-to-date) - secondary.
8. [Wikipedia: Windows Media Player (2022)](https://en.wikipedia.org/wiki/Windows_Media_Player_(2022)) - secondary; format table, extension notes.
9. [Microsoft Edge blog: WebM, VP9 and Opus support (2016-04-18)](https://blogs.windows.com/msedgedev/2016/04/18/webm-vp9-and-opus-support-in-microsoft-edge/) - primary, old.
10. [VLC 3.0.x NEWS](https://code.videolan.org/videolan/vlc/-/raw/3.0.x/NEWS) - primary.
11. [iPhone 15 Pro tech specs](https://support.apple.com/en-us/111829) - primary.
12. [iPhone 16 tech specs](https://support.apple.com/en-us/121029) - primary.
13. [iPhone 15 tech specs](https://support.apple.com/en-us/111831) - primary.
14. [Meta AV1 White Paper (2025-09)](https://engineering.fb.com/wp-content/uploads/2025/09/Meta-AV1-White-Paper-FINAL.pdf) - primary; SoC table, SW decode tiers.
15. [Bitmovin: Apple AV1 support](https://bitmovin.com/blog/apple-av1-support) - secondary.
16. [Apple Community: transcoded AV1 cannot be saved to Photos (2025-12)](https://discussions.apple.com/thread/256212244) - secondary, single report.
17. [Apple Developer Forums 759210: Opus on iOS (Media Engineer, 2024-07)](https://developer.apple.com/forums/thread/759210) - primary-ish.
18. [Android: Supported media formats](https://developer.android.com/media/platform/supported-formats) - primary.
19. [Media3 ExoPlayer: Supported formats](https://developer.android.com/media/media3/exoplayer/supported-formats) - primary.
20. [Android 15 CDD](https://source.android.com/docs/compatibility/15/android-15-cdd) - primary.
21. [Apple HLS Authoring Specification](https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html) - primary.
22. [FFmpeg cvslog 2017: allow hvc1 tag](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2017-July/108220.html) - primary.
23. [FFmpeg movenc.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c), [libx265.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/libx265.c), [libsvtav1.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/libsvtav1.c) - primary source code.
24. [FFmpeg trac #9177: Opus in MP4 end trimming](https://trac.ffmpeg.org/ticket/9177) - primary, not opened.
25. [mpv manual](https://mpv.io/manual/stable/) - primary.
26. [Haruna handbook](https://lxr.kde.org/source/multimedia/haruna/doc/index.docbook) - primary.
27. [libaom av1_cx_iface.c](https://aomedia.googlesource.com/aom/+/refs/heads/main/av1/av1_cx_iface.c) - primary; `kf_max_dist` 9999.
28. [SVT-AV1 Parameters.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/Parameters.md) - primary; keyint, fast-decode.
29. [x265 CLI docs](https://x265.readthedocs.io/en/master/cli.html) - primary; keyint 250.
30. [Qualcomm Snapdragon 7+ Gen 3 product brief](https://docs.qualcomm.com/bundle/publicresource/87-73943-1_REV_E_Snapdragon_7__Gen_3_Mobile_Platform_Product_Brief.pdf) - primary.
31. [Android Authority: Exynos 1480](https://www.androidauthority.com/p-3429457/) - secondary.
32. [Gizmochina: Exynos 1580](https://www.gizmochina.com/2024/10/24/samsung-unveils-exynos-1580-processor-with-upgraded-cpu-and-gpu/4/) - secondary.
33. [MediaTek Dimensity 7300](https://www.mediatek.com/products/smartphones/mediatek-dimensity-7300) - primary.
34. [Meta Engineering: AV1 for Reels (2023-02-21)](https://engineering.fb.com/2023/02/21/video-engineering/av1-codec-facebook-instagram-reels/) - primary, older.
35. [WebKit: Features in Safari 17.0](https://webkit.org/blog/14445/webkit-features-in-safari-17-0/) - primary.
36. [Jellyfin forum: Opus in MP4 on iOS 17.4+](https://forum.jellyfin.org/printthread.php?tid=10247) - secondary, single report.
37. [Wikipedia: AV1 hardware support](https://en.wikipedia.org/wiki/AV1) - secondary.
