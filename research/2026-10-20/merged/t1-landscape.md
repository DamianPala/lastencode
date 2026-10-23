# T1 merged: existing tools and where the new tool fits

Merged 2026-10-20 from Report A (`self/t1-landscape.md`, Claude agent) and Report B (`codex/t1-landscape.md`, Codex).
History files were read as hypotheses only. Verification in this pass used the GitHub API (`gh api`) on repos, releases, issues and source, plus WebFetch on vendor docs.

## 1. Bottom line

- **Build the project as its own thin Python orchestrator over `ffmpeg`/`ffprobe`/`exiftool`, not as a wrapper around ab-av1 or Av1an.** Both reports land here: the quality-search engine exists, the archive workflow (metadata, VFR timing, per-file gate, category presets) does not [1][9][13].
- **One fixed preset per category, tuned in benchmark mode, matches the owner's decision and the evidence.** Per-file CRF search (ab-av1) degenerates to near-full passes on short phone clips and adds a VFR failure mode [4]; keep `ab-av1 crf-search --stdout-format json` as a benchmark comparison arm, not the archive-run engine [2][5].
- **Measurement stays in-house and VFR-safe.** ab-av1 #311 (VFR phone clip scored VMAF 34,48 vs 93,37 after CFR conversion) is real and was closed "not planned"; ab-av1 later moved sample encodes to `-fps_mode passthrough`, but nobody has shown that fixes phone VFR [4][6]. Reproduce #311 as a regression test.
- **Use VMAF v1 models; they exist and are in BtbN builds.** libvmaf v3.2.0 (2026-06-20) shipped VMAF v1 with a phone model (`vmaf_v1.0.16_5d0h`), 4K models and `_hfr` variants for 50/60 fps; BtbN's `gpl` build compiles libvmaf with built-in models from a commit 8 commits after v3.2.1 [23][24][25][26]. Ubuntu's ffmpeg 8.0.1 has no `libvmaf`, only `xpsnr` [47].
- **Do not bundle ffmpeg.** Detect capabilities at startup (`-encoders`, `-filters`), recommend the BtbN `gpl` build, fall back to XPSNR when libvmaf is missing. Shelling out to GPL binaries keeps the Python CLI under its own license per the FSF FAQ (not legal advice) [27][28].
- **Per-file gate must go beyond ab-av1's `--verify`** (decode + duration within 2 s): add frame count, stream set, `creation_time`, GPS, rotation read-back and restored mtime [2].
- **Drop from consideration:** Tdarr (proprietary EULA), FileFlows (closed source, optimised encode paywalled), Av1an (VapourSynth stack, MKV-centric, metadata issue open since 2022), HandBrake as engine (no metric), Unmanic (server, not CLI) [12][16][18][21].
- **Webinar fps reduction needs a defined comparison method before it enters the benchmark.** VMAF between a 30 fps reference and a 24/25 fps distorted file is a known trap (ab-av1 #341 open) [7].

Owner decisions that make parts of the reports moot: gallery-app tag priority (Immich, Synology, Google Photos) from Report A is dropped; GPS and `creation_time` must still survive in every category, so the metadata read-back stays.

## 2. Findings

### Q1. Maintained tools for quality-targeted re-encoding

| Tool | Encoders | Target quality | Granularity | Post-encode check | Metadata | License | Activity |
|---|---|---|---|---|---|---|---|
| ab-av1 | any ffmpeg encoder; default `libsvtav1`; `libx265`, `libx264` | sampled binary search on `--min-vmaf` (default 95) or `--min-xpsnr` | per file | `--verify` (decode + duration), `--fail-fast` | ffmpeg defaults (`-map 0`, no `-map_metadata`) | MIT | v0.11.7, 2026-08-21, 1 020 stars |
| Av1an | aomenc, SvtAv1EncApp, rav1e, vpxenc, x264, x265 | per-chunk probing on VMAF, SSIMULACRA2, Butteraugli, XPSNR | per scene | not documented | issue #678 open since 2022 | GPL-3.0 | v0.5.2, 2026-01-04 |
| HandBrakeCLI | x264, x265, SVT-AV1, HW | none, fixed RF | per file | none | passthru incl. creation date + location (1.10.0) | GPL-2.0 | 1.11.2, 2026-06-07 |
| Tdarr | ffmpeg or HandBrake via plugins | none built in | per file | health check: quick (HandBrake) or thorough (ffmpeg decode) | plugin-dependent | proprietary EULA; plugins GPL-3.0 | pushed 2026-10-15, 4 361 stars |
| FileFlows | H.264, HEVC, AV1, HW | "Video Encode Optimized": sampled VMAF vs minimum | per file | Compute VMAF task | not documented | closed source; feature needs paid license | 26.10 series |
| Unmanic | libx265, libsvtav1, HW | none, fixed CRF | per file | optional `vmaf_quality_audit` plugin | plugin-dependent | GPL-3.0 | 0.4.1, 2026-08-14 |

- ab-av1: features, version, license and JSON output `[both]`; `--verify`/`--fail-fast` in v0.11.7, `hvc1` default for x265 in v0.11.6, temp-file + atomic rename in v0.11.5 `[both][verified]` [1][2]. Default VMAF model is libvmaf's default (v0.6.1; switches to `vmaf_4k_v0.6.1` above 2560x1440), `--vmaf-fps` default 25, and it now calls libvmaf with `ts_sync_mode=nearest` `[A only][verified]` (source read) [3]. The crate is "not a library", so call the CLI `[B only]` [1].
- Av1an: per-scene target quality, metric set, GPL-3.0, v0.5.2 `[both][verified release]` [9][10]. VapourSynth + plugins needed for the newer metrics `[A only]` [10]. Metadata issue #678 still open `[A only][verified]` [12].
- HandBrake: fixed RF only, no metric `[both]` [15]. **Metadata `[conflict, resolved]`:** A says 1.10.0 passes creation date and location; B says the passthru doc lists `Location6709` but not creation time. Both are right about their source: the 1.10.0 release notes list "Creation date" and "Location", the docs page lists only `Location6709` and no creation date or rotation `[verified]` [13][14]. Docs lag the code; behaviour on Android VFR clips is untested.
- Tdarr, FileFlows, Unmanic: web/server workflow managers, not CLIs `[both]`. Licensing see Q2.
- Newer entrants (2025-2026), all experimental, all below ~150 stars: A lists xav, ffdash, Auto-Boost-Essential/RabbitEncoder, av1q, phone-media-reducer, media-library-compressor; B lists Video-AV1-Optimizer (Windows, FFmpeg 9, replaces source in place), VideoTuner (AGPL, Windows, VapourSynth), ffvm (Python, sampled VMAF), transQrate (QSV AV1), Viser (encoding ladders) `[A only]` / `[B only]` [44]. None is a credible backend; the tiny phone compressors confirm people hand-roll ffmpeg + exiftool.

### Q2. Reuse as a backend, licensing, ffmpeg packaging

- **ab-av1 is the only clean backend candidate** `[both]`: MIT, single static binary, `crf-search --stdout-format json` emits NDJSON (`sample-encode-done`, `crf-search-done`, `crf-search-error`), errors exit non-zero `[verified]` (doc read) [5]. It reports the **mean** sample VMAF, not low percentiles [5].
- **Av1an** callable but drags VapourSynth; GPL-3.0 `[both]`. **HandBrakeCLI** adds nothing over direct ffmpeg except its metadata passthru `[both]`.
- **Tdarr is proprietary** `[both][verified]`: `LICENSE.md` is an EULA with Personal Free / Personal Subscription / Business tiers, prohibits redistribution, reverse engineering and distribution without written permission; GitHub reports license `NOASSERTION`. `Tdarr_Plugins` is GPL-3.0 [16][17].
- **FileFlows is closed source** `[both][verified]`: no public core repo (`revenz/FileFlows` returns 404), docs footer "Copyright © 2026 Reven Software. All rights reserved.", and the optimised encode page says "This feature is available only with a valid FileFlows license" [18][19]. A's "proprietary freemium" holds. Nuance found in this pass: an AGPL-3.0 snapshot of early FileFlows (2021-2023) survives at `FreekingDean/FileFlows`; it predates the VMAF feature and is irrelevant as a backend [20].
- **Unmanic** GPL-3.0 Python, reuse means writing an Unmanic plugin, not a CLI dependency `[A only]` [21].
- **ffmpeg licensing** `[both]`: ffmpeg is LGPL by default, GPL once x264/x265 are enabled; BtbN `lgpl` variant lacks x264/x265 [26][27]. Exec/pipes/CLI args count as separate programs per the FSF FAQ, so a non-GPL Python CLI that shells out to user-installed binaries keeps its own license; vendoring binaries brings source-offer duties [27][28].
- **BtbN builds and VMAF v1** `[verified]`: `scripts.d/45-vmaf.sh` builds libvmaf with `-Dbuilt_in_models=true` at Netflix commit `86da14d` (2026-09-16), which is 21 commits after v3.2.0 and 8 after v3.2.1. At that commit `libvmaf/src/model.c` registers built-in versions `vmaf_v1.0.16_3d0h`, `_5d0h`, `_1d5h_2160`, `_3d0h_2160` and `vmaf_v1.0.16_hfr_{3d0h,5d0h,1d5h_2160,3d0h_2160}`. Latest BtbN release (2026-10-19) ships `master`, `n8.1` and `n9.0` linux64 `gpl` builds [25][26]. Not checked: running a downloaded binary (left to the benchmark setup, see Q-list).
- **johnvansickle builds** `[B only][partly verified]`: B read the page as GPLv3, last build 29 June 2024. Site timed out in this pass. Project history (Jan 2026) shows its 7.0.2 build carried libvmaf 2.3.0 with external model files and no SVT-AV1 [47]. Either way: no VMAF v1, not a 2026 default.
- **`ffmpeg-quality-metrics`** (MIT, v3.13.0) supports VMAF v1 only with libvmaf 3.2.1+; **easyVmaf** does PSNR-based frame sync before libvmaf `[A only]` [31][32]. **`static-ffmpeg`** on PyPI ships ffmpeg 8.0, libvmaf not mentioned `[A only]` [48].

### Q3. What personal/phone-video archivers recommend

Report A could not reach Reddit; Report B cites Reddit threads. Neither set was re-read in this pass, so community claims stay single-report.

- **Keep originals; split camp on re-encoding** `[both]`: DataHoarder threads (Dec 2025, Jul 2026) lean to keeping originals in cold storage, some prune or compress [38][39] `[B only]`; HN Dec 2025 users run ab-av1/Av1an at VMAF 95-96 overnight, others warn lossy-to-lossy gains little [33] `[A only]`.
- **Trust eyes as well as metrics** `[both]`: r/AV1 (Jun 2026) and Doom9 advise worst-scene review and frame-wise A/B, not mean VMAF alone [35][40] `[B only]`; codec wikis call VMAF v0.6.x weak near transparency and prefer SSIMULACRA2/Butteraugli [45] `[A only]`. Wikis predate VMAF v1.
- **VFR phone footage breaks things** `[both]`: ab-av1 #311 and Av1an #828 (open) `[A only][verified]` [4][11]; r/ffmpeg report of a phone clip turned into 120 fps with duplicated frames, explained by ffmpeg's `-fps_mode auto` [41][43] `[B only]`.
- **Fixed CRF per footage type is common practice**: VideoHelp user settles on 1080p30 x265 CRF 28 for phone clips, 50-80 % savings `[A only]` [37]; an r/ffmpeg poster found long CRF optimisation gave little visible gain `[B only]` [42].
- **CPU over GPU for archival** `[A only]` [34]; matches the owner's decision.
- **Noisy handheld clips**: light denoise or downscale, or keep the source `[A only]` [36].
- **Phone-specific stream failures**: ab-av1 broke on iPhone `apac` spatial audio (fixed 2026-03) and on container/timebase mismatches (fixed 2026-01) `[A only]` [8]. Relevant because iPhones are a playback target and may also be a source.
- **GPS copy with `-movflags use_metadata_tags` lands in tags Apple apps ignore** (ffmpeg trac #4209, open) `[A only]` [46]. Still relevant for iPhone playback even with gallery apps out; details belong to T5.

### Q4. Gap analysis

- **Niche is real but narrow** `[both]`. Nothing combines: category presets tuned once; VFR-safe measurement; GPS/`creation_time`/rotation/mtime as checked outputs; a fast per-file gate before optional deletion; phone-aware metrics.
- **Not a thin layer** `[both, different emphasis]`: A says own the pipeline and call ab-av1 optionally; B says "build the archive workflow, not another quality-search engine". With the owner's one-preset-per-category decision these converge: the archive run is a fixed ffmpeg encode plus verification; ab-av1 is useful only to answer in the benchmark whether per-file search beats the category preset.
- **ab-av1's per-file search does not fit short clips** `[A only]`: it switches to a full pass when samples would cover 85 % of the clip [1][3].
- **Verification cost** `[B only]`: a full decode may not be "fast" for long files; measure it [1].

## 3. Verification log

| # | Claim | Result | Source |
|---|---|---|---|
| a1 | libvmaf 3.x / VMAF v1 released ~June 2026 | **Confirmed.** v3.2.0 published 2026-06-20 ("Initial public release for VMAF v1"); v3.2.1 on 2026-09-14 | [23] |
| a2 | v1 includes a phone model and HFR variants | **Confirmed.** Phone = `vmaf_v1.0.16_5d0h` (5H); 4K `1d5h_2160` (default) and `3d0h_2160` (range 0-110); `_hfr` variants for ~50/60 fps, named `vmaf_v1.0.16_hfr_<cond>` (not `..._<cond>_hfr`). Netflix says measure SDR at 10-bit and calls HFR handling still immature | [24] |
| a3 | BtbN static builds include them | **Confirmed from build source**, not from a binary: `-Dbuilt_in_models=true`, pin `86da14d` (2026-09-16, v3.2.1 + 8) whose `model.c`/`meson.build` embed all 8 v1 models. Script last touched 2026-09-23. Runtime check (`ffmpeg -h filter=libvmaf`, `model=version=vmaf_v1.0.16_5d0h`) still to do on the benchmark host | [25][26] |
| b1 | ab-av1 #311: VFR phone footage gives VMAF ~34, closed not planned | **Confirmed.** Opened 2025-07-04 on ab-av1 0.10.1, Xiaomi POCO X5 HEVC VFR; `crf 32 VMAF 34.48` (range ~12-35) vs `93.37` after `fps=30`; closed 2025-08-17, `state_reason: not_planned`. Only reply: "VFR = problems" | [4] |
| b2 | Has anything changed since #311? | **New:** v0.10.4 (2026-02-01) uses `-fps_mode passthrough` for sample encodes (#335), not for the final encode. Not shown to fix #311. Open: #341 (wrong VMAF with `--reference-vfilter fps=30` on 60 to 30 fps), #391 (`fps_mode=cfr` breaks size estimate) | [2][6][7] |
| b3 | Current ab-av1 version and features | **Confirmed.** v0.11.7 (2026-08-21), MIT, 1 020 stars. `--verify` = `--verify-decode` + `--verify-duration` (v0.11.7); `--stdout-format json` for `crf-search` since v0.11.5 and `sample-encode`; v1 model auto-scaling incl. `hfr` variants (v0.11.7); SVT-AV1 quarter-step CRF needs SVT-AV1 ≥ 4.0.0 (v0.11.0) | [2][5] |
| c1 | Tdarr licensing | **Proprietary.** EULA in `LICENSE.md`, three tiers, no redistribution, no reverse engineering. Plugins repo GPL-3.0 | [16] |
| c2 | FileFlows licensing | **Proprietary / closed source.** No public core repo; "All rights reserved"; Video Encode Optimized needs a valid license. Old AGPL snapshot (2021-2023) exists, irrelevant | [18][19][20] |
| d | HandBrake creation-date passthru (conflict A vs B) | Resolved: in 1.10.0 release notes, missing from the docs list | [13][14] |
| e | Av1an metadata issue #678 and VFR issue #828 still open | **Confirmed open** | [11][12] |
| f | Unmanic has a post-encode VMAF audit | **Confirmed:** `vmaf_quality_audit` in `unmanic-plugins` (official branch); 0.4.1 = 2026-08-14 | [21][22] |
| g | johnvansickle: GPLv3, last build 2024-06-29 | **Unverified** in this pass (site timed out; search found only third-party mirrors listing 7.0.2). Consistent with the project's Jan 2026 use of 7.0.2 / libvmaf 2.3.0 | [29][47] |
| h | Community (Reddit, HN, Doom9) claims | **Not re-checked**; kept as single-report anecdotes | — |

## 4. Benchmark candidates

Encoders and rate control
- `libx265 -preset slow` and `veryslow`, fixed CRF sweep per category; MP4 `-tag:v hvc1`, Opus audio (AAC fallback arm).
- `libsvtav1` preset 2-6, CRF sweep with 0,25 steps (needs SVT-AV1 ≥ 4.0; check the BtbN build's version) [2].
- Comparison arm: `ab-av1 crf-search -e libx265 --min-vmaf {93,95,97} --stdout-format json` per clip, then the resulting size vs the category preset at equal p5 VMAF. Only meaningful after VFR handling is settled.
- Compare encoders at matched size or matched metric, never matched CRF.

Metrics
- VMAF v1 `vmaf_v1.0.16_3d0h` (desktop/Haruna/Windows) and `vmaf_v1.0.16_5d0h` (phones); `vmaf_v1.0.16_hfr_3d0h` / `_hfr_5d0h` for 50/60 fps sources; v0.6.1 as a reference to the January results [24][25].
- Measure at 10-bit (`format=yuv420p10le` on both inputs) as Netflix recommends; pass `cambi.enc_width/enc_height/enc_bitdepth` for the 720p dance downscale [24].
- XPSNR as the libvmaf-free fallback and fast-gate candidate [47].
- Report mean plus p1/p5 and the worst 1-2 s window; ab-av1 reports mean only [5].

Alignment and VFR
- Reproduce ab-av1 #311 on an Android VFR clip: raw vs `fps_mode passthrough` vs CFR-normalised vs frame-index comparison. Keep it as a regression test [4][6].
- Record frame count, duration, time base and fps grid of input and output in MP4 and MKV; Netflix's ffmpeg guide requires synchronised PTS (e.g. `setpts=PTS-STARTPTS`) on both inputs `[B only]` [30].
- Webinar fps reduction (30 to 24/25 and `mpdecimate`): define the comparison first (reference resampled with the same `fps` filter, or frame-matched by timestamp) and test it against ab-av1 #341's failure case [7].

Per-file gate (time it per GB on the 7950X3D)
- Full decode with `-xerror`; duration delta; frame count delta; stream set (video, audio, data/`apac`).
- Read-back of `creation_time`, GPS (QuickTime keys and `©xyz`), rotation/display matrix; file mtime restored.
- Optional XPSNR or subsampled VMAF on 2-3 short segments.

Test clips
- Android VFR 30 and 60 fps HEVC/H.264, `yuvj420p` full range, rotated, with GPS (apartment, holiday).
- iPhone clip with `apac` spatial audio if available [8].
- Dance 1080p60 downscaled to 720p; webinar MKV screen recording; Zoom-style call; static session recording.

Toolchain
- BtbN `gpl` build (n8.1 or n9.0 line): verify `-filters` lists `libvmaf` and `xpsnr`, and `libvmaf=model=version=vmaf_v1.0.16_5d0h` runs.

## 5. Open questions for the owner

1. **Which VMAF model defines "near-transparent"?** Phone (`5d0h`) is more lenient than desktop (`3d0h`); Windows PCs and Haruna argue for `3d0h` as the acceptance metric, phone model as secondary.
2. **Is a per-file CRF search ever allowed in archive runs** (e.g. holiday clips with mixed content), or is the benchmark the only place it runs?
3. **ffmpeg provisioning:** document "install BtbN gpl build" only, or let the tool download a pinned BtbN build on first run? The second is more convenient and, if the tool fetches rather than ships the binary, likely stays outside redistribution; still a licensing call.
4. **Project license** (MIT / Apache-2.0 / GPL): any choice works when ffmpeg and ab-av1 are external processes.
5. **Time budget for the per-file fast check** (e.g. ≤ 10 % of encode time), which decides whether full decode plus sampled XPSNR fits.

## 6. Sources

1. [alexheretic/ab-av1 README](https://github.com/alexheretic/ab-av1) - primary
2. [ab-av1 CHANGELOG](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md) - primary
3. [ab-av1 `src/command/args/vmaf.rs`](https://github.com/alexheretic/ab-av1/blob/main/src/command/args/vmaf.rs) and [`src/`](https://github.com/alexheretic/ab-av1/tree/main/src) - primary
4. [ab-av1 issue #311](https://github.com/alexheretic/ab-av1/issues/311) - primary
5. [ab-av1 stdout-format-json.md](https://github.com/alexheretic/ab-av1/blob/main/stdout-format-json.md) - primary
6. [ab-av1 issue #335: `-fps_mode passthrough` for sample encodes](https://github.com/alexheretic/ab-av1/issues/335) - primary
7. [ab-av1 issue #341: abnormal VMAF with `--reference-vfilter` fps change](https://github.com/alexheretic/ab-av1/issues/341) and [#391](https://github.com/alexheretic/ab-av1/issues/391) - primary
8. [ab-av1 issue #351 (iPhone `apac`)](https://github.com/alexheretic/ab-av1/issues/351), [#333 (container timebase)](https://github.com/alexheretic/ab-av1/issues/333) - primary
9. [rust-av/Av1an](https://github.com/rust-av/Av1an), [target-quality docs](https://rust-av.github.io/Av1an/Cli/target_quality.html), [releases](https://github.com/rust-av/Av1an/releases) - primary
10. [Av1an PR #988: new target-quality metrics](https://github.com/rust-av/Av1an/pull/988) - primary
11. [Av1an issue #828: VFR encoding](https://github.com/rust-av/Av1an/issues/828) - primary
12. [Av1an issue #678: copy audio streams and metadata](https://github.com/rust-av/Av1an/issues/678) - primary
13. [HandBrake releases (1.10.0, 1.11.2)](https://github.com/HandBrake/HandBrake/releases) - primary
14. [HandBrake metadata passthru doc](https://handbrake.fr/docs/en/latest/advanced/metadata-passthru.html) - primary
15. [HandBrake CLI reference](https://handbrake.fr/docs/en/latest/cli/command-line-reference.html) - primary
16. [Tdarr LICENSE.md (EULA)](https://github.com/HaveAGitGat/Tdarr/blob/master/LICENSE.md) - primary
17. [Tdarr_Plugins runHealthCheck](https://github.com/HaveAGitGat/Tdarr_Plugins/tree/master/FlowPluginsTs/CommunityFlowPlugins/video/runHealthCheck) - primary
18. [FileFlows: Video Encode Optimized](https://fileflows.com/docs/plugins/video-nodes/ffmpeg-builder/video-encode-optimized) - primary
19. [FileFlows pricing](https://fileflows.com/pricing) - primary
20. [FreekingDean/FileFlows (AGPL snapshot, 2021-2023)](https://github.com/FreekingDean/FileFlows) - primary
21. [Unmanic/unmanic](https://github.com/Unmanic/unmanic) - primary
22. [unmanic-plugins, official branch](https://github.com/Unmanic/unmanic-plugins/tree/official/source) - primary
23. [Netflix/vmaf releases](https://github.com/Netflix/vmaf/releases) - primary
24. [Netflix VMAF models_v1.md](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v1.md) - primary
25. [libvmaf `model.c`](https://github.com/Netflix/vmaf/blob/86da14d0306a138fd3f01319860b905169746516/libvmaf/src/model.c) and [`meson.build`](https://github.com/Netflix/vmaf/blob/86da14d0306a138fd3f01319860b905169746516/libvmaf/src/meson.build) at BtbN's pin - primary
26. [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), [`scripts.d/45-vmaf.sh`](https://github.com/BtbN/FFmpeg-Builds/blob/master/scripts.d/45-vmaf.sh), [releases](https://github.com/BtbN/FFmpeg-Builds/releases) - primary
27. [FFmpeg License and Legal Considerations](https://www.ffmpeg.org/legal.html) - primary
28. [GNU GPL FAQ: mere aggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation) - primary
29. [John Van Sickle static builds](https://johnvansickle.com/ffmpeg/) - primary (not reachable in this pass)
30. [Netflix VMAF FFmpeg guide](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) - primary
31. [slhck/ffmpeg-quality-metrics](https://github.com/slhck/ffmpeg-quality-metrics) - primary
32. [gdavila/easyVmaf](https://github.com/gdavila/easyVmaf) - primary
33. [HN: "What I learned about deploying AV1", Dec 2025](https://news.ycombinator.com/item?id=46345756) - community
34. [HN comment, Feb 2026: avoid GPU encodes for archival](https://news.ycombinator.com/item?id=47030585) - community
35. [Doom9: x265 near-lossless settings and VMAF](https://forum.doom9.org/archive/index.php/t-186479.html) - community
36. [Doom9: x265 for fast motion and fine detail](https://forum.doom9.org/archive/index.php/t-187079.html) - community
37. [VideoHelp: phone clips x265 CRF 28](https://forum.videohelp.com/showthread.php?p=2622599) - community, date unverified
38. [r/DataHoarder: archiving video when raw cannot be kept (Dec 2025)](https://www.reddit.com/r/DataHoarder/comments/1pwpym1/how_do_you_archive_video_when_you_cant_keep_raw/) - community
39. [r/DataHoarder: storage is no longer cheap (Jul 2026)](https://www.reddit.com/r/DataHoarder/comments/1v7kg57/well_storage_is_no_longer_cheap-how-many-of-you/) - community
40. [r/AV1: re-encoding older family videos (Jun 2026)](https://www.reddit.com/r/AV1/comments/1uasg6f/reencoding_older_videos_to_av1_quality/) - community
41. [r/ffmpeg: phone footage turning into 120 fps](https://www.reddit.com/r/ffmpeg/comments/1s0ee4z/ffmpeg_keeps_turning_my_24fps_phone_camera/) - community
42. [r/ffmpeg: CRF optimisation experiment](https://www.reddit.com/r/ffmpeg/comments/1vxf6lc/crfbased_video_encoding_optimization_i_wasted_my/) - community
43. [FFmpeg docs: `-fps_mode`](https://www.ffmpeg.org/ffmpeg.html) - primary
44. Newer tools: [xav](https://github.com/emrakyz/xav), [ffdash](https://github.com/bcherb2/ffdash), [RabbitEncoder](https://github.com/Rabbit-Company/RabbitEncoder), [av1q](https://github.com/heyuforia/av1q), [phone-media-reducer](https://github.com/2020-abhilash/phone-media-reducer), [media-library-compressor](https://github.com/Ghorbel37/media-library-compressor), [Video-AV1-Optimizer](https://github.com/emike09/Video-AV1-Optimizer), [VideoTuner](https://github.com/sleepy-af-dev/VideoTuner), [ffvm](https://github.com/birkdev/ffvm), [transQrate](https://github.com/dermute/transqrate), [Viser](https://github.com/vbasky/viser) - primary (READMEs)
45. [codecs.wiki: VMAF](https://codecs.wiki/docs/metrics/VMAF), [encode.wiki: SSIMULACRA2](https://encode.wiki/reference/metrics/ssimulacra2) - secondary, predate VMAF v1
46. [FFmpeg trac #4209 comment, Apr 2024](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-April/069027.html) - primary
47. Local observations: Report A's check of Ubuntu `ffmpeg 8.0.1-3ubuntu2` (`xpsnr`, `psnr`, `ssim`, `vmafmotion`, no `libvmaf`); notes from the January 2026 prototype, not published (johnvansickle 7.0.2 with libvmaf 2.3.0, BtbN n7.1 used) - primary observation / history
48. [static-ffmpeg on PyPI](https://pypi.org/project/static-ffmpeg/) - primary
