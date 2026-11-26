# Clipivo 2.3.1 — Approved automation and usability plan

Owner approved the 24-feature simplification plan on 26 November 2026 and named the development version 2.3.1 (not V3).

Preserve original Clip Extractor v0.7.7, all six tabs, archived V2.3, clean source layout, AppData storage, model licensing and explicit final output approval. No EXE builds, packaging or GitHub Actions build workflows.

## First source checkpoint
- Central SQLite analysis lookup with source path/size/mtime/ctime and scan settings validation; new completed analyses register automatically. Existing V2.2/V2.3 projects remain manually reopenable; legacy files without provenance are not silently trusted.
- Automatic reuse in Analyzer and reference opening, explicit reanalysis, timeline zoom and Open output. Shared automatic reference/selected-folder footage analysis and matching through existing engine, caching, index and validated plan builder.
- Simple Replacement controls, optional duration constraints, person column, Advanced controls retained, validation-only bulk approval; manual and missing selections remain reviewable.
- Existing extraction/Batch/People Library/CapCut/render code retained. No new runtime dependencies.

## Remaining work
- Windows/Qt acceptance, real inference and cache performance, source-fingerprint migration for legacy projects with explicit user confirmation, profile-change rematching of cached data and cache management.
- Automatic Batch output registration; persistent person-wise footage catalog UI; automatic reuse in original Extractor/Batch without changing upstream behavior.
- Synchronized full video previews, editable visual replacement timeline, scene thumbnails, categorized settings with save/reset defaults, simple-mode user-controlled repetition/speed, richer cancellation/progress, legacy profile migration acceptance.
- Full regression, accurate GPU/CPU behavior, CapCut playback and final render acceptance. No claim of full completion.


## Focused 2.3.1 tests actually run

`PYTHONPATH=. python -m pytest -q tests/test_automation_231.py` — 7 passed in 0.07s in an isolated Linux mirror. The exact Git blob hashes of analysis_library.py, automation.py and the test file were verified. Real SQLite and source file metadata were used; unrelated model, storage, video/planner imports were stubbed, and project loading was mocked for the lookup test. The automated generation pipeline itself, UI, actual inference and entire regression suite were not executed. PySide6 and ONNX Runtime were unavailable. No build or workflow.
