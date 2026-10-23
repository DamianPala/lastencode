I’ll research the four angles in the brief, prioritizing current project docs and releases, then checking community reports and licensing details against primary sources. I’ll keep the project’s own January prototype results as hypotheses rather than established findings.

The current tool landscape already includes two quality-search approaches: ab-av1 searches a whole-file CRF from samples, while Av1an encodes scene chunks and can target several metrics. FileFlows has also added a VMAF-based optimized mode, though its preset-like quality labels and licensing model matter for a standalone open-source CLI. I’m checking the packaging and metadata details now, where the project’s fit is less obvious.

The strongest backend candidate has improved since the January prototype: current ab-av1 supports x265 search, defaults x265 MP4 tagging to `hvc1`, and can fully decode and duration-check the finished file. That narrows the project’s defensible gap to archive-specific safety, metadata and VFR handling, category profiles, and a usable benchmark workflow.

### TL;DR

**ab-av1 already covers much of the quality-search core:** it can search a file-level CRF against VMAF or XPSNR for x265 as well as AV1, and current releases add output decoding, duration checks, atomic output handling, and an `hvc1` default for x265. [1][2] Av1an adds per-scene quality targeting; HandBrake provides mature fixed-RF encoding; Tdarr, FileFlows, and Unmanic focus on library automation. [3][4][5][6][7]

The project has a defensible niche as a **safe personal-archive workflow and benchmark layer over existing encoders**, centered on tested category profiles, phone-friendly outputs, metadata and VFR handling, and sensible verification. The evidence does not support rebuilding the CRF search engine from scratch.

### Key Findings

#### 1. Existing tools and newer entrants

**What (source-grounded).** The main distinction is whether a tool searches quality settings for one whole file, adjusts quality by scene, or simply runs a configured transcode.

- **ab-av1** is an MIT-licensed command-line tool with about 1,000 GitHub stars; version 0.11.7 was published on 21 August 2026. Its sample-based CRF search targets a minimum VMAF or XPSNR score and chooses one CRF for the whole file. It supports FFmpeg encoders including `libx265` and `libx264`. Version 0.11.7 added full-output decode and duration checks, with a two-second duration tolerance; v0.11.6 made `hvc1` the default tag for x265, and v0.11.5 added temporary output followed by atomic rename. [1] The crate is explicitly marked “not a library,” so a Python tool should call its CLI; it also offers newline-delimited JSON output. [2] **[single-source: project documentation]** I found no documented guarantee that it preserves all phone `creation_time`, GPS, rotation, or filesystem-mtime data. [1][2]

- **Av1an** is a GPL-3.0 command-line framework with about 2,000 stars; its latest listed release is v0.5.2 from 4 January 2026. It supports AV1, VP9, HEVC, and H.264 with external encoders such as SVT-AV1 and x265. Unlike ab-av1’s one-CRF-per-file search, Av1an can search quality per chunk or scene using VMAF, SSIMULACRA2, Butteraugli, or XPSNR. Its own docs say this mode is slower than normal encoding. [3] It is a plausible optional backend for scene-level experiments, but I found no documented personal-archive metadata contract or explicit equivalent to ab-av1’s final-file verification. [3] **[single-source: project documentation]**

- **HandBrake** is an actively released GPL-2.0 transcoder with about 24,500 stars; version 1.11.2 was released on 7 June 2026. Its CLI supports software x265 and SVT-AV1, along with hardware encoders. Its quality control is fixed RF/CRF for the chosen encoder; the docs explicitly warn that RF values do not compare across encoders. I found no documented automatic VMAF/XPSNR CRF search or per-scene quality targeting. [4] Its “common metadata” passthrough list includes `Location6709`, but that list does not document a complete phone-capture metadata contract, including `creation_time`. [4] **[single-source: project documentation]**

- **Tdarr** is a server-and-node transcoding manager with about 4,300 stars. Its flows can call FFmpeg or HandBrake plugins, and its health-check plugin offers a quick HandBrake check or a more thorough FFmpeg check. The current docs cover V3 and its Rust engine, but it remains a web-managed workflow system rather than a direct Python CLI backend. Its repository’s current license file is a proprietary EULA with free and paid tiers that prohibits redistribution and reverse engineering. [5] **[single-source: project and product documentation]** I found no first-class quality-target search in the reviewed docs; its quality behavior is configured through plugins and flows. [5]

- **FileFlows** has a `Video Encode Optimized` flow element that samples segments and searches compression settings against a minimum VMAF target, with configurable sample count and maximum iterations. It supports H.264, HEVC, and AV1, and offers CPU/software encoding; its optimized mode is available through a FileFlows server, not local Flux processing. [6] The optimization feature requires a valid FileFlows license, and its current docs list the 26.10 series. It is useful as a workflow example, but not as a free library or CLI dependency. [6] **[single-source: vendor documentation]**

