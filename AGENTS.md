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
