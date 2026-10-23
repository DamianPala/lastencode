# T2 merged: encoders, parameters per category, ways to do better

Merge date: 2026-10-20. Inputs: report A (`self/t2-encoders.md`, Claude agent), report B (`codex/t2-encoders.md`, Codex), history notes. Verification in this pass: WebFetch of primary sources, a download of libaom source code, and a download of the Android 14/15/16 CDDs. Owner decisions from `_merge-brief.md` are applied; recommendations they make moot (gallery-app playback, location scrubbing) are dropped.

Number format: comma decimals in prose, dot decimals inside encoder parameters.

## 1. Bottom line

- **x265 (now 4.3) stays the default for the camera categories (walkthroughs, dance, holiday).** Neither report found a current independent test showing AV1 ahead at near-transparent quality. The older high-bitrate evidence and the owner's own A/B point to a tie on metrics and x265 preferred by eye [both] [11][17][19].
- **SVT-AV1 mainline 4.2 is the only AV1 encoder worth benchmarking.** The PSY features landed in mainline but are **off by default** (tune 1 = PSNR, varboost off, ac-bias 0, QM off), so every AV1 arm must turn them on explicitly. PSY is archived. SVT-AV1-HDR is alive but is an optional experimental arm, not a dependency [verified] [1][2][5][8].
- **Drop VVC.** Drop libaom too, except as an optional screen-content arm. VVC has no Apple support, needs Android 17 plus a vendor decoder, and failed in Haruna [both] [21].
- **Fix the prototype dance preset.** CRF 30 with `deblock=-1:-1` weakens deblocking at a bitrate where blocking is the risk [verified, x265 docs] [12]. Benchmark CRF 18-26 at `slower`/`veryslow`, with deblock 0:0 as the baseline. Opus for dance music goes from 64 to 96-128 kb/s [both] [32].
- **Always set the keyframe interval explicitly (`-g`).** libaom's default is 9999 frames when ffmpeg `-g` is unset, which explains the slow Haruna seeks [verified, source code] [23][25]. Start at ~2 s for camera content and 5-10 s for static content, and record the size cost in the benchmark.
- **8-bit vs 10-bit:** use 10-bit (HEVC Main10) as the default for x265 presets, gated by a one-time playback check on the real devices. Keep an 8-bit Main switch. The evidence that 2-year-old phones decode Main10 is strong (iPhones record 10-bit HEVC themselves). The Windows risk is about HEVC in general, not about bit depth (section 2b).
- **The biggest remaining gains are not about encoder choice.** They come from a CRF sweep per category scored with SSIMULACRA2/XPSNR plus a blind visual A/B, skip/abort rules for already-efficient sources (Zoom), frame-rate tests for webinars, and 2-4 encodes running in parallel to fill 32 threads [both] [35][36].

## 2. Findings

### Q1. Encoder choice

- **Versions (Oct 2026)**: x265 **4.3 (31 Jul 2026)** [conflict: A said 4.2, B said 4.3; verified 4.3] [11]. SVT-AV1 **4.2.0 (2026-07-14)**, after 4.0.0 (2026-01-13), 4.0.1 (2026-01-27) and 4.1 (2026-03-23) [both, verified] [1]. libaom **3.15 (26 Sep 2026)**, which speeds up IntraBC [B only, verified] [26]. VVenC 1.14.0 [B only].
- **PSY features in mainline** [verified, changelog + Parameters.md] [1][2]:
  - 3.0.0: "several features from SVT-AV1-PSY" ported into `tune 0`.
  - 2.1.0: variance boost first added; 3.1.0: more varboost porting and chroma QM flags.
  - 4.0.0: AC bias, the IQ tune, `--scm 3`, togglable adaptive film grain, dynamic delta-q.
  - 4.2.0: tune VMAF (claims ~15% VMAF BD-rate).
  - `--sharpness` (−7..7, default 0) and `--tf-strength` (0-4, default 3) exist in the 4.2 parameter docs. The changelog does not name the release that added them.
  - Mainline defaults: `--tune 1`, `--enable-variance-boost 0`, `--ac-bias 0.0`, `--enable-qm 0`, `--qm-min 8`, `--scm 2`, `--film-grain 0`, `--keyint -2` (~5 s).
  - Per the PSY authors, these did **not** land: Tune 3 (SSIM-subjective), noise normalization and tx-bias [A only] [6].
