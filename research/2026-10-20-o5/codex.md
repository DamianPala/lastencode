# Dropped frames and VFR: research findings

This research examines detection and sampling, MP4/FFmpeg timestamps, player and hardware compatibility, editing, and the savings beyond modern encoding.
Documentation and issue reports take precedence over user anecdotes.

## Summary

`mpdecimate=max=24` limits consecutive dropped frames, not elapsed time.
For regular 25–30 fps input it bounds kept-frame spacing to about 1–0,83 s; irregular PTS can produce longer gaps.
The remaining risks include specific AV1/mono Opus/MP4 players, subtitle refresh during still frames, timestamp precision and small-text quality at CRF 50. [1][2][10][11][13]
VFR and preserved PTS are supported, but a 2 ms sync result on one file does not establish seeking, subtitle or hardware behavior.
Test archive playback on the intended devices; a separate CFR H.264/AAC file is more practical for editing and uploads. [1][7][12][14][17]

## Findings

### Frame dropping and timestamps

Documentation: the filter compares 8×8 blocks with `hi`, `lo` and `frac` thresholds against the last kept reference and preserves the timestamps it passes.
Twenty-four consecutive drops give at most 25 regular input intervals between kept frames, but this is not a time guarantee for irregular PTS. [1][2]
Inference: subtle cursor, text or typing changes can remain below thresholds and accumulate relative to the reference; conversely, a moving cursor can prevent drops.
User reports of both effects are anecdotal. [2][23][24]
`vfr` can drop colliding timestamps; `passthrough` passes timestamps onward, though a muxer can still change them.
The default encoder time base can round small PTS differences to a nominal-rate grid.
Consider `-enc_time_base:v filter` only after comparing input/output PTS demonstrates that problem. [1]
Confidence: medium.

### Playback, MP4 and hardware decoding

MP4 has movie and track time scales; FFmpeg normally derives the video track scale from the stream time base and enables edit lists automatically.
Opus in ISO BMFF uses `dOps` and edit lists for pre-skip.
VFR itself is valid, but correct Opus playback depends on a player's handling of the start edit and pre-skip; inspect sample durations as well as final PTS. [3][4]
`r_frame_rate` is not simply the actual frame rate, and an unusual value is not proof of damage.
Inspect PTS, `time_base`, `avg_frame_rate` and track durations.
A Microsoft issue says MP4 Opus support shipped to Windows 11 24H2, 25H2 and 26H1, rather than older unsupported releases; check the actual player and OS. [5][6][13]
Android documents AV1 decoding from Android 10 with device-specific capabilities.
Apple documents Safari AV1 on hardware-decoder devices; Jellyfin documents MP4 Opus on newer Apple systems for stereo.
These do not establish every mono Opus + AV1 + VFR combination; software fallback may cost more on devices without AV1 hardware. [10][11][12]
An mpv issue reports delayed subtitle/UI refresh during long frames, and its manual warns about VFR frame stepping.
The frame limit reduces long holds on regular input, but subtitles changing between frames still require player checks in Haruna/mpv, VLC and browsers. [7][8]
Confidence: medium.

### Editing, subtitles, thumbnails and services

Adobe recommends CFR conversion as a VFR editing workaround; Shotcut reports inaccurate cuts and sync risks, and Kdenlive offers transcoding profiles for difficult inputs.
An archive playback file can therefore be less predictable as an editing intermediate. [14][15][16]
Time-based forced keyframes preserve the intended schedule only at available frames.
An expression based on `n_forced` can bunch keyframes after a long timestamp jump while catching up.
Use `-force_key_frames 'expr:if(isnan(prev_forced_t),gte(t,0),gte(t,prev_forced_t+5))'` to schedule the next keyframe five seconds after the previous forced one, delayed to the next available frame.
`-g 300` is a frame-count limit, not a five-second guarantee in VFR. [1]
YouTube's general recommendations do not establish this AV1/VFR/mono Opus combination, and Drive's preview list does not include AV1 with Opus.
Upload success does not establish preview/transcoding success; use a tested CFR H.264/AAC copy if that workflow matters. [17][18]
Inference: thumbnail and transcription tools sampling by frame number can interpret VFR differently from tools sampling by PTS.
Sample pictures by time; the sources do not support generalizing this to all transcription products. [1]
Confidence: medium.

### Savings and image detail

AV1 can display an already decoded frame and includes screen-content tools; SVT documentation says it does not insert keyframes based on scene-change detection.
Those capabilities do not quantify the extra saving of `mpdecimate` with this exact CRF 50 pipeline.
Modern encoders can encode static regions cheaply, so additional savings require measurement. [19][20][21][22]
Higher CRF trades detail for size; inspect small text, fine lines and UI elements, not just the CRF number.
One archive user's roughly threefold reduction came with poor seeking and different settings, so it is not a benchmark for this pipeline. [22][23]
Confidence: low for predicted savings, medium for high-CRF detail loss.

