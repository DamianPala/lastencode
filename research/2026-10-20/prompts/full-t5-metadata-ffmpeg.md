You are a research analyst with live web search. Investigate the topic below thoroughly.

## Protocol

1. **Scope**: Identify 3-5 distinct angles (current state, key players, technical approaches, tradeoffs, community opinion). If topic is broad, prioritize the 2-3 most actionable angles and go deep rather than covering everything shallowly.

2. **Search**: For each angle, run 6-10 web searches with varied queries. Depth over breadth.
   - Mix expert and layman terminology
   - Include specific names: products, companies, benchmarks, conferences, researchers
   - Include recent timeframes ("2025", "2026", "latest")
   - Search for comparisons, alternatives, known problems
   - Prioritize primary sources: official docs, release notes, papers, author posts
   - Search aggressively. More searches = better coverage. Do not stop at first results
   - When a search reveals a key player or benchmark, do follow-up searches on that specific name

3. **Diversify perspectives**: Search from multiple angles for the same question. Look for industry reports, academic benchmarks, vendor comparisons, independent developer blogs, Reddit/HN discussions, and case studies. Different source types reveal different truths.

4. **Cross-reference**: Verify claims across multiple sources. Flag single-source claims as [single-source]. Note disagreements. Major claims require 2+ independent sources.

5. **Synthesize**: Combine into the output format below. Prioritize actionable over background, recent over outdated (last 12 months), facts over opinions (label opinions), specifics over generalities.

6. **Self-critique**: Before writing the final output, review your findings. Ask: Are there obvious gaps? Did I miss a major player or perspective? Are any claims under-sourced? If yes, do targeted follow-up searches to fill the gaps.

## Output Format

Write in English. Use inline citations [N] throughout the text, referencing the numbered Sources list.

### TL;DR
2-3 sentences. The most important takeaway.

### Key Findings
Organize by angle (use the numbered questions of the thread as angles). For each:
- **What**: 1-3 sentences with inline citations [N]
- **Evidence**: supporting sources by number
- **Confidence**: high (3+ reliable sources agree) / medium (2 sources or mixed signals) / low (single source or speculative)

Clearly label what is source-grounded fact vs your own synthesis. Use "Based on [N], ..." for facts and "Synthesizing across sources, ..." for inferences.

### Perspectives
Where experts disagree, present each position fairly with reasoning and citations. Do not pick a winner unless evidence is overwhelming.

### Practical Implications
What this means for the project described in the topic. Concrete candidates to put into its benchmark matrix or design, if applicable.

### Sources
Numbered list: [N] [Title](URL) - one-line description.
Mark primary (official docs, original research) vs secondary (blogs, summaries).
Aim for 10+ distinct sources. If fewer exist, note the topic's limited coverage.

### Gaps
What could not be determined or needs hands-on testing (the project will run its own benchmark, so say what to measure).

## Rules
- No filler, no hedging. Be direct
- If topic is too broad, narrow to the most actionable subset and note exclusions. Depth always beats breadth
- Distinguish "widely adopted" vs "emerging" vs "experimental"
- Include version numbers, dates, concrete figures where available
- Every factual claim must have an inline citation [N]. No uncited claims
- Never fabricate sources. If you cannot find information, say so
- Today is 2026-10-20. Prefer sources from 2025-2026; flag anything older than 2024 as possibly stale

Topic:

## Project context (shared by all research threads)

We are building an open-source CLI (Python, wraps ffmpeg, public on GitHub) that archives personal and work video into much smaller files with visually near-transparent quality, plus a benchmark mode to tune presets per content type.

- **Usage pattern**: a few tens of GB per run, once every 1-2 years. Runs on a Linux box with an AMD Ryzen 9 7950X3D (16 cores / 32 threads, Zen 4, AVX-512) and 91 GB RAM. Throughput is not critical.
- **Priority**: quality over encode time, within reason (e.g. x265 `slow`/`veryslow` or SVT-AV1 presets around 2-6 are acceptable; days-long encodes are not). Software encoding only: hardware encoders were judged visibly worse.
- **Playback targets**: phones about 2 years old (Android and iPhone), desktop computers, and gallery apps (Google Photos, Apple Photos, Synology Photos, Immich). HEVC is acceptable; AV1 is acceptable only if those phones decode it well.
- **Originals**: kept by default; the tool offers optional deletion only after verification passes.
- **Verification**: a fast check after every file; slow, thorough measurement only in benchmark mode.
- **Content categories** (each will get its own preset):
  1. Apartment / property walkthroughs: handheld phone, lots of camera motion, 1080p-4K.
  2. Dance lessons: people moving, fine detail on hair, edges and clothing matters; current output 720p.
  3. Session recordings: people talking in a room, mostly static camera (exact content private; tests will use public footage of similar character).
  4. Webinars: mostly static slides/text with a small talking-head inset (screen content).
  5. Zoom-style calls: two large talking heads, already heavily compressed at the source.
  6. Holiday / everyday clips: general handheld phone footage, mixed scenes.
