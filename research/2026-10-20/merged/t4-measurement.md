# T4 merged: quality measurement, fast verification, public test corpora

Merged 2026-10-20 from `self/t4-measurement.md` (A, Claude) and `codex/t4-measurement.md` (B, Codex), with a verification pass on primary sources.
Owner decisions applied: no gallery-app target (phones, Haruna, Windows PCs only), GPS and `creation_time` kept, Opus by default, one preset per category, webinar fps reduction goes into the benchmark.

## 1. Bottom line

- **Metrics:** run VMAF v1 (libvmaf 3.2.x, built-in models `vmaf_v1.0.16_*`) plus XPSNR on every benchmark clip. Add SSIMULACRA2 and CVVDP on a subset. Keep VMAF v0.6.1 only to compare with the January prototype. Desktop and Haruna are targets too, so gate on the 3H model and report the 5H phone model next to it.
- **ffmpeg:** keep the BtbN static build (distro 8.0.1 has no libvmaf). Its libvmaf pin is 8 commits after v3.2.1, so the v1 models are inside. Always set `model=` explicitly, because ffmpeg's default is still `version=vmaf_v0.6.1`.
- **Alignment is where measurement goes wrong.** Encode with `-fps_mode passthrough`. Compare frame-by-frame with the same input `-r` on both legs and `setpts=PTS-STARTPTS`. Normalise range and bit depth explicitly (10-bit, ranges from ffprobe), autorotate both legs, and check frame counts outside the metric run. Input order: `libvmaf` takes the distorted video first, `xpsnr` takes the reference first.
- **Webinar fps reduction needs two numbers:** a compression score (reference passed through the same `fps=` filter, then index-matched) and a temporal score (timestamp pairing against the source at its native rate). Otherwise the fps change goes unmeasured.
- **Verifier for every file:** ffprobe stream and tag inventory (including GPS and `creation_time`), packet count equal to the source (zero tolerance under passthrough), timestamp and duration checks, a full decode with `-xerror`, and VMAF/XPSNR on 2-3 short windows. Mux once to a temp name, verify, then rename. No post-encode remux pass. Throughput is not critical, so the full decode runs on every file, not only before deletion.
- **Corpus:** auto-download only from the AOM CTC set (xiph), the Xiph derf collection, YouTube UGC (GCS bucket), Microsoft VCD (Azure blob) and AVT-VQDB `Dancers_8s`. LIVE-VQC and the 2025 screen-content dataset sit behind forms; Pexels forbids automated collection. Commit manifests (URL, SHA-256, licence, attribution), never media.
- **No public clip looks like Android footage** (VFR, `yuvj420p` full range, rotation matrix, GPS). The benchmark needs synthetic "phone-ified" variants plus a few of the owner's own clips, run locally.
- **Thresholds are calibration targets, not facts.** Start at VMAF v1 3H mean ≥ 94 with P5 ≥ 88, XPSNR-min ≥ 40-42 dB and SSIMULACRA2 mean ≥ 80, then set the per-category floors with a blind check on the actual phones and a PC.

## 2. Findings

### Q1. Metrics near transparency, tools, CPU speed

