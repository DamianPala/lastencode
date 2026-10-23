# Spike conclusions (2026-10-20)

These are historical measurements, not size or compatibility promises.
Materials were synthetic clips or owner-selected recordings outside the repository.

## SP1: playback

**Question:** Do HEVC bit depths, range tags and audio combinations play on the target devices?
**Material:** Six synthetic 15 s clips with a test pattern, grey ramp and 440 Hz tone, covering HEVC 8/10-bit, full/limited range, Opus/AAC and an H.264/AAC reference.
**Result:** All six played with sound and seeking in Haruna 1.7.1 on Linux and a stock Android player on a 2025 phone; full-range luma was 0–255 / 1–1023 and limited-range luma 16–235 / 64–940.
The 8-bit ramp had coarser steps than 10-bit; range endpoints looked alike.
**Conclusion:** HEVC 10-bit limited with Opus in MP4 worked on these devices; iPhone and Windows were not covered.

## SP2: metadata round-trip

**Question:** Can conversion preserve capture metadata, strip GPS on request and add a processing tag without changing media bytes?
**Material:** A synthetic 12 s, roughly 7 Mb/s, 1920×1080 variable-rate phone-like clip with a −90° rotation, full-range video, capture dates, public-landmark GPS and Android tags; MP4 and MOV outputs.
**Result:** With ffmpeg 8.0.1 and exiftool 13.50, all five header dates, the Keys date, precise Keys and user-data GPS, defined Android tags, faststart and nanosecond file time survived the complete workflow.
Rotation was baked into 1080×1920 pixels.
The media-data hash stayed equal through metadata copy, stripping and tag writing.
Stripping required an explicit `UserData:LocationInformation` removal for the `loci` box; ffmpeg's own GPS was rounded to four decimals.
A Keys processing tag survived exiftool copying but was lost in a later plain ffmpeg remux; a comment survived that remux.
**Conclusion:** Write metadata with exiftool after encoding, restore file time afterwards and check faststart and GPS stripping.
Undefined Android tags require definitions; real-phone undefined tags and files over 4 GB were not tested.

## SP3: frame timing, keyframes and range

**Question:** Do frame counts, timestamps, keyframe types and range conversion meet the intended checks?
**Material:** Synthetic 20 s 1080p variable-rate clips with 565 or 600 frames, timestamp jitter and black/grey/white patches, encoded with x265 and SVT-AV1 under ffmpeg 8.0.1.
**Result:** Passthrough with the demuxer time base kept 565/565 and 600/600 frames and zero timestamp error relative to the first frame.
Default mode moved timestamps by up to 10,8 ms and dropped 21/600 frames in the stress case.
A nonzero source start caused a constant 6 ms shift without `-copyts`.
Closed-GOP x265 and SVT-AV1 each produced 10 IDR/KEY frames; a nominal 2 s interval reached 2,197 s.
Open-GOP x265 produced only one IDR among five flagged keyframes.
Swscale mapped white to 937 rather than 940; zscale gave black 64, grey 504 and white 940 in 10-bit limited range.
**Conclusion:** Compare times relative to the first frame, use passthrough and the demuxer time base, require closed GOPs and measure keyframe spacing in seconds.

## SP4: synced work files

**Question:** Does a hidden work file reach synced storage after its final rename?
**Material:** A Synology Drive client log for visible and dot-prefixed files under rules excluding dot files and temporary files.
**Result:** One visible-to-visible rename synced without a second upload; a hidden file had zero uploads until renamed to a visible final name, then the finished file uploaded once in full.
Renaming a synced file to a hidden name deleted the remote copy.
Hard links do not sync under the owner's setup, as recorded in the specification; this log tested renames.
**Conclusion:** Use a hidden work file and a plain final rename so only the completed output uploads once.
Growing visible files and trash behavior were not observed.

## SP5: benchmark toolchain

**Question:** Which lossless excerpt format and scoring tools work at practical cost?
**Material:** BtbN ffmpeg/ffprobe 9.0.2, SVT-AV1 4.2, fssimu2 0.2.0 and two synthetic 20 s 1080p30 clips, one clean and one strongly noisy, measured on a 12-thread laptop.
**Result:** The build supplied libvmaf, XPSNR, SSIM, PSNR and zscale; two VMAF v1 models worked in one pass with distinct names and matched pixel formats.
Two models on 500 frames at 1280×616 took 6–8 s on four threads.
For clean/noisy clips, lossless x264 ultrafast used 85,5/1 114 MB in 2,3/18,7 s; x264 medium used 62,1/994 MB in 6,6/67,7 s; FFV1 level 3 with four slices used 64,6/994 MB in 4,0/15,7 s.
FFV1 made every frame a keyframe.
On one 600-frame 1080p variant, two VMAF models took 32 s and SSIMULACRA2 every fifth frame, including extraction, took 25 s.
SSIMULACRA2 distinguished equal-size variance-boost settings with 5th percentiles 63 versus 59 where VMAF barely separated them.
**Conclusion:** Use FFV1 in Matroska for excerpts: it matched lossless x264 medium in size and was fastest on noisy 1080p.
Allow roughly 3 GB for three difficult excerpts and roughly a minute of scoring per variant/excerpt.
The acceptance toolchain used ffmpeg 9.0.2; this does not establish behavior on older versions.

