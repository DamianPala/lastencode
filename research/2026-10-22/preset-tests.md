# Preset tests, 2026-10-22

The measurements behind decision rows D52, D61, D67, D69 to D72, D74, D75 and D82 of `SPEC.md`.
The footage is the owner's own and is not in the repository; each section describes it instead.
"Blind" means the owner ranked crops or clips without knowing which encode was which.

## Encode speed on a smaller machine (D67)

- **Measured:** encode time of the portable preset (x265 `slow`) as a multiple of the excerpt's duration.
- **Material:** two 20 s 4K phone excerpts, on an 8-thread virtual machine.
- **Result:** about 15 times real time.
- **Verdict:** the owner set a target of 2 times real time for Full HD 30 fps on the target machine; it has not been measured there yet.

## Colour labels on Oppo Reno phone clips (D61, 2026-10-21)

- **Measured:** each clip's container colour values (`ffprobe -show_streams`) against the values its decoder reports for the first frame (`ffprobe -show_frames -read_intervals %+#1`), and the mean RGB shift between source and portable output rendered as a player does.
- **Material:** a 2022 4K H.264 clip and 2023 1080p HEVC clips from an Oppo Reno phone (exact model not recorded).
- **Result:** the 2022 clip's `colr` box says BT.2020 primaries and matrix, BT.709 transfer and limited range, while its stream header says BT.601 (`bt470bg`, `smpte170m`) and full range; the 2023 clips' `colr` says BT.709 against a BT.601 header. Following the container, the 4K portable output shifted by 6,63 of 255 (largest channel mean) and looked oversaturated; following the stream header, the shift was 0,98 to 1,11.
- **Verdict:** the colour description comes from the video stream; the container counts only where the stream is silent.

## Encoder that ignores settings (D52, observed 2026-10-20)

- **Observed:** Ubuntu's SVT-AV1 2.3 accepted the webinar desktop parameter string, silently ignored `ac-bias`, `tf-strength` and `sharpness`, and exited cleanly.
- **Verdict:** an encoder that rejects or ignores a preset parameter stops the run before any encode.

## Encoders at equal file size (D69, D71)

- **Measured:** a blind ranking of three encoders at equal file size, next to VMAF, SSIMULACRA2 and XPSNR.
- **Material:** one 1080p60 apartment-tour excerpt, encoded with x265 CRF 28, VVC QP 30 and SVT-AV1 CRF 57 to files of 3,2 to 3,4 MB, compared on three 640x640 crops.
- **Result:** the owner ranked x265 and VVC above SVT-AV1, as VMAF did; SSIMULACRA2 and XPSNR ranked x265 last.
- **VVC:** the owner rated it about equal to x265; on three excerpts it encoded 1,4 to 6,6 times slower, and ffmpeg 9.0.2's libvvenc in MP4 lost the first 0,8 s of frames.
- **Verdict:** VMAF judges preset choices, XPSNR stays only as a sanity check, SSIMULACRA2 is dropped, and there is no VVC output.

## AV1 for camera footage on desktop (D70)

- **Measured:** the file size of SVT-AV1 preset 4 at the CRF where its VMAF matched the portable x265 output's.
- **Material:** two 20 s 4K apartment-tour excerpts and their 1080p downscales.
- **Result:** matched on the VMAF mean, AV1 files were 0 to 6 % larger than portable; matched on the 5th percentile, they were 8 to 25 % smaller.
- **Verdict:** apartment tours use their portable settings on desktop, and the owner applies the same to dance lessons and holiday clips without a run of their own.

## Slower x265 presets (D72)

- **Measured:** file size, VMAF and encode time of x265 `slower` and `veryslow` against `slow`, all at CRF 28.
- **Material:** three 1080p excerpts.
- **Result:** files 4 to 12 % larger at 0,3 to 0,8 lower VMAF, in 3 to 6 times the time.
- **Verdict:** the x265 presets stay at `slow`.

## Dance-lesson aq-mode (D74)

- **Measured:** a blind comparison of x265 aq-mode 1, 2, 3 (aq-strength 1.1) and 4 at equal file size, with VMAF.
- **Material:** one 20 s 720p dance-lesson excerpt, 2-pass at 1 738 kb/s.
- **Result:** no visible difference; VMAF 94,11 (aq-mode 1), 94,51 (2), 94,31 (3) and 94,20 (4).
- **Verdict:** dance lessons keep aq-mode 3 with aq-strength 1.1.

## Apartment-tour CRF (D75)

- **Measured:** a blind ranking of x265 CRF 24, 26 and 28, and their file sizes.
- **Material:** one 20 s 4K phone apartment-tour excerpt, compared on four 640x640 crops and in playback.
- **Result:** the owner ranked CRF 24 above 26 above 28 on the crops, barely visible in playback; CRF 26 and 24 made the file 53 % and 122 % larger than CRF 28.
- **Verdict:** apartment tours and dance lessons stay at portable CRF 28.

## Webinar and call portable CRF (D82)

- **Measured:** how often x265 at each CRF meets the desktop AV1 output's quality, and its size against that output. "Meets" means the x265 VMAF mean lies within 1 point of the desktop AV1 output's.
- **Material:** nine 20 s excerpts of one 1280x616 online-course recording for webinar; the same excerpts scaled to short side 360 for call.

| CRF | webinar meets | webinar size vs desktop | call meets | call size vs desktop |
|---|---|---|---|---|
| 26 | 8/9 | 1,82× | 6/9 | 1,53× |
| 28 | 4/9 | 1,49× | 1/9 | 1,26× |
| 30 | 0/9 | 1,22× | 0/9 | 1,06× |

- **Copy threshold:** the course recording averages 0,36 Mb/s, so at the 0,3 Mb/s copy-video threshold it gets encoded. On one excerpt with a 0,80 Mb/s source, x265 CRF 26 gave 1,02 Mb/s, which the no-gain rule turns into a copy of the source.
- **Blind test:** x265 CRF 26 ranked best in 3 of 4 crop sets and the desktop AV1 output last in 3 of 4.
- **Verdict:** the owner chose CRF 28 for webinar and call on portable, about 18 % smaller than CRF 26.
