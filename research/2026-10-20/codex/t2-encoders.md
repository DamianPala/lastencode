This research covers codec selection and quality, category presets, screen content, noise and grain, audio, and archiving practices. It prioritizes 2025–2026 documentation and benchmarks and labels older sources where they still define codec behavior.

### TL;DR

Keep x265 and HEVC as the compatibility baseline, and compare them against current SVT-AV1 at matched visual quality and measured file size. AV1 can save substantial bits in streaming deployments, but the public evidence I found does not establish a fixed advantage at near-transparent archival quality on your footage; recent phone and gallery-app playback also needs device-by-device testing. [1][2]

The January prototype’s x265 settings are reasonable candidates, not established category presets. For this project, the most valuable next steps are calibrated per-file quality searches, careful VFR-aware comparisons, selective downscaling, and tests that include motion and fine-detail scenes.

### Key Findings

#### 1. Encoder choice in 2026

**What:** As of 20 October 2026, the latest releases I found are x265 4.3, SVT-AV1 4.2.0, libaom 3.15, and VVenC 1.14.0. [3][4][5][14] The latest MSU FullHD comparison tested older versions, including x265 4.1, SVT-AV1 3.0.1, libaom 3.12.0, and VVenC 1.13.1; it used 50 sequences, but its objective-metric winners varied by metric and its “slow” category meant 1080p at 1 frame per second on an Intel i7-12700K. [1]

**Evidence and synthesis:** Meta’s 2025 encoding analysis reports about 30% fewer bits for SVT-AV1 than x265 at the same energy level across its encoder comparison, but that is a vendor analysis for streaming workloads, not a test of near-transparent personal archives on your CPU. [2] Synthesizing across that result and MSU’s metric-dependent rankings, AV1 merits a place in your benchmark matrix, but the available evidence does not show that it will reliably beat x265 at your chosen archival quality. Your January prototype’s encode times are useful local evidence about speed; without retained quality measurements, they do not settle the size-quality comparison.

**Fork status:** The original SVT-AV1-PSY project ended in April 2025 and its repository is archived; its README points users toward SVT-AV1-HDR as the continuation. [9] Many PSY-originated features, including variance boost, adaptive film grain, IQ tune, SCM level 3, intraBC optimizations, and AC bias, have since appeared in mainline SVT-AV1. [4] SVT-AV1-HDR and SVT-AV1-Essential remain active alternatives, but their defaults and tune behavior can differ from mainline; the HDR README also documents a relaxed release cadence. Pin the exact build, and check that build’s `--help` before encoding, because online parameter examples may lag changes. [10][11][12]

**Playback and recommendation:** Meta reports AV1 hardware decoding on iPhone 15 Pro and iPhone 16 or newer, and on many high-tier Android SoCs; software decoding can work but uses more CPU and battery, with device performance varying. [2] Android 17 has added VVC media-framework support, but decoding depends on a vendor-provided decoder and Android does not supply a VVC software decoder. [13] **Synthesis:** use x265 4.3 as the practical baseline, SVT-AV1 4.2 as the main challenger, and test libaom 3.15 for screen content or selected difficult clips. VVenC is a useful experiment, but not a default for a library meant to play reliably in existing phone and gallery apps. [1][2][5][13][14]

**Confidence:** Medium. Current versions and benchmark methodology are well documented; the best encoder for this project’s near-transparent quality target remains unsettled.

#### 2. Category presets and parameter choices

**What:** x265 and SVT-AV1 have different CRF scales, so the numbers below are pilot search brackets, not equivalent-quality settings or guaranteed “transparent” values. x265 describes CRF as a quality-controlled variable bitrate mode, while SVT-AV1 has its own quality scale and tune options. [6][7]

**Synthesis:** Begin with x265 `slow`; test `slower` or `veryslow` only where the output-size improvement justifies the additional time. For SVT-AV1, compare presets 2–4 with `tune=0` (VQ), and retain a fixed build and parameter set during each comparison. The encoder documentation confirms that lower SVT preset numbers trade speed for quality, and that tune 0 targets subjective quality rather than PSNR. [7][8]

