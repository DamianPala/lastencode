# T2: encoders, parameters per content category, and ways to do better

Research date: 2026-10-20. Method: live web search and fetches (no research skill, no sub-agents). The session's web-search budget ran out near the end, so a few follow-ups (dav1d tile decoding, HEVC Main10 on phones, Opus-in-MP4 on Android/Google Photos) stayed unresearched; they are listed under Gaps.

Number format: comma decimals in prose (European), dot decimals inside encoder parameters.

## TL;DR

For camera footage at "transparent-ish" quality, no independent 2025-2026 benchmark shows AV1 clearly beating a well-tuned x265; the older evidence and your own A/B test point to a tie on metrics, with x265 often preferred by eye. So x265 (`slower`/`veryslow`, 10-bit, CRF in the low-to-mid 20s) should stay the default for the camera categories [16][20][12][23].
AV1 (mainline SVT-AV1 4.x, with the PSY-derived options turned on, since its defaults tune for PSNR) earns its place for the low-bitrate categories (webinars, Zoom, talking heads), and only if the AV1 playback check passes on the target phones [1][2][8][26].
The biggest wins left are mostly not encoder choice. They are: per-file quality targeting with a metric that punishes smoothing (SSIMULACRA2/XPSNR, plus visual A/B), Opus bitrate fixed for music, a short GOP for seekability, skip rules for already-efficient sources, and running several files in parallel to use 32 threads [49][50][58][59][28].

## Key Findings

### 1. Quality-first encoder choice (x265 vs SVT-AV1 vs forks vs libaom vs VVC)

**State of the encoders (October 2026)**

- **What**: Based on [13], x265's current release is **4.2 (19 April 2026)**. It adds experimental `--threaded-me` (up to 1,5x faster at 1080p, but slower on high-clock systems and at 4K, the known-issue note says), SBRC quality improvements, and AOM film-grain parameter signalling. 4.1 (Nov 2024) added `--aom-film-grain`; 4.0 (Sep 2024) added `--scc`.
  Based on [1], SVT-AV1 mainline is at **4.2.0 (2026-07-14)**, after 4.0.0 (2026-01-13, breaking API), 4.0.1 and 4.1. 4.0 added these from SVT-AV1-PSY: AC bias, an IQ tune, extended quarter-step CRF (range up to 70), adaptive film grain, `--scm 3`, transform restriction and dynamic delta-q. 3.1 added chroma QM controls and more variance-boost porting, and 3.0 ported "several features from SVT-AV1-PSY" into tune 0. 4.2 adds a tune 5 (VMAF) "targeting ~15% VMAF BD-rate improvement" [1][2].
- **Evidence**: [1][2][13]
- **Confidence**: high (primary changelogs)

**Fork status**

- **What**: Based on [6][7], **SVT-AV1-PSY is dead**: the end was announced 2025-04-20 and the repo was archived 2026-02-12. Its README names **SVT-AV1-HDR** as "the official recommended continuation", while SVT-AV1-PSYEX is on the back burner.
  Based on the PSY authors' VDD 2025 slides [8], these were merged into mainline: variance boost and octile, alternative varboost curves, `--sharpness`, Tune 4 (now Tune IQ), `--qp-scale-compress-strength`, `--enable-dlf 2`, frame luma bias, adaptive film grain, temporal-filter strength controls, chroma QM, the AC energy bias ("psy-rd"), anti-alias-aware screen content detection, and fractional/extended CRF. These were **not merged**: Tune 3 (Subjective SSIM), noise normalization, and transform-type bias ("spy-rd").
  **SVT-AV1-HDR** is alive: automated LTO+PGO builds were published up to 2026-10-03 [10]. On top of mainline it keeps a film-grain tune (tune 6 = `--tune 0 --enable-tf 0 --enable-restoration 0 --enable-cdef 0 --complex-hvs 1 --tx-bias 1 --ac-bias 4.00`), `--noise-norm-strength`, `--tx-bias`, `--sharp-tx`, and `--kf-tf-strength`. Its defaults are tuned for quality: preset 4, QM on, varboost on, sharpness 1, keyint ~10 s [9]. It ships no first-party ffmpeg binaries, only community builds [9].
  **SVT-AV1-Essential** is alive but lags: its last release is v4.0.1-Essential (14 Mar 2026), based on mainline 4.0.1, while mainline is at 4.2 [11]. It forces 10-bit and ships "sensible defaults": varboost on, `--enable-dlf 2`, `--tf-strength 1`, `--sharpness 1`, QM on, `--ac-bias 0.25`, film grain off [11].
- **Evidence**: [1][6][7][8][9][10][11]
- **Confidence**: high

**Quality per bit at high quality: AV1 vs HEVC**

- **What**: There is no independent 2025-2026 test of x265 4.x vs SVT-AV1 4.x at transparent quality with perceptual metrics; I searched specifically (MSU, Streaming Learning Center, Doom9, r/AV1, codecs.wiki) and found none. What exists:
  - The 2023 Chips and Cheese test (x265 3.5 veryslow vs SVT-AV1 1.4 preset 0, 4K Sintel, VMAF 91-96) found AV1 ahead only between VMAF 91 and 94. **HEVC led at VMAF 94-96 and needed 5,6% less bitrate at VMAF 95** [20]. This is possibly stale: SVT-AV1 has changed a lot since then.
  - The SVT-AV1-HDR author (May 2025) says the fork's features help AV1 "close the gap" with HEVC and that it "is now rivaling x265 in the higher-bitrate (>10 Mbps) range" [12]. That is an admission from the AV1 side that x265 was the stronger high-bitrate encoder. It is a vendor-of-the-fork claim.
  - A GitLab report on SVT-AV1 (preset 4, CRF 21) found it competitive in static scenes, but "in motion scenes x265 kept more detail while SVT-AV1 looked blurry with some blocking" [23] (old version, 0.9).
  - A VideoHelp 4K test found x265 12-bit and SVT-AV1 10-bit "trade punches" on PSNR/SSIM [22].
  - Reference-encoder studies (HM vs libaom/AV1 CTC) put AV1 at only ~10-15% average savings over HEVC [24]. Vendor blogs claim 20-30% with no methodology [21].
  - **Your own test matches this.** libaom cpu-used 6 was ~10% smaller at equal VMAF with higher SSIM/PSNR, yet looked softer. See angle 1b for why the metrics disagree with your eyes.
