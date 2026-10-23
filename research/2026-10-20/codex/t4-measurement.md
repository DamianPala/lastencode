I’ll research the four questions in parallel as a source-driven review, prioritizing 2025–2026 papers and official tool documentation. I’ll also check older standards where they still define the metric or workflow, and label those as older evidence.

The measurement literature and tool documentation point to a key benchmark rule: align decoded presentation timestamps and viewing resolution before scoring. I’m now checking what practical verification can catch cheaply, then I’ll compare available corpora against the six content types.

### TL;DR

For this project, use **VMAF v1 with the phone model as the main practical score**, **XPSNR as a second video metric**, and sampled **SSIMULACRA2 or ColorVideoVDP** to expose detail or temporal issues that a single average can miss. There is no evidence-backed score that guarantees “transparent on a phone”; calibrate candidate thresholds with blind comparisons on representative footage and actual phones. [1][5][6][7]

For real-world sources, preserve presentation timestamps and normalize rotation, range, dimensions, and pixel format deliberately before scoring. A quick check can catch many failures, but only a full decode checks every frame; sampled checks cannot safely authorize deleting the original. [3][4][11][12][14]

### Key Findings

#### 1. Metrics for near-transparent encodes

**What:** Based on Netflix’s current model documentation, VMAF v1 offers a 1080p phone model calibrated for a 5H viewing distance, alongside standard 1080p and two 4K models. It recommends 10-bit precision for SDR measurement to better detect banding, even when the encoded video is 8-bit. The older v0.6.1 models include NEG variants, which remove enhancement gain; don’t assume the new phone model has an equivalent NEG option. [1][2]

For practical CPU scoring, FFmpeg includes XPSNR, a perceptually weighted PSNR metric. SSIMULACRA2 is available through libjxl, but it is an image metric: use it on selected frames, not as the sole score for a video. ColorVideoVDP models spatial and temporal vision and has a Python package; its authors report gains over other metrics, including VMAF, on their evaluated datasets. Those datasets do not establish that it wins on this project’s phone footage or six content categories. [5][6][7][8]

**Synthesizing across sources:** Use VMAF v1 phone as the primary phone-viewing score, XPSNR as an independent check, and sampled-frame SSIMULACRA2 for fine detail such as hair, clothing edges, and text. Add ColorVideoVDP in benchmark mode if its CPU runtime is acceptable. Treat a metric disagreement as a reason to inspect the affected scenes, not to average unlike score scales. VMAF is available through FFmpeg only when built with `libvmaf`; XPSNR is an FFmpeg filter, while ColorVideoVDP’s reference Python implementation recommends CUDA for acceleration but can run without it. [3][5][6][8]

**Evidence:** [1][2][3][5][6][7][8]  
**Confidence:** Medium. Tool capabilities and model viewing conditions are documented; the best metric for these particular sources remains untested.

#### 2. Aligning real-world sources before measurement

**What:** Based on Netflix and FFmpeg documentation, VMAF compares frames through timestamps, so reset each input’s time base and start time consistently. The documented pattern is `settb=AVTB,setpts=PTS-STARTPTS` on both inputs. FFmpeg autorotates from display-matrix metadata by default; either let it rotate both inputs or disable it for both and normalize orientation explicitly. `scale2ref` is deprecated; FFmpeg documents using `scale` with a split reference input instead. [3][4][11][12][13]

For a downscaled encode, score it at the intended display/model resolution by scaling the encoded output up to that resolution. VMAF expects equal dimensions and pixel formats; its documentation warns that comparing at the lower encoded resolution can miss the loss from downscaling. Range should follow the actual signal metadata: the prototype’s `yuvj420p` sources are full-range, so blindly treating them as limited-range can contaminate scores. [3][4][11]

**Synthesizing across sources:** For VFR, do not force both inputs to a nominal `fps` as a default metric fix. That can hide dropped or repeated frames. Preserve timestamps for the main comparison, check cadence and frame counts separately, and only resample both streams when measuring a deliberately normalized playback cadence. For CFR outputs from VFR originals, timestamp-based pairing is more appropriate than assuming frame *n* in one file corresponds to frame *n* in the other. [3][11][12]

A starting filter graph for equal-rate, equal-orientation inputs is:

```text
[0:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p10le[dist];
[1:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p10le[ref];
[dist][ref]libvmaf=...
```

Add explicit rotation and scale handling before the format conversion, and set range conversion from the source and output metadata. For a downscaled output, scale `[dist]` to the reference/display dimensions; do not downscale the reference to match it. [3][4][11][12][13]

