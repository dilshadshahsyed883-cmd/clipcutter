# Clipivo V2.3 / Clipcutter — development checkpoint

One Qt desktop application with Clip Extractor, Person Analyzer, Replacement Studio, Batch, People Library and Settings. It reuses the original Clipivo layout shown in the owner's reference screenshot.

This is source, not a compiled Windows executable. Integration is incomplete and further fixes/testing were deferred by the owner. Read `STATUS.md` before using it on important projects.

## Windows source launch

Install x64 Python 3.11 or newer with the Python launcher. Extract or clone the complete folder. Run `START_V2.bat`. The first source launch installs dependencies in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3`; Internet access is required. The ZIP/repository does not contain a virtual environment. Subsequent launches reuse the AppData runtime, including after replacing the source folder. When requirements change, the launcher reconciles the pinned versions once before startup. The extractor uses the original v0.7.7 dependency pins plus the studio-only psutil dependency. Never create or use `.venv` or `venv` inside `Clipivo_V2`. If a previous version left one there, close Clipivo and remove that old virtual-environment folder manually if no longer needed; the launcher does not migrate or delete it. If `LOCALAPPDATA` is unavailable, source startup stops rather than creating a local environment.

EXE builds are prohibited. The historical recipe is inactive in `../dev/BUILD_EXE.bat`. Native playback uses VLC; without VLC, extraction remains accessible but full upstream playback is unavailable. Person Analyzer uses an OpenCV silent preview.

## Models and data

Clip Extractor and Batch use the original upstream checksum-verified model discovery and original Extraction / media settings. Person Analyzer model settings no longer modify the extractor engine. For a parity test use the same source, references, match strictness, device and scan settings in both apps, and turn off optional strict clip limits. Existing projects and settings are retained. Actual Windows/inference parity is pending.

Person Analyzer models are searched in `%LOCALAPPDATA%\Programs\Clipivo\_internal`, standard Clipivo model caches and the user's InsightFace cache. No username is hardcoded. A manually supplied model folder must contain compatible `det_10g.onnx` and `w600k_r50.onnx`. Default model downloads verify SHA-256 and require research-license acceptance. The default buffalo_l weights are non-commercial research models. Supply separately licensed compatible weights for commercial use.

V2.3 projects/settings live under `%LOCALAPPDATA%\ClipivoV2`. Existing V2.2 `analysis.json` projects can be reopened without modifying their source videos. Saved People Library references and the new embedding cache use upstream AES-GCM encryption with an OS credential-store key. Analysis project JSON, observation embeddings and reference crops remain local plaintext; they are not encrypted by this checkpoint. Store private projects on an access-controlled/encrypted user volume. The app never uploads biometric data for recognition.

## Workflows currently wired

- Extractor: original reference photos, saved people, current frame, A/B cuts, export quality/resolution/framing, filters and batch.
- Analyzer: discover anonymous people, sampled live boxes/timeline, rename/merge/split/ignore/restore/delete/solo, regions, reversible filters, profile saving and JSON/CSV/TXT project export.
- Replacement: index footage, label scenes, link analyzer identities, rank alternatives, manual replacement, approval, trim, missing report, preserve-duration rendering and original/none/external audio.
- Clip picker: Concat-inspired seeded weighted selection, source cooldown, repeat penalty and random source trims. Minimum/maximum duration and infeasible-total checks. Optional strict extraction limits use accurate cutting with Whole picture framing; stitched outputs can exceed the per-shot maximum.
- Gap fill: suggested same-identity footage pieces, followed by bounded slowdown when total footage is sufficient at >=0.67× speed. Suggestions always require approval. Unknown identity labels are not treated as recognized real people.
- Open in CapCut: adapted Rajudesktop Z Builder native draft writer, a new editable project with source trims, optional audio and limited speed support. CapCut opens its Home screen; select the created project there. JSON verification does not establish installed CapCut playback compatibility. Node is reused or downloaded from the official distribution with checksum verification on Windows.

## Tests

From `_internal`, install pytest, then `python -m pytest -q tests`. Qt tests can use `QT_QPA_PLATFORM=offscreen`. Some tests require real FFmpeg and FFprobe. See `../reports/TEST_REPORT.md` for checks actually performed and limitations. Source-video inference, GPU and real Windows/CapCut compatibility have not been accepted.

See `THIRD_PARTY.md` and `../licenses/LICENSE-AGPL-3.0.txt` for attribution and licenses.

## PC-testing source layout and storage

Only `START_V2.bat` and `_internal` belong in the source-folder root. Run the launcher from any location. It creates/reuses the AppData runtime, sets pip and temporary caches to `%LOCALAPPDATA%\ClipivoV2\cache`, and preserves old local virtual environments untouched. Export cache is `%LOCALAPPDATA%\ClipivoV2\cache\export`; original model/FFmpeg downloads are in `%LOCALAPPDATA%\Clipivo`, Studio model downloads in `%LOCALAPPDATA%\ClipivoV2\models`, Node in `%LOCALAPPDATA%\ClipivoV2\runtime\node`. Existing legacy stores and externally supplied verified models are not moved or deleted. Source replacement does not replace user data. Explicit output locations remain user-controlled. A broken existing AppData runtime is reported rather than deleted.
