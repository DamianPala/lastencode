# T1: Existing tools and where a new tool fits

Research date: 2026-10-20. Method: web search, GitHub API (repo stats, releases, issues, source), primary docs, one local check on the project host.
Limits: Reddit was not reachable (search engine returned no Reddit threads, direct API blocked), so the community angle leans on Hacker News, Doom9, VideoHelp, ExifTool/Synology forums and GitHub issues. The session's web-search budget ran out near the end, so two follow-ups (johnvansickle builds, Debian libvmaf status) stay open in Gaps.

### TL;DR

No maintained open-source tool combines quality-targeted encoding with phone-video realities: VFR timestamps, `creation_time`/GPS for gallery apps, per-file verification and per-content-type presets.
ab-av1 (MIT, CLI, JSON output) is the only clean backend candidate for a CRF search, but it has a known VFR sample-desync problem on phone footage and leaves metadata to ffmpeg defaults [1][3][4]. Av1an, HandBrake, Tdarr, FileFlows and Unmanic either lack target quality, lack metadata care, or are proprietary [6][11][13][15][19].
Recommendation (synthesis): build the project as its own thin Python orchestrator over ffmpeg + exiftool, keep VMAF measurement in-house for benchmark mode, and treat ab-av1 as an optional per-file CRF-search backend, not the core.

### Key Findings

#### Q1. Maintained tools for quality-targeted re-encoding

Comparison table (stats from GitHub API on 2026-10-20 unless marked):

| Tool | Encoders | Target-quality method / metric | Granularity | Verification after encode | Metadata (creation_time, GPS, rotation) | License | Activity | CLI ergonomics |
|---|---|---|---|---|---|---|---|---|
| **ab-av1** [1][2][3] | Any ffmpeg encoder; default `libsvtav1`, also `libx265`, `libx264`, `libvpx-vp9`, HW encoders via `-e` | Interpolated binary search over sample encodes; `--min-vmaf` (default 95) or `--min-xpsnr`; also `--max-encoded-percent` | Per file (samples: 20 s each, one per 12 min; short files get a full pass) | `--verify` (full decode + duration within 2 s), `--fail-fast` (both since v0.11.7) | Relies on ffmpeg defaults: `-map 0`, no `-map_metadata`, no exiftool; drops data streams for MKV (`-dn`); adds its own `AB_AV1_FFMPEG_ARGS` tag | MIT | v0.11.7 (2026-08-21), 1 020 stars, pushed 2026-09 | Single static musl binary; `--stdout-format json` (NDJSON) for `crf-search`/`sample-encode` |
| **Av1an** [6][7][8] | aomenc, SvtAv1EncApp, rav1e, vpxenc, x264, x265 (standalone binaries) | Per-chunk probing; metrics VMAF, SSIMULACRA2, Butteraugli (inf, 3-norm), XPSNR, weighted XPSNR (added in 0.5) | Per scene/chunk | Frame-count checks; no decode/duration verify documented | Not covered in docs; open issue "Copy multiple audio streams and leave metadata" since 2022 [10] | GPL-3.0 | v0.5.2 (2026-01-04), 2 001 stars, pushed 2026-10-16 | Heavy: needs VapourSynth + plugins (vszip, vship, julek) for the newer metrics; MKV-centric |
| **HandBrake / HandBrakeCLI** [11][12] | x264, x265, SVT-AV1 4.1.0 (in 1.11.2), HW encoders | None: constant quality `-q` only | Per file | None (no metric options) | 1.10.0 (2025-08-09) added passthru of creation date and location; `--keep-metadata` | GPLv2 [47] | 1.11.2 (2026-06-07), 24 721 stars | JSON presets via `--preset-import-file`; `--vfr` default keeps source timing |
| **Tdarr** [13][14][43] | ffmpeg or HandBrake (any) | No built-in target quality; community plugins exist (e.g. third-party ab-av1 wrappers) | Per file | Health check: quick (HandBrake) or thorough (ffmpeg full decode) | Plugin-dependent | **Proprietary EULA** (free/personal/business tiers); plugins GPL-3.0 | 3.01.00 (2026-10-15), 4 361 stars | Server + nodes web app, not a CLI |
| **FileFlows** [15][16][17][18] | H.264, HEVC (8/10-bit), AV1 (8/10-bit), "automatic" encoder pick incl. HW | "Video Encode Optimized": sample encodes scored with VMAF against "Minimum VMAF", modes Fast/Balanced/Thorough/Custom | Per file | Compute VMAF task (Forge) | Not documented | **Proprietary freemium**; Video Encode Optimized "available only with a valid FileFlows license"; no public core repo found; a fork's README says "All Rights Reserved" | 26.10 image (2026-10-16) | Web app with flow editor, not a CLI |
| **Unmanic** [19][20] | libx265, libsvtav1, NVENC/QSV/VAAPI (video_transcoder plugin 0.1.20) | None; fixed CRF (default 28 for x265) | Per file | Optional "VMAF Quality Audit" plugin (post-encode VMAF vs source, sampled 1-min chunks or whole file) | Plugin-dependent | GPL-3.0 | 0.4.1 (2026-08-14), 2 530 stars | Python web app/library optimiser, not a CLI |