- **Forks** [verified] [5][8][9]:
  - SVT-AV1-PSY: end announced 2025-04-20, repository archived **2026-02-12**. Its README names SVT-AV1-HDR "the official recommended continuation". PSYEX is "on the backburner".
  - SVT-AV1-HDR (`juliobbv-p`) is active, with automated PGO builds up to 2026-10-03, and keeps fork-only tools (tune 6 for grain, `--noise-norm-strength`, `--tx-bias`) [7]. It ships no official ffmpeg build. Report B linked `github.com/gavinljj/svt-av1-hdr`, which is a 0-star personal fork; use `juliobbv-p` [verified].
  - SVT-AV1-Essential is alive but lags. Its last release is v4.0.1-Essential (14 Mar 2026), based on mainline 4.0.1. Not worth an arm.
- **AV1 vs HEVC at high quality**:
  - No current independent test of x265 4.x vs SVT-AV1 4.x at transparent quality exists [both].
  - MSU 2025 tested older versions (x265 4.1, SVT-AV1 3.0.1, libaom 3.12, VVenC 1.13.1), and "the winners vary for different objective quality metrics" [B only, verified] [19].
  - Chips and Cheese (2023, stale) found HEVC ahead above VMAF 94 [A only] [17].
  - The SVT-AV1-HDR author concedes that x265 led above ~10 Mb/s before the fork [A only, author claim] [10].
  - An SVT-AV1 issue report (old 0.9) saw x265 keep more detail in motion scenes [A only] [18].
  - Meta's ~30% AV1 saving is a streaming result at equal energy [B only] [20].
  - AV1 hardware decode on iPhone starts with the A17 Pro (iPhone 15 Pro); the plain iPhone 15 would decode in software, if at all [both] [20][44]. This gates any AV1 preset behind the device check.
  - Synthesis: the AV1 advantage is real at streaming bitrates and shrinks or reverses at archive quality on motion and texture.
- **Why the owner's AV1 test looked softer** [A only, mechanism well-sourced]: libaom cpu-used 6, like SVT-AV1 at defaults, is tuned toward PSNR, while x265 has psy-rd 2.0 and psy-rdoq 1.0 on at `slow`+ [verified, x265 docs] [12][6]. A result of higher SSIM/PSNR with a softer look is the expected signature. SSIMULACRA2 penalizes smoothing [41], and VMAF can be gamed by sharpening [40].
- **Speed and threads**:
  - SVT-AV1 presets 2-4 are the efficiency sweet spot. P4 costs ~22% BD-rate vs P−1 [A only, codecs.wiki] [14].
  - One x265 1080p encode does not fill 32 threads [A only, forum + docs] [30]. Run several files in parallel.
  - libaom needs `-row-mt 1` plus tiles to use the cores [A only].

### Q2. Parameters per category

