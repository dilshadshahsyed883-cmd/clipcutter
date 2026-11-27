# Integrated source checkpoint — 26 November 2026

All three agents' source changes are combined on `work/capcut-integration` (merge `52b7170076e3a9061392fb8227a2dd7d00f5e92a`). Main remains untouched; review PR only. This is not a certified release. Read the three existing agent reports and `Clipivo_V2/_internal/reports/TEST_REPORT.md` for distinct testing boundaries.

## Implemented source paths

- Original Clipivo Qt extractor/backend retained, with six-workspace integration.
- V2.2 analysis/filtering/model-location code reused; new Qt person analysis page, project reopening and profile matching.
- Persistent SQLite footage index, estimated hard scene cuts and HSV visual descriptors; semantic labels are manual.
- Replacement suggestions/review, missing report, trim, FFmpeg reconstruction and audio choice.
- Rajudesktop Z Builder draft writer/bridge reused, with a small optional speed extension and Clipcutter adapter. No runtime dependency on Rajudesktop.
- Video-only Python adaptation of Concat C Builder selection: xorshift seed, group-first selection, inverse usage penalty, source cooldown and random trims. Strict min/max feasibility added. No runtime dependency on Concat.
- Draft same-person multi-clip gap filling and bounded slowdown integration.
- Source startup and Windows executable build scripts.

## Partial or pending

- Supervisor source fixes applied: confirmed-person regression fixture, per-file no-reuse capacity and validation, background matching/picking and shutdown lifecycle, canonical CapCut fixtures. Focused cross-agent backend tests passed; full combined regression/Qt acceptance remains blocked.
- Real Windows execution and compiled EXE verification; no compiled executable exists in this checkpoint.
- Real SCRFD/ArcFace inference on user footage, model downloads over the live network, GPU initialization/runtime fallback on hardware.
- Tracking between sampled frames, exact-frame appearance refinement, embedding inference cache, advanced clustering/duplicate correction.
- Automatic activity/environment/framing/angle understanding. The UI currently uses manual labels; histogram similarity is not semantic recognition.
- OpenCLIP/FAISS or equivalent semantic retrieval and production-calibrated match confidence.
- Automatic face analysis of all indexed footage. Current workflow links a completed analyzer project or manual labels to indexed scenes.
- Simultaneous live inference preview is sampled; original/reference reconstruction previews show still frames. Full replacement timeline playback is pending.
- Saved profiles use model/reference provenance and local embedding-cache rebuilding. Explicit V2.2 profile import is limited to documented schemas; real legacy user data remains unverified.
- Full V2.2 People_Library migration and complete encryption of project observations/crops.
- Strict min/max behavior under all export/filter/frame-rate combinations and CapCut speed playback acceptance.
- Complete acceptance report and final Windows package remain deferred. EXE build, packaging and GitHub Actions build workflows are prohibited.

## Storage decisions

Projects/settings stay outside the installation folder. Existing upstream project and people-store paths are reused where present; new Windows data uses the V2 data folder. Older V2.2 project JSON stays compatible. No automatic deletion of original footage.

## Scope additions captured from the owner

1. Match the provided original Clipivo UI screenshot.
2. Reuse models from the existing Windows Clipivo installation, including `_internal`.
3. Copy the relevant Open in CapCut logic from Rajudesktop's Z Builder.
4. Add minimum and maximum clip duration controls.
5. Reuse only Concat's clip-pick/rearrangement logic.
6. If one replacement clip is short, use another clip of the same person or bounded speed adjustment.
7. Save all work in the independent clipcutter repository; integrated review branch only, no main merge.

Reordering and speed changes are editing tools; they do not establish permission or copyright clearance.

## Integration contracts

Agent 1's stable analyzer busy state and extractor handoff are retained. Only matched/manual groups with persistent profile IDs are treated as confirmed cross-video identities. Agent 2's canonical version-1 plan is expanded once by the native adapter; source reuse disabled means one physical source file across all picked rows. Existing settings keys `clip_limits`, `picker`, and `capcut_drafts` are retained. Both selection operations use the worker task; cooperative cancellation does not instantly interrupt a native call. Native draft export blocks short/offset audio when exact representation cannot be guaranteed; FFmpeg reconstruction can pad short audio. Silent original reference handling differs: native export preserves silence, while the renderer requires an audio stream unless None is selected.

## Subsequent clean source layout checkpoint

The PC-testing source tree is reorganized under `_internal`. AppData source launcher paths and persistent storage policy are documented; no user data or local environments are removed. Windows launch and complete regression execution remain pending. No executable build or workflow.

## 2.3.1 automation source checkpoint

See PLAN_2_3_1.md. Central lookup, simplified generation and analyzer controls are implemented in source. Native Windows, inference and full regression are not verified. The earlier sections are historical.


## Focused 2.3.1 tests actually run

`PYTHONPATH=. python -m pytest -q tests/test_automation_231.py` — 7 passed in 0.07s in an isolated Linux mirror. The exact Git blob hashes of analysis_library.py, automation.py and the test file were verified. Real SQLite and source file metadata were used; unrelated model, storage, video/planner imports were stubbed, and project loading was mocked for the lookup test. The automated generation pipeline itself, UI, actual inference and entire regression suite were not executed. PySide6 and ONNX Runtime were unavailable. No build or workflow.
