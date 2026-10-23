# Side effects of mpdecimate and VFR in screen-recording archives

## Summary

In the regular synthetic input tested, `max=24` made sub-threshold changes appear by the next forced keep, at most 25 input intervals later (0,83 s at 30 fps); without a limit a subtle change disappeared completely. [37]
Risks include misleading frame-rate metadata such as `r_frame_rate=6/1`, missing faststart, Opus edit lists for uploads, and codec support in editors and older devices.
In the synthetic SVT-AV1 test a static CFR frame cost about 25 B, roughly 6 kb/s at 30 fps, less than 24 kb/s audio.
The larger measured advantage was about sixfold faster encoding. [37]

## Findings

### Filter semantics and small changes

Source inspection: comparisons use the last reference frame, not the immediately previous frame; a forced `KEEP_NO_UPDATE` emits a frame without updating that reference.
Luma and chroma use the same thresholds.
Block scanning starts at x=8, ignoring the left eight columns of each plane.
The threshold `(w/16)*(h/16)*frac` uses a 16 px grid while blocks are sampled every 4 px, making effective `frac` about 16 times more sensitive than its name suggests.
The filter changes neither PTS nor duration and accepts only 8-bit formats: placing 10-bit conversion after it is valid, but a 10-bit source is reduced before comparison. [1]
Positive `max` limits consecutive drops; negative `max` sets minimum spacing between drops. [1][2]
The tested ffmpeg 8.0.1 had `keep`; `mode` and `min` were only in master, following a request to preserve short pauses. [1][3][37]

| Synthetic change | Measurement [37] |
|---|---|
| Moving 10×16 px cursor | All frames kept |
| Blinking 2×16 px caret | Every blink kept |
| Appended 20 px text | Every change kept |
| Grey 12 px digits, #C8C8C8 on white | 4/10 changes appeared only on forced keeps, 0,5–0,73 s late |
| #F8F8F8 highlight, 300×40 px, max=0 | Never appeared; stream ended at 6 s out of 12 s |
| Same highlight, max=24 | Appeared 0,4 s late |
| 320×180 camera tile | 3 600/3 600 frames kept; no saving |

Forum anecdotes describe cursors and blinking lights preventing drops. [29][31]
Confidence: high for inspected semantics and measured input, medium for generalizing to noisy conference recordings.

### SVT-AV1 and keyframes

The inspected FFmpeg wrapper set `force_key_frames=1` only for `gop_size == 1`; a 2023 patch explained that SVT did not support arbitrary keyframe requests. [5][6]
Nevertheless ffmpeg 8.0.1/SVT-AV1 2.3.0 forced keyframes every 5 s in the tested CFR and VFR clips, on the first available frame after a mark (80,17 and 95,07 s).
An older report also showed forcing with `enable-force-key-frames=1`. [7][37]
`-g 300` counts frames, potentially spanning 250 s in sparse VFR, so time-based forcing determines spacing. [5]
The default 1/framerate time base rounded jittered PTS by up to 4,3 ms; `-enc_time_base demux` gave zero error. [4][37]
VFR mode removes colliding timestamps; passthrough does not. [4]
Confidence: medium; verify the actual build with ffprobe.

### MP4 and subsequent re-encoding

The measured output had `moov` at the end without faststart.
Its video edit list covered 119,2 s, roughly 0,8 s short of audio, because the last frame lasted 1/30 s.
Opus used `media_time=312`, a 6,5 ms pre-skip, consistent with Mp4Opus. [20][37]
YouTube recommends no edit lists and `moov` first; historical muxer and Windows-player edit handling differed. [19][21]
ffprobe reported `r_frame_rate=6/1` and `avg_frame_rate=5/4`; frame-rate guessing can use the former even when it does not describe the presentation cadence. [9][35][36][37]
Matroska rounded timestamps to 1 ms; mpv documents VFR MKV/display-sync limitations, whereas the measured MP4 used exact timestamps at time scale 15 360. [10][37]
A plain x264 re-encode rounded 5/149 PTS by up to 67 ms after choosing a 1/6 time base from the guessed rate; denser changes could also lose frames. [37]
Confidence: high for these measurements.

### Playback

mpv/Haruna's default audio sync tolerates VFR; display-sync modes need CFR and fall back at low frame rates. [10]
A VLC 3.0.3 VFR MP4 seeking black-screen issue was fixed in 2018, and Firefox's Windows WMF uneven-duration issue was fixed in versions 70/71.
These historical issues do not establish a current Windows-player bug. [11][12]
One Jellyfin web-client report suspected VFR; no specific Plex report was found. [25]
Video Station was removed in DSM 7.2.2. [26]
Codec compatibility is separate: Apple AV1 hardware started with A17 Pro/M3; older support was uncertain. [23]
An Apple forum reported Opus MP4 working on iOS 17 but not 15. [22]
Android 12+ received software dav1d through Play updates, around 720p30 in the cited report. [24]
Windows needs the AV1 extension, and the cited inbox Media Foundation list omitted Opus. [33][34]
Confidence: medium; these claims are dated research, not a current compatibility matrix.