Newer (2025-2026) entrants, all emerging or experimental:
- **xav** (emrakyz, created 2025-09-22, 95 stars, no clear license): chunked encoder with target quality on CVVDP, Butteraugli and SSIMULACRA2; avoids ffmpeg/VapourSynth entirely [40]. Experimental.
- **ffdash** (MIT, 143 stars, pushed 2026-10-05): TUI batch AV1/VP9 encoder with a VMAF target, default 93 [41].
- **Auto-Boost-Essential** ecosystem (RabbitEncoder, portable wrappers, GPL-3.0, 13-20 stars): SSIMULACRA2-driven zone boosting on top of Av1an/SVT-AV1, aimed at anime/film rips (repo search, 2026-10-20) [39].
- A long tail of tiny phone/library compressors (0-12 stars): `media-library-compressor` (exiftool clone of all metadata, restores dates), `phone-media-reducer` (x265 CRF 28 + exiftool GPS/rotation copy, created 2026-09), `MovieCompressor`, `batch-media-compressor`, `transcode`, `av1q` (VMAF-targeted AV1 with final VMAF check) [39].

- **What**: Based on [1][6][16], only ab-av1, Av1an and FileFlows do real target-quality search; only Av1an does it per scene; only HandBrake documents creation-date/location passthru [11]; verification after encode exists in ab-av1 (decode + duration), Tdarr (decode), Unmanic (VMAF audit plugin) [2][14][20].
- **Evidence**: [1][2][3][6][7][8][11][12][13][14][15][16][19][20]
- **Confidence**: high for features and licenses (primary docs and source read directly); medium for FileFlows source status (no public repo found, fork notice single-source [18]).

#### Q2. Reuse as a backend, licensing and ffmpeg packaging

