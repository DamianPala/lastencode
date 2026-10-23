I’ll focus on current device decode support, file-format behavior in the named gallery apps, and the metadata risks that affect this archive workflow. I’ll cross-check vendor documentation with implementation docs and independent reports, then separate verified support from areas that still need device testing.

The codec picture is already split by model tier: several 2024 flagships have AV1 hardware decode, while some midrange phones do not, and Apple’s AV1 support starts at iPhone 15 Pro rather than the whole iPhone 15 family. I’m checking the practical consequences now, especially whether container, audio, and library support undermine that device-level capability.

### TL;DR

For straightforward phone playback, use **HEVC Main, MP4 with `hvc1`, and AAC-LC**; use H.264 instead if compatibility with browsers and older devices matters more than file size. AV1 hardware decode is common on 2024 flagships but uneven across iPhone 15 models and Android midrange phones. Container and codec support in a phone’s decoder does not guarantee that a gallery app will import, preview, sync, or preserve the file’s metadata.[1][2][3][4][8][12][17][20]

### Key Findings

#### 1. AV1 hardware decode and software playback

**What:** Based on Meta’s 2025 device survey, AV1 hardware decode covers Pixel phones with Tensor G3/G4, Snapdragon 8 Gen 2 and later, recent Exynos flagships, and Dimensity 9000-series chips. On iPhones, the 15 Pro and Pro Max have hardware decode; the regular iPhone 15 and 15 Plus do not. Apple’s iPhone 16 specifications list AV1 playback, and WebKit identifies iPhone 15 Pro and Pro Max as Safari’s first iPhones with hardware AV1 decode.[1][2][3][4]

Android’s AV1 decoder availability is not a promise of hardware decoding: Android documents AV1 support, while Meta reports that software decoding can cost battery and responsiveness. Meta describes mid-tier phones as capable of software playback up to 1080p60, but does not make 4K software playback a safe general assumption. Its concrete battery example is a low-end Moto e13 playing 720p30 AV1, which used about 3,2% battery per hour; that result should not be extrapolated to other phones, resolutions, or playback conditions.[1][8]

**Evidence:** [1][2][3][4][5][6][7][8]  
**Confidence:** High for the flagship hardware split; medium for software playback outside the specific tested devices.

**What:** A-series and other midrange phones are the main uncertainty. Qualcomm’s Snapdragon 7+ Gen 3 brief lists H.264, HEVC, and VP9 decode but not AV1; Meta reports AV1 decode in Snapdragon 7 Gen 4, so “Snapdragon 7” alone does not establish support. The same caution applies to Samsung A-series and MediaTek models: check the exact chip and phone rather than infer support from Android version or brand.[1][7]

**Evidence:** [1][7]  
**Confidence:** Medium. The named product brief is clear, but the available evidence does not settle every 2024–early-2025 A-series model.

#### 2. HEVC profiles, sample entries, and color range

**What:** HEVC is the more dependable compact codec for this target group. Apple supports HEVC on current iOS devices, and Android documents HEVC decoding; the exact profile and performance still depend on the device. For an 8-bit SDR source, HEVC Main is the conservative starting point. Main10 is supported on many recent flagships, but it should be tested before making it the only archive output for a mixed fleet.[8][10][30]

Apple’s HLS guidance recommends the `hvc1` sample entry for HEVC compatibility. That guidance is for HLS, so it is not proof that every local-file app rejects `hev1`; nevertheless, MP4 with `hvc1` is the safer compatibility candidate. Browser playback is a separate constraint: HEVC support varies by browser and operating system, and may depend on hardware or platform support.[9][12]

**Evidence:** [8][9][10][12][30]  
**Confidence:** High for HEVC being broadly available and Apple’s HLS `hvc1` recommendation; medium for applying that HLS recommendation to every local player.

**What:** Full-range video is valid when correctly signaled, but the reviewed sources do not establish a widespread full-range HEVC or AV1 failure on iOS or Android. Apple’s color guidance emphasizes that range, primaries, transfer function, and matrix must be represented correctly. A public player issue reports washed-out or clipped color in one full-range playback path; treat it as an example of a possible signaling bug, not evidence of a platform-wide problem.[11][28]

**Evidence:** [11][28]  
**Confidence:** Medium on correct signaling being necessary; low on the prevalence of full-range playback problems.

#### 3. Containers, audio, and player behavior

**What:** MP4 is the best default container for this workflow. Android documents MP4 and Matroska support for relevant media components, but Apple’s native playback path is built around formats such as MP4 and MOV. The project’s supplied iOS 18 test also found that MP4 with HEVC and Opus played natively while MKV did not. VLC and mpv offer broader container and codec coverage on desktop and mobile, but that does not make MKV a good default for native gallery playback.[8][24][25][29]

Google Photos lists MKV among accepted video upload extensions, and Immich supports both MKV and MP4. Synology Photos documents MOV and MP4 as its supported video formats. These are container-level statements: they do not establish that each service will process every codec, profile, audio stream, or color configuration inside those containers.[13][17][20]

