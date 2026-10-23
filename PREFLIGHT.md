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

## 2026-10-23 · public · candidate 85a4bb9 · destination github:DamianPala/lastencode (public)
Decisions: name lastencode · licence MIT · history squash · maturity experimental · disclosure: "Built with AI coding agents under my direction."

| Item | Result | Note |
|---|---|---|
| A01 | PASS | decision block unchanged; 0.2.0 delivery delegated by the owner |
| A02 | PASS | tree clean at the candidate apart from this record |
| A03 | PASS | fast-forward on the published main, no rewrite |
| A04 | FINDINGS 1 resolved | 1 false positive kept |
| A05 | N/A no committed credential |  |
| A06 | FINDINGS 15 resolved | all kept: approved public identity and account, documented default paths |
| A07 | PASS | private files untracked and excluded |
| A08 | PASS | one identity, owner approved |
| A09 | PASS | no status file ships |
| A10 | PASS | new tests build synthetic clips |
| A11 | PASS | no binary content |
| A12 | PASS | bytes unchanged since v0.1.0 |
| A13 | PASS | first-party only |
| A14 | PASS | 2FA on |
| A15 | PASS | no dependents |
| A16 | PASS | public, not a fork, sole collaborator, no secrets |
| A17 | PASS | one CI workflow, read-only token, publishes nothing |
| B01 | PASS | all except the private set |
| B02 | PASS | MIT; tzdata (Apache-2.0) on Windows only |
| B03 | PASS | name unchanged |
| B04 | PASS | clean install and both quick start forms in an empty HOME |
| B05 | PASS | changed README lines true on the candidate |
| B06 | PASS | mutants caught; CI green on Linux and macOS, Windows media tests flaky on the tagged commit (0.2.1) |
| B07 | PASS | no network traffic |
| B08 | PASS | tzdata audited, no known vulnerability |
| B09 | PASS | 0.2.0 in metadata, --version and the tag on this record; changelog entry |
| B10 | FINDINGS 4 resolved | checkout credentials no longer persisted; actions pinned, read-only |
| B11 | PASS | sdist and wheel hold no private files |
| B12 | FINDINGS 1 resolved | 1 kept |
| B13 | PASS | secret scanning, push protection, private reporting on |
| B14 | PASS | fresh install from the public tag and both quick start forms in an empty HOME; links live |
| B15 | PASS | private status updated |
| B16 | PASS | bytes unchanged since v0.1.0 |
| L01 | PASS | help and version exit 0 |
| L02 | PASS |  |
| L03 | PASS | new path cases tested on three systems |
| L04 | PASS | install route works |
| L08 | PASS | twine check strict passed |
| L09 | PASS | wheel in a clean venv |
| L10 | N/A no PyPI upload |  |
| L11 | N/A no publish job |  |
| L12 | N/A no index upload, B14 covers the public install |  |
| L21 | PASS | ffmpeg, ffprobe, exiftool declared with minimums and checked |

## 2026-10-23 · public · candidate 55229dd · destination github:DamianPala/lastencode (public)
Decisions: name lastencode · licence MIT · history squash · maturity experimental · disclosure: "Built with AI coding agents under my direction."

| Item | Result | Note |
|---|---|---|
| A01 | PASS | decision block unchanged; 0.2.1 approved by the owner |
| A02 | PASS | tree clean at the candidate apart from this record |
| A03 | PASS | fast-forward on the published main, no rewrite |
| A04 | FINDINGS 1 resolved | 1 false positive kept |
| A05 | N/A no committed credential |  |
| A06 | FINDINGS 16 resolved | all kept: approved public identity and account, documented default paths |
| A07 | PASS | private files untracked and excluded |
| A08 | PASS | one identity, owner approved |
| A09 | PASS | no status file ships |
| A10 | PASS | new test uses a synthetic ffprobe document |
| A11 | PASS | no binary content |
| A12 | PASS | bytes unchanged since v0.2.0 |
| A13 | PASS | first-party only |
| A14 | PASS | 2FA on |
| A15 | PASS | no dependents |
| A16 | PASS | public, not a fork, sole collaborator, no secrets |
| A17 | PASS | workflows unchanged since v0.2.0 |
| B01 | PASS | all except the private set |
| B02 | PASS | MIT; tzdata (Apache-2.0) on Windows only |
| B03 | PASS | name unchanged |
| B04 | PASS | wheel installs and runs in a clean venv |
| B05 | PASS | changed README lines true once the tag is pushed |
| B06 | PASS | mutant caught; CI green on all three systems, Windows media tests passed three times |
| B07 | PASS | no network traffic |
| B08 | PASS | dependencies unchanged since the run 5 audit |
| B09 | PASS | 0.2.1 in metadata, --version and the tag on this record; changelog entry |
| B10 | PASS | workflows unchanged since run 5 |
| B11 | PASS | sdist and wheel hold no private files |
| B12 | FINDINGS 1 resolved | 1 kept |
| B13 | PASS | secret scanning, push protection, private reporting on |
| B14 | PASS | fresh install from the public tag in an empty HOME; links live |
| B15 | PASS | private status updated |
| B16 | PASS | no house or source names added |
| L01 | PASS | help and version exit 0 |
| L02 | PASS | CLI surface unchanged |
| L03 | PASS | fix covered by a portable test on three systems |
| L04 | PASS | install route unchanged |
| L08 | PASS | twine check strict passed |
| L09 | PASS | wheel in a clean venv |
| L10 | N/A no PyPI upload |  |
| L11 | N/A no publish job |  |
| L12 | N/A no index upload, B14 covers the public install |  |
| L21 | PASS | tool requirements unchanged and checked |