- **Typical sources**: Android phone recordings, H.264 or HEVC, 8-bit `yuvj420p` full range, variable frame rate (30/60 fps nominal), rotation in the display matrix, GPS and `creation_time` tags; screen recordings in MKV.

### What the January 2026 prototype did and learned (history, treat as hypotheses, not facts)
- ffmpeg CLI from Python. Final presets: `libx265 -preset slow -crf 28`, `aq-mode=3:aq-strength=1.1:deblock=-1:-1` for dance, 720p downscale for dance, Opus 48-64 kbps audio, MKV (apartment) or MP4 with `-tag:v hvc1` (dance). Compression ratios achieved: 2,2x (4K 50 Mbit/s sources) to 6,9x (720p dance at CRF 30).
- Talking-head preset: SVT-AV1 preset 6, CRF 42, 360p, 25 fps, Opus 48k.
- AV1 was dropped without a quality comparison: CRFs are not comparable across encoders and no VMAF results were kept. libaom was ~7 min per 60 s 1080p60 clip; SVT-AV1 ~30 s; x265 slow ~1-2 min.
- A user test on iOS 18 showed real MP4 + HEVC (`hvc1`) + Opus plays natively; MKV does not open in the native player.
- Observed problems: ffmpeg drops `creation_time` and file mtime is not kept; distro ffmpeg (Ubuntu, 8.0.1) lacks libvmaf, so a static BtbN build was used; VMAF without frame-rate/timestamp alignment gave nonsense on VFR phone footage; MKV outputs at 59,94 fps lost 4 of 3601 frames and had a 1 ms timestamp grid; one intermittently corrupt MKV appeared after a post-encode remux (`-fflags +genpts -max_interleave_delta 0 -cues_to_front 1`); the user remembers some outputs "slightly hanging" during playback in one ffmpeg version (cause unknown).

## Thread T5: metadata preservation, ffmpeg builds and container pitfalls

Questions:
1. Preserving metadata when re-encoding phone video with ffmpeg 7.x/8.x: why `creation_time` is dropped by default and the right flags to keep it (container and stream level), GPS (`location`, `©xyz`, Apple `com.apple.quicktime.location.ISO6709`), Android `com.android.*` tags, Apple QuickTime keys, rotation/display matrix (keep as metadata vs bake into pixels: pros and cons for players and gallery apps), and file mtime. Differences between MP4 and MKV in what survives. When to use exiftool after ffmpeg, and what exiftool can and cannot write for MP4/MOV/MKV.
2. How gallery apps decide a video's date and location (Google Photos, Apple Photos, Immich, Synology Photos, Nextcloud Memories): which atoms/tags they read, fallback to file mtime, and what a re-encoded file must contain to land at the right date.
3. ffmpeg builds in 2026: which distro packages include libvmaf, libsvtav1 (and which version), libx265 4.x, libopus; static builds (BtbN, johnvansickle, others) and their contents/licensing; how an open-source Python tool should require, detect or pin ffmpeg (capability probing, minimum versions). ffmpeg 8.x changes relevant here (e.g. `scale2ref` deprecation, libvmaf option names, new filters like `xpsnr`).
4. Known ffmpeg bugs or regressions 2024-2026 that produce stuttering, freezing or non-seekable output: MKV timestamp precision (1 ms timebase at 59,94/29,97 fps, frame drops), `-max_interleave_delta 0`, `-cues_to_front`, `+genpts`, VFR to CFR handling (`-fps_mode`), MP4 `+faststart`, edit lists and Opus pre-skip, HEVC in MKV seeking issues. Which settings are recommended to produce archives that seek and play smoothly everywhere?
5. Safe handling of originals in an archiving tool: verify-then-trash patterns, atomic writes (temp file + rename), resumable batch runs, keeping a manifest (hashes, parameters, tool and ffmpeg versions) so a future run can tell what was converted and how.