| Content | x265 pilot CRF | Mainline SVT-AV1 pilot CRF | Initial test |
|---|---:|---:|---|
| Apartment and property walkthroughs | 18–24 | 22–32 | Keep source resolution and frame rate first; test 4K to 1080p separately. |
| Dance lessons, fine detail | 16–22 | 20–30 | Keep native frame rate and resolution; compare x265 AQ modes 2 and 3. |
| Static session recordings | 20–28 | 24–36 | Test without denoising first; include clips with visible sensor noise. |
| Webinars with slides and a talking head | 18–24 | 20–32 | Compare screen-content tools; retain motion in the talking-head inset. |
| Compressed Zoom-style calls | 22–28 | 28–40 | Re-encode only if a sample predicts worthwhile savings without objectionable damage. |
| Holiday and everyday clips | 18–24 | 22–32 | Preserve 50/60 fps for motion; test selective 4K to 1080p. |

These ranges are **my proposed search brackets**, not measured recommendations for your footage. A practical first pass is a small CRF sweep on representative clips, then a narrower search around the best quality-size tradeoff. [6][7][23][25]

For x265, `aq-mode=3` is specifically biased toward dark scenes and is documented as useful for 8-bit or low-bitrate 10-bit encodes. That makes it a sensible comparison for dark dance footage, but it does not specifically target hair or clothing detail. The default AQ strength is 1.0; because strength changes can significantly affect bitrate in AQ modes 2 and 3, compare mode 2 versus 3 and strengths around 0.8–1.1. [6] Your `deblock=-1:-1` is a reasonable candidate for visual comparison, but keep a default-deblock encode in the matrix: the result depends on the footage. I would also keep `psy-rd` and `psy-rdoq` at encoder defaults initially; x265 warns that high psychovisual strengths can raise bitrate and cause artifacts, including ringing. [6]

The prototype’s x265 dance settings are therefore plausible, particularly where dark scenes need help, but they are not validated as a general dance preset. Treat AQ3, strength 1.1, and negative deblocking as separate variables so the benchmark reveals which one helps. Leave `no-sao` out of the default until it passes a direct visual comparison. For genuinely grainy footage, test x265’s grain tune as a separate variant; the documentation warns that overriding its interacting settings can cause grain strobing. [6][26]

For SVT-AV1, start with `tune=0` for ordinary video. Compare `--enable-variance-boost 1` against the default, especially on moving footage with fine texture; the documented default is off, with strength 2 and variance octile 5. Keep `--enable-overlays` at its default initially, and test it only as a separate variable. SVT’s `--scm` options are for screen-content detection, while overlays are an additional reference-frame option; they should not be treated as interchangeable tuning switches. [7]

**Global defaults to test:** A 10-bit output from an 8-bit source can reduce rounding and may slightly improve fidelity; SVT’s documentation estimates about a 5% file-size cost and warns that some decoders work harder on 10-bit. Include `yuv420p10le` as a candidate, then check playback on the actual phones and gallery apps. [8] Keep the source frame timing and avoid forcing constant frame rate in the general path. SVT’s default GOP is about five seconds, while x265’s default maximum is 250 frames, about 8,3 seconds at 30 fps; retain scene-cut behavior and only change the interval if seekability or a measured compression difference justifies it. [6][7]

**Confidence:** Medium for parameter behavior and the prototype assessment; low for the proposed CRF brackets, which need the project’s own benchmark.

#### 3. Slides, text, and mostly static webinars

**What:** Current SVT-AV1 exposes screen-content modes: level 1 uses block copy and palette tools, level 2 is content-adaptive, and level 3 is anti-alias-aware. The current changelog identifies SCM level 3 as a feature brought over from SVT-AV1-PSY. [4][7] libaom exposes `--tune-content=screen`, palette mode, and IntraBC; x265’s SCC Intra Block Copy is available only in builds compiled with `ENABLE_SCC_EXT`. [16][17]

**Synthesis:** For webinars, compare SVT `scm=0` against `scm=3`; also test libaom’s screen tune on a representative slide-heavy clip. Check whether the installed x265 build actually has SCC enabled before investing time in it. These tools are strongest candidates for rendered text and repeated screen patterns; they are not general-purpose settings for apartment or holiday footage. [6][7][16][17]