- **What (backends)**: Based on [1][5], ab-av1 is directly scriptable: `ab-av1 crf-search -e libx265 --min-vmaf N --stdout-format json` emits NDJSON (`sample-encode-done`, `crf-search-done` with `crf`, mean `vmaf`, predicted size/time), and failures exit non-zero. It needs ffmpeg with libsvtav1, libvmaf, libopus on `$PATH` [1]. Av1an is a Rust binary with VapourSynth and plugin dependencies, GPL-3.0 [6][8]; calling it is possible but drags a heavy toolchain. HandBrakeCLI is callable but adds nothing a direct ffmpeg call does not, except its metadata passthru [11][12]. Tdarr and FileFlows are proprietary servers and cannot be a backend for a public CLI [13][15][16]. Unmanic is GPL-3.0 Python but is a library-watching server; reusing it means writing an Unmanic plugin, not a CLI [19][20].
- **What (metric libraries for benchmark mode)**: Based on [27], `ffmpeg-quality-metrics` (MIT, v3.13.0 on 2026-10-14) computes PSNR/SSIM/VMAF/VIF from Python, warns on resolution/frame-rate/duration mismatch, and supports the new VMAF v1 models only with libvmaf 3.2.1+. Based on [28], `easyVmaf` (MIT) does frame-accurate sync via a PSNR search before libvmaf.
- **What (VMAF v1)**: Based on [21][22], Netflix released VMAF v1 models in libvmaf v3.2.0 (2026-06-20), including a **phone model** (5H viewing distance), 4K variants and `_hfr` variants for ~50/60 fps, and recommends measuring SDR at 10-bit to catch banding (CAMBI). ab-av1 v0.11.7 already supports auto-scaling for the `vmaf_v1.0.16_*` models [2], but its default remains the v0.6.1 model [3].
- **What (ffmpeg builds)**: Based on [23], BtbN publishes daily static Linux x86_64 builds in `gpl`, `lgpl` and `nonfree` variants; the `lgpl` variant lacks libx264/libx265. Its libvmaf recipe pins a Netflix commit from 2026-09-16 (21 commits after v3.2.0) with built-in models, so v1 models should be available (verify `ffmpeg -filters` and model names on a real build). On the project host, Ubuntu's `ffmpeg 8.0.1-3ubuntu2` has the native `xpsnr`, `psnr`, `ssim` filters but no `libvmaf` [44]; the XPSNR filter is in FFmpeg since 7.1 [45]. The PyPI `static-ffmpeg` 3.0 (2026-01-16) downloads ffmpeg 8.0 from its own `ffmpeg_bins` repo and does not mention libvmaf [26].
- **What (licensing)**: Based on [24], FFmpeg built with GPL parts (x264/x265) is GPL as a whole; redistributing binaries carries source-offer and notice duties. Based on [25], the FSF treats programs communicating via exec, pipes and command-line arguments as normally separate programs ("mere aggregation"), so an MIT/Apache Python CLI that shells out to a user-installed GPL ffmpeg, ab-av1 (MIT) or Av1an (GPL-3.0) stays under its own license. Synthesizing across sources: do not vendor ffmpeg binaries in the wheel or repo; document "install BtbN `gpl` build or distro ffmpeg + check for libvmaf", detect capabilities at runtime (`-filters`, `-encoders`), and fall back to XPSNR when libvmaf is missing. This is not legal advice.
- **Evidence**: [1][2][3][5][6][8][11][12][13][15][16][19][20][21][22][23][24][25][26][27][28][44][45]
- **Confidence**: high for build variants, VMAF v1 facts and the ab-av1 interface; medium for the licensing synthesis (FSF position is clear, but untested in court per [25]).

#### Q3. What personal/phone-video archivers recommend and report

- **What (workflows)**: Based on [34], HN users in Dec 2025 report running ab-av1 or Av1an with a VMAF target of 95-96 to transcode collections overnight, plus a Python GUI wrapper for ab-av1. Based on [37], a VideoHelp user settled on 1080p30 x265 CRF 28 for phone clips for 50-80 % savings. Based on [42], a 2025 note frames ab-av1 as fitting "reduce size while ensuring minimum quality" and Av1an as fitting archiving [single-source]. Based on [35], an HN commenter (Feb 2026) advises against GPU encodes for archival and points to CPU AV1 via Av1an, which matches the project's own finding.
- **What (pitfalls)**:
  - Generation loss and "keep the originals": HN commenters warn that re-encoding an already-lossy H.265 source cannot gain quality and AV1 gains shrink on such sources [34]; older sources say the same [38] (2021, possibly stale).
  - VFR phone footage breaks sample-based VMAF: ab-av1 issue #311 shows a VMAF of ~34 on a VFR phone HEVC clip because the sample cutter mishandled VFR timing; CFR conversion gave 93,37; closed "not planned" in Aug 2025 [4]. Av1an issue #828 (open since 2024) reports very low VMAF on 4K60 phone video with dropped frames [9].
  - Metadata loss: FFmpeg ticket #4209 (open, reproduced, 2024 comment) shows GPS copied with `-movflags use_metadata_tags -map_metadata 0` lands in `moov/udta/meta` keys that Apple apps do not read [31]. Gallery apps sort by specific QuickTime date tags: Immich has a fixed priority list of date tags [32]; Synology Photos reportedly falls back to file mtime when its tags are missing, so re-encoded videos land on the conversion date [33] (2021 forum report, possibly stale). Common fix in forums: copy tags back with `exiftool -TagsFromFile` [31][33].
  - Phone-specific streams: ab-av1 failed on iPhone videos with an `apac` spatial-audio stream (fixed, closed 2026-03) [49]; container/timebase mismatches in samples were fixed by matching containers (closed 2026-01) [50].
  - Noisy handheld footage compresses badly; Doom9 advice is to denoise lightly (e.g. KNLMeans) or downscale rather than lean on x265 options, and some posters say "just keep the source" for high-bitrate action-cam clips [36].
  - Metric choice: community wikis say VMAF (v0.6.x) is weak at near-transparent quality and blind to some AV1/VVC artifacts; SSIMULACRA2 and Butteraugli are the enthusiast standard for high-fidelity tuning [29][30].
