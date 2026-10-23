# T4: Quality measurement, fast verification and public test corpora

Research date: 2026-10-20.
Method: web search plus direct reads of primary sources (official docs, source code via `gh api`, dataset buckets and per-file licence files).
The shared web-search budget ran out near the end, so a few follow-ups (screen-content metric studies, MP4Box/GPAC validation, Pixabay API terms, Commons upload policy) rest on fewer sources than planned; these are flagged inline and in Gaps.

## TL;DR

Use **VMAF v1** (libvmaf 3.2.x, released June 2026; NEG behaviour built in, phone and HFR variants) plus **XPSNR** (native ffmpeg filter) as the CPU-cheap pair. Add **SSIMULACRA2** (CPU via vszip/fssimu2) and **CVVDP** (slow on CPU, so only on a subset) in benchmark mode, because legacy VMAF v0.6.1 tracks human judgement poorly in the near-transparent range [29][9][14].
Most real-world measurement errors come from **alignment, not the metric**. Encode with `-fps_mode passthrough`, then compare frame-by-frame (input `-r N` on both sides, `setpts=PTS-STARTPTS`). Normalise colour range and resolution explicitly, and check frame counts separately, because ffmpeg's framesync silently repeats frames [4][12][1][21].
For per-file verification, a full decode with `-xerror`, ffprobe stream, duration, packet and timestamp checks, and a metric on 2-3 short windows fit in well under a minute for typical clips. No public corpus reproduces Android VFR, full-range, rotated footage, so the benchmark needs synthetic "phone-ified" variants or the owner's own CC0 clips.

---

## Key Findings

### Q1. Which metrics, how well they track humans at high quality, tools and CPU speed

**VMAF: v1 replaces v0.6.1 (June 2026)**
- **What**: Based on [13][9][14], Netflix released VMAF v1 (libvmaf v3.2.0 on 2026-06-20; v3.2.1 on 2026-09-14). It ships models for 1080p at 3H, phone at 5H, 4K at 1.5H and 4K at 3H (range 0-110), plus `_hfr` variants for ~50/60 fps. Its features: an added AIM impairment term (penalises blocking, which v0 under-penalised), CAMBI banding inside the model, chroma features (v0 was luma-only), a bounded motion feature, and NEG (no enhancement gain) on by default. Scores are calibrated to v0's scale [14].
  - The v1 phone model adjusts the elementary features for a 5H viewing distance; the v0 phone model was a polynomial on top of the score and "could overpredict quality" [14].
  - v1 "should ideally be applied at 10-bit precision for SDR" so that banding is caught, even for 8-bit encodes [9].
  - The v1 models are built into libvmaf as `vmaf_v1.0.16_3d0h`, `_5d0h`, `_1d5h_2160`, `_3d0h_2160` and the `_hfr_*` variants [15]. That means ffmpeg can select them with `model=version=...`.
  - The ffmpeg-quality-metrics tool notes that the v1 models need ffmpeg linked against libvmaf ≥ 3.2.1 [45]. BtbN's static builds pin a libvmaf commit 8 commits after v3.2.1 [16], so the static-build route the prototype already used gets v1.
- **Evidence**: [9][13][14][15][16][45]
- **Confidence**: high for availability and features (primary sources). Medium for accuracy gains: Netflix says v1 "matches or outperforms v0 in most datasets", with gains on phone-viewing, banding and chroma datasets, but the SRCC table is an image I could not read [14].

**Legacy VMAF v0.6.1 is weak near transparency**
- **What**: Based on [29], on the JPEG AIC-3 high-fidelity image set (≤1 JND subset), VMAF scored SROCC 0.635 versus 0.810 for VMAF-NEG, 0.831 for SSIMULACRA2, 0.852 for CVVDP and 0.857 for Butteraugli. Over the full set, CVVDP ranked first (SROCC 0.960) and was statistically superior to all the others.
  - Cloudinary's own table puts VMAF last on KonFiG-IQA (SRCC 0.49 vs 0.93 for SSIMULACRA2) [25]. The older MSU video benchmark found all metrics correlate worst above 6 Mbit/s, which is the high-quality regime [35].
- **Evidence**: [29][25][35]
- **Confidence**: high that v0.6.1 (non-NEG) is a poor transparency gate. The caveat is that [29] and [25] are still-image studies.

**CVVDP (ColorVideoVDP)**
- **What**: Based on [28][27], CVVDP is a full-reference, colour-aware spatio-temporal metric (SIGGRAPH 2024). It reports JOD units, where 10 = no difference and a 1 JOD gap means 75% of people prefer the better clip [27].
  - It needs a display model. Built-ins include `standard_fhd`, `standard_4k`, `standard_phone`, `iphone_14_pro` and `iphone_14_pro_vert` [27].
  - It is a PyTorch package (`pip install cvvdp`, v0.5.7 on 2026-08-02) and runs on CPU "but the processing times will be much longer, especially for video" [27].
  - The Vship README measured the original CVVDP at 1632 s on CPU for 1339 frames of 1080p (~0.8 fps on a Ryzen 7940HS), versus 16 s with Vship on CUDA [26].
- **Evidence**: [26][27][28][29]
- **Confidence**: medium-high on accuracy (paper plus one independent 2025 study, which is image-only). High on the speed problem.

**SSIMULACRA2 and Butteraugli**
- **What**: These are image metrics applied per frame. The SSIMULACRA2 scale is anchored at 90 = "visually lossless (flicker test)", 85 = not noticeable in in-place comparison, 80 = not noticeable side by side at 1:1, and 70 = artifacts perceptible but not annoying [25].
  - CPU options: vszip (Zig, VapourSynth) took ~30 s for 1339 frames of 1080p (~45 fps) versus 115 s for the libjxl tool [26]. fssimu2 claims to be up to 40% faster than the reference, with PCC 0.9997 against it, and takes Y4M input [33].
  - Butteraugli on CPU (libjxl) took 239 s for the same clip (~5.6 fps) [26].
  - Vship runs both metrics plus CVVDP on CUDA/HIP or Vulkan, through FFVship (a CLI that decodes with ffms2) or a VapourSynth plugin. MIT licence, last commit 2026-10-19 [26]. It has no CPU backend, only software Vulkan (llvmpipe) [26].
  - Av1an uses Vship or vszip/vapoursynth-julek for these metrics [24].
