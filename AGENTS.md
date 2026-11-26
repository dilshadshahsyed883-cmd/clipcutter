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

The approved automation/usability work is named 2.3.1 (not V3). `old_releases/V2.3` is immutable. See `docs/PLAN_2_3_1.md`. Preserve original extractor behavior and explicit review; no EXE builds.

## Mandatory delivery clarification — 26 November 2026

The owner's latest instruction supersedes the earlier ZIP destination rule: **the final PC-testing source ZIP must be saved in the Windows Downloads folder**, as `Clipivo_V2_3_Windows.zip`. A direct browser download or a PowerShell command targeting the user's Downloads known folder is acceptable. The extracted application also belongs in Downloads as `Clipivo_V2/`. Python runtime, dependencies, models, settings and temporary setup files remain in LocalAppData. Verify ZIP structure before delivery; preserve existing user data and archived releases. No EXE build or EXE build workflow is authorized.

## Owner-approved GPU build hold (latest instruction)

No GPU Docker build or trigger until owner explicitly approves finalization. GPU workflow is manual-only with its build job disabled during the hold. GPU source belongs in ClipCutterGPU/ on main; Web source belongs in ClipCutterWeb/ on main. Source changes may be reviewed and merged independently without building. Do not enable build until owner approval. Follow docs/GPU_FINAL_IMAGE_CONTRACT.md. This hold supersedes general permission to build GPU candidates, without changing the permanent no-EXE rule.

## Latest owner instruction — private educational image build

The owner explicitly directs building the model-inclusive image for private,
non-commercial educational testing and assumes licensing responsibility. This
supersedes the earlier build hold and the requirement to wait for written vendor
clarification for this testing build. It does not establish verified model
redistribution rights or a commercial license. Enable only manual exact-main-SHA
builds with explicit private educational approval; keep package-private checks,
model hashes, all smoke tests, immutable tags and digest verification. No EXE,
Concat changes, Salad starts or VPS deployment are authorized by this exception.

## Latest owner rule — independent Web and GPU releases

The approved manual GPU build remains pinned to the exact main commit at dispatch. Subsequent main updates outside `ClipCutterGPU/` do not cancel or invalidate that image build or publication. Compare the pinned `ClipCutterGPU` Git tree against current main before building and publishing; if GPU source differs, require renewed approval. Keep immutable original SHA tags, private package verification, model pins, smoke tests and digest checks. No automatic image rebuild on Web-only merge. Already dispatched runs use their original workflow; do not cancel them merely for a Web update. Web and GPU deployments remain separately authorized.