- **Synthesizing across sources**: the AV1 advantage is real at streaming bitrates and shrinks to roughly zero, or reverses, at the quality level this project targets. This is especially true for handheld motion and fine texture, which is exactly categories 1, 2 and 6. Treat "AV1 is 30% better" as a low-bitrate statement.
- **Evidence**: [12][20][22][23][24]
- **Confidence**: medium (consistent direction, but no current, rigorous, high-quality-range benchmark)

**Speed at the presets that matter**

- **What**: Based on codecs.wiki's v3.0 sweep [16] (7 clips, SSIMU2/Butteraugli/W-VMAF/W-XPSNR):
  - SVT-AV1 presets 2 and 4 are the "efficiency champions".
  - BD-rate penalty vs preset −1: P0 0,97%, P1 3,79%, P2 7,82%, P3 17,08%, P4 22,41%.
  - Speed roughly doubles per preset step around P1-P3, and there is a notable gap between P4 and P5.
  - P8 is the fastest preset the author still calls usable, and P9-10 have consistency problems.

  Based on [15], x265 `slow`→`slower` raises rd 4→6, subme 3→4, ref 4→5, bframes 4→8, turns on AMP and tu-intra/inter 3, and raises lookahead 25→40; `veryslow` additionally drops limit-modes/limit-refs. Your hair test (veryslow +4,4% size, visibly fewer edge artifacts) fits that, since rect/AMP partitions and full RDO matter most on moving edges.
- **Evidence**: [15][16]
- **Confidence**: high for SVT presets (single independent source but extensive), high for x265 preset contents (docs)

**Thread scaling on 32 threads**

- **What**: Based on [28], one x265 1080p encode at default settings saturates only about 12 threads (one report) or reaches ~75-80% on 16 threads. Scaling is good to ~8c/16t at 1080p `slow`, and 2160p or `--ctu 32` scales further. Doom9 users recommend running several encodes in parallel instead.
  SVT-AV1 is designed to scale across cores. One 2022 test (40-core) showed a ~90% time cut from 1 to 32 threads at a 0,16 VMAF cost [29], which may be stale. Its CommonQuestions says output is identical for `--lp 1` and `--lp n` in CRF mode, and recommends scene-chunking tools for more parallelism [3].
  libaom only spreads across cores with tiles, and row-mt helps only together with tiles. That explains your "~2 of 32 cores" observation [61].
- **Evidence**: [3][28][29][61]
- **Confidence**: medium (forum-grade for x265 scaling, consistent across posts)

**Playback constraints that gate AV1 and VVC**

- **What**: Based on [26], iPhone hardware AV1 decode starts with the A17 Pro (iPhone 15 Pro/Pro Max), and one source adds the iPhone 16 family. The plain iPhone 15 (A16) has no AV1 hardware, and one source says Apple ships no system software AV1 decoder [26] [single-source].
  Android gained a dav1d software decoder for Android 12+ via the March 2024 Play system update, but apps had to opt in [27]. Android hardware AV1 decode: Pixel 6+, Exynos 2100+, Dimensity 1000+, Snapdragon 8 Gen 1/2+ (sources disagree on which). Mid-range Snapdragon 7-series is unconfirmed [27].
  **VVC**: AOSP documents VVC platform support only from Android 17, and hardware decode depends on the SoC vendor shipping a C2 decoder [25]. I found no Apple VVC support. Your libmpv/Haruna test failed too. **VVC stays out of scope**; nothing found argues otherwise.
- **Evidence**: [25][26][27]
- **Confidence**: medium (AV1 device lists are fragmentary; VVC conclusion high)

### 1b. Why AV1 looked softer, how to counter it, and which metric rewards texture (addendum)

- **What**:
  - Based on the PSY authors [8], mainline SVT-AV1 (and libaom) were developed "benchmaxxed", targeting the arithmetic mean of PSNR/SSIM/VMAF, and that is the motivation for the psychovisual features. **Mainline's default is still `--tune 1` (PSNR)**, and AC bias defaults to 0.0 and varboost to off [2]. So an untuned SVT-AV1 or libaom encode is expected to look smoother than x265, whose psy-rd 2.0 and psy-rdoq 1.0 (at `slow` and above) are on by default [14].
  - libaom at cpu-used 6 has no psy machinery at all in that sense, so your A/B compared a texture-preserving HEVC encoder against a PSNR-tuned fast AV1 encoder.
  - In x265, `--tune psnr` and `--tune ssim` disable psy-rd [15]. That is the vendor's own admission that psy tools lower PSNR/SSIM. Your result (AV1 higher SSIM/PSNR, x265 sharper by eye) is the textbook signature of this.