A global frame-rate reduction is risky for webinars because the talking head still moves. Test 30 to 15 fps only on clips where the face and gestures remain acceptable, and compare video-only size; inter-frame compression already exploits repeated frames, so halving the frame rate does not imply half the file size. I found no reliable general savings figure for this mixed slide-and-speaker content, so measure it on the project’s public test clips.

**Confidence:** High for tool availability; low for expected savings and frame-rate reduction, which are content-dependent.

#### 4. Phone-camera noise and grain

**What:** AV1 film-grain synthesis can encode a denoised image and signal synthesized grain for playback. Netflix reported one grainy film example dropping from 8 274 kbit/s to 2 804 kbit/s with its AV1 film-grain-synthesis pipeline, but that is one streaming example, not evidence of equivalent savings or fidelity on phone-camera noise. [19] ITU-T’s 2025 film-grain supplement warns that denoising may remove real picture detail as well as noise, including detail around edges and complex textures. [18]

**Synthesis:** Make no denoise the archival baseline. On visibly noisy clips, compare it with mild `hqdn3d` and `nlmeans`; include BM3D only if its extra runtime is acceptable. Review hair, clothing, foliage, and edges at full size. Use AV1 film-grain tools only on clips where the result looks better in playback; synthetic grain is not a pixel-preserving archive of the captured noise. Since the project keeps originals by default, that separation makes the grain-synthesis test practical. [7][8][18][19][20]

**Confidence:** High that denoising and synthesized grain have fidelity tradeoffs; low for how much either will help personal phone clips.

#### 5. Audio: Opus or AAC

**What:** Opus covers a wide bitrate range, with RFC 6716 giving 64–128 kbit/s as a range for fullband stereo music; FFmpeg’s libopus wrapper exposes application and bitrate controls. FFmpeg also includes its native AAC encoder and can optionally be built with the external `libfdk-aac` encoder. [21][22]

**Synthesis:** Use these as starting tests, not universal transparency thresholds:

- Speech: try Opus at 32–48 kbit/s mono when the source is genuinely mono; preserve stereo where it carries room or speaker separation. For AAC, include a 64–96 kbit/s mono test.
- Dance lessons or music: retain stereo; try Opus at 96–128 kbit/s and AAC-LC at 128–192 kbit/s.
- Compare FFmpeg’s native `aac` with `libfdk-aac` only if the latter is already available in the build. Pick based on listening tests and size, not encoder reputation. [21][22]

Do not apply loudness normalization in the archival path. The project’s own iOS test found HEVC MP4 with Opus playable in the native player, but validate the actual combinations of phone, container, and gallery app before choosing a universal default.

**Confidence:** Medium for codec capabilities; low for per-content transparency thresholds without listening tests.

#### 6. Other ways to improve size, quality, or time

**What:** `ab-av1` can search for a CRF that meets a sampled VMAF target, and Av1an can target quality by chunk while encoding chunks in parallel. [23][25] x265’s documentation describes CRF as a quality-controlled mode rather than a target-size mode; SVT’s documented second pass is restricted to non-CRF modes. [6][7]

**Synthesis and practical candidates:**

- **Use per-file CRF search as a size-quality control.** Probe several representative portions of a file, then check the chosen CRF against the most difficult motion and detail scenes. A whole-file mean can conceal a short but important bad section. Do not make VMAF the sole acceptance test: Netflix’s 2026 VMAF v1 article lists high-frame-rate handling and film-grain noise among areas still being improved. [14][15][23][25]
- **Use metrics with visual review.** Record VMAF v1, XPSNR, and SSIMULACRA2 where available, then inspect matched frames and motion crops. Align comparisons by timestamps: Netflix’s FFmpeg guidance says filter synchronization uses timestamps, so VFR footage needs correct frame-rate and PTS handling. [1][12][15]
- **Downscale only after testing.** Compare native resolution against 4K to 1080p on phone playback and on desktop crops. For dance detail and screen text, include close inspection before adopting a smaller output. The project’s originals make this a reversible choice.
- **Preserve frame rate where motion matters.** Keep 50/60 fps for dance and fast handheld scenes as the baseline. Compare a lower frame rate only on slow or mostly static speech footage; frame removal sacrifices temporal detail, and the size effect must be measured on the clip.
- **Reserve two-pass encoding for a size or bitrate target.** For ordinary archival CRF encoding, begin with single-pass quality control; use two-pass when there is a defined bitrate budget or target size. [6][7]
- **Use chunked parallel encoding selectively.** Av1an can encode chunks in parallel and supports target quality, but chunking has method-specific costs; its documentation reports that one method can take up to 30% longer than segment encoding on a 30-minute 30 fps video. Since throughput is not critical here, first measure whether a single SVT encode uses the available CPU well. [8][23][24]
- **Skip likely low-value re-encodes.** Test a short representative sample before committing to a source already encoded efficiently as HEVC or AV1, or to a heavily compressed Zoom recording. Use projected savings and visual quality together; a codec or source bitrate threshold alone cannot predict whether a re-encode will be worthwhile.
- **Carry metadata and timing through verification.** The project has already observed lost `creation_time`, file modification time, rotation, and VFR-alignment problems. Make those explicit checks in the encode pipeline and benchmark so a smaller file is not accepted with altered playback orientation, timing, or library dates.