### Downstream tools

Adobe's Preserve Audio Sync handles VFR with drops/duplicates, but Adobe recommends CFR conversion. [13]
Reports described Premiere 25.1/26.3 failing to import AV1 MP4 and Opus; Kdenlive/Shotcut detect VFR and suggest transcoding; Resolve sources reported no Opus support. [14][15][16][17][18]
YouTube recommends H.264 and no edit lists; its cited format list did not include AV1.
A weak secondary source described Drive AV1 previews as unsupported officially. [19][32]
Inference: audio transcription and timed subtitle tracks retain timing because audio timing and kept-frame PTS are preserved; subtitle rendering still depends on players. [1]
Confidence: high for documented editor limitations, medium for upload services.

### Savings

Own synthetic clean-content measurement with SVT-AV1 2.3.0 preset 10, CRF 50: 120 s video used 208 kB CFR versus 118 kB VFR (43 % less video, about 6 kb/s); a static CFR frame cost about 25 B.
With 24 kb/s Opus, total saving was about 15 %; encoding took 22,8 versus 3,6 s. [37]
Forum anecdotes say x264 duplicates are nearly free and most savings come from re-encoding; an x265 forum estimated at least roughly 600 B per frame even with frame duplication. [28][30]
x265 3.3+ offers `--frame-dup` with pic_struct SEI while retaining CFR; SVT had screen-content mode (`--scm`, default auto=2), without an equivalent option. [8][27][28]
Confidence: medium, one synthetic test plus anecdotes.

## Perspectives and implications

Hardware-compatibility warnings on forums are opinions, while editor CFR recommendations and historical player fixes are documented. [11][12][13][15][29]
VFR is common in phone, conferencing and screen captures; compatibility depends on the client and profile.
The synthetic test gives a stronger CPU-saving argument than an absolute bitrate-saving argument. [30][37]

1. Keep a drop limit; consider `max=14` for at most 0,5 s delay on regular 30 fps input, at roughly one extra cheap frame per second. [1][37]
2. Force keyframes relative to the previous forced time: `expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+5))`, avoiding catch-up bursts after long gaps. [4]
3. Use the demuxer time base and faststart. [4][19][37]
4. Inspect packet PTS and keyframe flags with ffprobe for every toolchain build; wrapper-version behavior needs measurement. [5][6][37]
5. For later re-encodes use an explicit demuxer time base or deliberate CFR/rate conversion, avoiding accidental rounding from a guessed frame rate. [9][37]
6. Make a separate H.264/AAC CFR intermediate for editing or uploads where needed; the AV1/Opus/VFR archive is a storage format. [14][17][19]
7. A changing camera tile prevented all frame drops in this synthetic test; do not assume gains for camera recordings. [37]

### Sources