- **Evidence**: [24][25][26][32][33]
- **Confidence**: high for tooling. Medium for the speed figures (single author, different hardware).

**XPSNR**
- **What**: XPSNR is a native ffmpeg filter (`xpsnr`) [1]. It is a block-wise, perceptually weighted PSNR that includes temporal activity. Fraunhofer HHI designed it for high-resolution video; the documentation recommends reporting the minimum of the Y/U/V averages [1].
  - The authors' 2020 study reports PLCC roughly on par with VMAF across MOS datasets (e.g. 0.863 vs 0.862 on the CfP set) [30]. The table text was partly garbled; [single-source].
  - The community codec wiki calls it fast (real-time 1080p24) and puts "visually lossless" at ~42 dB, noting this is content-dependent and preliminary [31] [single-source].
  - The ffmpeg filter source has no slice threading [1, source read], so parallelism has to come from running several files or windows at once.
  - Gotcha: input order is **reference first, distorted second**, the opposite of `libvmaf` (distorted first) [1].
- **Evidence**: [1][30][31]
- **Confidence**: medium (little independent validation in the high-quality range).

**Screen content (webinars, slides)**
- **What**: Based on [60][61], screen content differs statistically from camera content, and most quality models perform worst on it. The 2020 UGC study found most algorithms "performed worst on screen content videos" (possibly stale).
  - I found no 2024-2026 study that scores VMAF, SSIMULACRA2 or CVVDP on text or slide video (search budget ran out).
  - Usable public test material does exist: the AOM CTC `b2_scc` set [47].
- **Evidence**: [60][61]
- **Confidence**: low.
- **Synthesis**: For category 4, gate on a structural, edge-sensitive pair: XPSNR-Y minimum per window plus SSIMULACRA2 worst-frame. Treat VMAF as secondary. Calibrate with a visual check on a cropped text region, and treat this as a hypothesis for the benchmark.

**Non-pristine references (Zoom-style sources, all phone footage)**
- **What**: Based on [34], on BVI-UGC (1080 transcodes of 60 compressed references, more than 3500 raters), all 10 full-reference metrics reached SROCC < 0.6.
- **Evidence**: [34]
- **Confidence**: medium (one large study).
- **Synthesis**: Every source here is already lossy (category 5 heavily so). FR metrics measure fidelity to an artifact-laden reference, so absolute targets transfer poorly from studio-content literature. Calibrate per category.

### Q2. Measuring real-world sources correctly

**Frame alignment and VFR**
- **What**: Netflix's ffmpeg guide states that "FFmpeg filters synchronize based on timestamps instead of frames". Its examples set the frame rate with input `-r` and synchronise with `setpts=PTS-STARTPTS` [12].
  - Input `-r` makes ffmpeg "ignore any timestamps stored in the file and instead generate timestamps assuming constant frame rate" [4]. On both inputs, that turns timestamp matching into frame-index matching. ab-av1 does exactly this: `-r 25` for VMAF and `-r 60` for XPSNR by default [18][19].
  - ab-av1's libvmaf filter is `libvmaf=shortest=true:ts_sync_mode=nearest`, with `setpts=PTS-STARTPTS,settb=AVTB` on both legs [19].
  - The precondition is that the encode kept every frame. ffmpeg's default `-fps_mode auto` picks `vfr` for MKV (drops frames whose timestamps collide) and effectively `cfr` for MP4 (duplicates and drops). An ab-av1 contributor measured one VFR sample: 1196 source frames became 1195 in MKV and 1197 in MP4. The fix is `-fps_mode passthrough` [21][4]. ab-av1 has used passthrough for all sample encodes since v0.10.4 [18].
  - This matches the prototype's "MKV at 59.94 lost 4 of 3601 frames": Matroska's default timestamp precision is 1 ms, and a 2021 patch to make it configurable is not in the current muxer docs [43][5].
- **Evidence**: [4][5][12][18][19][21][43]
- **Confidence**: high.

**Framesync hides missing frames**
- **What**: Based on [1], dual-input filters default to `eof_action=repeat` and `repeatlast=1`. A shorter distorted stream therefore gets its last frame repeated rather than causing an error. ab-av1 sets `shortest=true` [19], and ffmpeg-quality-metrics stops at the shorter stream and warns on resolution, frame-rate or duration mismatches [45].
- **Evidence**: [1][19][45]
- **Confidence**: high.
- **Synthesis**: Always compare frame counts outside the metric run.

**Colour range (yuvj420p full range)**
- **What**: ffmpeg 7.1 introduced YUV colorspace negotiation "obsoleting the YUVJ pixel format" [2].
  - `libvmaf` compares raw values. ffmpeg only logs a warning when the two inputs' `color_range` differs [7][38]; it does not convert.
  - Older trac reports show yuvj input being squeezed to limited range by default unless `scale=in_range=pc:out_range=pc` (or `-color_range pc`) is set [39] (2021, possibly stale).
- **Evidence**: [2][7][38][39]
- **Confidence**: high that a range mismatch silently biases scores. Medium on current default encode behaviour, which the benchmark should test.
- **Synthesis**: Convert both legs explicitly to the same range and depth before any metric, e.g. `scale=in_range=<probed>:out_range=tv,format=yuv420p10le`. 10-bit also matches VMAF v1's recommendation [9].