- **Unmanic** is a GPL-3.0 Python library optimizer with about 2,500 stars; release 0.4.1 was published on 14 August 2026. It provides a web-managed library queue and plugins that can pass custom FFmpeg arguments, including video encoder options. The docs I reviewed show configurable transcoding, not an automatic VMAF/XPSNR target search or a specific post-encode verification contract. [7] **[single-source: project documentation]**

- **Newer projects are emerging, but none is an established replacement.** The MIT-licensed **Video-AV1-Optimizer** is a Windows PowerShell tool with per-file VMAF/XPSNR sampling and verification utilities, using CPU SVT-AV1 or optional NVIDIA/Intel hardware encoders. It has one GitHub star, requires a full FFmpeg 9 build, defaults to replacing the source in place, and lists Linux, AMD, and broader content-category calibration as future work. [8] **[single-source: project README; experimental]** **VideoTuner** (AGPL-3.0, zero stars, 82 commits) searches x264/x265 profiles against VMAF and SSIMULACRA2, but currently targets Windows and needs VapourSynth and `mkvmerge`. [9] **ffvm** (GPL-3.0, one star) is a Python CLI that supports `libx265`, SVT-AV1, and other FFmpeg encoders, with per-file sampled VMAF CRF sweeps; its roadmap still lists better error handling and tests. [10] **transQrate** (MIT, zero stars) has a per-folder VMAF target and sample-based search, but is an Intel QSV AV1 Docker server, not a software-encoding Linux CLI. [11] **Viser** (BSD-2-Clause, 13 stars) explores per-title, per-shot, and per-segment bitrate optimization, primarily for encoding ladders rather than personal archiving. [12]

**Evidence:** [1]–[12].  
**Confidence:** High for documented tool capabilities and licenses; medium for metadata and verification comparisons, because absence from documentation does not prove a tool cannot do something through custom FFmpeg arguments.

#### 2. Backend reuse, licensing, and FFmpeg packaging

**What (source-grounded).** For this Python CLI, the most direct reuse is calling ab-av1 as a subprocess for CRF search, then letting the project own the final archive workflow. ab-av1 is explicitly a CLI rather than a library, and its JSON output is suitable for parsing. [1][2] Use Av1an as an optional CLI backend only if per-scene targeting proves valuable in the benchmark. HandBrakeCLI is an option for fixed-RF encodes, but it does not replace metric-target search. [3][4]

FFmpeg is LGPL-2.1-or-later by default, but enabling GPL-only components changes FFmpeg’s license to GPL; BtbN documents that its GPL variant includes GPL-only dependencies such as x264/x265, while its LGPL variant excludes them. BtbN offers current static Linux x86-64 builds, but the exact binary’s filters and encoders still need to be checked. [13][14] VMAF is only available in FFmpeg builds configured with `libvmaf`. [16] **John Van Sickle’s static builds are GPLv3**, and the page’s latest build date shown is 29 June 2024, so I would not use it as the default source for a 2026 toolchain. [15]

The GNU GPL FAQ says that command-line arguments and pipes are normally communication between separate programs, but it does not make every packaging arrangement automatically safe. A Python CLI that launches external executables is a cleaner integration boundary than linking FFmpeg libraries or embedding encoder code; if the project distributes FFmpeg or other binaries, it must account for the actual build’s license and source obligations. [13][14][17]

**Synthesis.** Start by detecting the user’s installed `ffmpeg`, `ffprobe`, encoders, and VMAF filter. Document a known-good BtbN GPL build as an option when x265 and VMAF are both needed. Avoid bundling binaries initially; the BtbN repository’s license does not by itself determine the license of each FFmpeg artifact. **Do not treat Tdarr or FileFlows as reusable open-source backends:** Tdarr’s EULA restricts redistribution, while FileFlows gates optimized processing behind a product license. [5][6][13][14]

**Evidence:** [1]–[6], [13]–[17].  
**Confidence:** High for the projects’ stated licenses and build variants; medium for how a particular distribution arrangement applies to the new project, since that depends on what it actually ships and links.

#### 3. Community recommendations and reported pitfalls

**What (source-grounded).** Community advice about compressing personal footage is split. A December 2025 DataHoarder discussion about long-term footage preservation has several replies recommending keeping originals and using cold storage. A July 2026 storage-cost discussion shows people also choosing to prune or compress some libraries, while raising playback support as a constraint. These are anecdotes from self-selected discussions, not a representative survey. [19][20]

The technical discussions point to two recurring practices: use metrics to narrow choices, then inspect real output; and preserve source timestamps carefully. In a June 2026 r/AV1 thread about family video, users ask how to automate reasonable quality without spending hours per file, while others say they trust their eyes and playback devices more than a metric alone. Doom9 participants similarly recommend checking the lowest-scoring scenes and doing frame-wise A/B comparisons rather than assuming small VMAF differences are visible. [23][24]

