# Windows PC-testing source ZIP method

Owner preference recorded on 26 November 2026: **the ZIP and extracted test application must not be placed in Downloads by default. Use the current Windows user's Local AppData.**

## Required locations

| Item | Location |
| --- | --- |
| Source ZIP | `%LOCALAPPDATA%\ClipivoV2\packages\Clipivo_V2_3_Windows.zip` |
| Extracted test app | `%LOCALAPPDATA%\ClipivoV2\app\Clipivo_V2\` |
| Launcher | `%LOCALAPPDATA%\ClipivoV2\app\Clipivo_V2\START_V2.bat` |
| Shared Python runtime/dependencies | `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\` |

Resolve paths from LOCALAPPDATA; never hardcode a username or assume a literal `C:\Users\...` path.

## Source ZIP preparation and PC setup

1. Use the requested, verified GitHub main commit and record its full SHA. An old checkpoint SHA must not silently replace a newer requested revision.
2. Include the repository's `Clipivo_V2` application tree, required resources, licenses and relevant documentation. The archive must have exactly one outer folder named `Clipivo_V2`, with `START_V2.bat` and `_internal` inside.
3. Exclude Git metadata, virtual environments, Python/test caches, temporary files and user projects, credentials or biometric data. Do not include runtime installations or redundant model weights.
4. Save/download or generate the final source ZIP directly in the AppData packages directory above. Do not default to `$HOME\Downloads`, the Windows Downloads known folder, or the shell's current working directory. Setup scripts should explicitly create and use the AppData directories.
5. Extract into the AppData app directory above, avoiding a duplicate `Clipivo_V2\Clipivo_V2` nesting. Prepare replacements separately and preserve the previous source folder if replacement fails. Do not erase projects, settings, models, profiles or the shared runtime.
6. Verify ZIP integrity and launcher/resource paths. Run `START_V2.bat` only when the user requests PC testing. It reuses the AppData runtime and may install missing Python dependencies on first launch.
7. Deliver a short launch instruction and the recorded source SHA. Clearly label the package as source; it is not a compiled Windows executable.

If the owner already has a copy in Downloads, do not automatically delete or move it. The new default applies to future ZIP/setup deliveries; moving an existing copy is a separate user-directed action.

## Restrictions and implementation status

No EXE build, executable packaging, or GitHub Actions build workflow is authorized by this method. This change documents the required delivery/setup locations; it does not itself modify or certify any existing PowerShell helper or launcher. A helper that still targets Downloads must be updated by the implementing agent before claiming compliance. No ZIP was created or executed by this documentation update.