- **What (missing tools)**: Synthesizing across sources, people stitch together ffmpeg + exiftool by hand or with tiny scripts [39]; the dedicated target-quality tools are built for movie/anime libraries in MKV and ignore phone metadata and gallery-app compatibility [1][6][10].
- **Evidence**: [4][9][29][30][31][32][33][34][35][36][37][38][39][42][49][50]
- **Confidence**: medium. Primary issue trackers are solid; community opinion is thin because Reddit could not be reached, and several forum sources are undated or old.

#### Q4. Gap analysis: is there a niche?

- **What (facts)**: Based on [1][3][4], ab-av1 picks a CRF per file from the **mean** sample VMAF, analyses at a forced frame rate (`--vmaf-fps`, default 25), defaults to the v0.6.1 model, and does not copy container metadata beyond ffmpeg defaults. Based on [6][10], Av1an targets per-scene quality but is MKV/VapourSynth-centric with metadata handling unaddressed. Based on [11][12], HandBrake handles creation date and location but has no quality metric. Based on [13][15][16], the server tools are proprietary or plugin-dependent.
- **What (synthesis)**: The niche is real but narrow. What the new tool adds that none of the above combine:
  1. Content-category presets tuned once in benchmark mode (fixed CRF/preset/filters per category) instead of a per-file search; fast and deterministic on archive runs.
  2. VFR-safe measurement: normalise both reference and distorted to the same CFR grid (or compare by frame index after checking frame counts) before VMAF/XPSNR, the exact failure ab-av1 #311 and Av1an #828 hit [4][9].
  3. Gallery-app metadata as a first-class feature: copy QuickTime/Keys/UserData dates and GPS with exiftool into the tags Immich/Apple/Synology read, restore file mtime, keep rotation, then **verify** they are present [31][32][33].
  4. A fast per-file gate: decode check + duration + frame count + metadata presence + cheap metric (XPSNR or subsampled VMAF) before offering deletion of originals; ab-av1's `--verify` covers only decode and duration [2].
  5. Phone-aware metrics in benchmark mode: VMAF v1 phone and HFR models, plus XPSNR when libvmaf is absent [21][27][44].
- **Decision**: Synthesizing across sources, do not make the project a thin layer over ab-av1 or Av1an. Own the ffmpeg + exiftool pipeline, verification and metadata; optionally call `ab-av1 crf-search --stdout-format json` for categories with mixed content (holiday clips) after VFR normalisation, with the result validated by the project's own metric.
- **Evidence**: [1][2][3][4][6][9][10][11][12][13][15][16][21][27][31][32][33][44]
- **Confidence**: medium (the gap is well evidenced; whether per-file CRF search beats per-category fixed CRF for this footage is untested).

### Perspectives

- **Per-file search vs fixed CRF per category.** ab-av1/FileFlows users argue a per-file VMAF target saves space without guessing [1][16][34]. Doom9/VideoHelp posters work with fixed CRF per footage type and accept size variance [36][37]. Per-file search on short phone clips often degenerates to a full pass, since ab-av1 switches to full-pass when samples would cover 85 % of the clip [3]; that removes most of its speed advantage for 10-60 s clips.
- **VMAF vs SSIMULACRA2/Butteraugli.** Netflix claims better accuracy with VMAF v1 and adds phone and HFR models [21]. Community wikis predate v1 and consider VMAF unreliable near transparency, preferring SSIMULACRA2 [29][30]. No independent comparison of VMAF v1 against SSIMULACRA2 was found.
- **Re-encode at all?** One camp re-encodes whole libraries and is happy [34][37]; another says lossy-to-lossy re-encoding of already compressed sources is "subtly very bad" and gains little going H.265 to AV1 [34][38]. The project's "keep originals by default" stance sits between them.
- **ab-av1 for archiving vs distribution.** A 2025 note positions ab-av1 for size reduction with a quality floor and Av1an for archiving [42]; HN users use either for archiving [34]. Opinion, single-source.

### Practical Implications