- **x265 deblock** [verified, x265 CLI docs] [12]: offsets range "−6 (lowest strength) to 6 (highest strength)", with a default of 0:0. **Negative = weaker deblocking.** The handoff notes already flag the dance `deblock=-1:-1` as adopted on a wrong premise. A recommends 0:0 at CRF ≥24 and −1:−1 only at CRF ≤22 [31][16]. B says keep a default-deblock arm and treat the setting as a variable. Merge: baseline 0:0, test −1:−1 only in the low-CRF arm.
- **aq-mode** [verified] [12]: default 2. Mode 3 is "recommended for 8-bit encodes or low-bitrate 10-bit encodes, to prevent color banding/blocking". It biases bits toward dark areas and is not an edge fix [both + handoff]. With 10-bit output, compare modes 1/2/3 **at equal size**.
- **psy-rd 2.0 / psy-rdoq 1.0 at slow+** are fine. High values are mostly copied from guides [both] [12][42].
- **`--tune grain`** sets aq 0, cutree off, no SAO, psy-rd 4, psy-rdoq 10. It is meant for film grain, not general phone footage [both] [13].
- **SAO**: keep it. Test `limit-sao` or `selective-sao` for dance [A only] [16]. Leave `no-sao` out of the defaults [both].
- **Preset** [conflict]: A wants `slower`/`veryslow`, citing rd 6, AMP and the owner's hair test (veryslow +4,4% size, visibly fewer edge artifacts) [13]. B wants `slow`, adding slower presets only if size justifies it. Merge: the owner chose quality over time, so `slower` is the baseline and `veryslow` gets tested for dance.
- **CRF brackets** [conflict on numbers, agreement that they are only pilots]: A gives x265 20-26 (dance 20-24); B gives 16-24 (dance 16-22). codecs.wiki tiers put "transparent" at 14/16/18 and "high" at 18/22/24 for 720p/1080p/4K [16]. The owner's CRF 26 at 1080p60 reached VMAF 96,5. Merge: sweep x265 CRF 18-26 in steps of 2. For SVT-AV1, calibrate CRF to the same SSIMULACRA2 targets instead of a fixed offset.
- **SVT-AV1 psy baseline for any AV1 arm** [A only; parameters verified in docs] [2][6][46]: `tune=0:enable-variance-boost=1:ac-bias=1.0:tf-strength=1:sharpness=1:enable-qm=1:qm-min=2`. B suggests tune 0 plus varboost and leaving `enable-overlays` at its default (0) [both on tune 0].
- **10-bit from 8-bit sources**: x265 gains "not much if at all" but is "never worse" [A only, forum] [29]. SVT-AV1 gives "slightly better fidelity" at ~5% size [both] [3]. It is anti-banding insurance, not a size win. See 2b.
- **Prototype review**:
  - `-preset slow -crf 28` is below "high" quality at 1080p [A] [16].
  - `aq-mode=3:aq-strength=1.1` is defensible for 8-bit output [both] [12].
  - `deblock=-1:-1` at CRF 30: drop it (see above).
  - Dance at 720p: kept per the owner's decision. The scaler filter (bicubic vs lanczos/spline) is untested and belongs in the benchmark [A only].
- **Resolution for other categories**: the owner keeps native resolution. Google's "≤1080p is close to the original" argument [A] applied to gallery apps and phones. With Haruna and Windows desktops as targets, 4K→1080p is not free, so keep native unless the benchmark shows otherwise.

### 2b. 8-bit vs 10-bit (resolution of the open question)

The prototype forced `yuv420p` (8-bit, HEVC Main, level 4.1) because Codex called it "Apple-safe" in January. That was a web-doc claim, not a test, and Codex had itself proposed 10-bit [history]. The evidence per target:

