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

## Thread T4: quality measurement, fast verification, and public test corpora

Questions:
1. Metrics in 2026 for judging near-transparent encodes: VMAF (v0.6.1, 4K model, NEG mode, phone model), XPSNR (now in ffmpeg), SSIMULACRA2, Butteraugli, ColorVideoVDP / CVVDP, others. Which correlate best with human judgement at high quality for camera footage, and which work for screen content (text, slides) where VMAF is known to be weak? Tool availability (ffmpeg filters, vship/GPU implementations, Python packages) and speed on CPU.
2. Correct measurement of real-world sources: variable frame rate, rotation metadata vs rotated pixels, full vs limited range, downscaled outputs vs full-resolution reference, frame-count mismatches. What do ab-av1, Av1an and Netflix guidance do, and what is the recommended ffmpeg filter chain (e.g. `setpts`, `fps`, `scale` with range, `libvmaf` `n_threads`, `scale2ref` deprecation and its replacement)?
3. Fast post-encode verification that catches real failures in seconds to a minute per file: full decode check vs sampled decode, frame/packet count and duration comparison, timestamp monotonicity, stream presence, container validation for MKV and MP4 (e.g. mkvalidator, MP4Box, ffprobe checks), metric on a few sampled windows. What failure modes are actually seen in practice (truncated files, corrupt Matroska after remux, A/V desync, dropped frames)?
4. Target-quality approach: how sample-based CRF search works (ab-av1 sampling, Av1an probes), how many samples and what length, accuracy vs a full encode, and sensible VMAF/XPSNR/SSIMULACRA2 targets for "visually transparent on a phone".
5. Public, redistributable or freely downloadable test footage for each content category (walkthrough/handheld motion, dance/people moving, static room camera, webinar/screen content, video-call recordings, general phone footage): Xiph derf collection, Netflix Open Content, AVT-VQDB, YouTube UGC dataset, KonViD, LIVE datasets, screen content datasets (e.g. JCT-VC SCC sequences), Pexels/Pixabay/Wikimedia Commons. For each: license, whether a benchmark script may download it automatically, typical resolution/fps, and how close it is to phone-captured VFR footage.
