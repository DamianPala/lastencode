## Thread T3: playback compatibility on ~2-year-old phones and gallery apps (state in 2026)

Questions:
1. AV1 hardware decode on phones released in 2024 and early 2025: iPhone (A17 Pro and later only? iPhone 15/16 non-Pro?), Samsung Galaxy S and A series, Pixel (Tensor G3/G4), Snapdragon 8 Gen 2/3 and 7-series, MediaTek Dimensity. Where hardware decode is missing, is software decode (dav1d) smooth for 1080p30/60 and 4K, and what does it cost in battery?
2. HEVC: Main vs Main10 support on those phones, `hvc1` vs `hev1` tagging, full-range (`yuvj420p` / `color_range pc`) vs limited range, any reported playback or color problems with full-range HEVC or AV1 on iOS/Android/browsers.
3. Containers and audio: MP4 vs MKV support in native players, Google Photos, Apple Photos, Synology Photos, Immich and common desktop players. Opus in MP4 (iOS 17/18, Android, browsers, Apple Photos import), AAC as the safe fallback. Any known issues with Opus in MP4 written by ffmpeg.
4. Gallery and sync behaviour: will Google Photos / Apple Photos / Immich / Synology Photos accept, transcode or reject AV1 or HEVC uploads, and do they show the right date and location for re-encoded files?
5. Synthesis: a recommended default codec + container + audio combination for "plays on a 2-year-old phone without fuss" and one for "smallest file, recent devices only", with the evidence.