- **SVT-AV1 levers against softness, all in mainline 4.x unless noted**:
  1. `--tune 0` (VQ): "often results in an image with greater sharpness" [3]. Note the trade-off: codecs.wiki found tune 1 wins on most metrics, including SSIMU2/Butteraugli, and tune 0 sharper "with possible artifacting" [17]. The PSY fork had defaulted to tune 2, and one user found tune 2 smoother and tune 0 more detailed [search summary, low].
  2. `--enable-variance-boost 1` (strength 2 default; 3 with octile 3 suggested below CRF 20) "helps retain faint textures (e.g. skin)" [8][17]. Expect bigger files, so raise CRF to compensate [17].
  3. `--ac-bias`: the energy-preserving psy-rd analogue. 1.0-1.5 "helps retain sharpness and acuity of textures and scenes with complex motion"; 4.0-6.0 together with `--enable-tf 0 --enable-cdef 0` for grain retention [63][2]. HDR fork tune 6 bakes in `--ac-bias 4` [9]. Essential uses 0.25 [11].
  4. `--tf-strength 1` (default 3). Lower strengths scored better, and 1 or lower removes keyframe blocking/smearing [17]. Both Essential and HDR use reduced tf [9][11].
  5. `--sharpness` (deblocking bias, −7..7): +1/+2 are neutral to decent, and ≥+3 is content-dependent [17]. HDR and Essential default to 1 [9][11].
  6. `--enable-qm 1` with low `--qm-min`: QM scaling gives "better multi-scale detail preservation… complex textures, camera noise" [8]. Mainline defaults: QM off, qm-min 8 [2]. Essential uses qm-min 2 / chroma 4 [11], and codecs.wiki suggests qm-min 0 [19] (older page).
  7. Film grain synthesis (angle 4) re-adds noise texture, but changes the archive.
  8. Fork-only extras: `--noise-norm-strength`, `--tx-bias`, `--sharp-tx`, `--complex-hvs` (SVT-AV1-HDR) [9].
- **Which metric rewards texture**:
  - SSIMULACRA2 was designed to penalize **both smoothing and ringing** (the original SSIMULACRA penalized only ringing) [58]. The PSY team developed against SSIMULACRA2 and Butteraugli [8].
  - XPSNR is a psychovisually weighted PSNR that ships in ffmpeg (filter present in 7.1) [59].
  - VMAF has known enhancement-gain blind spots: sharpening and contrast inflate it (default model up to ~112), and even VMAF NEG can be pushed up to 23,6% by preprocessing [55][56]. VMAF and PSNR/SSIM also underrate synthesized grain [41].
  - A caution in the other direction: a 2017 subjective study found x264 psy-rd's perceptual gain was *negative on average*, and that full-reference metrics broadly tracked the subjective results [57]. Psy is not free, and "looks sharper" is not always "better".
- **Synthesizing across sources**: no single metric reliably rewards retained texture over smooth fidelity. Even SSIMULACRA2 favoured tune 1 over tune 0 in [17]. Use SSIMULACRA2 (harmonic mean or 10th percentile) plus XPSNR as the numeric gate, keep VMAF only as a sanity check, and make a blind visual A/B on crops (fabric, hair, window edges) a mandatory part of benchmark mode.
- **Evidence**: [2][3][8][9][11][14][15][17][41][55][56][57][58][59][63]
- **Confidence**: high on the "PSNR default + psy features" mechanism; medium on which knob fixes your specific clip (needs testing)

### 2. Parameters per category

Grounded facts first, then a synthesized table.

- **x265 facts**:
  - CRF guidance from codecs.wiki: transparent 14/16/18, high 18/22/24, medium 24/26/28 (720p/1080p/4K); ~6 CRF steps ≈ 2x size [18].
  - Deblock: the default is fine for most encodes, and at low CRF try −1:−1 (anime) or −2:−2 (live action) [18]. **Negative offsets weaken deblocking**: they give more detail but more blocking risk, and at low bitrate relative to complexity "it will produce worse results with negative values" [32].
  - SAO: keep it on at CRF ≥20, `--limit-sao` helps at high quality, and consider `--no-sao` only below CRF 16 [18]. `--selective-sao` 0-4 [14].
  - AQ: default mode 2. Docs recommend mode 3 "for 8-bit encodes or low-bitrate 10-bit encodes, to prevent color banding/blocking" [14]. Mode 4 adds edge information and was aimed at high-edge content [31]. Forum experience with mode 3 is mixed (one report of +35% size at the same CRF on a dark film) [31].
  - psy-rd default 2.0, psy-rdoq 1.0 at slow/slower/veryslow [14]. A 2025 Doom9 thread found default psy values changed grain structure least, and that high values (2-4+) are popular mostly from copied guides [30].
  - `--tune grain` sets aq-mode 0, cutree off, no SAO, psy-rd 4, psy-rdoq 10 and rskip 0 [15]. It is meant for film grain, not general phone footage.
  - keyint default 250 [14], which is ~4,2 s at 60 fps and ~8,3 s at 30 fps.
  - 10-bit from 8-bit: x265 gains "not much if at all" in compression but is "never worse" [33]. SVT-AV1 docs: "slightly better fidelity" at ~5% size cost [3]. Treat 10-bit as anti-banding insurance, not a size win.
