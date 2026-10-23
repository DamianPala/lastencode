# Research synthesis (2026-10-20)

Inputs: 10 reports (`self/`, `codex/`), merged and source-checked per thread in `merged/`. History: notes from the January 2026 prototype, not published. This file is the short version for the spec; details and sources live in `merged/`.

## Settled by evidence

- **Build our own thin Python CLI over ffmpeg/ffprobe/exiftool.** No maintained tool covers phone VFR + metadata + per-file gate + category presets. ab-av1 only as a benchmark comparison arm (its VFR bug #311 is real, closed "not planned"). Tdarr/FileFlows closed, Av1an MKV-centric, HandBrake has no metric.
- **x265 4.3 is the default for camera footage.** No current evidence of AV1 winning at near-transparent quality; owner's A/B preferred x265 by eye. SVT-AV1 4.2 is the only AV1 worth testing, with PSY features turned on explicitly (all off by default). VVC and libaom out.
- **Prototype bugs with known causes and fixes:**
  - lost `creation_time`: ffmpeg deletes it unless `-map_metadata 0` is explicit.
  - GPS in the wrong MP4 box: ffmpeg writes 3GPP `loci` only; ExifTool step copies `Keys`/`©xyz` from the source.
  - lost mtime: restore with `os.utime` after the metadata step.
  - dropped frames (4/3601): default `vfr` fps mode rounds and drops colliding frames; use `-fps_mode passthrough -enc_time_base demux`.
  - slow seeking in Haruna: libaom default keyframe distance 9999 frames; always set `-g` (~2 s camera, longer for static), x265 `open-gop=0`.
  - corrupt MKV: the post-encode remux; drop it (mux once, MP4 `+faststart`).
  - colour range tagged `tv` from `pc` sources: AV1 encoders default to limited; set range explicitly on filter, output and encoder.
  - nonsense VMAF: frame alignment, rotation, range; libvmaf input order distorted-first, xpsnr reference-first; `scale2ref` deprecated.
  - dance preset `deblock=-1:-1` weakens deblocking; CRF 28-30 is medium quality, not archival (sweep CRF 18-26).
- **Container: MP4** (`hvc1`, `+faststart`). MKV does not open on iOS and keeps fewer usable metadata.
- **Playback:** HEVC Main 8-bit plays on every ~2-year-old phone and in Haruna; Windows needs HEVC Video Extensions or VLC (owner: acceptable). Opus in MP4 plays on iOS 17+ and Android; Windows only via VLC (acceptable). AV1: iPhone 15 Pro / 16 / 17 only; mid-range Android in software (works, costs battery).
- **ffmpeg provisioning:** distro packages (Ubuntu 26.04, Debian) lack libvmaf; encoding works with distro 7.1+, benchmark needs BtbN `gpl` (has VMAF v1 models from libvmaf 3.2). Probe capabilities at start; do not bundle ffmpeg.
- **Metrics:** VMAF v1 (`vmaf_v1.0.16_3d0h` desktop, `5d0h` phone; set `model=` explicitly) + XPSNR; thresholds are placeholders until a blind check.
- **Fast per-file check:** ffprobe inventory (streams, range, rotation result, `creation_time`, GPS), packet/frame count vs source, keyframe gap, full decode with `-xerror`, duration; write to temp name, verify, rename. Metric on 2-3 windows is optional.
- **Throughput:** one x265 1080p encode fills ~12-16 threads; run 2-4 files in parallel on 32 threads.

## First real workload: a course recording collection (26 files, 5,3 GB, ~37 h)

H.264 ~1280x616-720, 24-25 fps, video only 0,2-0,4 Mb/s (already heavily compressed), AAC 127 kb/s = a quarter to a third of each file. Expect the biggest safe win from audio (Opus speech 32-48 kb/s) and a modest one from re-encoding video; the benchmark must show whether video re-encode is worth the generation loss at this bitrate (skip rule candidate).

## Open decisions (for the scope interview)

1. Scope of v1: convert + verify + manifest; how much `bench` in v1.
2. Owner's phone model (decides AV1 and Main10).
3. 8-bit vs 10-bit HEVC default.
4. Fixed CRF per category vs per-file search (default: fixed).
5. Output placement (mirror tree vs next to original), originals' trash location on the NAS.
6. Skip rule for already-efficient sources (course recordings): audio-only re-encode when video bitrate is below a threshold?
7. Webinar fps: native vs 25 fps vs mpdecimate (benchmark arm, needs two-number measurement).
8. Benchmark corpus: own clips only for v1, or public downloads; NC licences opt-in.
9. Sources without `creation_time` (screen recordings): leave empty or write from mtime.
10. Project license (MIT/Apache-2.0).
