# Clipcutter repository instructions

## Current development restriction

Owner instruction recorded on 26 November 2026:

- Do not trigger any EXE build, including the existing local `BUILD_EXE.bat` script or any manual/automatic CI build.
- Do not create or add a GitHub Actions EXE/build workflow, or enable automatic executable builds.
- Keep current work limited to source code, documentation, fixes and source-level testing when requested. Tests must not invoke EXE packaging.
- Existing build scripts are retained as inactive source; their presence and older build instructions do not authorize execution.
- This restriction overrides earlier packaging/build plans and remains in force until the owner explicitly changes it.

## Permanent Windows source runtime rule

- Keep all source-launch Python virtual environments and installed dependencies under `%LOCALAPPDATA%\ClipivoV2\runtime\` (V2.3: `python-v2.3`). Never create or reuse `.venv` or `venv` inside the application/source folder.
- Source ZIPs must exclude virtual environments, Python caches and temporary files. Reuse the AppData runtime across source-folder replacements. A legacy local environment is ignored, not automatically deleted; users may remove it manually.

## Clip Extractor compatibility rule

- Preserve original Clipivo v0.7.7 recognition, scan and extractor UI behavior, upstream verified model discovery and original dependency pins. Studio analyzer model settings must not override the extractor/Batch engine. Keep new optional clip-duration controls opt-in and verify parity with them disabled. Do not reset or delete existing user data to restore compatibility.

## Windows source ZIP location rule

- Store PC-testing source ZIPs under `%LOCALAPPDATA%\ClipivoV2\packages\`, never in Downloads by default.
- Extract the runnable source app under `%LOCALAPPDATA%\ClipivoV2\app\Clipivo_V2\`, never into Downloads by default.
- Preserve the archive name `Clipivo_V2_3_Windows.zip`, its single outer `Clipivo_V2` folder, `START_V2.bat` and `_internal` structure.
- Keep the Python runtime under `%LOCALAPPDATA%\ClipivoV2\runtime\`; do not bundle it in the ZIP.
- Follow `docs/PC_TEST_ZIP_METHOD.md`. Creating a requested source ZIP does not authorize an EXE build, packaging an executable, or adding a GitHub Actions build workflow.

## Clean, location-independent Windows PC-testing source layout

- `Clipivo_V2/` must contain exactly `START_V2.bat` and `_internal/`. Keep documentation in `_internal/docs/`, licenses in `_internal/licenses/`, reports in `_internal/reports/`, tests in `_internal/tests/`, and inactive development scripts in `_internal/dev/`.
- Default extraction remains LocalAppData, but the launcher must run from any writable or read-only source location with spaces; all dependencies are installed only in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\`. Ignore legacy source-local virtual environments; recreate the runtime in AppData from Python, never relocate or delete the legacy environment automatically.
- AppData stores pip cache, launcher temp files and export cache. Preserve verified upstream model/FFmpeg caches at `%LOCALAPPDATA%\Clipivo` and Studio models, Node, settings, projects and profiles at `%LOCALAPPDATA%\ClipivoV2`; retain existing legacy data read paths without moving/deleting user data. Existing external model files may be reused read-only. User-selected media/export paths remain user-controlled.
- Source replacement never requires clearing persistent AppData. EXE builds and GitHub Actions build workflows remain prohibited. Keep package documentation snapshots aligned with repository docs.

## Active development version

The approved automation/usability work is named 2.3.1 (not V3). `old_releases/V2.3` is immutable. See `docs/PLAN_2_3_1.md`. Preserve original extractor behavior and explicit review; no builds.