**Evidence:** [8][13][17][20][24][25][29]  
**Confidence:** High for the documented container support; medium for native iOS behavior, supported by Apple’s format documentation and the project’s supplied device test.

**What:** AAC-LC is the safer audio choice for cross-platform gallery playback. Android documents Opus in MP4 from Android 10, and the project reports a successful iOS 18 HEVC-plus-Opus test; however, Apple’s current iPhone playback-format list does not list Opus. That makes Opus a reasonable tested optimization, but not as strong a default as AAC for a mixed gallery-app workflow.[2][8]

**Evidence:** [2][8]  
**Confidence:** High that AAC is the more conservative choice; medium for Opus because support varies by app and was only established here by platform documentation plus one supplied iOS test.

#### 4. Galleries, sync, and metadata

**What:** Google Photos documents accepted upload extensions, including MKV, but its upload documentation does not promise support for every video codec. Its API exposes a processing state, so a successful upload request alone does not establish that the service has finished processing or that playback works.[13][14][15]

Synology Photos’ documentation lists MOV and MP4, and its release notes describe a client-side change for HEVC handling: HEVC preview or conversion may require Synology Image Assistant, depending on the DSM and client path. Its documented web playback also depends on a client that supports HEVC. Immich accepts a wider range of video extensions and can transcode or remux to configured formats, but that is library behavior rather than a guarantee that every browser can play the original file.[17][18][19][20][21]

**Evidence:** [13][14][15][17][18][19][20][21]  
**Confidence:** High for documented extensions and Synology’s HEVC workflow; medium for end-to-end playback because processing depends on the service and client.

**What:** Re-encoding can disrupt gallery dates and locations if metadata is not preserved in the form each app recognizes. Google Photos’ API includes a creation time and processing state; Apple Photos lets users view and edit date, time, and location; Immich’s metadata service parses date and GPS fields and documents XMP sidecar support. Synology Photos organizes media by date, but its public documentation does not guarantee that every re-encoded video’s creation time and GPS will be interpreted identically across import paths.[15][16][22][23][26][27]

**Evidence:** [15][16][22][23][26][27]  
**Confidence:** Medium. The apps expose relevant metadata features, but the reviewed documentation does not provide a common, complete video-tag precedence rule.

### Perspectives

- **“AV1 is ready for recent phones.”** This is true for many 2024 flagships: the iPhone 15 Pro, Pixel 8/9 generation, Snapdragon 8 Gen 2 and later, and several recent flagship Android chips have hardware decode. Hardware decoding is the relevant distinction for predictable power use, not merely whether a platform lists AV1 as a supported format.[1][2][4][5][6]

- **“AV1 is not yet a safe universal mobile default.”** That is also supported: base iPhone 15 models lack the hardware decode path identified for the Pro models, midrange Android chips vary, and software decode has device-dependent performance and battery cost. Android’s decoder support alone does not settle whether a particular device uses hardware.[1][3][7][8]

- **“A gallery accepts the file.”** That statement can mean it accepts the extension, accepts the upload, finishes processing, or plays the stream in a particular client. Google Photos’ extension list and Immich’s supported-format list establish only part of that chain; Synology’s HEVC documentation makes the dependence on client software especially explicit.[13][14][17][18][20][21]

### Practical Implications

For the benchmark matrix, compare:

- **Compatibility candidate:** HEVC Main, 8-bit SDR, MP4 with `hvc1`, AAC-LC. Include H.264/MP4/AAC as the wider-compatibility reference, especially for browser and older-device playback.[8][9][10][12]
- **Recent-device candidate:** AV1 in MP4 with AAC-LC, limited to devices confirmed to have hardware AV1 decode. Test gallery import and playback separately from local playback; decoder capability does not establish Apple Photos or Synology Photos ingestion support.[1][2][17][18]
- **Audio optimization:** Compare Opus against AAC only after testing the actual iOS, Android, browser, and gallery-app paths in scope.[2][8]
- **Range and metadata:** Keep an explicit color-range test using known black/white levels. Test both playback and gallery rendering, and verify creation time, timezone, and GPS after import. Preserve the originals as the recovery path for metadata or playback failures.[11][15][16][22][23][26]

For a “plays on a two-year-old phone without fuss” default, I recommend **HEVC Main, MP4/`hvc1`, AAC-LC**. If “without fuss” includes arbitrary browsers or older devices, keep **H.264/MP4/AAC** as the compatibility profile. For a smaller file aimed only at verified recent devices, benchmark **AV1/MP4/AAC**, but do not assume it will work smoothly in every named gallery app.[1][8][9][12][17][20]

### Sources

