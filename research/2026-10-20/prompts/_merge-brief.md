# Merge brief (one thread)

You merge two independent research reports on the same thread into one report. Do not start new broad research; verify only what this brief asks.

## Inputs
- Thread questions and project context: `prompts/full-<thread>.md`
- Report A (Claude agent): `self/<thread>.md`
- Report B (Codex): `codex/<thread>.md`
- History (treat as hypotheses): notes from the January 2026 prototype, not published

All paths are relative to `research/2026-10-20/`.

## Decisions the owner made after the research started (apply them; drop recommendations they make moot)
- Archive is plain folders on a NAS. Viewing: phones (~2 years old, Android and iPhone), Haruna (KDE, libmpv) on Linux, and Windows PCs (other people). Gallery apps (Synology Photos, Google Photos, Immich) are NOT a target.
- GPS/location is kept in every category, including apartment tours. creation_time must survive.
- Audio: Opus by default, AAC as fallback.
- One preset per content category; resolutions as in the prototype profiles (dance 720p, others native) unless evidence says otherwise.
- Webinars: fps reduction (30 -> 24/25) or dynamic decimation goes into the benchmark, not decided.
- Software encoding only; quality over time within reason.

## Output
Write `merged/<thread>.md` (English) with:
1. **Bottom line** (5-8 bullets): what the project should do, given the owner's decisions.
2. **Findings** grouped by the thread's questions. Tag each claim: `[both]` (both reports support it), `[A only]` / `[B only]`, `[conflict]` (state each side with its source), `[verified]` when you checked it yourself in this pass (say how: URL fetched, doc read).
3. **Verification log**: every conflict and every decisive single-source claim you checked, with the result and the URL. Use WebFetch on primary sources (official docs, release notes, source code, issue trackers). WebSearch may be rate-limited; if a check cannot be done, say so and mark the claim `[unverified]`.
4. **Benchmark candidates**: concrete encoder settings, metrics, test clips and checks this thread suggests, as a list the benchmark plan can take over.
5. **Open questions for the owner** (only ones the owner must decide; max 5).
6. **Sources**: deduplicated, numbered, keep the URLs from both reports that your text cites.

Keep it under ~250 lines. Plain, direct language. No filler. Return a 5-line summary when done.