**Confidence:** Medium for the described tools and rate-control behavior; recommendations about search strategy, skip thresholds, and selective processing need project-specific measurements.

### Perspectives

- **The case for AV1:** Meta’s 2025 analysis shows meaningful bitrate savings against x265 in its energy-normalized streaming comparison. Recent mainline SVT releases have also absorbed several psychovisual and screen-content features from community work. [2][4]
- **The case for staying with HEVC:** MSU’s 2025 comparison found that winners vary by metric, and it did not use the newest encoder versions or your Ryzen CPU. Your project also has an already-tested HEVC playback path on iOS 18. These points favor keeping HEVC as a reliable option while measuring AV1’s actual savings. [1]
- **The case for VVC:** VVenC offers five speed/quality presets, XPSNR-based perceptual optimization, and parallel encoding. Android 17 now has VVC media-framework support, but decoding still depends on a device vendor decoder, so VVC is a benchmark candidate rather than a practical default for this target set. [13][14]
- **The grain tradeoff:** Streaming services can save bits by synthesizing grain, while archival fidelity favors preserving the captured noise and texture. The right choice depends on whether the priority is a visually convincing smaller copy or retaining the original sensor noise; the originals should remain the reference. [18][19]

### Practical Implications

For the first benchmark matrix, pin x265 4.3 and SVT-AV1 4.2.0, then add current SVT-AV1-HDR as an experimental challenger. Use x265 `slow` and SVT presets 2–4; output 10-bit as a tested variant; retain source timing; and sweep the category-specific pilot CRFs above. Include libaom 3.15 on webinar clips and VVenC 1.14.0 on a small subset if you want a compression-efficiency reference. [3][4][5][10][11][14]

For each category, use public representative footage and measure output size, encode time, decode/playback behavior, visual metrics, and full-resolution motion crops. Test each candidate in the actual gallery apps and phone models. Only promote a preset after it meets both the visual-quality target and a worthwhile size reduction.

### Sources

