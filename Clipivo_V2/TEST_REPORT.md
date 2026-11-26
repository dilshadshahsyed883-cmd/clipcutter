# Verification record — saved development checkpoint

## Completed checks

- Original supplied V2.2 baseline: **9 tests passed** (unittest).
- Original upstream Clipivo source: **113 tests passed** (pytest, Linux, offscreen Qt).
- Initial Clipcutter extension suite before the latest selection/gap-fill/speed changes: **22 tests passed**. It exercised identity-margin matching, mocked GPU runtime fallback, fixture model download/checksum/cancellation, project path rejection, person constraints, matching/repetition, encrypted profile cache, real FFmpeg scene detection/index caching, original/no/external audio reconstruction, cancellation preserving an existing file, source-overwrite protection and real Node editable draft creation/uniqueness.
- Initial six-tab Qt startup/navigation smoke test passed. Extractor/Analyzer/Replacement screenshots were inspected during development; tree/table dark styling was subsequently corrected.
- Upstream self-test with the integrated app: FFmpeg/FFprobe launch, real decode/export, ONNX Runtime import, Qt JPEG/SVG plugins and bundled license/icon checks passed. Host had no VLC, no face models and no usable default OS keyring. Encryption tests used an explicit temporary test key; they do not validate Windows Credential Manager.

## Latest full-suite attempt

**142 passed, 2 failed** at that point. Both failures expected the original Linux project-data path after a storage-location change. The storage code was adjusted to retain Linux/legacy paths, but the full suite has not been rerun since that adjustment.

Later clip-selection, min/max export, same-person gap-fill and CapCut speed extensions have **not** been fully tested. The owner deferred fixes to a later session. Do not infer that the earlier 22-test pass validates these later changes.

## Not performed

- Windows EXE compilation/signing/launch.
- Real face-model inference, real person grouping quality or GPU execution.
- Live model/FFmpeg/Node download acceptance on Windows.
- Native CapCut installed-project playback, speed/audio synchronization or visual compatibility.
- Full responsiveness/performance/upgrade acceptance across the requested V2.3 scope.

This is a source checkpoint, not a completed or certified release.