**Evidence:** [3][4][11][12][13]  
**Confidence:** High for timestamp, dimension, and rotation handling; medium for a single “best” VFR policy, because the right frame pairing depends on whether the output intentionally changed cadence.

#### 3. Fast verification after each encode

**What:** Based on ab-av1’s implementation, a useful low-cost verification includes a complete decode and a duration comparison; it specifically checks decode errors because an encoder can exit successfully while producing a cut or damaged output. A full FFmpeg decode with `-xerror` is the stronger corruption check. It may take longer than a minute for long files, so a sampled decode is a speed-versus-coverage tradeoff, not an equivalent check. [14][15]

Check that expected video and audio streams exist, their codecs and dimensions are correct, and their start times and durations are plausible. Compare packet counts and timestamps as diagnostics; use decoded-frame counts when a full decode is already running. Check DTS monotonicity in packet order, but do not require PTS to be monotonic in packet order because reordered frames can have different presentation order. For Matroska, `mkvalidator` checks specification conformance; it does not prove that every frame decodes or plays correctly. For MP4, GPAC’s `inspect` can report tracks and packet details. [11][16][17][18]

**Synthesizing across sources:** A fast per-file pass can combine `ffprobe` stream/container checks, duration and timestamp checks, and a full decode if it fits the time budget. If it does not, decode short windows from the start, middle, and end, while clearly treating that as a smoke test. For optional original deletion, require a full decode and the project’s other verification checks. Container checks are useful additions, not substitutes for decoding. A public OBS issue documents a remux report involving choppy playback and a missing B-frame, but it does not establish the cause of the prototype’s intermittent MKV corruption. [14][16][17][18][19]

**Evidence:** [11][14][16][17][18][19]  
**Confidence:** High for what the tools check; low for the frequency and causes of real-world remux defects, which the cited report cannot quantify.

#### 4. Sample-based CRF search and quality targets

**What:** Based on current ab-av1 documentation and changelog, its sample workflow uses 20-second samples by default, spaced at a default interval of 12 minutes, then searches CRF using the measured metric. Av1an probes chunks, allows up to four probes by default, and can use a faster probing rate or faster settings. These are practical search heuristics, not a guarantee that the selected CRF will meet the target on every scene in a full encode. [14][15][20]

There is no documented universal VMAF, XPSNR, or SSIMULACRA2 threshold for “visually transparent on a phone.” The available VMAF models define viewing conditions and score ranges, while ColorVideoVDP and screen-content work evaluate metric performance on specific study sets; none supplies a general threshold for this project’s footage. [1][7][9][10]

**Synthesizing across sources:** Start with 20–30 second windows selected across the clip, including motion, fine detail, static scenes, and scene changes. For a heterogeneous long clip, pilot a set of roughly 6–10 windows, report the mean plus a low percentile and worst window, then compare the prediction against a full encode. These counts are a proposed starting experiment, not a published optimum. For threshold calibration, try a small phone-VMAF ladder such as 95, 97, and 99, then run blind A/B comparisons on actual phones and select the smallest encode that consistently passes. Treat those scores as pilot points, not established transparency cutoffs. [1][14][15][20]

**Evidence:** [1][7][9][10][14][15][20]  
**Confidence:** High that sample search is approximate and no universal threshold is documented; low for any proposed sample count or score ladder until calibrated on this project’s footage.

#### 5. Public test footage and fit to the six categories

The closest matches are uneven: recent screen-content corpora are useful for webinars and calls; LIVE-VQC is unusually close to handheld phone capture; and public codec datasets provide reproducible clips but are generally not raw phone originals. License and provenance need to be recorded per asset. [9][10][21][22][23][24][25][26][27]

