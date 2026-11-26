# Clipivo V2.3 / Clipcutter — development checkpoint

One Qt desktop application with Clip Extractor, Person Analyzer, Replacement Studio, Batch, People Library and Settings. It reuses the original Clipivo layout shown in the owner's reference screenshot.

This is source, not a compiled Windows executable. Integration is incomplete and further fixes/testing were deferred by the owner. Read `../docs/STATUS.md` before using it on important projects.

## Windows source launch

Install x64 Python 3.11 or newer with the Python launcher. Extract or clone the complete folder. Run `START_V2.bat`. The first source launch installs dependencies in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3`; Internet access is required. The ZIP/repository does not contain a virtual environment.

Run `BUILD_EXE.bat` on Windows to attempt a PyInstaller one-folder executable build. Keep `dist\Clipivo\Clipivo.exe` and its `_internal` directory together. This build has not been run or verified on Windows. It does not include model weights, VLC or Node; missing dependencies may require first-use installation. Native playback uses VLC; without VLC, extraction remains accessible but full upstream playback is unavailable. Person Analyzer uses an OpenCV silent preview.

## Models and data

Models are searched in `%LOCALAPPDATA%\Programs\Clipivo\_internal`, standard Clipivo model caches and the user's InsightFace cache. No username is hardcoded. A manually supplied model folder must contain compatible `det_10g.onnx` and `w600k_r50.onnx`. Default model downloads verify SHA-256 and require research-license acceptance. The default buffalo_l weights are non-commercial research models. Supply separately licensed compatible weights for commercial use.

V2.3 projects/settings live under `%LOCALAPPDATA%\ClipivoV2`. Existing V2.2 `analysis.json` projects can be reopened without modifying their source videos. Saved People Library references and the new embedding cache use upstream AES-GCM encryption with an OS credential-store key. Analysis project JSON, observation embeddings and reference crops remain local plaintext; they are not encrypted by this checkpoint. Store private projects on an access-controlled/encrypted user volume. The app never uploads biometric data for recognition.

## Workflows currently wired

- Extractor: original reference photos, saved people, current frame, A/B cuts, export quality/resolution/framing, filters and batch.
- Analyzer: discover anonymous people, sampled live boxes/timeline, rename/merge/split/ignore/restore/delete/solo, regions, reversible filters, profile saving and JSON/CSV/TXT project export.
- Replacement: index footage, label scenes, link analyzer identities, rank alternatives, manual replacement, approval, trim, missing report, preserve-duration rendering and original/none/external audio.
- Clip picker: Concat-inspired seeded weighted selection, source cooldown, repeat penalty and random source trims. Minimum/maximum duration and infeasible-total checks. Optional strict extraction limits use accurate cutting with Whole picture framing; stitched outputs can exceed the per-shot maximum.
- Gap fill: suggested same-identity footage pieces, followed by bounded slowdown when total footage is sufficient at >=0.67× speed. Suggestions always require approval. Unknown identity labels are not treated as recognized real people.
- Open in CapCut: adapted Rajudesktop Z Builder native draft writer, a new editable project with source trims, optional audio and limited speed support. CapCut opens its Home screen; select the created project there. JSON verification does not establish installed CapCut playback compatibility. Node is reused or downloaded from the official distribution with checksum verification on Windows.

## Tests

From `_internal`, install pytest, then `python -m pytest -q tests`. Qt tests can use `QT_QPA_PLATFORM=offscreen`. Some tests require real FFmpeg and FFprobe. See `TEST_REPORT.md` for checks actually performed and limitations. Source-video inference, GPU and real Windows/CapCut compatibility have not been accepted.

See `THIRD_PARTY.md` and `LICENSE-AGPL-3.0.txt` for attribution and licenses.