Variable-frame-rate phone video is a concrete failure mode. A recent r/ffmpeg user reported a phone clip becoming 120 fps with duplicated frames under default settings. FFmpeg’s docs say its default `auto` frame-sync mode selects CFR or VFR based on muxer capability; CFR may duplicate or drop frames. [21][22] That aligns with the project’s reported VFR and metric-alignment problems. VMAF comparisons also need synchronized timestamps; Netflix’s FFmpeg guide calls out PTS synchronization when inputs do not start at zero. [16]

**Synthesis.** I found evidence of interest in per-file quality search and scene-aware tools, but no stable community consensus that everyone needs per-scene optimization. One recent r/ffmpeg comparison found that a much longer CRF optimization produced little visible difference from a simpler encode on that author’s test, illustrating why the benchmark should measure useful quality gains against added encode time. [25][26]

**Evidence:** [16], [19]–[26].  
**Confidence:** Medium. The technical behavior is supported by FFmpeg documentation, but the personal-archive recommendations are anecdotal and conflicting.

#### 4. Gap analysis: niche or thin layer?

**What (source-grounded).** Existing tools cover individual pieces: ab-av1 provides whole-file metric search and full decode/duration checks; Av1an provides per-scene targeting; HandBrake handles ordinary fixed-RF encodes and a limited set of metadata; and workflow managers support configurable flows or folder profiles. [1][3][4][5][6][7][11] I found no tool shipping tested profiles for the project’s particular personal-footage categories together with a clear contract for phone metadata, VFR timestamps, filesystem time, gallery playback, and safe handling of originals. This is a synthesis across the reviewed feature sets, not a claim that those workflows cannot be assembled manually.

**Synthesis.** The niche is real but narrow: **build the archive workflow, not another quality-search engine.** ab-av1 already covers most of the CRF-search implementation, and its verification is meaningful, though a full output decode may not be “fast” for every file. The more distinctive work is safe defaults, metadata and timing correctness, category-specific benchmark results, and reproducible playback checks. [1][2][4][16][18]

Practical candidates for the benchmark and design:

- Compare x265 and SVT-AV1 against the current encodes for each content category, recording encoder version, preset, quality setting, output dimensions, file size, and encode time. Do not compare raw CRF values between encoders. [4]
- For VFR sources, align timestamps before VMAF and record frame count, duration, time base, and output sync behavior. Include a phone clip that exposes unusual inferred frame rates. [16][21][22]
- Pair metric summaries with worst-scene review and device A/B playback. The community sources specifically caution against treating a high mean VMAF or a small score difference as proof of transparency. [23][24]
- Check preservation of `creation_time`, GPS/location, rotation/display matrix, file mtime, audio streams, and duration through the actual chosen container and FFmpeg build. FFmpeg has metadata mapping controls, but those controls do not establish that every source tag survives every container conversion. [4][18]
- Keep the original by default. Make full decode, duration comparison, metadata comparison, and destructive deletion eligibility explicit stages; measure whether ab-av1’s full decode meets the desired per-file verification time. [1][19]

**Evidence:** [1]–[7], [11], [16], [18], [21]–[24].  
**Confidence:** Medium. The component gaps are visible in official feature docs; the claim that they add up to a distinct niche is an inference about this project’s workflow.

### Sources

