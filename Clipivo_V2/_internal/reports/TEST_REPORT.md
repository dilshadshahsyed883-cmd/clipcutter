# Clean source layout checkpoint — 26 November 2026

Static source/path checks only; Windows launcher, downloads and end-to-end regression not executed. Root layout, relocated resources and tests, AppData runtime and cache path contracts verified at source level. Existing models/tools/user data are not relocated. No executable build or workflow.

# Extractor parity restoration — 26 November 2026

Static source comparison against upstream v0.7.7: face_engine.py, face_models.py, video_analysis.py, ui/main_window.py, ui/settings_dialog.py and core/downloads.py are unchanged; the original model constructor and dependency pins are restored. Studio settings no longer assign the extractor model directory or invalidate its engine. AppData launcher checks the requirements hash and reconciles dependencies before startup if it changes. Optional strict clip limits and output safety guards remain. No Windows runtime, actual face inference or same-video parity result is claimed. No EXE build or workflow.

# Verification record — combined integration checkpoint

## Current integration results (26 November 2026)

Exact Agent 1 `61381f891c44899f58f015223ff6b4f1093ebdb7` and Agent 2 `694500d57be3d8fca8c900e310a4d80f80e993dd` merged with Agent 3 `fd6b6a54d475b00f479e741f9960afdc19e40378` in `52b7170076e3a9061392fb8227a2dd7d00f5e92a`. No overlapping file changes in the merge; integration fixes followed. Existing agent reports retained.

- **9 passed in 3.72s** on the integrated picker/footage/render/CapCut Python adapter and focused test source, mirrored from the connector. Actual OpenCV, FFmpeg/FFprobe, libx264 and SQLite ran. Only storage-root and FFmpeg tool-discovery imports were stubbed. Verified exact Git blob hashes: `picker.py` `93253b4637da0bb1107642248b64fd415d6aad9e`, `footage.py` `aa43bcf30063cb40a8fbeea93682d0566aa77a65`, `render.py` `31eeed8405adf0d5f112fcafb67e1ef66ee21e17`, `capcut.py` `70fb75c83c3db6ad1dcd4b0b5eafa01ba7153a52`, `Clipivo_V2/tests/test_replacement_picker_v23.py` `d86c5a744805d1927ae06c3ab361fe601cc32ead`.
- The corrected confirmed multi-person regression assertions passed against the mirrored footage module: confirmed pair eligible; removing confirmation rejects it. No weaker legacy identity fallback was introduced.
- Added no-repeat multi-scene test (50 seeds), cooperative cancellation tests, and an actual FFprobe cross-agent test for reviewed same-person multi-piece and free-picked plans through `request_from_plan`, with original/none/external audio. These passed as part of the nine tests.
- Native CapCut tests were adapted to canonical reference `scenes`, confirmed piece IDs and approval state; an additional identity/pending review test was added (six test methods in that file). **Real Node draft writing was not rerun on the integrated head.** The independent agent report's simulated filesystem checks and any prior supervisor results are not combined acceptance.
- **Qt startup attempt blocked** at `import PySide6` (`ModuleNotFoundError`). No offscreen navigation or large-library UI timing claim. Source checks preserve Agent 1's six tabs, analyzer busy state, extractor range handoff and add replacement busy state/worker cancellation; these UI changes require runtime acceptance.
- **Full combined regression not run:** GitHub clone failed (`Could not resolve host: github.com`), direct raw-source transfer unavailable, and PySide6 and ONNX Runtime are not installed. The isolated mirror is not a full checkout. Do not sum previous agent counts or label this a full pass. No EXE build/packaging/Actions workflow.

Run on a full accessible source checkout (with Python dependencies, Node and FFmpeg/FFprobe installed), from `Clipivo_V2/_internal`:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

On Windows set the same environment variable using the shell's syntax; then run six-tab startup/navigation, background match/pick/cancel/close and extractor handoff checks. Real Windows/GPU/face model inference and installed CapCut draft playback remain outstanding.

---

## Historical pre-integration baseline (not current results)

### Historical completed checks

- Original supplied V2.2 baseline: **9 tests passed** (unittest).
- Original upstream Clipivo source: **113 tests passed** (pytest, Linux, offscreen Qt).
- Initial Clipcutter extension suite before the latest selection/gap-fill/speed changes: **22 tests passed**. It exercised identity-margin matching, mocked GPU runtime fallback, fixture model download/checksum/cancellation, project path rejection, person constraints, matching/repetition, encrypted profile cache, real FFmpeg scene detection/index caching, original/no/external audio reconstruction, cancellation preserving an existing file, source-overwrite protection and real Node editable draft creation/uniqueness.
- Initial six-tab Qt startup/navigation smoke test passed. Extractor/Analyzer/Replacement screenshots were inspected during development; tree/table dark styling was subsequently corrected.
- Upstream self-test with the integrated app: FFmpeg/FFprobe launch, real decode/export, ONNX Runtime import, Qt JPEG/SVG plugins and bundled license/icon checks passed. Host had no VLC, no face models and no usable default OS keyring. Encryption tests used an explicit temporary test key; they do not validate Windows Credential Manager.

### Historical full-suite attempt

**142 passed, 2 failed** at that point. Both failures expected the original Linux project-data path after a storage-location change. The storage code was adjusted to retain Linux/legacy paths, but the full suite has not been rerun since that adjustment.

Later clip-selection, min/max export, same-person gap-fill and CapCut speed extensions have **not** been fully tested. The owner deferred fixes to a later session. Do not infer that the earlier 22-test pass validates these later changes.

### Historical checks not performed

- Windows EXE compilation/signing/launch.
- Real face-model inference, real person grouping quality or GPU execution.
- Live model/FFmpeg/Node download acceptance on Windows.
- Native CapCut installed-project playback, speed/audio synchronization or visual compatibility.
- Full responsiveness/performance/upgrade acceptance across the requested V2.3 scope.

This is a source checkpoint, not a completed or certified release.