## SP6: course copy versus re-encode

**Question:** Is copying already compressed screen video preferable to re-encoding it?
**Material:** One roughly 2 h course recording, 1280×616 at 25 fps, H.264 averaging 0,36 Mb/s with AAC 128 kb/s stereo, 440,2 MB; a busy 20 s excerpt, eight further 20 s excerpts distributed across the recording and two blind ratings of text and face crops.
**Result:** Copying video and replacing audio with Opus 48/40/32 kb/s reduced total size by 17,1/18,6/20,0 %.
The channels were identical (difference −91 dB versus −26 dB signal); mono Opus 16 kb/s already sounded acceptable to the owner, who chose 24 kb/s mono (53 KB versus 326 KB AAC per 20 s).
On the busy excerpt, x265 slow CRF 28 reduced video from 2,01 to 1,84 MB (8,5 %); CRF 32 reached 1,19 MB with more face smoothing.
Phone-model VMAF at CRF 28 was mean 95,99, 5th percentile 93,30 and minimum 90,34; the worst frames, rather than the mean, separated settings on faces.
Combined desktop AV1 CRF 50 settings produced a 1,06 MB complete file versus 2,34 MB (55 % smaller), with text intact.
Blind text and face ratings put the face-detail limit at CRF 50; CRF 54 and 58 smoothed more detail.
Dropping repeats saved 12,5 % of video on the busy excerpt; tune 1 saved 5,6 % and forced screen-content mode 1,9 % against their respective base.
Across eight excerpts, repeated frames ranged from 22 to 37 % (mean 30 %), video savings from 9 to 62 %, and summed video fell from 5,55 to 3,10 MB (44 %).
This suggested roughly 203 MB including mono Opus versus 440 MB (54 % smaller), with uncertainty of about 10 percentage points because only 2 % of the recording was sampled.
Encoding those 160 s took 136 s (0,85 times real time).
Tune 4 was 0,9 % larger overall and had a lower SSIMULACRA2 5th percentile in five excerpts, so tune 1 stayed.
The owner watched 15 and 25 fps variants and found 15 fps visibly worse.
BtbN ffmpeg 9.0.2 with SVT-AV1 4.2 accepted all proposed desktop parameters: `tune=1:enable-variance-boost=1:ac-bias=1.0:tf-strength=1:sharpness=1:enable-qm=1:qm-min=2:scm=1`.
**Conclusion:** Desktop AV1 re-encoding saved space even in the quietest sampled parts; keep CRF 50, preset 4, tune 1, time-based 5 s keyframes and 24 kb/s mono for dual-mono audio.
These are measurements of one recording, not a general saving estimate; later preset decisions in SPEC supersede the initial portable recommendation.

## SP7: synthetic webinar

**Question:** Do the course results generalize to different screen content?
**Material:** A synthetic 60 s 1280×720, 25 fps clip with slides, scrolling text, a moving cursor and a noisy camera stand-in, encoded from a 2,91 MB x264 source.
**Result:** AV1 CRF 50/54/58 produced 2,61/2,04/1,48 MB (10/30/49 % smaller); desktop VMAF means were 98,8/98,5/98,0 and 5th percentiles 95,8/94,9/93,5.
Text remained readable in blind still comparisons, but all 1 500 frames survived because the cursor and noise changed every frame.
**Conclusion:** Readable text generalized; the roughly 55 % course saving did not.
Measure each source; a noisy test pattern cannot establish face quality.

## SP8: dropped frames, sync and seeking

**Question:** Does dropping repeats preserve sync and timestamps while keeping seeking practical?
**Material:** A synthetic 60 s, 1280×720, 25 fps grey still with one white frame at 3, 10, 17,4, 31 and 52 s, matching 40 ms 1 kHz beeps, a 21 s still stretch and an 8 s still tail; a lossless H.264/FLAC MKV reference and desktop AV1 CRF 50/mono Opus 24 kb/s MP4 output.
**Result:** Unlimited dropping kept 11/1 500 frames, ended video at 52,08 s and made the longest frame 20,96 s.
A 124-drop limit kept 20 frames, ended at 57,08 s and limited frames to 5 s; keyframe gaps still reached 8 s.
A 24-drop limit kept 66 frames, ended at 59,08 s and limited frames to 1 s, with keyframes every 5–5,4 s.
Every white flash retained its exact source timestamp; beeps started within 2 ms in all variants.
On two real course excerpts the 24-drop limit produced byte-identical video to unlimited dropping.
Accurate ffmpeg seeking inside the long still could jump 12 s ahead without a limit, versus at most 0,44 s with the 24-drop limit; player seeking was not tested.
Forcing each keyframe 5 s after the previous one avoided doubled keyframes and gave gaps of 5–5,6 s.
Passthrough and VFR modes gave byte-identical output on the constant-rate course excerpt; one real output reported 25/1 and retained all 395 timestamps through a plain x264 re-encode.
**Conclusion:** Keep at least one frame per second, original timestamps and time-based keyframes; use passthrough with the demuxer time base.
Sync held in these tests, but player seeking still required a device check.