**Rotation**
- **What**: ffmpeg's `-autorotate` is on by default. When transcoding, rotation is applied "at the filtering stage"; for stream copy, the display matrix is written to the output [4]. A 2025 ticket reports ffmpeg 7.1 writing a display matrix to outputs where none was expected (EXIF JPEG case, still open) [40].
- **Evidence**: [4][40]
- **Confidence**: medium.
- **Synthesis**: Decode both files with autorotate on, so a baked-in rotation and a kept display matrix compare equally. The verifier should assert that the *displayed* width and height (after the matrix) match the source. That catches double rotation and lost rotation in milliseconds.

**Resolution changes (720p dance, 360p talking head)**
- **What**: Netflix recommends upsampling the distorted video to the reference resolution with bicubic and computing VMAF there. It warns against comparing scores across native resolutions [11][12].
  - ab-av1 automatically upscales to 1080p (1k model) or 2160p (4k model) when the input is smaller [19]. Av1an computes VMAF at 1920x1080 by default (`--vmaf-res`) [24].
  - VMAF v1 lets you pass the encode-side size and bit depth to CAMBI (`cambi.enc_width`, ...) when measuring an upscaled encode [9].
- **Evidence**: [9][11][12][19][24]
- **Confidence**: high.

**`scale2ref` replacement**
- **What**: `scale2ref` was deprecated in ffmpeg 7.1. `scale` gained an optional second "ref" input, which is enabled automatically when the size expressions use `rw`/`rh`/`ref_*`. The old filter had no guaranteed frame ordering between its inputs [2][3][1].
  - The documented pattern is `[ref][a]scale=rw:rh[c]` [1]. Because `scale` consumes the ref stream, a `split` is needed if the reference is used again (user report) [3].
- **Evidence**: [1][2][3]
- **Confidence**: high.

**`n_threads`**
- **What**: libvmaf's `n_threads` defaults to 0 (no threading) in ffmpeg [1]. ab-av1 sets it to all logical CPUs [19].
  - One user reported 1080p VMAF going from ~22 fps to ~100 fps on an i5-13600K with `n_threads=20` [62] [single-source].
  - Netflix says v1 is cheaper than v0 (VIF removed, chroma at lower scale) and that the libvmaf threading in that release improves speed for both model generations [14].
- **Evidence**: [1][14][19][62]
- **Confidence**: medium (no 7950X3D numbers; measure them).

**Recommended chain (synthesis from [1][4][9][12][19][21])**
Preconditions: the encode used `-fps_mode passthrough` and any `fps=`/`scale=` from the preset; the reference gets the *same* `fps=` filter if the preset changed the frame rate.

```sh
ffmpeg -hide_banner -nostdin -r 30 -i dist.mp4 -r 30 -i src.mp4 -an -sn -dn -filter_complex "
 [0:v]scale=1920:1080:flags=bicubic:in_range=tv:out_range=tv,format=yuv420p10le,setpts=PTS-STARTPTS,settb=AVTB[dis];
 [1:v]scale=1920:1080:flags=bicubic:in_range=pc:out_range=tv,format=yuv420p10le,setpts=PTS-STARTPTS,settb=AVTB,split[ref1][ref2];
 [dis]split[dis1][dis2];
 [dis1][ref1]libvmaf=model=version=vmaf_v1.0.16_3d0h\:name=v3h|version=vmaf_v1.0.16_5d0h\:name=v5h:n_threads=32:shortest=1:log_fmt=json:log_path=vmaf.json;
 [ref2][dis2]xpsnr=stats_file=xpsnr.log:shortest=1" -f null -
```

- The `-r 30` value is arbitrary; it only has to be identical on both inputs.
- `in_range` comes from ffprobe and is never assumed.
- Use the `_hfr_` models for 50/60 fps content [9].
- Note the swapped input order for `xpsnr` [1].

### Q3. Fast post-encode verification

**Full decode**
- **What**: ab-av1 v0.11.7 (2026-08-21) added `--verify`. It runs `ffmpeg -v error -stats -xerror -i out -map 0:v? -map 0:a? -f null -`, checks that the output duration is within 2 s of the input, writes to a temp file and only renames after the checks pass [18][19].
  - `-xerror` stops on the first error. `-err_detect` has `crccheck`, `bitstream`, `buffer`, `explode` and stricter `careful`, `compliant` and `aggressive` modes [4][6].
  - An ffmpeg maintainer warned that ffmpeg "tries hard to read known-to-be-broken files" and is not an ideal validator. A user observed that `-v error` can print nothing even for a non-video file [41] (2015/2019, still plausible).
- **Evidence**: [4][6][18][19][41]
- **Confidence**: high.
- **Synthesis**: A silent decode is necessary but not sufficient. Pair it with the explicit counts and stream checks below.

**Container-level facts**
- **What**:
  - A normal (non-fragmented) MP4 "is undecodable if it is not properly finished". `+faststart` runs a second pass that rewrites the file [5]. So a truncated MP4 fails at open time, which ffprobe catches instantly.
  - The Matroska muxer writes a CRC32 element into every Level-1 element by default (`write_crc32`) [5]. ffmpeg's Matroska demuxer skips CRC32 elements and does not verify them [8, source read]. A decode check therefore will not use those CRCs.
  - `cues_to_front` moves the index to the start "by shifting the main data if necessary", i.e. a rewrite of the file [5]. Historic muxer bugs overwrote data when the reserved Cues space was too small (fixed in 2020) [44].
  - mkvalidator checks for missing mandatory elements, junk data, bad track or cue entries, and profile violations. Its latest release is v0.6.0 from 2021-01-31 (stale but packaged) [42].
- **Evidence**: [5][8][42][44]
- **Confidence**: high for the documented behaviour. Medium for how relevant this is to the prototype's corrupt MKV, whose cause is unknown.
- **Synthesis**: Avoid post-encode remux passes entirely: mux once to a temp name in the final container, verify, then rename atomically. Each rewrite pass (remux, `cues_to_front`, `faststart`) is another chance to corrupt the file.