1. [FFmpeg mpdecimate source: thresholds, reference and formats (primary)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavfilter/vf_mpdecimate.c).
2. [FFmpeg 2013 max option documentation (primary)](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2013-April/063436.html).
3. [FFmpeg-user: minimum pauses feature request (secondary)](https://ffmpeg.org/pipermail/ffmpeg-user/2023-April/056322.html).
4. [FFmpeg command-line documentation (primary)](https://ffmpeg.org/ffmpeg.html).
5. [FFmpeg libsvtav1 wrapper (primary)](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavcodec/libsvtav1.c).
6. [FFmpeg-devel: forced keyframes patch rationale, known from search results; page blocked (primary)](https://lists.ffmpeg.org/pipermail/ffmpeg-devel/2023-October/315421.html).
7. [FFmpeg issue 10372: libaom versus libsvtav1 keyframes (primary)](https://ffmpeg.org/pipermail/ffmpeg-trac/2023-May/065972.html).
8. [SVT-AV1 parameters (primary)](https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/Parameters.md).
9. [FFmpeg av_guess_frame_rate implementation (primary)](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/avformat.c).
10. [mpv video-sync documentation (primary)](https://mpv.io/manual/stable/#options-video-sync).
11. [VLC issue 20740, fixed in 2018 (primary)](https://code.videolan.org/videolan/vlc/-/issues/20740).
12. [Mozilla bug 1576990: WMF frame durations (primary)](https://bugzilla.mozilla.org/show_bug.cgi?id=1576990).
13. [Adobe VFR FAQ: sync and CFR recommendations (secondary, moderators)](https://community.adobe.com/t5/premiere-pro/faq-variable-frame-rate-vfr-video/m-p/10348229).
14. [Adobe Community: Premiere 25.1/26.3 AV1 import failures (secondary)](https://community.adobe.com/questions-729/premiere-pro-25-1-and-26-3-cannot-import-valid-av1-mp4s-audio-only-or-complete-import-failure-while-clipchamp-and-vlc-play-them-correctly-1629966).
15. [Kdenlive frame-rate warning and commit (mixed)](https://discuss.kde.org/t/frame-rate-transcoding/4178), [Kdenlive frame-rate warning and commit (mixed)](https://commits.kde.org/kdenlive/3aba11ca37aca20804d1eb9cc0c9b79e098783ab).
16. [Shotcut 17.12 VFR detection release notes (primary)](https://shotcutapp.com/blog/new-release-1712/).
17. [FFmpeg issue 10206: Resolve Opus comment (secondary)](https://trac.ffmpeg.org/ticket/10206).
18. [DaVinci Resolve Club: WebM in Resolve 21.1 (secondary)](https://davinciresolveclub.com/davinci-resolve-webm/).
19. [YouTube upload recommendations and supported formats (primary)](https://support.google.com/youtube/answer/1722171), [YouTube upload recommendations and supported formats (primary)](https://support.google.com/youtube/troubleshooter/2888402).
20. [Xiph Mp4Opus pre-skip and edits (primary draft)](https://wiki.xiph.org/Mp4Opus).
21. [FFmpeg issue 7185: edits and codec delay (primary)](https://trac.ffmpeg.org/ticket/7185).
22. [Apple Developer Forums: MP4 Opus, iOS 15 versus 17 (secondary)](https://developer.apple.com/forums/thread/722399).
23. [Bitmovin: Apple AV1 support (secondary)](https://bitmovin.com/apple-av1-support).
24. [9to5Google: Android software AV1 decoder (secondary)](https://9to5google.com/guides/av1/).
25. [Jellyfin web-client playback report, suspected VFR (secondary)](https://forum.jellyfin.org/t-jittery-playback-issues-with-some-files-using-web-client).
26. [NAS Compares: DSM 7.2.2 removes Video Station (secondary)](https://nascompares.com/news/synology-dsm-7-2-2-update-a-major-shift-in-multimedia-support/).
27. [x265 adaptive frame duplication announcement (primary)](https://mailman.videolan.org/pipermail/x265-devel/2019-October/012692.html).
28. [Doom9: x265 frame-dup cost and CFR compatibility (secondary)](https://forum.doom9.org/showthread.php?p=1944549).
29. [VideoHelp: x264 duplicates and duration, search results only; page returned 503 (secondary)](https://forum.videohelp.com/threads/393903).
30. [VideoHelp: near-free duplicates, search results only; page returned 503 (secondary)](https://forum.videohelp.com/showthread.php?p=2588415).
31. [Shotcut: screencast static parts (secondary)](https://forum.shotcut.org/t/automatically-cut-off-multiple-static-parts-of-a-video/48764).
32. [VideoConverterFactory: unofficial Drive AV1 support (weak secondary)](https://www.videoconverterfactory.com/tips/google-drive-video-formats.html).
33. [Microsoft Media Foundation format list (primary)](https://learn.microsoft.com/en-us/windows/win32/medfound/supported-media-formats-in-media-foundation).
34. [Microsoft AV1 Video Extension (primary)](https://apps.microsoft.com/detail/9mvzqvxjbq9v).
35. [Wikimedia T135671: incorrect avg_frame_rate (secondary)](https://phabricator.wikimedia.org/T135671).
36. [FFmpeg issue 8909: AV1 frame rate after remux (primary)](https://trac.ffmpeg.org/ticket/8909).
37. Own measurements, 2026-10-20: ffmpeg 8.0.1 on Ubuntu, SVT-AV1 2.3.0, synthetic 720p30 clips in a scratch folder; drops, delays, sizes, keyframes, MP4 atoms and re-encoding (primary, synthetic data).

### Gaps

- Actual Windows Media Player, Movies & TV, Samsung Gallery/Video, Plex, Jellyfin and Safari/QuickTime Opus MP4 playback were not tested.
- No VFR-specific AV1 hardware-decoder report was found for VA-API, MediaCodec or DXVA; decoder timestamp independence was not verified.
- Clean synthetic input does not establish repeated-frame shares or savings on noisy conference recordings; measure two or three representative inputs.
- The discrepancy between the inspected SVT wrapper and successful forced keyframes remains unexplained and may depend on version.
- Plex/Jellyfin transcoding with `r_frame_rate=6/1`, AV1 decoding in Linux free Resolve, and the actual effect of Opus edit lists on YouTube were unverified.