- **SVT-AV1 facts**: presets 2-4 for efficiency [16]; CRF default 35, range 1-70 in 0,25 steps; keyint default −2 ≈ 5 s (ffmpeg `-g`); `--scm` default 2 (auto) [2]. A rough community rule of SVT-AV1 CRF ≈ x265 CRF + 4 exists but is a single opinion. Calibrate by metric instead [search summary; low].
- **Review of the prototype's x265 parameters** (synthesis on the facts above):
  - `-preset slow -crf 28`: CRF 28 is the "medium" tier at 4K and below "medium" at 1080p [18]. That is not near-transparent. Your own 1080p60 test at CRF 26 reached VMAF 96,5. For an archive, benchmark CRF 20-26, and use `slower` or `veryslow`: rd 6 and AMP buy visible edge quality for ~4% size [15], as your hair test shows.
  - `aq-mode=3:aq-strength=1.1`: defensible for 8-bit output (the docs' own recommendation). With 10-bit output, test aq-mode 2 vs 3 vs 1 at equal *size*, not equal CRF [14][31].
  - `deblock=-1:-1` on dance at CRF 30: **likely counter-productive**. Weaker deblocking at a high CRF on motion and hair is exactly where blocking and edge artifacts appear [32][18]. Use `deblock=0:0` at CRF ≥24 and reserve −1:−1 for CRF ≤22.
  - 720p downscale for dance: fine if sources are 720p-viewed, but the downscale filter matters (gap).
- **Evidence**: [2][3][14][15][16][18][30][31][32][33]
- **Confidence**: medium (parameter facts are high; per-category numbers below are my synthesis to be benchmarked)

**Starting points for the benchmark (synthesis, not measured)**

| Category | Codec / preset | Rate | Key options | Notes |
|---|---|---|---|---|
| 1 Walkthroughs (motion, 1080p-4K) | x265 `slower` 10-bit | CRF 21-25 | aq-mode 2 vs 3, deblock 0:0, psy defaults, keyint ≈ 2-5 s | motion favours x265 [23]; test 4K→1440p/1080p (angle 6) |
| 2 Dance (hair, edges, 720p) | x265 `veryslow` 10-bit | CRF 20-24 | deblock 0:0 (−1:−1 only if CRF ≤22), `limit-sao` or selective-sao, psy defaults | drop prototype CRF 30 + deblock −1 |
| 3 Session cams (static) | x265 `slower` or SVT-AV1 P3-4 tune 0 + varboost | CRF 22-26 / ~28-34 | long static scenes compress well in both | candidate for AV1 if playback passes |
| 4 Webinars (screen) | SVT-AV1 P4 `--scm 2/3` or x265 `slower` | CRF ~30-38 / ~24-28 | fps reduction (angle 3), 10-bit | x265 `--scc` unusable via ffmpeg |
| 5 Zoom (pre-compressed) | skip rule first; else SVT-AV1 P4 | high CRF | downscale to source's real resolution | generation loss (angle 6) |
| 6 Holiday clips | x265 `slower` 10-bit | CRF 21-25 | as category 1 | AV1 candidate only with full psy set |

SVT-AV1 psy baseline for any AV1 arm: `--tune 0 --enable-variance-boost 1 --ac-bias 1.0 --tf-strength 1 --sharpness 1 --enable-qm 1 --qm-min 2` plus `--keyint` ≈ 2-5 s, with `--film-grain 0` unless testing angle 4 [2][8][11][17][63].

### 3. Screen content

- **What**:
  - **SVT-AV1**: `--scm` 0 off / 1 forced palette + IBC / 2 auto (default) / 3 auto with anti-alias awareness [2]. The anti-alias-aware detector was built because the old libaom-derived detector missed screenshots with anti-aliased fonts [8]. Palette runs only when screen content mode is active [4]. **Intra block copy works only on key or intra frames and disables all in-loop filtering for that frame** [5], so for a webinar it helps keyframes and slide-change intra blocks, not the inter frames that make up most of the file. The 4.1/4.2 screen-content changes target still images [1].
  - **libaom**: auto detection by default. On keyframes, forcing `--tune-content=screen` beat the default by <0,3%, and its RTC screen mode claimed 10-19% BD-rate gains [34].
  - **No AV1-specific savings figure for palette/IBC on webinar-style video was found.** The closest quantified figure is VVC's SCC tools: 41-61% savings vs HEVC HM on 4:2:0 screen content, and 19-25% vs the HEVC-SCC profile [35]. That says SCC-class tools matter a lot for real screen content.
  - **x265** `--scc` needs a custom `ENABLE_SCC_EXT` build and is **CLI-only** [14], so it is unavailable through ffmpeg's libx265. HEVC-SCC decode support on phones was not checked (gap).
  - **Frame-rate reduction**: `mpdecimate` drops near-duplicate frames. One write-up went from 18,6 MB to 1,8 MB, though that run also sped playback up [36]. The output must stay VFR, or ffmpeg re-inserts duplicates. Some editors play VFR at the average rate [37]. Defaults can drop subtle real changes, so tune the thresholds [36].
- **Synthesizing across sources**: for webinars, the reliable big lever is temporal (VFR via mpdecimate, or a low CFR such as 10-15 fps that keeps the talking-head inset watchable), not the SCC tools. Encoders already spend almost nothing on unchanged inter blocks, so the measured saving from dropping frames is likely smaller than the 10x anecdote. Measure it.
- **Evidence**: [1][2][4][5][8][14][34][35][36][37]
- **Confidence**: medium (tool behaviour high; savings for this content type unmeasured)

### 4. Noise and grain from phone cameras

- **What**:
  - SVT-AV1: `--film-grain` level ~8 for normal live-action grain, 10-15 for noisier video, ~4 for 2-D animation. `--film-grain-denoise=0` "may result in higher fidelity by disabling source denoising" [3]. It is the mainline default [2].
  - codecs.wiki: film-grain-denoise "always removes fine detail" [19]. A 2026 how-to that pairs level 8 with denoise=1 notes that full-reference metrics are "structurally unreliable on FGS output" and that over-denoising gives "waxy mid-tones" [39].
  - The FGS model was designed for film grain. Camera sensor noise "is usually uncorrelated between samples and has different characteristics", although downscaled and compressed video can produce grain-like patterns [38]. FGS saved up to 50% on heavily grained sequences [38].
  - VMAF/PSNR/SSIM underrate synthesized grain [41], so the benchmark cannot score FGS with its normal metrics.
  - x265 4.1/4.2 can signal AOM film-grain parameters in HEVC SEI [13][14], but player support for that is unknown and it is not a practical path.
  - Pre-denoise: ffmpeg's wiki points to bm3d and nlmeans for best quality and hqdn3d as the fast option [42]. No measured bitrate-vs-detail data for phone footage was found.
- **Synthesizing across sources**: for an archive, synthesized grain replaces the original noise with a statistical lookalike over a denoised base. That is acceptable for viewing, but it is an irreversible loss if originals get deleted. Default: no pre-denoise and no FGS. Offer FGS (`film-grain` 4-8, denoise 0) and light hqdn3d only as benchmarked options for low-light clips, judged by eye. Whether hardware AV1 decoders on the target phones apply grain was not verified (gap).
- **Evidence**: [2][3][13][19][38][39][41][42]
- **Confidence**: medium

### 5. Audio

- **What**:
  - Xiph's recommendations: speech 24 kb/s mono (fullband) or 32 kb/s stereo for podcasts/audiobooks; music for storage 96-128 kb/s stereo; "Opus at 128 KB/s (VBR) is pretty much transparent" [43]. In the 2014 Hydrogenaudio multiformat test, Opus 96 kb/s was the overall winner ahead of Apple AAC [44].
  - ffmpeg's native AAC: the claim that it beats fdk-aac at 128 kb/s was removed as unsubstantiated in 2020 [46]. libfdk_aac is non-free and missing from prebuilt builds [46].
  - A rewritten native AAC encoder is reported for ffmpeg "9.1": CBR only, tuned for 48 kHz, quality claims based on objective metrics (Zimtohrli, ViSQOL), no blind test [47] [single-source, version unclear: ffmpeg 9.0 shipped 2026-08-04 [48], so "9.1" is presumably upcoming or master].
  - **Playback**: Opus in MP4 plays on iOS only from iOS 17 [45], which matches your iOS 18 test. Android, Google Photos and Synology Photos handling was not verified (gap).
- **Synthesizing across sources**:
  - Speech categories (3, 4, 5): Opus 32-48 kb/s is comfortably above Xiph's fullband speech point. Mono saves little at these rates and loses any stereo room cue, so keep the source channel layout and use stereo 48 kb/s.
  - Dance lessons (music): **the prototype's 48-64 kb/s is below Xiph's storage range**. Use 96-128 kb/s stereo.
  - Use AAC (ffmpeg native, 160-192 kb/s for music) only as a fallback for players without Opus-in-MP4.
  - Loudness: apply no filters, so it stays untouched.
- **Evidence**: [43][44][45][46][47][48]
- **Confidence**: high for Opus bitrates, low for the new ffmpeg AAC encoder

### 6. Other ways to improve size, quality or time

- **Per-file/per-scene target quality**: ab-av1 runs a sample-based interpolated binary CRF search against `--min-vmaf` or `--min-xpsnr` with `--max-encoded-percent`, and works with libx265 as well as SVT-AV1 [49]. Av1an's target-quality mode supports VMAF, XPSNR and, via VapourSynth plugins, SSIMULACRA2 and Butteraugli, and it drives x265 as well as SVT-AV1 [50]. MainConcept notes that the CRF needed for uniform quality "can differ significantly across content". Brute-force search costs several encodes per segment [search summary; low]. **Confidence: high (tools exist), medium (savings unquantified).**
- **Chunked parallel encoding**: Av1an does scene-based chunks with parallel workers [50]. Its VFR handling is undocumented, which is a risk for phone footage with VFR and display-matrix rotation. x265 cannot fill 32 threads at 1080p [28]. Synthesis: **run 2-4 files concurrently** (simple, timestamp-safe) before adopting Av1an chunking, and give chunking to 4K or single huge files only after a VFR round-trip test.
- **Two-pass vs CRF**: at equal output size, 2-pass and CRF give almost the same quality. CRF is for a quality target and 2-pass for a size target [54]. → CRF (plus search) is right for an archive. **Confidence: medium.**
- **Downscaling**: Google itself resizes >1080p to 1080p in "Storage saver" and calls ≤1080p "close to the original" [51]. Informal phone tests found 1440p vs 1080p was distinguishable mostly from ≤6 in (15 cm) viewing distance [52]. Synthesis: 4K→1080p is close to free for phone viewing, but **not** for the desktop target. Benchmark 4K→1440p as a middle option, and keep 4K for walkthroughs if desktop review matters. **Confidence: low-medium.**
- **Frame rate**: higher fps doesn't need proportionally more bits, because adjacent frames are more similar [forum, low]. Keep 60 fps for motion-heavy categories (1, 2, 6), and reduce only for webinars and static talking heads. **Confidence: low.**
- **Skip rules**: HEVC re-encoding studies show second-generation loss is small (~0,3 dB) but costs over 20% bitrate efficiency [53], and re-encoding low-bitrate lossy sources can give no size gain [search summary; low]. Synthesis:
  - skip or stream-copy sources that are already HEVC/AV1 below a bits-per-pixel threshold;
  - abort and keep the original when the output exceeds ~80-90% of source size (ab-av1's `--max-encoded-percent` idea [49]);
  - for Zoom files, prefer remuxing or downscaling to the real content resolution.

  **Confidence: medium.**
- **GOP and seekability (addendum)**:
  - libaom historically defaulted to `kf_max_dist` 9999 (over 5 minutes between keyframes). A commit lowering the default to 128 cites seek cost [60]. If ffmpeg was run without `-g`, that is the likely cause of the slow AV1 seeking in Haruna (verify with ffprobe keyframe timestamps).
  - SVT-AV1 defaults to ~5 s [2], and the HDR fork to ~10 s [9]. x265 uses 250 frames [14].
  - Keyframe seeking in mpv-family players decodes forward from the previous keyframe, and exact seeks get slower with long GOPs [62][67].
  - Synthesis: set `-g` explicitly to ~2 s (fps×2) for camera content, which costs a few percent in size, and up to ~5-10 s for static webinars. Report keyframe spacing in the fast verification step.

  **Confidence: medium.**
- **libaom**: if kept as a benchmark arm, it needs `-row-mt 1` plus tiles (`-tile-columns`), or it uses a few cores [61]. Given SVT-AV1 4.x, libaom has no clear role in this project.

## Perspectives

- **AV1 is better now vs x265 still wins at high quality**:
  - AV1 side: vendors and reference-encoder studies show 10-30% savings [21][24], and the PSY/HDR developers say the psy work closes the gap [8][12].
  - x265 side: the high-bitrate tests [20][22][23] and your own eyes. The HDR-fork author also concedes x265 led above 10 Mb/s before the fork [12].
  - Both can be true. The gap depends on bitrate, and on whether the AV1 encoder runs with psy features or PSNR tuning.
- **Tune 0 vs tune 1/2 in SVT-AV1**: codecs.wiki's metric study recommends the default tune 1 [17]. The PSY lineage pushed tune 2/3 and tune 0, and SVT's own docs call tune 0 sharper [3][8]. The disagreement is metrics vs eyes. Your tool should let both be measured.
- **psy-rd strength**: high values (4/15) are popular for grain [30], but the 2025 Doom9 thread and a 2017 subjective study argue that defaults or lower values are safer [30][57].
- **aq-mode for SDR**: one view recommends mode 3 for SDR distribution, another found mode 1 best for high-quality SDR, and the docs recommend 3 for 8-bit [14][30][31]. This is unresolved, so benchmark at equal size.

## Practical Implications

Benchmark matrix (per category, 3-5 representative clips each, including your sofa-fabric/window clip and the hair clip):

1. **x265 arm**: `slow` vs `slower` vs `veryslow` × CRF {20, 22, 24, 26} × deblock {0:0, −1:−1} × aq-mode {2, 3} × SAO {default, limit-sao}; 10-bit (`yuv420p10le`); `-g` = 2×fps.
2. **SVT-AV1 mainline 4.2 arm**: preset {2, 4} × CRF sweep calibrated to the same SSIMU2 targets × {stock tune 1; psy set: `tune 0 + varboost + ac-bias 1.0 + tf-strength 1 + sharpness 1 + QM`}; 10-bit; `-g` = 2×fps.
3. **Optional SVT-AV1-HDR arm** (community ffmpeg build) for categories 2 and 6 only: tune 0 defaults and tune 6, to see whether fork-only tools (noise-norm, tx-bias) close the texture gap. Do not make it a dependency of the public tool.
4. **Screen arm (category 4)**: SVT-AV1 `scm 0/2/3` × {source fps, mpdecimate VFR, 10 fps CFR}; x265 at the same fps variants.
5. **Grain arm (low-light subset)**: SVT-AV1 `film-grain` {0, 4, 8} with denoise 0, and x265 with/without light hqdn3d. Visual only.
6. **Audio**: Opus 48 vs 96 vs 128 kb/s on dance music clips (blind ABX by the user); Opus 32/48 kb/s on speech.
7. **Metrics recorded per encode**: SSIMULACRA2 (mean + 10th percentile), XPSNR (ffmpeg ≥7.1), VMAF NEG (sanity only), size, wall time at the thread count used, keyframe interval. Add a blind visual A/B on fixed crops as the deciding vote.
8. **Runner**: N concurrent single-file encodes sized to 32 threads (e.g. 3× x265 or 2× SVT-AV1), with per-encode thread limits (`pools`/`frame-threads` for x265, `lp` for SVT).

Design decisions:

- Default codec HEVC/x265 for categories 1, 2 and 6. AV1 is opt-in per category after a phone playback check on the actual devices (iPhone non-Pro vs Pro, the Android models in use, Google Photos/Immich/Synology Photos).
- Fix the prototype: CRF 28/30 → benchmark from 20-26, `deblock=-1:-1` off for dance, Opus for dance → 96-128 kb/s, explicit `-g`.
- Add skip/abort rules (already-efficient source, output > X% of source).

## Sources

Primary = official docs, release notes, original research, or the author's own post. Secondary = blogs, forums, summaries.

1. [SVT-AV1 CHANGELOG.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/CHANGELOG.md) - primary; release notes 3.0.0-4.2.0 with dates.
2. [SVT-AV1 Docs/Parameters.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Parameters.md) - primary; parameter ranges and defaults (tune, varboost, ac-bias, scm, keyint, film grain, QM).
3. [SVT-AV1 Docs/CommonQuestions.md](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/CommonQuestions.md) - primary; film-grain levels, 10-bit cost, tune 0 sharpness, lp determinism, chunking.
4. [SVT-AV1 Appendix: Palette Prediction](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Appendix-Palette-Prediction.md) - primary; when palette is active.
5. [SVT-AV1 Appendix: Intra Block Copy](https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/Docs/Appendix-Intra-Block-Copy.md) - primary; IBC only on intra frames, disables loop filters.
6. [psy-ex/svt-av1-psy README](https://github.com/psy-ex/svt-av1-psy) - primary; end of project, archived 2026-02-12, SVT-AV1-HDR named successor.
7. [Gianni Rosato: The End of SVT-AV1-PSY (2024-11-26)](https://giannirosato.com/blog/post/end-of-psy/) - primary; rationale for winding down and mainlining.
8. [Barba & Rosato: SVT-AV1-PSY, VDD 2025 slides](https://giannirosato.com/files/svt-av1-psy_vdd_2025.pdf) - primary; why psy features exist, varboost/AC bias/QM, SSIMULACRA2 use, list of merged vs unmerged features.
9. [juliobbv-p/svt-av1-hdr README](https://github.com/juliobbv-p/svt-av1-hdr) - primary; fork features, tune 6, modified defaults.
10. [svt-av1-hdr releases](https://github.com/juliobbv-p/svt-av1-hdr/releases) - primary; builds up to 2026-10-03.
11. [nekotrix/SVT-AV1-Essential README](https://github.com/nekotrix/SVT-AV1-Essential) and [releases](https://github.com/nekotrix/SVT-AV1-Essential/releases) - primary; defaults, last release v4.0.1-Essential (14 Mar 2026).
12. [r/AV1 "Introducing SVT-AV1-HDR" (May 2025, mirror)](https://reddit.birdcat.cafe/r/AV1/comments/1kjhpv3/introducing_svtav1hdr) - primary (author's claims, not independent); x265 vs AV1 >10 Mb/s remark.
13. [x265 release notes (4.2 docs)](https://x265.readthedocs.io/en/4.2/releasenotes.html) - primary; 4.0/4.1/4.2 dates and features.
14. [x265 CLI documentation](https://x265.readthedocs.io/en/master/cli.html) - primary; aq-mode, psy, deblock, SAO, scc, keyint, threading defaults.
15. [x265 preset and tune options](https://x265.readthedocs.io/en/master/presets.html) - primary; slow/slower/veryslow tables; what tune grain/psnr/ssim set.
16. [codecs.wiki: SVT-AV1 Deep Dive Part 1, presets v2.0-v3.0 (2025-06-20)](https://codecs.wiki/blog/svt-av1-fourth-deep-dive-p1) - secondary (independent benchmark); BD-rate per preset, SSIMU2/Butteraugli/XPSNR.
17. [codecs.wiki: SVT-AV1 Deep Dive Part 2, parameters (2025-07-02)](https://codecs.wiki/blog/svt-av1-fourth-deep-dive-p2) - secondary (independent benchmark); varboost, tune, tf-strength, sharpness, fast-decode.
18. [codecs.wiki: x265 encoder page](https://codecs.wiki/docs/encoders/x265) - secondary; CRF tiers, deblock/SAO/AQ guidance.
19. [codecs.wiki: SVT-AV1 encoder page](https://codecs.wiki/docs/encoders/SVT-AV1) - secondary, possibly stale (references v2.1.0); film-grain-denoise, qm-min.
20. [Chips and Cheese: Codecs for the 4K Era (2023)](https://chipsandcheese.com/p/codecs-for-the-4k-era-hevc-av1-vvc-and-beyond) - secondary, **stale (2023)**; x265 vs SVT-AV1 vs VVenC at VMAF 91-96.
21. [Fora Soft: Encoder implementations (2026)](https://www.forasoft.com/learn/video-encoding/articles/encoder-implementations-x264-x265-svt-av1-libaom-vvenc) - secondary/vendor, low reliability (internal inconsistencies, uncited numbers).
22. [VideoHelp: x265 12-bit vs SVT-AV1 10-bit](https://forum.videohelp.com/showthread.php?p=2673854) - secondary (forum).
23. [SVT-AV1 GitLab issue #1810](https://gitlab.com/AOMediaCodec/SVT-AV1/-/issues/1810) - primary report, old version; x265 more detail in motion.
24. [APSIPA: Compression efficiency analysis of AV1, VVC and HEVC for random access](https://www.cambridge.org/core/journals/apsipa-transactions-on-signal-and-information-processing/article/compression-efficiency-analysis-of-av1-vvc-and-hevc-for-random-access-applications/D2345DDC3750055AB0AA3D24FCF743BE) - primary research (reference encoders); AV1 ~10-15% over HEVC.
25. [AOSP: VVC support](https://source.android.com/docs/core/media/vvc) - primary; VVC from Android 17, SoC-dependent.
26. [Bitmovin: Apple AV1 support](https://bitmovin.com/blog/apple-av1-support) - secondary; A17 Pro first iPhone with AV1 hardware.
27. [9to5Google: Android AV1 software decoder (2024)](https://9to5google.com/2024/04/19/android-av1-software-decoder/) - secondary; dav1d on Android 12+, app opt-in.
28. [Doom9: high core count CPU for x265](https://forum.doom9.org/archive/index.php/t-177622.html?pda=1) and [x265 threading docs 4.1](https://x265.readthedocs.io/en/4.1/threading.html) - secondary + primary; x265 thread saturation.
29. [Streaming Learning Center: SVT-AV1 1.0 Shows Great Promise (2022)](https://streaminglearningcenter.com/encoding/svt-av1-1-0-shows-great-promise.html) - secondary, **stale**; thread scaling.
30. [Doom9: PSY settings for grain tuning (June 2025)](https://forum.doom9.org/archive/index.php/t-186396.html) - secondary (expert forum); psy-rd/rdoq, aq-mode 1, nr-inter.
31. [x265-devel: Use cases for aq-mode=4 (2019)](https://mailman.videolan.org/pipermail/x265-devel/2019-August/012618.html) and [Doom9 aq-mode discussion](https://forum.doom9.org/showthread.php?p=1882575) - primary (dev list) + secondary; aq-mode 3/4 behaviour. Possibly stale.
32. [VideoHelp: deblock values explained](https://forum.videohelp.com/showthread.php?p=2349198) - secondary; negative = weaker, worse at low bitrate.
33. [Doom9: 10-bit x265 from 8-bit sources](https://forum.doom9.org/archive/index.php/t-183044.html) - secondary.
34. [libaom commit: correctly set use_screen_content](https://aomedia.googlesource.com/aom/+/2a273eef9962296f8de0f449ac21776b2e372a6f%5E%21/) - primary; auto vs forced screen tools.
35. [Microsoft Research: Screen content support in VVC](https://www.microsoft.com/en-us/research/?p=798274) - primary research; SCC tool savings (VVC, not AV1).
36. [Zyxware: removing duplicate frames with ffmpeg](https://www.zyxware.com/article/6517/remove-duplicate-frames-and-increase-playback-speed-of-screen-recordings) - secondary; mpdecimate example.
37. [VideoHelp: mpdecimate and VFR output](https://forum.videohelp.com/showthread.php?p=2784026) - secondary.
38. [Norkin & Birkbeck: Film grain synthesis for AV1 (DCC 2018)](https://norkin.org/pdf/DCC_2018_AV1_film_grain.pdf) - primary research; up to 50% savings, sensor noise differs.
39. [DEV: Turn on AV1 film grain synthesis and measure it (2026)](https://dev.to/masonwritescode/turn-on-av1-film-grain-synthesis-and-measure-what-it-saves-on-your-own-footage-37bb) - secondary; caveats on metrics and over-denoising.
40. [Doom9: SVT-AV1 film-grain-denoise discussion](https://forum.doom9.org/archive/index.php/t-185159.html) - secondary.
41. [Streaming Media: Challenges of new encoding scenarios](https://streamingmedia.com/Articles/Post/Blog/Challenges-of-New-Encoding-Scenarios-Reflections-on-Measuring-Perceived-Quality-166721.aspx) - secondary; VMAF/PSNR/SSIM underrate FGS.
42. [FFmpeg wiki: Denoise](https://trac.ffmpeg.org/wiki/denoise) - primary docs; denoiser overview.
43. [Xiph: Opus Recommended Settings](https://wiki.xiph.org/Opus_Recommended_Settings) - primary; bitrates per use.
44. [Hydrogenaudio multiformat listening test (July 2014)](https://hydrogenaud.io/index.php/topic,106911.msg875036.html) - primary (public blind test), **stale (2014)**.
45. [Apple Developer Forums: Opus in MP4](https://developer.apple.com/forums/thread/722399) - primary-ish (Apple engineer answer); iOS 17+.
46. [FFmpeg-cvslog: remove unsubstantiated ffaacenc > fdk-aac claim (2020)](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2020-May/122054.html) - primary.
47. [Dr. Web: FFmpeg 9.1 bringt einen runderneuerten nativen AAC-Encoder (2026-07-02)](https://www.drweb.de/ffmpeg-9-1-bringt-einen-runderneuerten-nativen-aac-encoder/) - secondary, single source.
48. [Phoronix: FFmpeg 9.0 released](https://www.phoronix.com/news/FFmpeg-9.0-Released) - secondary; 9.0 on 2026-08-04.
49. [ab-av1](https://github.com/alexheretic/ab-av1) - primary; crf-search with VMAF/XPSNR, max-encoded-percent, libx265 support.
50. [Av1an](https://github.com/rust-av/Av1an) - primary; chunked encoding, target quality with VMAF/XPSNR/SSIMU2/Butteraugli.
51. [Google Photos Help: backup quality](https://support.google.com/photos/answer/6220791) - primary; Storage saver resizes >1080p to 1080p.
52. [PhoneArena: QHD vs 1080p, can people see it](https://www.phonearena.com/news/Quad-HD-vs-1080p-display-resolution-can-people-actually-see-the-difference_id69856) - secondary, informal, stale.
53. [arXiv 1702.07548: Quality losses in homogeneous HEVC transcoding](https://arxiv.org/pdf/1702.07548) - primary research; ~0,3 dB loss, >20% bitrate penalty.
54. [VideoHelp: 2-pass vs CRF](https://forum.videohelp.com/showthread.php?p=2687727) - secondary.
55. [arXiv 2107.04510: Hacking VMAF and VMAF NEG](https://arxiv.org/pdf/2107.04510) - primary research.
56. [Streaming Learning Center: VMAF hacking / NEG](https://streaminglearningcenter.com/?p=12877) - secondary; Netflix data, libaom tune=vmaf.
57. [Duanmu et al., IS&T EI 2017: Psy-RD subjective study](https://library.imaging.org/ei/articles/29/14/art00010) - primary research, **stale**.
58. [SSIMULACRA (AviSynthPlus port, describes SSIMULACRA2)](https://github.com/Asd-g/AviSynthPlus-ssimulacra) - secondary; SSIMULACRA2 penalizes smoothing and ringing.
59. [FFmpeg 7.1 doxygen: vf_xpsnr](https://ffmpeg.org/doxygen/7.1/vf__xpsnr_8c_source.html) - primary; XPSNR filter in ffmpeg.
60. [libaom commit: reduce default kf_max_dist](https://aomedia.googlesource.com/aom/+/2a0d7b1a55aff0870f6bda485cf7cb63662c2337) - primary; old 9999-frame default, seek cost.
61. [Doom9: libaom row-mt and tiles](https://forum.doom9.org/archive/index.php/t-172550-p-26.html) - secondary.
62. [IINA issue #4766: keyframe seeking in mpv-based player](https://github.com/iina/iina/issues/4766) - secondary.
63. [SVT-AV1 MR !2513: Introduce AC Bias](https://gitlab.com/AOMediaCodec/SVT-AV1/-/merge_requests/2513) - primary; AC bias strengths for texture vs grain.
67. [Cinelerra-GG list: AV1 seek failures fixed with g=30](https://lists.cinelerra-gg.org/pipermail/cin/2024-August/008506.html) - secondary.

(Numbers 64-66 are unused.)

## Gaps (what to measure hands-on)

- **x265 4.2 vs SVT-AV1 4.2 at transparent quality on phone footage**: no current independent data exists. This is the core of the benchmark. Compare at equal SSIMULACRA2 and equal XPSNR, then by blind visual A/B on texture crops.
- **Which SVT-AV1 psy knobs fix the softness you saw**: run an ablation (tune 0 / varboost / ac-bias / tf-strength / sharpness / QM), one at a time, on the sofa and window clip.
- **Thread usage**: measure wall time and CPU utilisation for 1 vs 2 vs 3 concurrent x265 `slower` encodes and 1 vs 2 SVT-AV1 P4 encodes on the 7950X3D. Also measure x265 `--threaded-me` on Zen 4, given the known regression on high-clock CPUs [13].
- **AV1 playback reality**: decode smoothness at 1080p60/4K60 and film-grain application on the actual phones (non-Pro iPhone, the Android models in use) and in Google Photos, Apple Photos, Synology Photos, Immich and Haruna. Search budget ran out before dav1d tiling/threading could be researched; measure seeking with `-g` 2 s vs default.
- **HEVC Main10 decode and full-range (`yuvj420p`) signalling** on the target phones and gallery apps (not researched).
- **Opus-in-MP4** on Android players and the gallery apps (not verified).
- **Screen content savings**: scm on vs off and mpdecimate VFR vs 10 fps CFR on real webinar recordings, plus VFR playback in the gallery apps.
- **Grain**: whether FGS or light hqdn3d yields worthwhile savings on low-light phone clips without visible change (visual only; metrics are unreliable here [41]).
- **Skip-rule thresholds**: the bits-per-pixel and output-size ratio below which re-encoding Zoom or already-HEVC sources stops paying off.
- **New ffmpeg AAC encoder**: its version and quality are unconfirmed [47]. Re-check before choosing AAC as the fallback.
- **Av1an with VFR, rotated phone sources**: whether timestamps and the display matrix survive chunking.