| Target | Main10 evidence | Status |
|---|---|---|
| iPhone (~2 years old: iPhone 15/16) | Apple's own camera records **10-bit HEVC** (Dolby Vision Profile 8.4, HLG-compatible) since the iPhone 12 / A14, so the decoder handles Main10 [27]. Apple's support page limits older devices only by resolution and fps: "1080p or lower and 60 fps or lower are more broadly compatible" [verified] [47]. | strong, indirect; confirm with one file |
| Android (~2 years old, Android 14+) | The CDD mandates HEVC only at **Main profile**, not Main10 [verified, CDD 5.3.5] [22]. Main10 is mandated only for Media Performance Class devices (10-bit HDR decode sessions). In practice, phones that record HDR10/10-bit HEVC decode it, but this varies by SoC and app [unverified]. Side finding: since Android 14, handheld devices **MUST decode AV1**, and AV1 support "MUST support Main Profile including 8-bit and 10-bit content" [verified, CDD 14/16 §2.2.2, §5.3.9] [22]. | medium; test on the actual phones |
| Haruna (libmpv/FFmpeg) | FFmpeg's HEVC decoder handles Main10 in software; VA-API hardware decode works on GPUs with Main10 blocks [not checked this pass; well established] | low risk |
| Windows PCs (other people) | HEVC needs the Microsoft HEVC Video Extensions, whose Store availability and pricing are inconsistent across sources [unverified] [45]. Hardware Main10 decode exists on Intel Kaby Lake (7th gen)+ (Skylake was only hybrid) [verified] [28], and on NVIDIA Pascal / AMD Polaris and later [unverified]. VLC or mpv play both bit depths in software. | the risk is HEVC itself, not Main10 |

**Recommendation**:
- Make 10-bit (`-pix_fmt yuv420p10le`, x265 `profile=main10`) the default for x265 presets once a one-time device check passes: one test file played on each phone model in use, Haruna, and one Windows PC with the built-in player.
- Keep an `--8bit` compatibility switch (Main, `yuv420p`). The 8-bit/10-bit difference in size is a few percent at most, so the choice costs little either way.
- Keep the source colour range: 10-bit full range is `yuv420p10le` + `color_range=pc`, since there is no `yuvj` 10-bit format (see T5 on range tagging).
- Level: 4.1 covers 1080p60; 4K60 needs 5.1. Do not hard-code 4.1.
- If Windows recipients cannot be reached or told to use VLC, that argues for H.264 copies for sharing, not for 8-bit HEVC.

### Q3. Screen content (webinars)

- SVT-AV1 `--scm`: 0 off, 1 forced, 2 auto (default), 3 auto with anti-alias awareness (from PSY, in 4.0) [both, verified] [1][2]. Intra block copy works only on key/intra frames and disables in-loop filtering for that frame [A only] [4], so it helps slide changes and keyframes, not the many unchanged inter frames.
- x265 `--scc` requires a custom `ENABLE_SCC_EXT` build and is CLI-only, so it is not usable through ffmpeg [both] [12].
- libaom `--tune-content=screen` and 3.15's faster IntraBC [B, verified release] [26]. It is an optional arm only, given libaom's speed and keyframe defaults.
- Frame-rate reduction (owner: 30→24/25 or dynamic decimation, benchmarked): `mpdecimate` output must stay VFR or ffmpeg re-inserts duplicates. The default thresholds can drop real changes [A only] [38]. Encoders already spend almost nothing on static inter blocks, so expect much less than "half the fps = half the size" [both]. Neither report found a measured saving for slide-plus-face content.

### Q4. Noise and grain

- Both reports: no pre-denoise and no film-grain synthesis by default. FGS replaces sensor noise with a statistical lookalike over a denoised base [33][43]. Sensor noise differs from film grain [33]. VMAF/PSNR/SSIM cannot score FGS [34]. SVT-AV1 `--film-grain-denoise` defaults to 0 [verified] [2].
- Test only on a low-light subset, judged visually: hqdn3d (light), nlmeans, and AV1 `film-grain` 4-8 with denoise 0. This is reversible only while originals exist [both].

### Q5. Audio (owner decided: Opus default, AAC fallback)

- Opus bitrates: speech 32-48 kb/s; music 96-128 kb/s stereo ("128 kb/s VBR is pretty much transparent") [both] [32]. The prototype's 64 kb/s for dance is below Xiph's storage range [A].
- Mono vs stereo [minor conflict]: A says keep stereo at 48 kb/s for speech; B says mono when the source is genuinely mono. Merge: keep the source channel layout, which is both reports' point. Make no loudness change [both].
- AAC fallback: ffmpeg native `aac` at 128-192 kb/s for music [both]. A reported rewritten native AAC encoder ("ffmpeg 9.1") is single-source [A only, unverified].