1. [Meta AV1 White Paper (2025)](https://engineering.fb.com/wp-content/uploads/2025/09/Meta-AV1-White-Paper-FINAL.pdf) — Primary, company research; device hardware decode coverage and software decode observations.
2. [iPhone 16 Technical Specifications](https://support.apple.com/en-euro/121029) — Primary, Apple; listed video playback formats.
3. [iPhone 15 Technical Specifications](https://support.apple.com/en-ie/111831) — Primary, Apple; iPhone 15 family specifications.
4. [WebKit Features in Safari 17.0](https://webkit.org/blog/14445/webkit-features-in-safari-17-0/) — Primary, WebKit; Safari AV1 availability on devices with hardware decode.
5. [Exynos 2400](https://semiconductor.samsung.com/processor/mobile-processor/exynos-2400/) — Primary, Samsung; codec and video decode capabilities.
6. [Snapdragon 8 Gen 3 Product Brief](https://docs.qualcomm.com/bundle/publicresource/87-71408-1_REV_D_Snapdragon_8_gen_3_Mobile_Platform_Product_Brief.pdf) — Primary, Qualcomm; video decode formats.
7. [Snapdragon 7+ Gen 3 Product Brief](https://docs.qualcomm.com/bundle/publicresource/87-73943-1_REV_E_Snapdragon_7__Gen_3_Mobile_Platform_Product_Brief.pdf) — Primary, Qualcomm; listed decode formats.
8. [Supported Media Formats](https://developer.android.com/media/platform/supported-formats?authuser=5&hl=en) — Primary, Android; codec, container, and platform support.
9. [HLS Authoring Specification for Apple Devices](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices/) — Primary, Apple; HEVC profile and sample-entry guidance for HLS.
10. [Using HEIF or HEVC Media on Apple Devices](https://support.apple.com/en-au/116944) — Primary, Apple; HEVC device and format support.
11. [Setting Color Properties for a Specific Resolution](https://developer.apple.com/documentation/avfoundation/setting-color-properties-for-a-specific-resolution) — Primary, Apple; color-property signaling.
12. [Video Codecs for the Web](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Video_codecs) — Secondary, Mozilla Developer Network; browser codec support and platform dependencies.
13. [Back Up Photos and Videos](https://support.google.com/photos/answer/6193313?hl=en-en) — Primary, Google; listed backup video extensions.
14. [Upload Media](https://developers.google.com/photos/library/guides/upload-media) — Primary, Google; media upload workflow.
15. [MediaItems API Reference](https://developers.google.com/photos/library/reference/rest/v1/mediaItems?authuser=44) — Primary, Google; creation time and processing status fields.
16. [Find and Manage Your Photos’ Location](https://support.google.com/photos/answer/6153599?hl=en-en) — Primary, Google; location information in Google Photos.
17. [Synology Photos Technical Specifications](https://www.synology.com/en-global/dsm/7.4/software_spec/synology_photos) — Primary, Synology; listed formats and client playback notes.
18. [Synology Photos Release Notes](https://www.synology.com/en-global/releaseNote/SynologyPhotos?model=DS218j) — Primary, Synology; HEVC processing changes.
19. [End of Video Codec Support](https://www.synology.com/en-us/products/status/eol-video-codec-support) — Primary, Synology; codec support and processing changes.
20. [Supported Formats](https://docs.immich.app/features/supported-formats/) — Primary, Immich documentation; accepted media extensions.
21. [System Settings](https://docs.immich.app/administration/system-settings/) — Primary, Immich documentation; transcoding and playback settings.
22. [Immich Metadata Service](https://github.com/immich-app/immich/blob/main/server/src/services/metadata.service.ts) — Primary, Immich source code; parsed date and location fields.
23. [XMP Sidecars](https://docs.immich.app/features/xmp-sidecars/) — Primary, Immich documentation; sidecar metadata import.
24. [VLC Features](https://images.videolan.org/vlc/features.html) — Primary, VideoLAN; supported formats and platforms.
25. [mpv Manual](https://mpv.io/manual/stable/) — Primary, mpv documentation; playback and codec capabilities.
26. [See Photo and Video Information on iPhone](https://support.apple.com/guide/iphone/see-photo-and-video-information-iph0edb9c18f/ios) — Primary, Apple; viewing and editing date, time, and location.
27. [Synology Photos Quick Start](https://kb.synology.com/en-global/DSM/tutorial/Quick_Start_Synology_Photos) — Primary, Synology; timeline and date management.
28. [SideScreen Full-Range Playback Issue](https://github.com/tranvuongquocdat/SideScreen/issues/55) — Secondary, single reported issue; example of a full-range color playback problem.
29. [How to Play MKV Files on iPhone](https://www.idownloadblog.com/2023/01/17/how-to-play-mkv-files/) — Secondary; notes the limitations of Apple’s native MKV playback path.
30. [Android 14 Compatibility Definition Document](https://source.android.com/docs/compatibility/14/android-14-cdd) — Primary, Android; codec requirements and device compatibility criteria.

### Gaps

The public documentation reviewed does not settle whether Google Photos, Apple Photos, and every Synology Photos client will successfully ingest and play each AV1 or HEVC profile. It also does not establish consistent date and GPS extraction across all re-encoding and upload paths.[13][15][17][18][20][22][23]

Measure dropped frames, startup time, seeking, decoder type, battery use, and device temperature for 1080p30, 1080p60, and 4K clips on representative iPhone, Pixel, Galaxy S, and Galaxy A devices. Test each file through local playback, gallery import and playback, and the relevant web client; separately verify processing completion and metadata after upload.[1][13][15][17][18][20]