- VMAF v1 exists: libvmaf v3.2.0 (2026-06-20) and v3.2.1 (2026-09-14). Its models are 1080p 3H, phone 5H, 4K 1.5H (0-100) and 4K 3H (0-110), plus `_hfr` variants for ~50/60 fps. Netflix says to measure at 10-bit even for 8-bit encodes so that banding is caught. `[both]` `[verified]` [7][8][9]
- NEG is built into v1. The v1 model JSON sets `adm_enhn_gain_limit: 1.0` and has no VIF feature, so no separate `neg` model is needed. `[conflict]` A said NEG is on by default [11]; B said not to assume a NEG equivalent [B:2]. Resolved in favour of A `[verified]` [10].
- v1 adds chroma, CAMBI banding and blocking (AIM) terms. Netflix says it "matches or outperforms v0 in most datasets". No independent benchmark of v1 was found. `[A only]` [11]
- Legacy VMAF v0.6.1 is a poor transparency gate. On the ≤1 JND high-fidelity image subset it scored SROCC 0.635, against 0.810 for VMAF-NEG, 0.831 for SSIMULACRA2, 0.852 for CVVDP and 0.857 for Butteraugli. These are still images, not video. `[A only]` [24][23]
- CVVDP reports JOD (10 = no visible difference) and has `standard_phone` and `standard_fhd` display models. It is slow on CPU: about 0.8 fps for 1080p, per Vship's numbers. `[both]` on availability and the CPU caveat; the speed figure is `[A only]` [20][21]
- SSIMULACRA2 anchors: 90 = visually lossless (flicker test), 80 = not noticeable side by side. On CPU, vszip or fssimu2 run about 45 fps at 1080p, versus about 12 fps for the libjxl tool. B suggests libjxl on sampled frames, A suggests vszip/fssimu2 on the whole clip. Both work; vszip/fssimu2 is cheaper. `[A only]` for the speed figures [21][22][23]
- XPSNR is a native ffmpeg filter, and the docs suggest reporting the minimum of the per-plane averages. Evidence for its validity at high quality is thin (one 2020 study from its authors; ~42 dB "visually lossless" on a wiki). `[both]` for availability, `[verified]` for the docs [1]; thresholds `[A only]` [26][27]
- Screen content: no 2024-2026 study scores VMAF, SSIMULACRA2 or CVVDP on slides or text. B's 2025 screen-content dataset and the AIM 2025 challenge publish subjective data, but the dataset is available on request only and states no licence. `[B only]` `[verified]` for the access terms [38][39]
- Already-compressed references (Zoom recordings, all phone footage): on BVI-UGC every full-reference metric had SROCC < 0.6. Absolute targets from studio literature therefore transfer poorly to category 5. `[A only]` [25]

### Q2. Measuring real-world sources correctly

- ffmpeg filters pair frames by timestamp. An input `-r N` on both legs replaces the stored timestamps with a CFR grid, which turns the comparison into frame-index matching. ab-av1 does this, with `ts_sync_mode=nearest` and `shortest=true`. `[A only]` [12][15]
- `[conflict]` A says to index-match with `-r` on both inputs once the encode used passthrough [15][17]. B says not to force a nominal fps by default, because timestamp pairing is safer when the output changed cadence [B:3,11]. **Resolution (synthesis):** both are right in their own case. Under passthrough, index matching is exact, and frame counts are checked separately. When the preset changes fps (webinars), measure compression against a reference passed through the same `fps=` filter, and measure the temporal loss by timestamp pairing at source rate. B's worry about hiding dropped frames is handled by the separate packet-count check.
- `-fps_mode auto` drops or duplicates frames on VFR input (one sample: 1196 frames became 1195 in MKV and 1197 in MP4). ab-av1 has used `passthrough` since v0.11.5. This matches the prototype's 4 lost frames at 59.94 fps in MKV; Matroska's 1 ms timestamp precision adds to it. `[A only]` `[verified]` changelog [15][17][41]
- Framesync defaults (`eof_action=repeat`) repeat the last frame of a shorter stream silently. Set `shortest=1` and compare counts separately; ffmpeg-quality-metrics warns on such mismatches. `[A only]` [1][40]
- Colour range: libvmaf only warns when the two `color_range` values differ; it does not convert. Convert both legs explicitly (`scale=in_range=<probed>:out_range=tv,format=yuv420p10le`). `[both]` `[verified]` source [4]
- Rotation: autorotate is on by default. Leave it on for both legs. The prototype scored VMAF 1.91 because one leg was autorotated and the other was not. `[both]` + history [5]
- Downscaled outputs (dance 720p): upscale the distorted video to the reference with bicubic; never downscale the reference to match. For v1, pass the encode size to CAMBI. `[both]` [8][13]. The ffmpeg syntax `model=version=vmaf_v1.0.16_3d0h\:cambi.enc_width=1280\:cambi.enc_height=720\:cambi.enc_bitdepth=8` is accepted, because the filter forwards `feature.option` keys to `vmaf_model_feature_overload`. `[verified]` source read, not run [4]
- `scale2ref` was deprecated in ffmpeg 7.1. It still exists on master (8.2-dev) and logs "scale2ref is deprecated, use scale=rw:rh instead", and its section is gone from the docs. The replacement is `scale` with a second input: `[to_scale][ref]scale=rw:rh[out]`. The first input is scaled; the second, a pad named `ref`, is consumed, so `split` the reference first. `[both]` `[verified]` [2][3][1][42]
- `n_threads` defaults to 0 (no threading) in ffmpeg; set it. The prototype ran VMAF at 15.6 fps without it. `[A only]` `[verified]` docs [1]; speed-up figures `[unverified]` [47]

