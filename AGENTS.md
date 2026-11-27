# Clipcutter repository instructions

## Build policy — updated 26 November 2026

The owner retains the EXE build prohibition and removes the earlier general build/workflow restriction.

- Do not build, package or trigger any desktop EXE, including `BUILD_EXE.bat` or manual/automatic executable CI jobs.
- Source development, testing, non-EXE CI, Docker GPU image builds and GHCR publishing are allowed. ClipCutter GPU candidates follow Concat's reviewed exact-main-SHA, smoke-test, immutable tag and digest-verification rules.
- GitHub Actions workflows for non-EXE testing and GPU candidate build/publish are permitted. No EXE workflow may be introduced or enabled.
- Candidate publishing is separate from production deployment; SaladCloud provisioning and live VPS changes still require the applicable review and deployment gates.
- Existing desktop source-package and data-preservation rules remain unchanged. This policy supersedes older general build/workflow bans in historical reports and desktop scope documents.

## Permanent Windows source runtime rule

- Keep all source-launch Python virtual environments and installed dependencies under `%LOCALAPPDATA%\ClipivoV2\runtime\` (V2.3: `python-v2.3`). Never create or reuse `.venv` or `venv` inside the application/source folder.
- Source ZIPs must exclude virtual environments, Python caches and temporary files. Reuse the AppData runtime across source-folder replacements. A legacy local environment is ignored, not automatically deleted; users may remove it manually.

## Clip Extractor compatibility rule

- Preserve original Clipivo v0.7.7 recognition, scan and extractor UI behavior, upstream verified model discovery and original dependency pins. Studio analyzer model settings must not override the extractor/Batch engine. Keep new optional clip-duration controls opt-in and verify parity with them disabled. Do not reset or delete existing user data to restore compatibility.

## Windows source ZIP location rule

- Store the final PC-testing source ZIP in the Windows Downloads folder by default.
- Extract the runnable source app beside the ZIP in the Windows Downloads folder as `Clipivo_V2/`.
- Preserve the archive name `Clipivo_V2_3_Windows.zip`, its single outer `Clipivo_V2` folder, `START_V2.bat` and `_internal` structure.
- Keep the Python runtime under `%LOCALAPPDATA%\ClipivoV2\runtime\`; do not bundle it in the ZIP.
- Follow `docs/PC_TEST_ZIP_METHOD.md`. Creating a requested source ZIP does not authorize an EXE build, packaging an executable, or enabling EXE build workflows.

## Clean, location-independent Windows PC-testing source layout

- `Clipivo_V2/` must contain exactly `START_V2.bat` and `_internal/`. Keep documentation in `_internal/docs/`, licenses in `_internal/licenses/`, reports in `_internal/reports/`, tests in `_internal/tests/`, and inactive development scripts in `_internal/dev/`.
- Default extraction is the Windows Downloads folder, but the launcher must run from any writable or read-only source location with spaces; all dependencies are installed only in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\`. Ignore legacy source-local virtual environments; recreate the runtime in AppData from Python, never relocate or delete the legacy environment automatically.
- AppData stores pip cache, launcher temp files and export cache. Preserve verified upstream model/FFmpeg caches at `%LOCALAPPDATA%\Clipivo` and Studio models, Node, settings, projects and profiles at `%LOCALAPPDATA%\ClipivoV2`; retain existing legacy data read paths without moving/deleting user data. Existing external model files may be reused read-only. User-selected media/export paths remain user-controlled.
- Source replacement never requires clearing persistent AppData. EXE builds and EXE build workflows remain prohibited. Keep package documentation snapshots aligned with repository docs.

## Active development version

The active desktop development version is 2.3.2 (JSON-driven timeline building). `old_releases/V2.3` and `old_releases/V2.3.1` are immutable. See `docs/PLAN_2_3_2.md`. Maintain one application version source (`Clipivo_V2/_internal/version.py`); use it for window, About, diagnostics and new analysis metadata. Keep app release numbers distinct from persisted JSON schema versions, the existing Windows ZIP filename, AppData runtime paths and independent Web/GPU versions. Update active docs and archive each verified source release before starting its successor. Preserve original extractor behavior and explicit review; no EXE builds.

## Mandatory delivery clarification — 26 November 2026

The owner's latest instruction supersedes the earlier ZIP destination rule: **the final PC-testing source ZIP must be saved in the Windows Downloads folder**, as `Clipivo_V2_3_Windows.zip`. A direct browser download or a PowerShell command targeting the user's Downloads known folder is acceptable. The extracted application also belongs in Downloads as `Clipivo_V2/`. Python runtime, dependencies, models, settings and temporary setup files remain in LocalAppData. Verify ZIP structure before delivery; preserve existing user data and archived releases. No EXE build or EXE build workflow is authorized.

## Current owner-approved automatic private GPU release policy

Automatic candidate builds are authorized for private, non-commercial educational testing only when GPU build inputs or GPU release workflow changes merge into main. This standing approval replaces the manual-only/each-build approval requirement and earlier build holds. Manual dispatch remains available with exact main SHA and explicit confirmation. No third-party redistribution rights or commercial license are represented as verified. No desktop EXE, Concat changes, automatic Salad deployment/start, paid GPU use, or VPS deployment.

- Build the exact main event SHA after source regression tests pass, with a clean checkout, pinned model hashes, private GHCR checks before staging and immediately before/after publication, CPU/image/HTTP smoke gates, immutable SHA tags and verified registry digest. No overwrites; check existing tags before building. Keep prior images for rollback.
- Automatic build paths: GPU Dockerfile, .dockerignore, requirements, worker/, tests/, build and model staging/verification scripts, and GPU release/source-test workflows. Documentation, release notes, Web and desktop-only changes never trigger GPU builds. In-flight builds compare these same inputs against latest main; unrelated changes do not invalidate the image. If relevant inputs change, the old candidate fails closed and a new main-event build handles the new inputs.
- Serialize builds for main; do not cancel running builds on Web changes. Pending runs may coalesce to the latest relevant main event.
- Permanent model supply: use the previously verified private GHCR seed by immutable digest, copy only the two exact pinned model files without executing the seed, and verify size/SHA256 again. Preserve that seed image. Optional owner-supplied Drive ID/HTTPS ZIP secret overrides the seed; never commit credentials or model files. Registry access or model verification failure blocks publication. No runtime download.
- Image publication is not deployment or physical GPU/media acceptance. Deployment remains separately authorized.