### Q6. Other improvements

- **Target-quality search**: ab-av1 (`crf-search`, VMAF/XPSNR, `--max-encoded-percent`, works with libx265) and Av1an (target quality, chunking) [both] [35][36]. This collides with "one preset per category" (open question 2).
- **Parallelism**: run 2-4 files concurrently before trying Av1an chunking. Av1an's handling of VFR and the display matrix is undocumented, and one chunk method costs up to 30% more time [A + B] [36][37].
- **Two-pass**: only for size targets. CRF is right for an archive [both].
- **Skip rules**: HEVC-to-HEVC transcoding costs over 20% bitrate efficiency for a small quality loss [A] [39]. Rules: skip or remux already-efficient HEVC/AV1 sources (by bits per pixel), and abort when the output exceeds ~80-90% of the source [A]. B prefers a sample-encode prediction over fixed thresholds. Merge: use the sample encode, with thresholds as a cheap pre-filter.
- **Keyframes / seeking** [conflict]: A says set `-g` ~2 s; B says keep the defaults unless seekability justifies a change.
  - Verified: ffmpeg's `libaomenc` defaults `g` to −1 and then leaves `kf_max_dist` unset [25]. libaom's GOOD_QUALITY default is `kf_min_dist 0`, `kf_max_dist 9999`, `kf_mode AOM_KF_AUTO` [23].
  - So keyframes occur only at detected scene cuts, up to 9999 frames apart (~2:47 at 60 fps). That is the likely cause of the slow Haruna seeks.
  - A's citation for this [24] is a 2012 **VP8** commit, so the conclusion is right but the source was wrong.
  - SVT-AV1 defaults to ~5 s [verified] [2]; x265 to 250 frames (4,2 s at 60 fps) [verified] [12].
  - Merge: set `-g` explicitly for every encoder, and benchmark 2 s vs 5 s for size.

## 3. Verification log

| # | Claim | Result | Source |
|---|---|---|---|
| 1 | Latest x265 (A: 4.2, B: 4.3) | **4.3, 31 Jul 2026**; 4.2 19 Apr 2026; 4.1 22 Nov 2024 | [11] fetched |
| 2 | SVT-AV1 mainline version | **4.2.0, 2026-07-14**; 4.1 2026-03-23; 4.0.0 2026-01-13 | [1] fetched |
| 3 | PSY features in mainline | Changelog: tune 0 ports (3.0), varboost (2.1, 3.1), chroma QM (3.1), AC bias / IQ tune / scm 3 / adaptive FG / dynamic dq (4.0). Parameters.md 4.2: sharpness, tf-strength, varboost, ac-bias present, all off/neutral by default; tune default 1 | [1][2] fetched |
| 4 | PSY archived Feb 2026 | **Archived 2026-02-12**; end announced 2025-04-20; HDR = "official recommended continuation" | [5] fetched |
| 5 | SVT-AV1-HDR alive | Yes, releases up to 03 Oct 2026; B's URL is a 0-star fork | [8], gavinljj repo fetched |
| 6 | SVT-AV1-Essential status | Last release v4.0.1-Essential, 14 Mar (2026, base 4.0.1) | [9] fetched |
| 7 | x265 deblock sign | "−6 (lowest strength) to 6 (highest strength)", default 0:0 | [12] fetched |
| 8 | x265 aq-mode 3 for 8-bit; psy defaults; keyint 250 | Confirmed verbatim | [12] fetched |
| 9 | libaom default keyframe interval without `-g` | ffmpeg `g`=−1 → `kf_max_dist` not set → libaom default **9999** (good-quality and realtime), auto keyframes at scene cuts | [23] source downloaded, [25] fetched |
| 10 | A's libaom citation | The commit is VP8 (`vp8_cx_iface.c`, 2012), not AV1 | [24] fetched |
| 11 | MSU 2025 versions, metric-dependent winners | Confirmed (x265 4.1, SVT 3.0.1, aom 3.12, VVenC 1.13.1) | [19] fetched |
| 12 | libaom 3.15 | Released 26 Sep 2026; faster IntraBC | [26] fetched |
| 13 | Android HEVC Main10 mandated? | No: CDD mandates HEVC Main profile; AV1 decode is MUST since Android 14 with 8- and 10-bit | [22] CDD 14/15/16 downloaded |
| 14 | iPhone 10-bit HEVC | Apple dev doc: Dolby Vision recording is 10-bit HEVC (iPhone 12+); Apple support: 1080p60 broadly compatible | [27] search result, [47] fetched |
| 15 | Intel Main10 hardware decode | Kaby Lake full; Skylake hybrid | [28] fetched |
| 16 | Windows HEVC extension availability and Main10 path | Not resolved: sources conflict; no Microsoft primary doc fetched | [45] [unverified] |