1. [ab-av1 README](https://github.com/alexheretic/ab-av1) and [changelog](https://github.com/alexheretic/ab-av1/blob/main/CHANGELOG.md) — **Primary.** Search methods, supported encoders, verification, `hvc1`, and current release behavior.
2. [ab-av1 on docs.rs](https://docs.rs/crate/ab-av1/latest) — **Primary.** Crate status, CLI and JSON details.
3. [Av1an repository](https://github.com/rust-av/Av1an), [target-quality docs](https://rust-av.github.io/Av1an/Cli/target_quality.html), and [releases](https://github.com/rust-av/Av1an/releases) — **Primary.** Encoders, metrics, per-chunk search, license, and current release.
4. [HandBrake repository](https://github.com/HandBrake/HandBrake), [CLI reference](https://handbrake.fr/docs/en/1.11.0/cli/command-line-reference.html), [quality guide](https://handbrake.fr/docs/en/1.11.0/workflow/adjust-quality.html), [metadata passthrough](https://handbrake.fr/docs/en/latest/advanced/metadata-passthru.html), and [releases](https://github.com/HandBrake/HandBrake/releases) — **Primary.**
5. [Tdarr repository](https://github.com/HaveAGitGat/Tdarr), [EULA](https://github.com/HaveAGitGat/Tdarr/blob/master/LICENSE.md), [health-check docs](https://docs.tdarr.io/docs/plugins/flow-plugins/index/video/Run%20Health%20Check/), and [V3 getting started](https://docs.tdarr.io/docs/installation/getting-started/) — **Primary.**
6. FileFlows [optimized encode docs](https://upload.fileflows.com/docs/plugins/video-nodes/ffmpeg-builder/video-encode-optimized), [pricing](https://upload.fileflows.com/pricing), [Flux video docs](https://upload.fileflows.com/docs/flux/video), and [version history](https://fileflows.com/docs/versions) — **Primary.**
7. [Unmanic repository](https://github.com/Unmanic/unmanic), [releases](https://github.com/Unmanic/unmanic/releases), and [FFmpeg transcoder plugin docs](https://github.com/Unmanic/plugin.video_transcoder/blob/master/description.md) — **Primary.**
8. [Video-AV1-Optimizer](https://github.com/emike09/Video-AV1-Optimizer) — **Primary.** Early Windows AV1 optimizer with metric search and verification tools.
9. [VideoTuner](https://github.com/sleepy-af-dev/VideoTuner) — **Primary.** Early CRF and profile search using VMAF and SSIMULACRA2.
10. [ffvm](https://github.com/birkdev/ffvm) — **Primary.** Python FFmpeg CLI with sampled VMAF CRF search.
11. [transQrate](https://github.com/dermute/transqrate) — **Primary.** Self-hosted QSV AV1 transcoding with per-folder VMAF targets.
12. [Viser](https://github.com/vbasky/viser) — **Primary.** Per-title and per-shot bitrate optimization prototype.
13. [FFmpeg licensing and legal notes](https://www.ffmpeg.org/legal.html) — **Primary.**
14. [BtbN FFmpeg builds](https://github.com/BtbN/FFmpeg-Builds) and [releases](https://github.com/BtbN/FFmpeg-Builds/releases) — **Primary.** Static builds, variants, and dependency/build information.
15. [John Van Sickle FFmpeg static builds](https://johnvansickle.com/ffmpeg/) — **Primary.** Build license and last displayed build date.
16. [Netflix VMAF FFmpeg guide](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) — **Primary.** Build requirements and timestamp synchronization.
17. [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html) — **Primary.** How program-to-program communication is generally distinguished from linking.
18. [FFmpeg metadata mapping documentation](https://www.ffmpeg.org/ffmpeg-all.html) — **Primary.** Default metadata mapping and explicit mapping behavior.
19. [DataHoarder: archiving video when raw files cannot be kept](https://www.reddit.com/r/DataHoarder/comments/1pwpym1/how_do_you_archive_video_when_you_cant_keep_raw/) — **Secondary.** December 2025 discussion of originals and cold storage.
20. [DataHoarder: storage costs and compression](https://www.reddit.com/r/DataHoarder/comments/1v7kg57/well_storage_is_no_longer_cheap-how-many-of-you/) — **Secondary.** July 2026 range of views on pruning, compression, and playback compatibility.
21. [r/ffmpeg: phone footage turning into 120 fps](https://www.reddit.com/r/ffmpeg/comments/1s0ee4z/ffmpeg_keeps_turning_my_24fps_phone_camera/) — **Secondary.** Recent user report of a VFR handling pitfall.
22. [FFmpeg frame-sync options](https://www.ffmpeg.org/ffmpeg.html) — **Primary.** Meaning of `auto`, `cfr`, and `passthrough`.
23. [r/AV1: re-encoding family videos and comparing quality metrics](https://www.reddit.com/r/AV1/comments/1uasg6f/reencoding_older_videos_to_av1_quality/) — **Secondary.** User demand for automation and advice to include subjective viewing.
24. [Doom9: x265 near-lossless settings and VMAF](https://forum.doom9.org/archive/index.php/t-186479.html) — **Secondary.** Expert discussion of worst-scene review and frame-wise A/B testing.
25. [Hacker News: AV1 versus HEVC at high data rates](https://news.ycombinator.com/item?id=44302574) — **Secondary.** Conflicting opinions about quality and codec tradeoffs.
26. [r/ffmpeg: CRF optimization experiment](https://www.reddit.com/r/ffmpeg/comments/1vxf6lc/crfbased_video_encoding_optimization_i_wasted_my/) — **Secondary.** Anecdotal comparison of longer metric-driven search with a simpler encode.

### Gaps

This was desk research; I did not run the tools on representative footage. The main unknowns are how accurately sampled CRF searches predict full-file quality on the project’s six categories, whether full-decode verification is acceptably quick, and whether any selected FFmpeg/container combination preserves phone metadata and VFR timing in practice.

The benchmark should also test the actual target phones and gallery apps with the intended output containers and codecs. Community posts do not establish broad device compatibility, and I found no independent test matrix covering those exact playback and metadata paths.
