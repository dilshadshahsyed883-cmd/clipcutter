# Windows PC-testing source ZIP method

Owner preference recorded on 26 November 2026: **the final source ZIP belongs in Windows Downloads; the extracted test application and runtime belong in Local AppData.**

## Required locations

| Item | Location |
| --- | --- |
| Source ZIP | `%USERPROFILE%\Downloads\Clipivo_V2_3_Windows.zip (or redirected Downloads known folder)` |
| Extracted test app | `%LOCALAPPDATA%\ClipivoV2\app\Clipivo_V2\` |
| Launcher | `%LOCALAPPDATA%\ClipivoV2\app\Clipivo_V2\START_V2.bat` |
| Shared Python runtime/dependencies | `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\` |

Resolve paths from LOCALAPPDATA; never hardcode a username or assume a literal `C:\Users\...` path.

## Source ZIP preparation and PC setup

1. Use the requested, verified GitHub main commit and record its full SHA. An old checkpoint SHA must not silently replace a newer requested revision.
2. Include the repository's `Clipivo_V2` application tree, required resources, licenses and relevant documentation. The archive must have exactly one outer folder named `Clipivo_V2`, with exactly `START_V2.bat` and `_internal` at its root; docs, reports, licenses, tests and inactive development scripts are inside `_internal`.
3. Exclude Git metadata, virtual environments, Python/test caches, temporary files and user projects, credentials or biometric data. Do not include runtime installations or redundant model weights.
4. Save/download the final source ZIP directly in the Windows Downloads known folder. Resolve its actual path if redirected; keep temporary setup files and extracted application in AppData.
5. Extract into the AppData app directory above, avoiding a duplicate `Clipivo_V2\Clipivo_V2` nesting. Prepare replacements separately and preserve the previous source folder if replacement fails. Do not erase projects, settings, models, profiles or the shared runtime.
6. Verify ZIP integrity and launcher/resource paths. Run `START_V2.bat` only when the user requests PC testing. It reuses the AppData runtime and may install missing Python dependencies on first launch.
7. Deliver a short launch instruction and the recorded source SHA. Clearly label the package as source; it is not a compiled Windows executable.

Preserve existing Downloads copies unless the owner authorizes replacement. Any other source-folder location is supported by the launcher.

## Restrictions and implementation status

No EXE build, executable packaging, or GitHub Actions build workflow is authorized by this method. This change documents the required delivery/setup locations; it does not itself modify or certify any existing PowerShell helper or launcher. A helper that targets AppData for the final ZIP must be updated before claiming compliance. No ZIP was created or executed by this documentation update.

## Clean, location-independent Windows PC-testing source layout

- `Clipivo_V2/` must contain exactly `START_V2.bat` and `_internal/`. Keep documentation in `_internal/docs/`, licenses in `_internal/licenses/`, reports in `_internal/reports/`, tests in `_internal/tests/`, and inactive development scripts in `_internal/dev/`.
- Default extraction remains LocalAppData, but the launcher must run from any writable or read-only source location with spaces; all dependencies are installed only in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\`. Ignore legacy source-local virtual environments; recreate the runtime in AppData from Python, never relocate or delete the legacy environment automatically.
- AppData stores pip cache, launcher temp files and export cache. Preserve verified upstream model/FFmpeg caches at `%LOCALAPPDATA%\Clipivo` and Studio models, Node, settings, projects and profiles at `%LOCALAPPDATA%\ClipivoV2`; retain existing legacy data read paths without moving/deleting user data. Existing external model files may be reused read-only. User-selected media/export paths remain user-controlled.
- Source replacement never requires clearing persistent AppData. EXE builds and GitHub Actions build workflows remain prohibited. Keep package documentation snapshots aligned with repository docs.

## Mandatory delivery clarification — 26 November 2026

The owner's latest instruction supersedes the earlier ZIP destination rule: **the final PC-testing source ZIP must be saved in the Windows Downloads folder**, as `Clipivo_V2_3_Windows.zip`. A direct browser download or a PowerShell command targeting the user's Downloads known folder is acceptable. The extracted application, Python runtime, dependencies, models, settings and temporary setup files remain in LocalAppData. Verify ZIP structure before delivery; preserve existing user data and archived releases. No EXE build or GitHub Actions workflow is authorized.
