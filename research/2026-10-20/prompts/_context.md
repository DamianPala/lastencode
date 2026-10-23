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