1. [MSU Video Codecs Comparison 2025, FullHD Objective/Subjective](https://www.compression.ru/video/codec_comparison/2025/main_report.html) — Primary independent benchmark; 50 sequences, encoder versions, methodology, and metric-dependent rankings.
2. [Meta, AV1 Decoding in the Mobile Ecosystem](https://engineering.fb.com/wp-content/uploads/2025/09/Meta-AV1-White-Paper-FINAL.pdf) — Vendor white paper on AV1 compression comparisons and mobile hardware/software decode.
3. [x265 4.3 Release Notes](https://x265.readthedocs.io/en/master/releasenotes.html) — Primary current x265 release details.
4. [SVT-AV1 Changelog](https://github.com/AOMediaCodec/SVT-AV1/blob/main/CHANGELOG.md) — Primary release history and features incorporated from SVT-AV1-PSY.
5. [AOMedia, libaom 3.15](https://aomedia.org/blog%20posts/Libaom-v3_15-is-now-available/) — Primary release announcement, including screen-content and performance updates.
6. [x265 Command-Line Options](https://x265.readthedocs.io/en/master/cli.html) — Primary documentation for CRF, AQ, psychovisual tuning, keyframes, and SCC.
7. [SVT-AV1 Parameters](https://github.com/AOMediaCodec/SVT-AV1/blob/main/Docs/Parameters.md) — Primary parameter ranges and defaults.
8. [SVT-AV1 Common Questions](https://github.com/AOMediaCodec/SVT-AV1/blob/main/Docs/CommonQuestions.md) — Primary notes on 10-bit encoding, threading, and grain.
9. [SVT-AV1-PSY repository](https://github.com/psy-ex/svt-av1-psy) — Primary archive notice and project continuation statement.
10. [SVT-AV1-HDR releases](https://github.com/juliobbv-p/svt-av1-hdr/releases) — Primary current release history.
11. [SVT-AV1-HDR README](https://github.com/gavinljj/svt-av1-hdr) — Fork documentation for its tunes, defaults, and release approach.
12. [SVT-AV1-Essential releases](https://github.com/nekotrix/SVT-AV1-Essential/releases) — Primary release history for the active Essential fork.
13. [Android VVC support](https://source.android.com/docs/core/media/vvc) — Primary documentation of Android 17 VVC framework and decoder requirements.
14. [Fraunhofer VVenC](https://github.com/fraunhoferhhi/vvenc) — Primary encoder documentation; see also its [release history](https://github.com/fraunhoferhhi/vvenc/releases).
15. [Netflix, “VMAF v1: Good Is Not Good Enough”](https://netflixtechblog.com/vmaf-v1-good-is-not-good-enough-60d7e4244ea8) — Primary description of VMAF v1 improvements and known gaps.
16. [Netflix VMAF with FFmpeg](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) — Primary instructions on PTS alignment and filter synchronization.
17. [AOMedia `aomenc` options](https://aomedia.googlesource.com/aom/%2B/edffc654fe8a1b44523136a8653edd6d85df2f69/apps/aomenc.c) — Primary screen-content, palette, and IntraBC option definitions.
18. [ITU-T H Supplement 21 (2025), Film Grain Synthesis](https://www.itu.int/epublications/publication/itu-t-h-suppl-21-2025-01-film-grain-synthesis-technology-for-video-applications) — Primary technical supplement on grain analysis and denoising risks.
19. [Netflix, AV1 Film Grain Synthesis deployment](https://medium.com/netflix-techblog/av1-now-powering-30-of-netflix-streaming-02f592242d80) — Primary streaming case study and bitrate example.
20. [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) — Primary filter reference, including denoising filters.
21. [FFmpeg Codecs Documentation](https://ffmpeg.org/ffmpeg-codecs.html) — Primary audio encoder options for Opus and AAC.
22. [RFC 6716, Opus](https://datatracker.ietf.org/doc/rfc6716/) — Primary codec specification and bitrate guidance.
23. [Av1an Target Quality](https://rust-av.github.io/Av1an/Features/TargetQuality) — Project documentation for chunk-level quality targeting.
24. [Av1an Chunk Method](https://github.com/rust-av/Av1an/wiki/Chunk-Method) — Project documentation on chunking methods and runtime tradeoffs.
25. [ab-av1 README](https://docs.rs/crate/ab-av1/latest/source/README.md) — Tool documentation for CRF search using VMAF targets.
26. [x265 preset documentation](https://github.com/videolan/x265/blob/master/doc/reST/presets.rst) — Primary preset and grain-tune notes.

### Gaps

- I found no independent public comparison of the current x265 4.3, SVT-AV1 4.2, and libaom 3.15 on near-transparent personal footage using the Ryzen 9 7950X3D. The benchmark should settle that locally.
- “Transparent” needs a project acceptance criterion. Measure quality and size across motion-heavy, detail-heavy, dark, and screen-content clips, then verify the result with visual comparisons.
- AV1 playback still depends on the exact phone, OS, container, and gallery app. Test the actual target devices, including 10-bit outputs.
- The size impact of frame-rate reduction, screen-content tools, denoising, and downscaling is unknown for the project’s content. Benchmark each as a separate change.
- Opus and AAC transparency for speech and dance audio needs listening tests at the proposed rates; codec specifications alone cannot establish an acceptable threshold.
- VFR alignment, rotation, full-range color handling, `creation_time`, file modification time, and output integrity should remain explicit verification measurements in the CLI.
