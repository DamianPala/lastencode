# Preflight record

Record of the pre-publication gate run with the `preflight` skill, one section per run. Item ids point at the checklist items in the skill's `references/` (A = private, B = public, C = announce, D = contribute, other letters = modules); results are PASS, FINDINGS n resolved (n hits found and dispositioned), N/A <reason>, DEFERRED <reason, owner>, TOOL-ERROR <tool>, FAIL.

## 2026-10-23 · public · candidate 28bfa9a · destination github:DamianPala/lastencode (public)
Decisions: name lastencode · licence MIT · history squash · maturity experimental · disclosure: "Built with AI coding agents under my direction."

| Item | Result | Note |
|---|---|---|
| A01 | PASS | decision block complete, owner decisions relayed by the owner's session |
| A02 | PASS | tree clean at the candidate apart from this record |
| A03 | PASS | single root, never pushed, bundle kept; changes since the bundle as declared |
| A04 | FINDINGS 1 resolved | 1 false positive kept |
| A05 | N/A no committed credential |  |
| A06 | FINDINGS 11 resolved | all kept: approved public identity and account, a documented default path, a former working name |
| A07 | PASS | private files untracked and excluded |
| A08 | PASS | one identity, owner approved |
| A09 | PASS | no status file ships |
| A10 | PASS | fixtures synthetic or public landmarks, provenance line present |
| A11 | PASS | no binary content |
| A12 | PASS | two pointers to optional local files kept |
| A13 | PASS | first-party only |
| A14 | PASS | 2FA on, verified with the API |
| A15 | PASS | no dependents |
| A16 | PASS | public, empty, not a fork, sole collaborator, no secrets |
| A17 | N/A no workflows |  |
| B01 | PASS | all except the private set |
| B02 | PASS | MIT everywhere, no runtime dependencies |
| B03 | PASS | no conflict |
| B04 | PASS | clean install and quick start in an empty HOME |
| B05 | PASS | contributions come in under the repository licence by the GitHub terms (owner decision) |
| B06 | PASS | suite green on the lowest Python, a deliberate break fails it |
| B07 | PASS | no network traffic, hostile input inert |
| B08 | N/A no runtime dependencies |  |
| B09 | PASS | 0.1.0 in tag, metadata and --version |
| B10 | N/A no CI |  |
| B11 | PASS | sdist and wheel hold no private files |
| B12 | FINDINGS 2 resolved | 2 kept |
| B13 | PASS | secret scanning, push protection, private reporting on |
| B14 | PASS | fresh install from the public URL and the README quick start in an empty HOME; links live |
| B15 | PASS | private status updated |
| B16 | PASS | shipped agent instructions portable |
| L01 | PASS | exit codes and error kinds in schema |
| L02 | PASS |  |
| L03 | PASS | interrupt exits 1 (note) |
| L04 | PASS | install, config and uninstall |
| L08 | PASS | twine check strict passed |
| L09 | PASS | wheel in a clean 3.12 venv |
| L10 | N/A no PyPI upload |  |
| L11 | N/A no publish job |  |
| L12 | N/A no index upload, B14 covers the public install |  |
| L21 | PASS | ffmpeg, ffprobe, exiftool declared and checked |