| Project category | Best candidates and limits |
|---|---|
| Apartment walkthroughs / handheld motion | **LIVE-VQC** contains 585 authentic videos captured by 80 users on 101 devices. Its usage terms permit copying and distribution with the stated copyright notice and acknowledgement. It is a strong capture-style proxy, but its videos are authentically distorted rather than pristine source references. **YouTube UGC** offers 1,500 user-uploaded clips under CC BY with attribution, across categories including how-to, technology reviews, gaming, and pets; it includes real-world issues such as camera shake, but the videos are already UGC uploads, not guaranteed raw phone masters. [23][24] |
| Dance / people moving | **AVT-VQDB-UHD-1** includes `Dancers_8s`, which is a strong content match and downloadable through the project’s tool. The dataset says its own footage is CC BY-NC 4.0, so do not bundle or redistribute those clips as general public benchmark assets without resolving the license fit. **Netflix Open Content** offers live-action 4K material, including 4096×2160, 60 fps El Fuente clips; check each title’s license file. These are controlled test sources, not smartphone VFR. [21][22] |
| Static room / session recordings | **LIVE-VQC** and **YouTube UGC** can supply talking-head or tutorial-like material after curation, but neither guarantees a static-room session recording with clean, original source video. This category remains a gap for a close match. [23][24] |
| Webinars / slides and text | The 2025 **screen-content video dataset** is a strong match: it contains screen content captured from video-conferencing apps, including presentations, code, browsing, spreadsheets, and mixed interfaces. Its site describes 1080p30 reference videos and says access is by request. The **AIM 2025 screen-content challenge** makes processed videos and subjective votes publicly available, useful for evaluating metric behavior on screen material. JCT-VC’s SCC sequences are a legacy coding-test resource for rendered text and graphics, rather than modern webinar captures. [9][10][26] |
| Zoom-style calls | The conferencing-app screen-content dataset is a useful proxy for call video and screen-sharing quality, but it does not establish coverage of the exact two-large-talking-head layout. The project should add a curated two-person call sample if that layout is important. [9][10] |
| Holiday / everyday clips | **LIVE-VQC** is the closest phone-capture corpus; **YouTube UGC** supplies broad, already-compressed real-world clips. **KoNViD-1k** adds 1,200 eight-second in-the-wild videos and subjective scores, but is described as freely available to the research community; its page does not establish broad redistribution rights for a public CLI benchmark. [23][24][25] |

**Synthesizing across sources:** Xiph’s Derf collection is useful for reproducible codec comparisons, but it mixes licenses and includes old test material, so check each item rather than treating the collection as uniformly redistributable. Wikimedia Commons can support a small curated sample set if the benchmark records each file’s license and attribution. Pexels and Pixabay prohibit bulk or systematic copying without permission, so avoid automated collection from those services as the default benchmark downloader. [22][27][28][29]

**Evidence:** [9][10][21][22][23][24][25][26][27][28][29]  
**Confidence:** Medium. Dataset characteristics and stated terms are documented, but actual content fit requires inspecting the selected clips and their per-file metadata.

### Perspectives

- **Best general predictor:** ColorVideoVDP’s authors report substantial gains over the next-best metric, VMAF, on the datasets they evaluated. That supports testing it in benchmark mode, but does not prove it will rank encodes best for phone-captured home video. [7]
- **Best practical default:** VMAF has a directly relevant phone viewing model and a mature FFmpeg workflow. Its score remains a model prediction, so it should not be read as a universal “transparent” certificate. [1][3][4]
- **Best screen-content approach:** The 2025 screen-content dataset and AIM challenge supply recent, relevant test material and subjective comparisons. They do not establish one metric as the correct metric for all slide, text, and call footage. [9][10]
- **Best detail checks:** SSIMULACRA2 and Butteraugli can help inspect frame-level spatial differences, but image metrics alone do not measure temporal cadence, flicker, or motion artifacts. SSIMULACRA2’s implementation is an image comparison tool tuned against subjective image datasets. [6]

### Practical Implications

For the project’s benchmark matrix, include:

- **Video metrics:** VMAF v1 phone at 1080p; a VMAF 4K model for 4K-target viewing; XPSNR; and sampled ColorVideoVDP if it runs acceptably on the CPU. Record the model, normalization, scaling, range, and timestamp policy with every score. [1][3][5][8]
- **Detail and screen checks:** Sampled SSIMULACRA2 for dance hair/clothing and slide/text frames. Keep a dedicated screen-content set rather than assuming natural-video VMAF rankings transfer to webinars. [6][9][10]
- **Per-category reporting:** Store mean, P5/P10, and worst-window values alongside bitrate and encode settings. Select samples that include both ordinary scenes and category-specific stress cases. This is a proposed design based on the documented limitations of aggregate metrics and sample-based search. [4][14][15][20]
- **Verification tiers:** Run stream, duration, timestamp, and container checks after every file; add sampled decode only as a speed compromise. Require a full decode before any optional original deletion. [14][16][17][18]
- **Corpus strategy:** Start with LIVE-VQC for handheld capture, the 2025 screen-content dataset/AIM data for conferencing and slides, and selected CC-licensed YouTube UGC or Wikimedia clips. Keep an attribution/license manifest and do not automate downloads from Pexels/Pixabay without permission. [9][10][23][24][27][28][29]

### Sources