**Recommended chain** (synthesis from [1][3][4][8][12][15]; the tool computes `W:H` from ffprobe, with the displayed short side capped at 1080 for the 1080p models):

```sh
ffmpeg -nostdin -hide_banner -r 30 -i dist.mp4 -r 30 -i src.mp4 -an -sn -dn -filter_complex "
 [1:v]scale=W:H:flags=bicubic:in_range=pc:out_range=tv,format=yuv420p10le,setpts=PTS-STARTPTS,settb=AVTB,split=3[rs][rv][rx];
 [0:v]setpts=PTS-STARTPTS,settb=AVTB[d0];
 [d0][rs]scale=rw:rh:flags=bicubic:in_range=tv:out_range=tv,format=yuv420p10le,split[dv][dx];
 [dv][rv]libvmaf=model=version=vmaf_v1.0.16_3d0h\:name=v3h|version=vmaf_v1.0.16_5d0h\:name=v5h:n_threads=32:shortest=1:log_fmt=json:log_path=vmaf.json;
 [rx][dx]xpsnr=stats_file=xpsnr.log:shortest=1" -f null -
```

`-r 30` only has to be identical on both legs. `in_range` comes from ffprobe, never assumed. Use the `_hfr_` models for 50/60 fps. Note that `libvmaf` takes the distorted video first and `xpsnr` takes the reference first.

### Q3. Fast post-encode verification

- ab-av1 v0.11.7 (2026-08-21) added `--verify`. It decodes the finished encode, fails on decode errors and checks duration, and the two checks can be split with `--verify-decode` and `--verify-duration`. `[both]` `[verified]` changelog [15]
- A silent `-xerror` decode is necessary but not sufficient, because ffmpeg is lenient. Pair it with explicit count, stream and timestamp checks. `[both]` [5]
- B adds: check that DTS is monotonic in packet order, not PTS, because B-frames reorder PTS. Check for duplicate PTS instead. `[B only]`; standard codec behaviour, not re-checked.
- A non-faststart MP4 without `moov` fails to open. `cues_to_front` and `faststart` rewrite the file in a second pass, and ffmpeg's Matroska demuxer skips CRC32 elements rather than verifying them. Hence: mux once, verify, rename. `[A only]` [6]
- mkvalidator (v0.6.0, 2021) checks conformance, not decodability. GPAC `inspect` reports MP4 track and packet details. `[both]` [28][29]
- Failure modes documented in practice: frame drops or duplicates from `fps_mode auto`, VFR desync in sampling tools, 1 ms Matroska timestamps at 59.94 fps, unexpected display matrices since ffmpeg 7.1, truncated MP4. No frequency data exists. `[A only]` [17][41][45]