**Failure modes seen in practice**
- **What**:
  - Dropped or duplicated frames from `fps_mode auto` on VFR input [21].
  - Desynchronised samples on VFR input in crf-search [22].
  - Sample-cut differences between containers: MKV keeps leading or trailing frames that have no keyframe, while MP4 drops undecodable frames and pads timestamps [21].
  - Phone VFR footage with min/max frame rates of 14.9/32.0 fps around a 29.68 average [63].
  - Audio drift in 59.94 fps MKV caused by 1 ms timestamps [43].
  - Display-matrix surprises [40].
  - Truncated outputs: MP4 without `moov` [5].
- **Evidence**: [5][21][22][40][43][63]
- **Confidence**: medium. These are documented cases; there is no frequency data.

**Recommended per-file verifier (synthesis; target ≤ 60 s for a 10-min 1080p clip, to be measured)**

| # | Check | Tool | Catches |
|---|---|---|---|
| 1 | Encode exit code, stderr scan; output written to temp name | ffmpeg | crashes, OOM, disk full |
| 2 | Stream inventory: v/a count, codec, `hvc1` tag, pix_fmt, `color_range`, displayed W×H after rotation, `creation_time`/GPS tags present | `ffprobe -show_streams -show_format` | lost audio, wrong range, rotation lost or doubled, metadata loss |
| 3 | Video packet count = source frame count (passthrough) or the predicted count (fps change), with zero tolerance | `ffprobe -count_packets` (demux only, fast) | dropped or duplicated frames |
| 4 | PTS sanity: no duplicate PTS, max gap ≤ source max gap; video end vs audio end within ~1 frame + codec priming | `ffprobe -show_entries packet=pts_time,duration_time` | timestamp grid problems, A/V desync, truncation |
| 5 | Duration: video within 1 frame of source (ab-av1 allows 2 s [19]; too loose here) | ffprobe | truncation |
| 6 | Full decode of all v/a streams with `-xerror` | `ffmpeg -f null` | bitstream corruption anywhere |
| 7 | 2-3 contiguous windows of ~2-3 s (start/middle/end), XPSNR + VMAF v1 against the source, compared to the preset's benchmarked floor | ffmpeg with the Q2 chain plus `-ss`/`-t` on both inputs | misalignment, range/colour errors, green/garbage frames, wrong preset |
| 8 | (MKV only, optional) mkvalidator | [42] | structural EBML errors |

Windows must be contiguous because XPSNR uses temporal activity [1]. Step 7 should cut both inputs at the same *frame index* (decode-side `trim=start_frame=` or `select`), not by seeking to keyframes; [21] shows that stream-copy cuts differ by container.

### Q4. Target quality via sampling

