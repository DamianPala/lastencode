# O5 side effects: dropping repeated frames (merged research, 2026-10-20)

Two workers (Claude with its own synthetic tests, Codex web-only), merged and checked against our files. Pipeline under review: `mpdecimate=max=24`, VFR, SVT-AV1, Opus mono, MP4.

## Verdict

No blocker for an archive that is played back. The risks sit in tools that edit or re-process the file, and in AV1/Opus support, which applies to the desktop target with or without O5.

## Findings

| Topic | Finding | Workers | Checked here |
|---|---|---|---|
| Sync | `mpdecimate` keeps source PTS; audio untouched; transcripts and caption timing unaffected | both | yes, SP8: within 2 ms |
| Lost changes | Without `max`, changes below the thresholds can vanish for good (a faint highlight never appeared in Claude's test). With `max=24` every change shows up, at most 1 s late at 25 fps; faint 12 px grey digits came 0,5-0,7 s late | Claude test | no; `max=14` would cap the delay at ~0,5 s |
| `max` counts frames | It bounds dropped frames, not seconds; a source with PTS gaps can still hold a frame longer | both | n/a for CFR Zoom sources |
| Reference frame | Comparison is against the last kept frame, so small changes accumulate until they cross the threshold; the left 8 columns are ignored; 8-bit input only (a 10-bit source is compared in 8 bits) | Claude, source code | no |
| Keyframes | `n_forced`-based expression bunches keyframes after a gap; `prev_forced_t` does not: `expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+5))` | both | yes: no doubled keyframes, gaps 5-5,6 s with `max=24` |
| Timestamps | `-fps_mode vfr` may drop frames with colliding timestamps; `passthrough` with `-enc_time_base demux` keeps source times exactly | both | yes: `vfr` and `passthrough` byte-identical on the CFR course excerpt |
| Frame-rate metadata | A sparse VFR file can report `r_frame_rate=6/1`; a later plain `ffmpeg -i` re-encode then rounded timestamps by up to 67 ms | Claude test | no on a real file: `r_frame_rate=25/1`, plain x264 re-encode kept all 395 timestamps |
| MP4 | Add `-movflags +faststart`; Opus pre-skip uses an edit list (correct per Mp4Opus; YouTube's upload guide asks for none); video ends up to ~1 s before audio with `max=24` | Claude | partly, SP8 end times |
| Players | mpv/Haruna fine (display-sync modes need CFR and fall back); old VLC and Firefox VFR bugs fixed; Media Foundation apps (Films & TV, Media Player) are the least proven; one Jellyfin web report | both | no; owner's Haruna check pending |
| Editors and uploads | Premiere, Resolve, Kdenlive and Shotcut want CFR; Premiere does not import AV1 MP4, Resolve has no Opus; YouTube and Drive prefer H.264/AAC | both | no |
| Saving | Static frames are cheap in AV1 (Claude: ~25 B each), so the gain is modest and content-dependent; encoding is faster with fewer frames | both | yes: -12,5 % on the course excerpt (SP6); 0 % with a noisy inset (SP7) |

## Changes to the proposal

- Keyframes: `-force_key_frames "expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+5))"`.
- Timing: `-fps_mode passthrough -enc_time_base demux` (as R10 already uses for other targets) instead of `vfr`.
- MP4: `-movflags +faststart`.
- Keep `max=24` (1 s); `max=14` is an option if late cursor or highlight changes bother the owner.
- The desktop archive is a storage format: editing or uploading needs a CFR H.264/AAC working copy, which is out of scope for v1.

## Sources

Full reports with numbered sources: `self.md` (Claude) and `codex.md` (Codex) in this folder.