| # | Check | Tool | Catches |
|---|---|---|---|
| 1 | Exit code, stderr scan, temp-name output | ffmpeg | crash, disk full |
| 2 | Streams: v/a count, codec, `hvc1` tag, pix_fmt, `color_range`, displayed W×H after rotation, `creation_time` and GPS tags | ffprobe | lost audio, range or rotation errors, metadata loss |
| 3 | Video packet count = source frames (passthrough) or the predicted count (fps change) | `ffprobe -count_packets` | dropped or duplicated frames |
| 4 | DTS monotonic, no duplicate PTS, max PTS gap ≤ source max; video end vs audio end within 1 frame + Opus pre-skip | ffprobe packets | timestamp grid, desync, truncation |
| 5 | Duration within 1 frame of the source (ab-av1's 2 s is too loose here) | ffprobe | truncation |
| 6 | Full decode of all streams with `-xerror` | `ffmpeg -f null` | bitstream corruption |
| 7 | 2-3 windows of 2-3 s (start, middle, end), cut by frame index on both legs, VMAF v1 + XPSNR against the preset floor | Q2 chain + `trim=start_frame=` | misalignment, range errors, garbage frames, wrong preset |
| 8 | MKV only: mkvalidator | [28] | EBML structure |

### Q4. Target quality via sampling

- ab-av1: interpolated binary search, 20-s samples, one per 12 min, whole file once the samples would cover ≥ 85% of it. Default target `--min-vmaf 95`; it averages sample scores, and a "worst sample" mode is still an open issue. `[both]` for the mechanics [15][18]
- One user saw x265 samples overshoot full-encode VMAF by ~1.5 points, against 0.4-0.6 for SVT-AV1. `[A only]`, single source [16]
- Av1an: per-chunk probes (default 4), `--probing-rate`, `--probe-res`, and metrics VMAF, SSIMULACRA2, Butteraugli and XPSNR. Its example targets are VMAF 95, SSIMULACRA2 75-90 and XPSNR 40-50. `[both]` [19]
- No published universal "transparent on a phone" threshold exists. `[both]`. The JND step is about 6 VMAF points per Netflix (2017), but it varies from 2 to 6 per clip [43][44] `[A only]`.
- Starting targets: `[conflict]` A proposes VMAF v1 3H mean ≥ 94 with P5 ≥ 88; B proposes a phone-model ladder of 95/97/99 [B:1]. **Resolution:** gate on 3H because PCs are a target (owner decision), log 5H alongside, and run B's ladder idea as the calibration sweep.
- Window length: A suggests 10-20 s windows chosen by scene change, B suggests 20-30 s. Both: 6-10 windows on long clips, report mean, P5 and the worst window, and validate once against a full encode. Clips under ~3 min get measured in full.

### Q5. Public test footage

All licences below were read in this pass from the per-file copyright files or the dataset's own pages. `[verified]` [30]-[38]

- AOM CTC (media.xiph.org): plain HTTP, `.md5` files alongside. Most clips are **only 130 frames** (2.2-5.2 s). The licence is per clip: CC0, CC BY 4.0, CC BY-SA 4.0, CC BY-NC-ND 4.0 (Netflix 2020 cuts), public domain, or standards use only (Tencent Slides1 and Slides2r, **Vidyo3 and Vidyo4**). A flagged only Vidyo4; Vidyo3 carries the same restriction. [30]
- Xiph derf: Johnny, KristenAndSara and FourPeople are 600-frame, 720p60, public-domain versions (831 MB each), longer than the AOM cuts. Derf also lists vidyo1/3/4 as public domain, which conflicts with AOM, so exclude them. [31]
- YouTube UGC: public GCS bucket listable via the JSON API. All 1069 ATTRIBUTION lines say CC BY 4.0 (the LICENSE file is CC BY legal text). Clips are 20 s with audio removed, and the `original_videos_h264` CRF10 MP4s are 7 MB to 1 GB. [32]
- Microsoft VCD: data under CDLA-Permissive-2.0, code under MIT. 160 clips (TH, TH-OB, TH-BB, TH-M; 40 each), 1080p30, 10 s, MP4 ~14 MB, served from an Azure blob over plain curl. TH-M clips are portrait 1080x1920. [33]
- AVT-VQDB-UHD-1 `Dancers_8s`: CC BY-NC 4.0, FFV1 3840x2160p60 yuv422p10le, 8 s, **3.58 GB**, plain HTTPS. [34]
- Netflix Open Content: the site says CC BY 4.0 and the S3 bucket allows anonymous access, but the assets are camera masters (e.g. 35 GB MXF). The same Netflix titles cut for AOM CTC carry CC BY-NC-ND 4.0, so the licence depends on where you download from. `[conflict]` A said CC BY 4.0, B said check per title; B's caution holds. [35][30]
- LIVE-VQC: `[conflict]` A said research use via a form; B said copying and distribution are permitted. Both are partly right: the terms allow use, copying, modification and distribution for any purpose with the notice kept, but the download is behind a Google form. Not auto-downloadable. [36]
- Pexels: `[conflict]` A said auto-download with an API key; B said bulk collection is prohibited. B is right: ToS §8 bans "bulk, large-scale or systematic copying" and "programs or robots for automatic data collection". [37]
- KoNViD-1k [46], Pixabay API, Wikimedia Commons MP4 policy: `[unverified]`; not needed for v1 of the corpus.

## 3. Verification log

| # | Claim | Result | Source |
|---|---|---|---|
| 1 | libvmaf 3.2.0/3.2.1 dates, v1 models | Confirmed: 2026-06-20 and 2026-09-14; 4 base + 4 `_hfr` models built in | `gh api` releases [7]; model.c [9]; models_v1.md [8] |
| 2 | v1 includes NEG | Confirmed: `adm_enhn_gain_limit: 1.0`, no VIF | v1 model JSON [10] |
| 3 | ffmpeg libvmaf syntax | Default `version=vmaf_v0.6.1`; `model=version=X\:name=Y\|...`; `feature.opt` keys forwarded | docs [1], vf_libvmaf.c [4] |
| 4 | BtbN ships v1 | Pin `86da14d` is 8 commits ahead of v3.2.1 | 45-vmaf.sh [14] + GitHub compare |
| 5 | Input order | libvmaf: "first input is the distorted video". xpsnr: "first input is considered a … reference" | ffmpeg-filters [1] |
| 6 | scale2ref | 7.1 Changelog: deprecated, scale gets ref input + framesync. Master still builds it with a warning; the doc section is removed | Changelog [2], vf_scale.c [3] |
| 7 | AOM CTC licences | Per file as listed in Q5; Vidyo3 is also restricted | `*_Copyright.txt` [30] |
| 8 | derf Johnny etc. | 600 frames, public domain, 831 MB | derf index [31] |
| 9 | YouTube UGC | CC BY 4.0 per clip, bucket listable, sizes | LICENSE, ATTRIBUTION, JSON API [32] |
| 10 | VCD | CDLA-P-2.0 / MIT, Azure blob, TH-M portrait | repo + ffprobe on a blob [33] |
| 11 | Dancers_8s | CC BY-NC 4.0, FFV1 4K60 422 10-bit, 3.58 GB | README, ffprobe over HTTPS [34] |
| 12 | Netflix OC licence | CC BY 4.0 on the site; the AOM cuts are BY-NC-ND | site, S3 listing [35] |
| 13 | LIVE-VQC terms | Liberal terms, form-gated download | site [36] |
| 14 | Pexels automation | Prohibited (§8) | ToS [37] |
| 15 | Screen-content dataset 2025 | On request, no licence stated | dataset page [38] |
| 16 | ab-av1 `--verify`, passthrough | v0.11.7 (2026-08-21) and v0.11.5 | CHANGELOG [15] |

Not re-checked: CVVDP and SSIMULACRA2 speeds, the XPSNR ~42 dB threshold, the ab-av1 x265 overshoot, the `n_threads` speed-up, DTS/PTS monotonicity advice.

## 4. Benchmark candidates

**Metrics per run**
- On every clip: VMAF v1 `3d0h` + `5d0h` (`_hfr_` at ≥ 50 fps) at 10-bit with `n_threads=32`, and XPSNR (min of Y/U/V). Report mean, P5, min, and the worst 1-s window.
- On a subset: SSIMULACRA2 (fssimu2 or vszip; mean, P5, min) and CVVDP (`standard_phone`, `standard_fhd`).
- For 4K walkthroughs: score at 1080p (both legs downscaled) and natively with `1d5h_2160`; the benchmark decides which to gate on.
- Prototype comparison only: `vmaf_v0.6.1` and `vmaf_v0.6.1neg`.

**Measurement checks to build first**
- Self-compare sanity test: a file against itself should score ~100 VMAF and infinite XPSNR.
- Range-mismatch test: a pc-flagged and a tv-flagged copy of the same clip.
- Rotation test: a display-matrix copy versus a baked-rotation copy.
- Frame-drop test: delete 1 frame and confirm check #3 catches it.
- Speed on the 7950X3D: fps per metric at 1080p and 4K.
- Sample vs full offset per encoder and preset.

**Webinar fps arm:** passthrough vs `fps=25` vs `fps=24` vs `mpdecimate`. Score compression against an `fps`-matched reference and temporal loss by timestamp pairing; add a visual check on cursor and scroll segments.

**Synthetic "phone-ified" variants** (built from 3 clips): H.264/HEVC at phone bitrates, full-range flag, `-display_rotation 90`, jittered VFR timestamps, and an MKV screen-recording variant.

**Clip list v1** (download manifest; all auto-downloadable)

| Cat | Clip | Source | Licence | Notes |
|---|---|---|---|---|
| 1 Walkthrough | Shaky_Walk_1920x1080_25fps | AOM `e_nonpristine` | CC BY-SA 4.0 | 130 f, handheld vlog |
| 1 | WalkingInStreet_1920x1080_30fps | AOM `a2_2k` | CC BY-SA 4.0 | 130 f |
| 1 | Vertical_Carnaby_1080x1920_5994 | AOM `a2_2k` | CC BY-SA 4.0 | portrait, 60 fps |
| 1 | 1-2 × `Vlog_2160P-*` (h264 CRF10) | YouTube UGC | CC BY 4.0 | 20 s, 4K, 0.2-1 GB |
| 2 Dance | Dancers_8s | AVT-VQDB-UHD-1 | CC BY-NC 4.0 | 4K60 FFV1, 3.58 GB |
| 2 | RitualDance_1920x1080_5994_10bit | AOM `a2_2k` | CC BY-NC-ND 4.0 | 130 f; local use only |
| 2 | Tango_3840x2160_5994fps_10bit | AOM `a1_4k` | CC BY-NC-ND 4.0 | 130 f, couple dance |
| 3 Static room | Johnny, KristenAndSara, FourPeople (720p60) | Xiph derf | public domain | 600 f each |
| 3 | 2 × `Lecture_1080P-*` | YouTube UGC | CC BY 4.0 | lecture room |
| 4 Webinar | Wikipedia_1920x1080p30 | AOM `b2_scc` | CC0 | text scrolling |
| 4 | Spreadsheet, Debugging (1080p30) | AOM `b2_scc` | CC BY 4.0 | 130 f |
| 4 | SceneComposition_1 | AOM `b2_scc` | CC BY-SA 4.0 | mixed screen |
| 4 | HowTo_1080P-0267 ("Road Signs in GIMP") | YouTube UGC | CC BY 4.0 | real screencast |
| 4 | Synthetic: Wikipedia + VCD TH inset (`overlay`) | derived | CC0 + CDLA-P-2.0 | talking-head inset |
| 5 Calls | 2 × VCD TH, 1 × TH-BB, 1 × TH-OB | Microsoft VCD | CDLA-Permissive-2.0 | 1080p30, 10 s |
| 5 | Synthetic: 2 VCD clips `hstack`, then H.264 at ~1 Mbit/s 720p | derived | CDLA-P-2.0 | simulates the call codec |
| 6 Holiday | 2 × `VerticalVideo_1080P-*`, 1 × `Sports_2160P-*` | YouTube UGC | CC BY 4.0 | real UGC |
| 6 | 1-2 × VCD TH-M | Microsoft VCD | CDLA-P-2.0 | portrait phone |
| all | 3-5 owner clips | owner | owner's choice | the only real Android VFR |

Excluded: Vidyo1/3/4, Slides1/2r, JCT-VC SCC (standards use only or conflicting terms), Pexels and Pixabay (no automated collection), LIVE-VQC and the 2025 screen-content dataset (form-gated; optional manual add-ons).
The total download is roughly 12-15 GB, mostly Dancers_8s and the 4K UGC clips.

## 5. Open questions for the owner

1. Will you contribute 3-5 of your own phone clips to the public repo (CC0)? They would have to be stripped of GPS or be location-safe. Without them, no test covers real Android VFR, full range and rotation.
2. Should the default manifest include NC and NC-ND clips (Dancers_8s, RitualDance, Tango)? They are fine for local measurement, but the tool would have to show the licence and never redistribute the encodes. The alternative is an opt-in `--with-nc` flag.
3. Can you spend ~1 hour on a blind A/B session (one phone of each kind plus a PC) to set the per-category floors? Every threshold above is a placeholder until then.
4. For 4K walkthroughs, do you view them anywhere above 1080p? If not, gating at 1080p (3H) is enough and the 4K models stay informational.

## 6. Sources

1. [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) (libvmaf, xpsnr, scale, framesync)
2. [FFmpeg Changelog](https://github.com/FFmpeg/FFmpeg/blob/master/Changelog) (7.1: scale ref input, scale2ref deprecated)
3. [vf_scale.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_scale.c) (ref pad, deprecation warning)
4. [vf_libvmaf.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_libvmaf.c) (model parsing, range warning)
5. [ffmpeg CLI documentation](https://ffmpeg.org/ffmpeg.html) (`-r`, `-fps_mode`, `-autorotate`, `-xerror`)
6. [FFmpeg Formats Documentation](https://ffmpeg.org/ffmpeg-formats.html) (Matroska `cues_to_front`, `write_crc32`; MP4 `faststart`)
7. [VMAF releases](https://github.com/Netflix/vmaf/releases)
8. [VMAF Models (v1)](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v1.md)
9. [libvmaf model.c](https://github.com/Netflix/vmaf/blob/master/libvmaf/src/model.c)
10. [vmaf_v1.0.16_3d0h.json](https://github.com/Netflix/vmaf/blob/master/model/vmaf_v1.0.16/vmaf_v1.0.16_3d0h.json)
11. [Netflix Tech Blog: VMAF v1](https://netflixtechblog.com/vmaf-v1-good-is-not-good-enough-60d7e4244ea8)
12. [Using VMAF with FFmpeg](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md)
13. [VMAF FAQ](https://github.com/Netflix/vmaf/blob/master/resource/doc/faq.md)
14. [BtbN FFmpeg-Builds 45-vmaf.sh](https://github.com/BtbN/FFmpeg-Builds/blob/master/scripts.d/45-vmaf.sh)
15. [ab-av1](https://github.com/alexheretic/ab-av1) and [CHANGELOG](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md)
16. [ab-av1 #220](https://github.com/alexheretic/ab-av1/issues/220) (sample vs full)
17. [ab-av1 #333](https://github.com/alexheretic/ab-av1/issues/333) (fps_mode drop/dup)
18. [ab-av1 #202](https://github.com/alexheretic/ab-av1/issues/202) (worst sample)
19. [Av1an target quality](https://github.com/rust-av/Av1an/blob/master/site/src/Cli/target_quality.md)
20. [ColorVideoVDP](https://github.com/gfxdisp/ColorVideoVDP)
21. [Vship](https://codeberg.org/Line-fr/Vship) (GPU metrics, CPU timings)
22. [fssimu2](https://github.com/gianni-rosato/fssimu2)
23. [cloudinary/ssimulacra2](https://github.com/cloudinary/ssimulacra2)
24. [Mohammadi et al. 2025, arXiv 2509.13150](https://arxiv.org/html/2509.13150v1)
25. [BVI-UGC, arXiv 2408.07171](https://arxiv.org/abs/2408.07171)
26. [codecs.wiki: XPSNR](https://codecs.wiki/docs/metrics/XPSNR)
27. [Helmrich et al., XPSNR study, ITU J. 2020](https://www.itu.int/en/journal/2020/001/Pages/08.aspx)
28. [mkvalidator](https://www.matroska.org/downloads/mkvalidator.html)
29. [GPAC inspecting guide](https://www.dev.wiki.gpac.io/Howtos/inspecting/)
30. [AOM CTC test set (xiph)](https://media.xiph.org/video/aomctc/test_set/)
31. [Xiph derf collection](https://media.xiph.org/video/derf/)
32. [YouTube UGC dataset LICENSE](https://storage.googleapis.com/ugc-dataset/LICENSE) and [ATTRIBUTION](https://storage.googleapis.com/ugc-dataset/ATTRIBUTION)
33. [microsoft/VCD](https://github.com/microsoft/VCD)
34. [AVT-VQDB-UHD-1](https://github.com/Telecommunication-Telemedia-Assessment/AVT-VQDB-UHD-1)
35. [Netflix Open Content](https://opencontent.netflix.com/home)
36. [LIVE-VQC](https://live.ece.utexas.edu/research/LIVEVQC/index.html)
37. [Pexels Terms of Service](https://www.pexels.com/terms-of-service/)
38. [Screen content video dataset](https://videoprocessing.github.io/screen-content-dataset)
39. [AIM 2025 screen-content VQA challenge](https://openaccess.thecvf.com/content/ICCV2025W/AIM/html/Safonov_AIM_2025_Challenge_on_Screen-Content_Video_Quality_Assessment_Methods_and_ICCVW_2025_paper.html)
40. [slhck/ffmpeg-quality-metrics](https://github.com/slhck/ffmpeg-quality-metrics)
41. [FFmpeg-devel: Matroska timestamp precision (2021)](https://ffmpeg.org/pipermail/ffmpeg-devel/2021-May/280479.html)
42. [ffmpeg-cvslog: deprecate scale2ref](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2024-May/142854.html)
43. [Ozer: JND with VMAF](https://streaminglearningcenter.com/blogs/finding-the-just-noticeable-difference-with-netflix-vmaf.html)
44. [QoMEX 2022 VMAF JND poster](https://athena.wp.itec.aau.at/wp-content/uploads/sites/12/2022/07/QoMEX_22__VMAF_JND_Poster.pdf)
45. [FFmpeg trac #11649 display matrix](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-June/073944.html)
46. [KoNViD-1k](https://database.mmsp-kn.de/konvid-1k-database.html)
47. [FFAStrans forum: VMAF n_threads](https://ffastrans.com/frm/forum/viewtopic.php?p=8886)

`[B:n]` refers to source n in `codex/t4-measurement.md`.