1. [Netflix VMAF v1 models](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v1.md) — Primary, current phone/1080p/4K models and viewing conditions.
2. [Netflix VMAF v0 models](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v0.md) — Primary, older 0.6.1 models and NEG variants.
3. [Netflix VMAF FFmpeg documentation](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) — Primary, timestamp alignment and FFmpeg usage.
4. [Netflix VMAF FAQ](https://github.com/Netflix/vmaf/blob/master/resource/doc/faq.md) — Primary, scaling and score interpretation notes.
5. [FFmpeg XPSNR implementation docs](https://www.ffmpeg.org/doxygen/trunk/vf__xpsnr_8c.html) — Primary, describes the XPSNR filter.
6. [libjxl SSIMULACRA2 implementation](https://github.com/libjxl/libjxl/blob/main/tools/ssimulacra2.cc) — Primary, metric design and subjective-image calibration.
7. [ColorVideoVDP paper](https://www.cl.cam.ac.uk/~rkm38/pdfs/mantiuk2024_ColorVideoVDP.pdf) — Primary research, metric comparison results and limitations.
8. [ColorVideoVDP repository](https://github.com/gfxdisp/colorvideovdp) — Primary, Python installation, CLI, display settings, and acceleration options.
9. [Screen content video dataset and benchmark](https://videoprocessing.github.io/screen-content-dataset) — Primary research dataset page, conferencing-app screen content and access details.
10. [AIM 2025 screen-content VQA challenge](https://openaccess.thecvf.com/content/ICCV2025W/AIM/html/Safonov_AIM_2025_Challenge_on_Screen-Content_Video_Quality_Assessment_Methods_and_ICCVW_2025_paper.html) — Primary challenge report and public dataset link.
11. [FFmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) — Primary, VMAF, scaling, range, and framesync filter behavior.
12. [FFmpeg command-line documentation](https://ffmpeg.org/ffmpeg.html) — Primary, autorotation and decode-error options.
13. [FFmpeg `scale2ref` deprecation patch](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-May/326625.html) — Primary, documented replacement pattern.
14. [ab-av1 project](https://github.com/alexheretic/ab-av1) — Primary, sample encode, CRF search, and verification behavior.
15. [ab-av1 changelog](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md) — Primary, sample duration/interval defaults and VMAF alignment changes.
16. [Matroska mkvalidator](https://www.matroska.org/downloads/mkvalidator.html) — Primary, container conformance checks and latest listed release date.
17. [GPAC file inspection guide](https://www.dev.wiki.gpac.io/Howtos/inspecting/) — Primary, MP4 packet and track inspection.
18. [FFmpeg command-line docs](https://ffmpeg.org/ffmpeg.html) — Primary, full decode and error handling options.
19. [OBS remux issue](https://github.com/obsproject/obs-studio/issues/8970) — Primary issue report of a specific remux playback/frame problem.
20. [Av1an target-quality documentation](https://rust-av.github.io/Av1an/Cli/target_quality.html) — Primary, probes, probing rate, and quality-search options.
21. [Netflix Open Content](https://opencontent.netflix.com/home) — Primary, downloadable live-action test material and per-title assets.
22. [Xiph Derf test media collection](https://media.xiph.org/video/derf/) — Primary, codec test clips and per-entry license/readme links.
23. [LIVE-VQC database](https://live.ece.utexas.edu/research/LIVEVQC/index.html) — Primary, mobile capture corpus and reuse terms.
24. [YouTube UGC dataset announcement](https://www.googblogs.com/launching-a-youtube-dataset-of-user-generated-content/) — Primary, dataset access, CC BY notice, and content description.
25. [KoNViD-1k database](https://database.mmsp-kn.de/konvid-1k-database.html) — Primary, video count, duration, access, and research-use description.
26. [HEVC Screen Content Coding extension](https://hevc.hhi.fraunhofer.de/scc) — Primary, SCC use cases and legacy test material.
27. [Wikimedia Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:First_steps/Reuse/en) — Primary, per-file license and attribution guidance.
28. [Pixabay Terms of Service](https://pixabay.com/service/terms/) — Primary, standalone-use and bulk/systematic-copying restrictions.
29. [Pexels Terms of Service](https://www.pexels.com/it-it/terms-of-service/) — Primary, standalone-use and bulk/systematic-copying restrictions.

### Gaps

- The sources do not establish metric runtime or throughput on the project’s Ryzen 9 7950X3D. Measure VMAF, XPSNR, SSIMULACRA2, and ColorVideoVDP on fixed short clips at each target resolution.
- No cited source establishes universal score thresholds for transparent phone playback. Run blinded comparisons on the actual Android and iPhone models and calibrate thresholds by content category.
- No public corpus found here exactly matches private static-room sessions or the stated two-person call layout while also providing clean, redistributable source video. Curate public stand-ins and record the mismatch.
- VFR frame-pairing choices need hands-on validation against clips with rotation metadata, full-range pixels, frame-rate conversion, and timestamp discontinuities. Compare frame counts and inspect the specific windows where the metrics disagree.
