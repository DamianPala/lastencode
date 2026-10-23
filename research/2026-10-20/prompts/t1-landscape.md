## Thread T1: existing tools and where a new tool fits

Questions:
1. Which maintained open-source tools already do quality-targeted video re-encoding for archiving? Cover at least ab-av1 (crf-search with a VMAF/XPSNR target), Av1an (target quality, chunked encoding), HandBrake (CLI and presets), Tdarr, FileFlows, Unmanic, and anything newer from 2025-2026 (search for it). For each: encoders supported (x265, SVT-AV1, others), target-quality method and metric, per-file vs per-scene, verification after encode, metadata handling (creation_time, GPS, rotation), license, activity (last release, stars), CLI ergonomics.
2. Which of them can be used as a library or backend instead of reimplementing (e.g. calling ab-av1 for the CRF search)? Licensing and packaging consequences for a Python CLI on GitHub, including how projects ship or depend on ffmpeg with libvmaf (static builds from BtbN / johnvansickle, distro packages, GPL vs LGPL builds).
3. What do people who archive personal/family/phone video actually recommend in 2025-2026 (Reddit r/DataHoarder, r/ffmpeg, r/AV1, Doom9, HN)? Common workflows, pitfalls they report, and what tools they miss.
4. Gap analysis: what would a content-category-aware archiver with fast per-file verification and metadata preservation add that these tools do not? Is there a real niche, or should the project be a thin layer over an existing tool?