**ab-av1**
- **What**: crf-search is an interpolated binary search over sample encodes. Each sample is 20 s by default, there is one sample per 12 min of input (`--sample-every 12m`, `--min-samples`), and the whole input is used when samples would cover ≥ 85% of it [18][19].
  - The default target is `--min-vmaf 95` with `--max-encoded-percent 80`; `--min-xpsnr` is the alternative. The score is the **mean** of the sample scores. The CRF step is 0.1 for x265 and 0.25 for SVT-AV1 [19].
  - The maintainer: accuracy "depends on the source video"; more samples converge to a full pass [20]. The "worst sample" mode (issue #202) is still open [23].
  - A user measured x265 samples predicting VMAF 93.24 and 94.99 where full encodes scored 91.70 and 93.35, an overshoot of about 1.5 points. SVT-AV1 overshot by only 0.4-0.6 [20] [single-source].
- **Evidence**: [18][19][20][23]
- **Confidence**: high for the mechanics; low-medium for the error size.

**Av1an**
- **What**: Target quality runs **per scene chunk**, using up to 4 probes by default (`--probes`). Probes default to a fast preset unless `--probe-slow` is set. `--probing-rate 1-4` subsamples frames, and `--probe-res` sets the measurement resolution [24].
  - Supported metrics: VMAF, SSIMULACRA2, Butteraugli-inf/-3, XPSNR and weighted XPSNR. Example targets in the docs are VMAF 95, SSIMULACRA2 75-90, Butteraugli-3 1.5-2 and XPSNR 40-50 [24].
  - Aggregation is via `--probing-stat`. The default is documented inconsistently: the table says `percentile=1`, the text says `auto` [24].
  - Release v0.5.2 is from 2026-01-04 [24].
- **Evidence**: [24]
- **Confidence**: high (primary documentation).

**Targets for "transparent on a phone"**
- **What**:
  - Netflix's 2017 rule of thumb is ~6 VMAF points per JND [36].
  - A QoMEX 2022 study found the JND step varies widely from clip to clip and lists recommended steps of 2 to 6 [37].
  - RealNetworks research is quoted for > 93 being "indistinguishable or noticeable but not annoying". Other researchers saw differences below 95, with ≤ 2-point gaps not perceived [36] (secondary, older).
  - SSIMULACRA2 anchors: 80/85/90 [25]. XPSNR ~42 [31]. CVVDP: 10 JOD = identical [27].
- **Evidence**: [24][25][27][31][36][37]
- **Confidence**: medium for VMAF and SSIMULACRA2; low for XPSNR and CVVDP thresholds on video.
- **Synthesis, as starting points for calibration rather than facts**:
  - VMAF v1 3H: mean ≥ 94, 5th-percentile frame ≥ 88. The phone 5H model will read higher, so gate on 3H because desktop is also a target.
  - XPSNR-min: ≥ 40-42 dB.
  - SSIMULACRA2: mean ≥ 80, P5 ≥ 70.
  - CVVDP (`standard_phone` and `standard_fhd`): ≥ 9.5 JOD on a subset.
  - Report mean, P5 and the worst 1-s window. Ozer, ab-av1 users and Av1an's percentile default all point out that means hide bad scenes [23][24].
  - The prototype's settings (x265 CRF 28; SVT-AV1 CRF 42 at 360p) were never measured against any of these; expect them to land below transparency for categories 1, 2 and 6.

### Q5. Public test footage per category

Licences below were read from the dataset's own licence or copyright file unless marked otherwise.

| Category | Candidate | Licence | Auto-download | Format | Closeness to phone VFR |
|---|---|---|---|---|---|
| 1 Walkthrough / handheld | AOM CTC `e_nonpristine`: Shaky_Walk (1080p25, ~404 MB y4m), Shaky_Quad (1080p30), Shaky_Baseball/Fireworks (4K) [47] | CC BY-SA 4.0 (YouTube vlog excerpts) [47] | yes, plain HTTP | y4m CFR, 8/10-bit | handheld UGC, already compressed; CFR, no rotation/VFR |
| 1/6 | YouTube UGC `Vlog`, `VerticalVideo` (360p-4K, 20 s) [48] | CC BY per clip (ATTRIBUTION file), CC licence text in bucket [48] | yes: public GCS bucket listable via JSON API; raw originals 1.2-3.7 GB/clip, `original_videos_h264` CRF10 MP4 12-115 MB [48] | raw `yuv420p` tv range, CFR 30 (probed) [48] | real UGC incl. phones; CFR, limited range |
| 1 | AOM CTC `a2_2k`: WalkingInStreet, Vertical_Carnaby, Vertical_bees [47] | CC BY-SA 4.0 [47] | yes | y4m | handheld-ish, vertical |
| 2 Dance | AVT-VQDB-UHD-1 `Dancers_8s` (UHD, 60 fps source) [50] | CC BY-NC 4.0 (TU Ilmenau own content) [50] | yes, `download.py` (whole DB ~55 GB; sources selectable) [50] | encoded segments + sources | studio, tripod |
| 2 | Netflix `RitualDance` 1080p59.94 10-bit, 130 frames (AOM CTC) [47] | CC BY-NC-ND 4.0 [47] | yes | y4m | pro camera; ND is fine for local benchmarking, not for redistributing encodes |
| 3 Static room | Johnny, KristenAndSara 720p60 [47][46] | public domain (per copyright file) [47] | yes | y4m | static webcam-like |
| 3 | Vidyo3/Vidyo4, FourPeople [46][47] | **conflict**: derf lists vidyo as public domain [46], the AOM copyright file restricts Vidyo4 to standards work [47] | yes | y4m | avoid Vidyo3/4 until clarified |
| 3/4 | YouTube UGC `Lecture`, `HowTo` [48] | CC BY [48] | yes | raw CFR | lecture rooms, slides |
| 4 Webinar / screen | AOM CTC `b2_scc`: Wikipedia (CC0), Spreadsheet and Debugging (Netflix, CC BY 4.0, 130 frames), MobileDeviceScreenSharing / SceneComposition (CC BY-SA 4.0) [47] | as listed | yes | y4m 1080p 15-60 fps | true screen content |
| 4 (exclude) | Slides1 / Slides2r (Tencent) [47]; JCT-VC SCC class F material [59] | standards-development use only [47] | technically yes, licence no | | do not ship in a public tool |
| 5 Video calls | Microsoft VCD: 160 clips, 1080p30, 10 s, webcam talking head, background replace/blur, mobile [49] | data CDLA-Permissive-2.0, code MIT [49] | yes, `download-vcd1-*.sh` / `downloader.py` [49] | YUV and MP4 | camera-side capture, *not* yet call-compressed; simulate the call codec yourself |
| 6 General phone | LIVE-VQC: 585 videos, 101 devices, 80 users [52]; LIVE-Qualcomm: 208 videos, 8 phones [53] | free for research, request form [52][53] | no (form) | phone originals | closest to real phone capture |
| 6 | KoNViD-1k (YFCC100M Flickr sample) [54] | rights statement "terms-of-use" / in-copyright on the repository page [54] | unclear | | UGC |
| any | Netflix Open Content (Meridian, Sparks, El Fuente, Chimera...) [51] | CC BY 4.0 (per listings) [51] | yes (S3 bucket) | pro masters | not phone-like |
| any | Xiph derf (classic + 1080p/4K) [46] | "believed to be freely redistributable", per-file terms [46] | yes | y4m | mostly broadcast/studio |
| any | Pexels videos via API [55][56] | free use, no attribution required; no redistribution on other stock platforms; API needs a key, 200 req/h, attribution link required for API use [55][56] | yes with user's key | Pexels-served MP4 | stock; whether files keep the uploader's phone VFR or rotation is unknown |
| any | Pixabay [57] | free use; no standalone redistribution [57] | API terms not checked | | |
| any | Wikimedia Commons [58] | per-file CC | yes | WebM/VP9 preferred; MP4/H.264 apparently not accepted (mirror, low confidence) [58] | re-encoded, not originals |

**Synthesis**:
- No auto-downloadable corpus has Android-style VFR, `yuvj420p` full range, rotation matrices, GPS and `creation_time` tags.
- The benchmark should therefore (a) take CFR public clips and generate "phone-ified" variants: H.264 or HEVC re-encode at phone bitrates, full-range flag, `-display_rotation 90`, jittered VFR timestamps, and an MKV screen-recording variant; and (b) let the owner contribute a handful of their own phone clips under CC0. Only (b) tests the real decoder and timestamp quirks.
- Commit only download manifests (URL + SHA + licence), never media. NC/ND and BY-SA terms are fine for local measurement but would bind redistributed encodes.

---

## Perspectives

- **Mean vs worst case.** ab-av1's maintainer argues sampling predicts the *average* VMAF, so averaging samples is correct [23]. Users and Av1an's percentile-style default argue a single bad scene ruins the encode, so the gate should be the worst sample or a low percentile [23][24]. Both hold: the mean predicts size and quality on average, while percentiles protect against visible failures. For archival transparency, the low-percentile view matters more.
- **Which metric "wins" near transparency.**
  - CVVDP leads overall in the 2025 high-fidelity study [29]. On the ≤ 1 JND subset, Butteraugli, HDR-VDP-3 and NLPD edge it on SROCC [29], and the codec wiki calls Butteraugli-vs-SSIMULACRA2 at very high fidelity "debatable" [32].
  - Netflix claims v1 fixes the v0 weaknesses [14], but VMAF v1 has not yet been independently benchmarked against CVVDP or SSIMULACRA2 (none found).
  - XPSNR's authors claim parity with VMAF [30]; independent high-quality validation is thin.
- **Ship VFR or force CFR.** One ab-av1 user's position is "VFR = problems … at some point you'll regret those files" [22]. The ffmpeg docs and ab-av1's own choice of `passthrough` preserve source timing [4][18]. For an archive that keeps creation timing and audio sync, passthrough is the lower-risk default; CFR conversion changes the content and needs its own reference pipeline.

## Practical Implications

1. **Toolchain**: keep the static BtbN ffmpeg. It already links a libvmaf with v1 models built in [16][15]. Add `vszip` or `fssimu2` for SSIMULACRA2 on CPU [26][33], and `cvvdp` via uv for subset runs [27]. Vship is worth a test only if a GPU is present; its Vulkan backend is "very new and experimental" [26].
2. **Benchmark matrix metrics**:
   - Run on every clip: VMAF v1 `3d0h` + `5d0h` (`_hfr` for 50/60 fps) at 10-bit, and XPSNR-min.
   - Run on a stratified subset: SSIMULACRA2 (mean, P5, min) and CVVDP (`standard_phone`, `standard_fhd`).
   - Keep VMAF v0.6.1 and NEG only for comparison with the January prototype.
3. **Encode settings that measurement depends on**: `-fps_mode passthrough`; mux once into the final container (no remux, `cues_to_front` or `faststart` second pass unless verified afterwards); explicit `color_range`; temp name, then rename after verification [18][21][5].
4. **Sampling in benchmark mode**: throughput is not critical, so use full-file measurement for clips under ~3 min. That covers most phone clips; ab-av1 would sample these as a single 20-s window or the whole file anyway [19]. For long webinars and sessions, use 6-10 windows of 10-20 s chosen by scene change, plus one full-pass validation per preset to measure the sample-vs-full offset (x265 showed ~1.5 VMAF overshoot [20]).
5. **Per-category gates**: calibrate the thresholds per category from the benchmark rather than using one number. Category 4 leans on XPSNR-Y and SSIMULACRA2 worst-frame plus a text-crop visual check. Category 5's targets should be relative to the already-degraded source (BVI-UGC [34]).
6. **Corpus manifest v1**:
   - Shaky_Walk and Shaky_Quad; 2 YouTube UGC Vlog and 2 VerticalVideo clips (h264 CRF10 variants to save bandwidth).
   - AVT `Dancers_8s`; RitualDance.
   - Johnny, KristenAndSara, 2 UGC Lecture clips.
   - Wikipedia, Spreadsheet, Debugging, MobileDeviceScreenSharing.
   - 4 VCD clips (TH, TH-BB, TH-M).
   - 3-5 owner CC0 phone clips.
   - Plus synthetic phone-ified variants of 3 of the above.

## Sources

Primary = official documentation, source code, dataset owner files, or the original paper. Secondary = blogs, forums, wikis, mirrors.

1. [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) - libvmaf, xpsnr, scale (ref input, range), framesync options. Primary. Also the [vf_xpsnr.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_xpsnr.c) source (read 2026-10-20).
2. [FFmpeg Changelog](https://github.com/FFmpeg/FFmpeg/blob/master/Changelog) - 7.1: scale ref input, scale2ref deprecated, YUVJ obsoleted. Primary.
3. [ffmpeg-cvslog: deprecate scale2ref in favor of scale=rw:rh](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2024-May/142854.html) - deprecation commit, 2024. Primary.
4. [ffmpeg CLI documentation](https://ffmpeg.org/ffmpeg.html) - input `-r`, `-fps_mode`, `-autorotate`, `-display_rotation`, `-xerror`. Primary.
5. [FFmpeg Formats Documentation](https://ffmpeg.org/ffmpeg-formats.html) - Matroska `cues_to_front`, `reserve_index_space`, `write_crc32`; MP4 `faststart`, unfinished MP4 undecodable. Primary.
6. [FFmpeg Codecs Documentation](https://ffmpeg.org/ffmpeg-codecs.html) - `err_detect` flags. Primary.
7. [vf_libvmaf.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_libvmaf.c) - colour-range mismatch warning, accepted pixel formats. Primary (code).
8. [matroskadec.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/matroskadec.c) - CRC32 elements skipped, not verified. Primary (code).
9. [VMAF Models (v1)](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v1.md) - v1 model table, phone 5H, HFR, 10-bit, CAMBI encode-side params. Primary.
10. [VMAF Models (v0)](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v0.md) - v0.6.1 3H, phone model, 4K 1.5H, NEG. Primary.
11. [VMAF FAQ](https://github.com/Netflix/vmaf/blob/master/resource/doc/faq.md) - upscale distorted to reference, pooling. Primary.
12. [Using VMAF with FFmpeg](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) - timestamp sync, `-r` before `-i`, bicubic. Primary.
13. [VMAF releases](https://github.com/Netflix/vmaf/releases) - v3.2.0 (2026-06-20, VMAF v1), v3.2.1 (2026-09-14). Primary.
14. [Netflix Tech Blog: VMAF v1: Good Is Not Good Enough](https://netflixtechblog.com/vmaf-v1-good-is-not-good-enough-60d7e4244ea8), 2026-06-19, read via [republication](https://noise.getoto.net/2026/06/20/vmaf-v1-good-is-not-good-enough/) because the original returned 403. Primary content.
15. [libvmaf model.c](https://github.com/Netflix/vmaf/blob/master/libvmaf/src/model.c) - built-in v1 model names. Primary (code).
16. [BtbN FFmpeg-Builds 45-vmaf.sh](https://github.com/BtbN/FFmpeg-Builds/blob/master/scripts.d/45-vmaf.sh) - pinned libvmaf commit (after v3.2.1). Primary.
17. [ab-av1 README](https://github.com/alexheretic/ab-av1) - crf-search, XPSNR, VMAF auto model/scale. Primary.
18. [ab-av1 CHANGELOG](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md) and [releases](https://github.com/alexheretic/ab-av1/releases) - v0.11.7 (2026-08-21) `--verify`, passthrough, sample defaults. Primary.
19. [ab-av1 source](https://github.com/alexheretic/ab-av1/tree/main/src) - `args/vmaf.rs`, `vmaf.rs`, `args.rs`, `crf_search.rs`, `encode.rs`, `ffmpeg.rs` (read 2026-10-20). Primary (code).
20. [ab-av1 #220: x265 VMAF estimations higher than full analysis](https://github.com/alexheretic/ab-av1/issues/220) - sample vs full numbers. Secondary (user data).
21. [ab-av1 #333: matching containers / timebase issues](https://github.com/alexheretic/ab-av1/issues/333) - fps_mode auto drop/dup measurement. Secondary.
22. [ab-av1 #311: crf-search fails on VFR video](https://github.com/alexheretic/ab-av1/issues/311) - VFR desync. Secondary.
23. [ab-av1 #202: crf-search using worst sample only](https://github.com/alexheretic/ab-av1/issues/202) - mean vs worst debate. Secondary.
24. Av1an docs: [Target Quality CLI](https://github.com/rust-av/Av1an/blob/master/site/src/Cli/target_quality.md), [Target Quality feature](https://github.com/rust-av/Av1an/blob/master/site/src/Features/TargetQuality.md), [VMAF CLI](https://github.com/rust-av/Av1an/blob/master/site/src/Cli/vmaf.md); releases (v0.5.2, 2026-01-04). Primary.
25. [cloudinary/ssimulacra2](https://github.com/cloudinary/ssimulacra2) - score anchors, KonFiG/CID22 correlation tables. Primary.
26. [Vship (Codeberg)](https://codeberg.org/Line-fr/Vship) - GPU SSIMULACRA2/Butteraugli/CVVDP, FFVship, CPU/GPU timings. Primary.
27. [ColorVideoVDP repository](https://github.com/gfxdisp/ColorVideoVDP) and its `display_models.json` - JOD scale, CPU caveat, display models; v0.5.7 (2026-08-02). Primary.
28. [Mantiuk et al., ColorVideoVDP (arXiv 2401.11485)](https://arxiv.org/abs/2401.11485) - SIGGRAPH 2024 paper. Primary.
29. [Mohammadi et al., Evaluation of Objective IQ Metrics for High-Fidelity Image Compression (arXiv 2509.13150)](https://arxiv.org/html/2509.13150v1) - 2025, CVVDP/SSIMULACRA2/Butteraugli/VMAF(-NEG) on JPEG AIC-3. Primary.
30. [Helmrich et al., XPSNR study, ITU Journal ICT Discoveries 2020](https://www.itu.int/en/journal/2020/001/Pages/08.aspx) - XPSNR vs VMAF PLCC. Primary (older than 2024).
31. [codecs.wiki: XPSNR](https://codecs.wiki/docs/metrics/XPSNR) - speed, ~42 threshold, min vs weighted. Secondary.
32. [codecs.wiki: SSIMULACRA2](https://codecs.wiki/docs/metrics/SSIMULACRA2) - video tooling overview. Secondary.
33. [fssimu2](https://github.com/gianni-rosato/fssimu2) - fast SSIMULACRA2, accuracy vs reference. Primary.
34. [BVI-UGC (arXiv 2408.07171)](https://arxiv.org/abs/2408.07171) - FR metrics with non-pristine references, SROCC < 0.6. Primary.
35. [MSU video compression metric benchmark (arXiv 2211.12109)](https://arxiv.org/pdf/2211.12109) - NeurIPS 2022, metrics weakest at high bitrates. Primary (older).
36. [Ozer: Finding the Just Noticeable Difference with Netflix VMAF](https://streaminglearningcenter.com/blogs/finding-the-just-noticeable-difference-with-netflix-vmaf.html) - 6-point JND, 93/95 thresholds. Secondary (2017-era).
37. [QoMEX 2022 VMAF JND poster](https://athena.wp.itec.aau.at/wp-content/uploads/sites/12/2022/07/QoMEX_22__VMAF_JND_Poster.pdf) - JND step varies per clip. Primary.
38. [FFmpeg-devel: vf_libvmaf warn when color ranges differ](https://ffmpeg.org/pipermail/ffmpeg-devel/2023-March/308068.html) - 2023. Primary.
39. [FFmpeg trac #8455: yuvj420p → yuv420p range](https://fftrac-bg.ffmpeg.org/ticket/8455) - range squeeze, workarounds. Primary (2021).
40. [FFmpeg trac #11649 (2025-06)](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-June/073944.html) - unexpected display matrix since 7.1. Primary.
41. [ffmpeg-user: Verify integrity of a video file?](https://lists.ffmpeg.org/pipermail/ffmpeg-user/2015-November/029162.html) - ffmpeg is lenient, not a validator. Secondary (2015).
42. [mkvalidator](https://www.matroska.org/downloads/mkvalidator.html) - checks, v0.6.0 (2021). Primary.
43. [FFmpeg-devel: Matroska timestamp precision option (2021)](https://ffmpeg.org/pipermail/ffmpeg-devel/2021-May/280479.html) - 1 ms precision issue at 59.94. Primary.
44. [FFmpeg-devel: matroskaenc reserved Cues space (2020)](https://ffmpeg.org/pipermail/ffmpeg-devel/2020-April/259590.html) - historic overwrite bug. Primary (older).
45. [slhck/ffmpeg-quality-metrics](https://github.com/slhck/ffmpeg-quality-metrics) - Python wrapper, input checks, v1 needs libvmaf ≥ 3.2.1; v3.13.0 (2026-10-14). Primary.
46. [Xiph.org Derf's Test Media Collection](https://media.xiph.org/video/derf/) - sequences, licence notes. Primary.
47. [AOM CTC test set on media.xiph.org](https://media.xiph.org/video/aomctc/test_set/) - `b2_scc`, `e_nonpristine`, `a2_2k`, `a3_720p` and per-file `*_Copyright.txt` (read 2026-10-20). Primary.
48. [YouTube UGC dataset bucket](https://storage.googleapis.com/ugc-dataset/LICENSE) (LICENSE, ATTRIBUTION, folder listing) and [paper arXiv 1904.06457](https://arxiv.org/abs/1904.06457). Primary.
49. [microsoft/VCD](https://github.com/microsoft/VCD) and [arXiv 2309.07376](https://arxiv.org/abs/2309.07376) - video-conferencing dataset, CDLA-Permissive-2.0. Primary.
50. [AVT-VQDB-UHD-1](https://github.com/Telecommunication-Telemedia-Assessment/AVT-VQDB-UHD-1) - download tool, per-source licences incl. `Dancers_8s`. Primary.
51. [Netflix Open Content](https://sites.google.com/netflix.com/opencontent) - CC BY 4.0 assets, S3 bucket. Primary (licence wording confirmed only via third-party listing).
52. [LIVE Video Quality Challenge (VQC) Database](https://www.colorado.edu/lab/live/live-video-quality-challenge-vqc-database) - 585 phone videos. Primary.
53. [LIVE-Qualcomm Mobile In-Capture Database](https://www.colorado.edu/lab/live/live-qualcomm-mobile-capture-video-quality-database) - 208 phone videos, form. Primary.
54. [KoNViD-1k (KOPS repository)](https://kops.uni-konstanz.de/entities/publication/ff476626-4219-4e08-9a02-f162eba305fc) - YFCC100M sample, terms-of-use. Primary.
55. [Pexels License](https://www.pexels.com/license/) - free use, redistribution limits. Primary.
56. [Pexels API documentation](https://www.pexels.com/api/documentation/) - attribution, rate limits, `video_files` fields. Primary.
57. [Pixabay Content License summary](https://pixabay.com/service/license-summary/) - standalone redistribution banned. Primary.
58. [Commons:Video (mirror)](https://c.enwp.org/wiki/Commons:Video) - accepted formats. Secondary (mirror; not verified on commons.wikimedia.org).
59. [ITU-T/JCT-VC call for screen content test material (Class F)](https://itu.int/en/ITU-T/studygroups/com16/video/Pages/rfs201101.aspx) - SCC sequences. Primary (2011).
60. [Perceptual Video Quality Assessment: A Survey (arXiv 2402.03413)](https://arxiv.org/pdf/2402.03413) - SCVD, CSCVQ datasets. Primary.
61. [User-generated Video Quality Assessment: A Subjective and Objective Study (arXiv 2005.08527)](https://arxiv.org/pdf/2005.08527) - metrics worst on screen content. Primary (2020).
62. [FFAStrans forum: VMAF n_threads speed](https://ffastrans.com/frm/forum/viewtopic.php?p=8886) - ~22 → ~100 fps 1080p. Secondary, single-source.
63. [VideoHelp forum: Android VFR example](https://forum.videohelp.com/showthread.php?p=2714018) - 14.9-32.0 fps around a 29.68 average. Secondary.

## Gaps (what to measure in the project's own benchmark)

1. **Metric speed on the 7950X3D**, in frames per second for 1080p and 4K: libvmaf v1 with `n_threads` 16/32 (8-bit vs 10-bit input), XPSNR (single-threaded filter, so check parallel processes), vszip vs fssimu2 SSIMULACRA2, Butteraugli, CVVDP on CPU. Also full-decode speed of HEVC/AV1 outputs with `-xerror`, which sets the verifier budget.
2. **VMAF v1 vs v0.6.1 vs SSIMULACRA2 vs CVVDP agreement** on this project's own clips, with a small blind A/B on the actual phones (iPhone and Android, ~2 years old) to anchor the per-category thresholds. No independent v1 validation was found.
3. **Screen content**: whether any metric tracks text legibility in webinar captures. The searches found no 2024-2026 study (budget ran out). Test on AOM `b2_scc` and a cropped text-region comparison.
4. **Sample vs full-encode offset** per preset (x265 slow/veryslow, SVT-AV1 2-6) and per category; check the reported x265 ~1.5 VMAF overshoot [20].
5. **Default range handling** of the current static ffmpeg + libx265/libsvtav1 for `yuvj420p` sources: does the output come out full-range-flagged, limited, or mis-squeezed? Verify with ffprobe plus a range-mismatch test of libvmaf.
6. **Rotation**: does the chosen encode path bake the rotation or keep the display matrix, and do Google Photos, Apple Photos, Synology Photos and Immich honour it? (Overlaps with T-threads on playback.)
7. **Root cause of the prototype's corrupt MKV and "hanging" playback**: reproduce with and without `cues_to_front` and remux, at 59.94 fps with 1 ms Matroska timestamps, and check mkvalidator and decode results.
8. **Not researched (budget)**: MP4Box/GPAC `-info` style MP4 validation; Pixabay API terms; current Wikimedia Commons MP4 policy; KoNViD-1k file licence details; AIST Dance DB terms; whether Pexels-served files preserve VFR and rotation.
9. **Corpus closeness**: every auto-downloadable corpus found is CFR and limited range. Validate that the synthetic "phone-ified" variants reproduce the decoder and timestamp behaviour of real Android files; the owner's CC0 clips are the ground truth.