## Practical implications

1. Compare input/output PTS and inspect `time_base`, `start_time`, `duration`, `avg_frame_rate`, `r_frame_rate`, `best_effort_timestamp_time`, `pkt_duration_time` and `key_frame` with ffprobe. [1][5]
2. Test static slides with subtitles, small typing, seeking within long stills and the file end in the actual players, phones and Plex/Jellyfin/Synology clients. There is no single supported-device matrix in these sources. [7][8][10][11][12][13]
3. Treat `max=24` as a frame limit; compare audio/video ends because fewer than 25 input frames after the last kept frame can leave a short video tail. [1][2]
4. Keep VFR mode if it preserves the intended PTS; test an explicit encoder time base if rounding is observed, and consider the previous-forced-time expression for keyframes. [1]
5. Compare with and without dropping at acceptable text readability and measure file size. CRF 50 is not a universal readability guarantee. [19][20][22]
6. Make a separate CFR H.264/AAC copy for editing or uploads when needed. Retain AV1 VFR for the archive only after testing the actual devices. [14][15][16][17][18]

VFR is reasonable for archive playback in modern software players, but editing and some playback paths need CFR or profile-specific checks.
AV1's efficient repetition alone does not establish whether dropping frames will save much space. [1][3][7][8][14][15][16][19][20][21][23]

### Sources

1. [FFmpeg command-line documentation](https://ffmpeg.org/ffmpeg.html).
2. [FFmpeg 8.1 mpdecimate source](https://www.ffmpeg.org/doxygen/8.1/vf__mpdecimate_8c_source.html).
3. [FFmpeg MOV/MP4 muxer documentation](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv).
4. [Opus in ISO Base Media File Format](https://www.opus-codec.org/docs/opus_in_isobmff.html).
5. [FFmpeg AVStream documentation](https://www.ffmpeg.org/doxygen/8.1/structAVStream.html).
6. [FFmpeg-devel: meaning of r_frame_rate](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-September/333929.html).
7. [mpv: subtitle redraw during long still frames](https://github.com/mpv-player/mpv/issues/11936).
8. [mpv manual](https://mpv.io/manual/stable/).
9. [MDN web video codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Video_codecs).
10. [Safari 17 release notes](https://developer.apple.com/documentation/safari-release-notes/safari-17-release-notes).
11. [Android supported media formats](https://developer.android.com/media/platform/supported-formats).
12. [Jellyfin codec support](https://jellyfin.org/docs/general/clients/codec-support/).
13. [Microsoft Media Foundation: Opus in MP4](https://github.com/microsoft/media-foundation/issues/36).
14. [Adobe FAQ: variable frame rate media](https://community.adobe.com/questions-729/faq-how-to-work-with-variable-frame-rate-vfr-media-in-premiere-pro-1349720).
15. [Shotcut: editing variable frame rate clips](https://forum.shotcut.org/t/editing-variable-frame-rate-source-clips/43414/1).
16. [Kdenlive configuration](https://docs.kdenlive.org/en/getting_started/configuration.html).
17. [YouTube upload encoding settings](https://support.google.com/youtube/answer/1722171?hl=en).
18. [Google Drive supported video formats](https://support.google.com/drive/answer/2423694?hl=en).
19. [AV1 bitstream semantics](https://github.com/AOMediaCodec/av1-spec/blob/master/07.bitstream.semantics.md).
20. [AOMedia AV1 algorithm description](https://aomedia.googlesource.com/aom/+/refs/heads/main/doc/AlgorithmDescription.md).
21. [SVT-AV1 common questions](https://github.com/AOMediaCodec/SVT-AV1/blob/main/Docs/CommonQuestions.md).
22. [SVT-AV1 parameters](https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/Parameters.md).
23. [Reddit: archiving presentations with mpdecimate](https://www.reddit.com/r/ffmpeg/comments/necre5).
24. [Reddit: cursor movement and mpdecimate](https://www.reddit.com/r/ffmpeg/comments/xqohmx).

### Gaps

No size/quality comparison was found for this exact SVT pipeline and typical webinar recordings; measure it on representative material.
No reliable general report established an AV1 VFR bug in VA-API, MediaCodec or DXVA at 720p–1080p, 25–30 fps.
The sources do not settle mono Opus compatibility across Apple clients, the exact Synology app matrix or YouTube's handling of this AV1/VFR/Opus combination.