- **Architecture**: Python CLI (MIT or Apache-2.0) calling `ffmpeg`, `ffprobe`, `exiftool` and optionally `ab-av1` as subprocesses; no bundled binaries [24][25].
- **ffmpeg detection**: at startup check `-encoders` for `libx265`/`libsvtav1` and `-filters` for `libvmaf` and `xpsnr`; recommend the BtbN `gpl` build when libvmaf is missing (Ubuntu's 8.0.1 lacks it) [23][44].
- **Benchmark matrix candidates**:
  - Encoders: `libx265` slow/veryslow vs `libsvtav1` 4.x preset 2-6 (SVT-AV1 4.0 added quarter-step CRF [2]).
  - Rate control: per-category fixed CRF vs `ab-av1 crf-search` per file (targets VMAF 93/95/97) on the same clips.
  - Metrics: VMAF v0.6.1 vs VMAF v1 `3d0h`, `5d0h` (phone), `_hfr` for 60 fps, XPSNR; record mean and low percentiles (p1/p5), not mean only [3][21][27].
  - Measurement alignment: CFR-normalised vs frame-index comparison on VFR sources; reproduce the ab-av1 #311 failure as a regression test [4].
- **Fast per-file verification** (each file): full decode with `-xerror`, duration delta, frame count delta, presence of `creation_time`/QuickTime dates/GPS/rotation in output, file mtime restored, optional XPSNR on a few short segments [2][14][31].
- **Metadata step**: after encode, `exiftool -TagsFromFile src` for QuickTime date and GPS groups, then read back and check the tags Immich/Apple Photos/Synology use; test each gallery app once by hand [31][32][33].
- **What not to adopt**: Av1an (VapourSynth stack, MKV, open metadata issue) [6][8][10]; Tdarr/FileFlows (proprietary) [13][15]; HandBrake as an engine (no metric) [12], though its 1.10 metadata passthru is a useful reference implementation [11].

### Sources

1. [alexheretic/ab-av1 README](https://github.com/alexheretic/ab-av1) - primary: commands, metrics, `--verify`, requirements, MIT.
2. [ab-av1 CHANGELOG](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md) - primary: v0.11.x changes (verify, hvc1 default, JSON output, VMAF v1 model scaling, SVT-AV1 4.0 quarter-step CRF).
3. [ab-av1 source `src/`](https://github.com/alexheretic/ab-av1/tree/main/src) - primary: ffmpeg encode args (`-map 0`, no `-map_metadata`), sample defaults (20 s every 12 min), `--vmaf-fps`, default model, min VMAF 95 (read 2026-10-20).
4. [ab-av1 issue #311: crf-search fails on VFR video](https://github.com/alexheretic/ab-av1/issues/311) - primary: VFR phone clip VMAF ~34, closed not planned 2025-08.
5. [ab-av1 stdout-format-json.md](https://github.com/alexheretic/ab-av1/blob/main/stdout-format-json.md) - primary: NDJSON message schema.
6. [rust-av/Av1an README](https://github.com/rust-av/Av1an) - primary: encoders, target quality, dependencies, GPL-3.0.
7. [Av1an release 0.5](https://github.com/rust-av/Av1an/releases/tag/0.5) and [CHANGELOG](https://github.com/rust-av/Av1an/blob/master/CHANGELOG.md) - primary: 0.5 (2025-10-02) to 0.5.2 (2026-01-04).
8. [Av1an PR #988: new target quality metrics](https://github.com/rust-av/Av1an/pull/988) - primary: SSIMULACRA2, Butteraugli, XPSNR and required VapourSynth plugins.
9. [Av1an issue #828: Question about VFR encoding](https://github.com/rust-av/Av1an/issues/828) - primary: low VMAF on 4K60 phone video, open.
10. [Av1an issue #678: Copy multiple audio streams and leave metadata](https://github.com/rust-av/Av1an/issues/678) - primary: open since 2022 (title and status only).
11. [HandBrake releases 1.10.0 / 1.11.0 / 1.11.2](https://github.com/HandBrake/HandBrake/releases) - primary: metadata passthru (creation date, location), bundled SVT-AV1/x265/FFmpeg versions.
12. [HandBrake CLI reference](https://handbrake.fr/docs/en/latest/cli/command-line-reference.html) - primary: presets, `-q`, `--vfr`, `--keep-metadata`, no metric options.
13. [HaveAGitGat/Tdarr README and LICENSE.md](https://github.com/HaveAGitGat/Tdarr) - primary: architecture, proprietary EULA with tiers.
14. [Tdarr_Plugins runHealthCheck](https://github.com/HaveAGitGat/Tdarr_Plugins/tree/master/FlowPluginsTs/CommunityFlowPlugins/video/runHealthCheck) - primary: quick (HandBrake) vs thorough (ffmpeg) health check.
15. [FileFlows pricing](https://fileflows.com/pricing) - primary: free tier limits, paid tiers.
16. [FileFlows: FFmpeg Builder Video Encode Optimized](https://fileflows.com/docs/plugins/video-nodes/ffmpeg-builder/video-encode-optimized) - primary: VMAF-sampled optimisation, license requirement.
17. [FileFlows: Compute VMAF task](https://fileflows.com/docs/forge/tasks/compute-vmaf) - primary: VMAF on Forge.
18. [Delta5/FileFlows fork README](https://github.com/Delta5/FileFlows) - primary but indirect (seen via search): "All Rights Reserved" notice [single-source].
19. [Unmanic/unmanic](https://github.com/Unmanic/unmanic) - primary: GPL-3.0, releases.
20. [Unmanic plugins (official branch): video_transcoder, vmaf_quality_audit](https://github.com/Unmanic/unmanic-plugins/tree/official/source) - primary: encoders, default CRF, post-encode VMAF audit.
21. [Netflix VMAF models_v1.md](https://github.com/Netflix/vmaf/blob/master/resource/doc/models_v1.md) - primary: VMAF v1 phone, 4K, HFR models.
22. [Netflix VMAF releases](https://github.com/Netflix/vmaf/releases) - primary: v3.2.0 (2026-06-20) VMAF v1, v3.2.1 (2026-09-14).
23. [BtbN/FFmpeg-Builds README](https://github.com/BtbN/FFmpeg-Builds) and [scripts.d/45-vmaf.sh](https://github.com/BtbN/FFmpeg-Builds/blob/master/scripts.d/45-vmaf.sh) - primary: variants, libvmaf pin with built-in models.
24. [FFmpeg License and Legal Considerations](https://www.ffmpeg.org/legal.html) - primary: LGPL/GPL, distribution checklist.
25. [GNU GPL FAQ: aggregate vs modified versions](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation) - primary: exec/pipes/CLI args as separate programs (text via search excerpt; direct fetch rate-limited).
26. [static-ffmpeg on PyPI](https://pypi.org/project/static-ffmpeg/) - primary: v3.0, ffmpeg 8.0 from ffmpeg_bins.
27. [slhck/ffmpeg-quality-metrics](https://github.com/slhck/ffmpeg-quality-metrics) - primary: Python metrics lib, VMAF v1 needs libvmaf 3.2.1+.
28. [gdavila/easyVmaf](https://github.com/gdavila/easyVmaf) - primary: VMAF with frame sync.
29. [codecs.wiki: VMAF](https://codecs.wiki/docs/metrics/VMAF) - secondary (community wiki, describes v0.6.2 as of Jan 2024).
30. [encode.wiki: SSIMULACRA2](https://encode.wiki/reference/metrics/ssimulacra2) - secondary (community wiki).
31. [FFmpeg trac #4209 comment, April 2024](https://ffmpeg.org/pipermail/ffmpeg-trac/2024-April/069027.html) - primary: GPS copy lands in tags Apple apps ignore; ticket open.
32. [Immich issue #20552](https://github.com/immich-app/immich/issues/20552) - primary: date-tag priority (via search summary).
33. [Synology forum: wrong date for videos](https://www.synoforum.com/threads/wrong-date-time-for-videos-despite-correct-exif-data.6807/) and [NASCompares 2021 thread](https://ask.nascompares.com/showthread.php?tid=3668) - secondary/community: Synology date tags and mtime fallback (2021, possibly stale).
34. [HN thread "What I learned about deploying AV1", Dec 2025 (sub-thread 46345756, comment 46347022)](https://news.ycombinator.com/item?id=46345756) - community: ab-av1/Av1an with VMAF 95-96, generation-loss objections, [AB-AV1-GUI](https://github.com/Loufe/AB-AV1-GUI).
35. [HN comment 47030585, Feb 2026](https://news.ycombinator.com/item?id=47030585) - community: avoid GPU encodes for archival.
36. [Doom9: x265 settings for fast motion and fine detail](https://forum.doom9.org/archive/index.php/t-187079.html) and [Visually lossless x265 settings](https://forum.doom9.org/archive/index.php/t-187075.html) - community (via search summary; dates unverified).
37. [VideoHelp thread p=2622599](https://forum.videohelp.com/showthread.php?p=2622599) - community: phone clips 1080p30 x265 CRF 28, 50-80 % savings (date unverified).
38. [Codecalamity: Stop re-encoding videos (2021)](https://codecalamity.com/stop-re-encoding-videos/) - secondary, older than 2024 (possibly stale).
39. GitHub long tail (repo search 2026-10-20): [media-library-compressor](https://github.com/Ghorbel37/media-library-compressor), [phone-media-reducer](https://github.com/2020-abhilash/phone-media-reducer), [MovieCompressor](https://github.com/PescheHelfer/MovieCompressor), [batch-media-compressor](https://github.com/sabaatworld/batch-media-compressor), [transcode](https://github.com/lucas-albers-lz4/transcode), [av1q](https://github.com/heyuforia/av1q), [RabbitEncoder](https://github.com/Rabbit-Company/RabbitEncoder) - primary (READMEs).
40. [emrakyz/xav](https://github.com/emrakyz/xav) - primary: experimental target-quality encoder.
41. [bcherb2/ffdash](https://github.com/bcherb2/ffdash) - primary: TUI batch encoder, VMAF target default 93.
42. [kituta: av1an Notes (note.com)](https://note.com/ktt_mee/n/n81e1911ced71?hl=en) - secondary blog, 2025 [single-source].
43. [Docker Hub tags: revenz/fileflows, haveagitgat/tdarr](https://hub.docker.com/r/revenz/fileflows/tags) - primary: release activity (FileFlows 26.10, Tdarr 3.01.00).
44. Local check on the project host, 2026-10-20: `ffmpeg -filters` on Ubuntu `8.0.1-3ubuntu2` shows `xpsnr`, `psnr`, `ssim`, `vmafmotion`, no `libvmaf` - primary observation.
45. [FFmpeg 7.1 doxygen: vf_xpsnr.c](https://ffmpeg.org/doxygen/7.1/vf__xpsnr_8c_source.html) - primary: XPSNR filter present in 7.1.
46. (merged into 19)
47. [HandBrake LICENSE](https://github.com/HandBrake/HandBrake/blob/master/LICENSE) - primary: GPLv2.
48. (merged into 34)
49. [ab-av1 issue #351: iPhone `apac` spatial audio](https://github.com/alexheretic/ab-av1/issues/351) - primary, closed 2026-03.
50. [ab-av1 issue #333: matching containers to avoid timebase issues](https://github.com/alexheretic/ab-av1/issues/333) - primary, closed 2026-01.

### Gaps

Not determined, or needs hands-on measurement in the project's benchmark:
- **johnvansickle static builds**: current version, whether libvmaf is included, maintenance status; the site did not respond and the search budget ran out. Same for whether Debian/Ubuntu plan to enable libvmaf.
- **BtbN build and VMAF v1**: confirm that `libvmaf` in the current BtbN `gpl` build accepts `model=version=vmaf_v1.0.16_5d0h` and the `_hfr` models.
- **Metadata survival matrix**: for each path (ffmpeg default, `-map_metadata 0`, `-movflags use_metadata_tags`, exiftool `-TagsFromFile` after encode) and container (MP4 `hvc1`, MKV), check `creation_time`, QuickTime `CreationDate`/`CreateDate`, Android `©xyz` / `location`, rotation/display matrix, and what Immich, Google Photos, Apple Photos and Synology Photos show. Also find why the prototype lost `creation_time`.
- **VFR handling**: frame count and timestamp grid of outputs vs inputs for 30/60 fps VFR Android clips, in MP4 and MKV; reproduce the 4-of-3601 frame loss and the 1 ms Matroska grid; compare CFR-normalised vs frame-index VMAF.
- **ab-av1 on this footage**: does `crf-search` with `-e libx265` give stable CRFs on 10-60 s VFR clips after CFR normalisation; how much size does per-file search save vs the per-category fixed CRF at the same p5 VMAF/XPSNR.
- **Metric agreement**: VMAF v0.6.1 vs v1 (`3d0h`, `5d0h`, `_hfr`) vs XPSNR (vs SSIMULACRA2 if a tool is available) on dance and webinar clips, against the user's own visual judgement.
- **Verification cost**: wall time of full decode + XPSNR on short segments per GB, to keep the "fast check" fast on the 7950X3D.
- **Community views**: Reddit (r/DataHoarder, r/ffmpeg, r/AV1) could not be read; a manual read would strengthen Q3.
- **FileFlows source status**: no public core repo found; the license statement rests on one fork notice.