Not re-verified (taken from one report, marked in the text): codecs.wiki preset/tune sweeps [14][15], the VDD slide list of unmerged features [6], the x265 thread-scaling forum reports [30], Meta's 30% figure [20], the new ffmpeg AAC encoder.

## 4. Benchmark candidates

1. **x265 4.3 arm** (categories 1, 2, 6; also 3): presets `slower`, plus `veryslow` for dance; CRF {18, 20, 22, 24, 26}; deblock {0:0; −1:−1 only at CRF ≤22}; aq-mode {1, 2, 3} compared at equal size; SAO {default, `limit-sao`}; `yuv420p10le` + `profile=main10` vs `yuv420p` Main; `-g` = 2×fps.
2. **SVT-AV1 4.2 arm** (all categories; primary candidate for 3, 4, 5): preset {2, 4}; CRF calibrated to the x265 arm's SSIMULACRA2 targets; {stock tune 1, psy set from Q2}; plus a one-knob-at-a-time ablation on the sofa/window and hair clips; 10-bit; `-g` = 2×fps.
3. **Optional SVT-AV1-HDR arm** (categories 2 and 6): fork defaults and tune 6. Use a community ffmpeg build or a pipe from `SvtAv1EncApp`. Not a tool dependency.
4. **Screen arm (category 4)**: SVT-AV1 `scm` {0, 2, 3}; fps {source, 24/25 CFR, mpdecimate VFR with tuned thresholds}; optionally libaom 3.15 `tune-content=screen` with `-row-mt 1` and tiles; x265 at the same fps variants.
5. **Zoom arm (category 5)**: remux-only vs downscale to the real content resolution vs SVT-AV1 P4 at high CRF; abort if output > 85% of source.
6. **Grain arm (low-light subset, visual only)**: none / hqdn3d light / nlmeans / AV1 `film-grain` {4, 8} with `film-grain-denoise=0`.
7. **Dance downscale**: 720p with `bicubic` vs `lanczos` vs `spline` scalers.
8. **Keyframes**: `-g` 2 s vs 5 s; record size delta and seek latency in Haruna (and on phones).
9. **Audio**: Opus 48 / 96 / 128 kb/s on dance music (owner's blind ABX); Opus 32 / 48 kb/s on speech, keeping source channels; AAC native 128 / 160 / 192 kb/s as fallback reference.
10. **Metrics per encode**: SSIMULACRA2 (mean + 10th percentile), XPSNR, VMAF-NEG (sanity only), size, wall time, CPU utilisation, keyframe spacing (ffprobe); timestamp-aligned (see T4). The deciding vote is a blind visual A/B on fixed crops (fabric, hair, window edges, slide text).
11. **Runner**: 1 vs 2 vs 3 concurrent x265 `slower` encodes and 1 vs 2 SVT-AV1 P4 encodes on the 7950X3D; also x265 `--threaded-me` (4.2+) on Zen 4.
12. **Device check (gate for 10-bit and any AV1 preset)**: one 1080p60 and one 4K30 file each in HEVC Main, HEVC Main10 and AV1 10-bit (MP4 + Opus) on every phone model in use, Haruna, and one Windows PC with the default player.

## 5. Open questions for the owner

1. **Windows viewers**: can they be told to use VLC/mpv, or must files play in the built-in Windows player? This decides whether HEVC at all, not just Main10, is acceptable for them.
2. **Fixed CRF per category vs per-file quality search** (ab-av1 style) inside each category preset: the search gives more uniform quality but costs several sample encodes per file.
3. **Mixed codecs in the archive**: if AV1 wins for webinars/Zoom/session recordings and the device check passes, is an archive with HEVC for camera footage and AV1 for talking heads acceptable?
4. **Keyframe interval**: accept a few percent of size for ~2 s seek granularity on camera content?
5. **Grain synthesis**: allowed at all for files whose originals may later be deleted, or excluded on principle?

## 6. Sources

1. [SVT-AV1 CHANGELOG](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/CHANGELOG.md) - primary
2. [SVT-AV1 Parameters.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Parameters.md) - primary
3. [SVT-AV1 CommonQuestions.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/CommonQuestions.md) - primary
4. [SVT-AV1 Appendix: Intra Block Copy](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Appendix-Intra-Block-Copy.md) - primary
5. [psy-ex/svt-av1-psy README](https://github.com/psy-ex/svt-av1-psy) - primary
6. [Barba & Rosato, SVT-AV1-PSY VDD 2025 slides](https://giannirosato.com/files/svt-av1-psy_vdd_2025.pdf) - primary
7. [juliobbv-p/svt-av1-hdr README](https://github.com/juliobbv-p/svt-av1-hdr) - primary
8. [svt-av1-hdr releases](https://github.com/juliobbv-p/svt-av1-hdr/releases) - primary
9. [SVT-AV1-Essential releases](https://github.com/nekotrix/SVT-AV1-Essential/releases) - primary
10. [r/AV1 "Introducing SVT-AV1-HDR" (mirror)](https://reddit.birdcat.cafe/r/AV1/comments/1kjhpv3/introducing_svtav1hdr) - author claim
11. [x265 release notes](https://x265.readthedocs.io/en/master/releasenotes.html) - primary
12. [x265 CLI documentation](https://x265.readthedocs.io/en/master/cli.html) - primary
13. [x265 presets and tunes](https://x265.readthedocs.io/en/master/presets.html) - primary
14. [codecs.wiki: SVT-AV1 deep dive part 1](https://codecs.wiki/blog/svt-av1-fourth-deep-dive-p1) - independent benchmark
15. [codecs.wiki: SVT-AV1 deep dive part 2](https://codecs.wiki/blog/svt-av1-fourth-deep-dive-p2) - independent benchmark
16. [codecs.wiki: x265](https://codecs.wiki/docs/encoders/x265) - secondary
17. [Chips and Cheese: Codecs for the 4K era (2023)](https://chipsandcheese.com/p/codecs-for-the-4k-era-hevc-av1-vvc-and-beyond) - secondary, stale
18. [SVT-AV1 issue #1810](https://gitlab.com/AOMediaCodec/SVT-AV1/-/issues/1810) - primary report, old version
19. [MSU Video Codecs Comparison 2025](https://www.compression.ru/video/codec_comparison/2025/main_report.html) - independent benchmark
20. [Meta: AV1 decoding in the mobile ecosystem (2025)](https://engineering.fb.com/wp-content/uploads/2025/09/Meta-AV1-White-Paper-FINAL.pdf) - vendor white paper
21. [AOSP: VVC support](https://source.android.com/docs/core/media/vvc) - primary
22. [Android 16 CDD](https://source.android.com/docs/compatibility/16/android-16-cdd) and [Android 14 CDD](https://source.android.com/docs/compatibility/14/android-14-cdd) - primary
23. [libaom av1/av1_cx_iface.c](https://aomedia.googlesource.com/aom/+/refs/heads/main/av1/av1_cx_iface.c) - primary source code
24. [libvpx/aom commit "Reduce the default kf_max_dist to 128" (VP8, 2012)](https://aomedia.googlesource.com/aom/+/2a0d7b1a55aff0870f6bda485cf7cb63662c2337) - primary, not about AV1
25. [FFmpeg libavcodec/libaomenc.c](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/libaomenc.c) - primary source code
26. [AOMedia: libaom v3.15](https://aomedia.org/blog%20posts/Libaom-v3_15-is-now-available/) - primary
27. [Apple: Incorporating HDR video with Dolby Vision into your apps](https://developer.Apple.com/av-foundation/Incorporating-HDR-video-with-Dolby-Vision-into-your-apps.pdf) - primary (via search result)
28. [Wikipedia: Intel Quick Sync Video](https://en.wikipedia.org/wiki/Intel_Quick_Sync_Video) - secondary
29. [Doom9: 10-bit x265 from 8-bit sources](https://forum.doom9.org/archive/index.php/t-183044.html) - forum
30. [Doom9: high core count for x265](https://forum.doom9.org/archive/index.php/t-177622.html?pda=1) and [x265 threading docs](https://x265.readthedocs.io/en/4.1/threading.html) - forum + primary
31. [VideoHelp: deblock values explained](https://forum.videohelp.com/showthread.php?p=2349198) - forum
32. [Xiph: Opus recommended settings](https://wiki.xiph.org/Opus_Recommended_Settings) - primary
33. [Norkin & Birkbeck: AV1 film grain synthesis (DCC 2018)](https://norkin.org/pdf/DCC_2018_AV1_film_grain.pdf) - primary research
34. [Streaming Media: measuring perceived quality](https://streamingmedia.com/Articles/Post/Blog/Challenges-of-New-Encoding-Scenarios-Reflections-on-Measuring-Perceived-Quality-166721.aspx) - secondary
35. [ab-av1](https://github.com/alexheretic/ab-av1) - primary
36. [Av1an](https://github.com/rust-av/Av1an) and [Av1an target quality](https://rust-av.github.io/Av1an/Features/TargetQuality) - primary
37. [Av1an chunk method](https://github.com/rust-av/Av1an/wiki/Chunk-Method) - primary
38. [VideoHelp: mpdecimate and VFR output](https://forum.videohelp.com/showthread.php?p=2784026) - forum
39. [arXiv 1702.07548: HEVC transcoding losses](https://arxiv.org/pdf/1702.07548) - primary research
40. [arXiv 2107.04510: Hacking VMAF and VMAF NEG](https://arxiv.org/pdf/2107.04510) - primary research
41. [SSIMULACRA2 description (AviSynthPlus port)](https://github.com/Asd-g/AviSynthPlus-ssimulacra) - secondary
42. [Doom9: psy settings for grain (2025)](https://forum.doom9.org/archive/index.php/t-186396.html) - forum
43. [ITU-T H Suppl. 21 (2025): film grain synthesis](https://www.itu.int/epublications/publication/itu-t-h-suppl-21-2025-01-film-grain-synthesis-technology-for-video-applications) - primary
44. [Bitmovin: Apple AV1 support](https://bitmovin.com/blog/apple-av1-support) - secondary
45. [Microsoft Q&A: HEVC Video Extensions availability](https://learn.microsoft.com/en-us/answers/a/1180572) - community answer, unverified
46. [SVT-AV1 MR !2513: AC bias](https://gitlab.com/AOMediaCodec/SVT-AV1/-/merge_requests/2513) - primary
47. [Apple Support: HEIF/HEVC media on Apple devices](https://support.apple.com/en-us/116944) - primary
