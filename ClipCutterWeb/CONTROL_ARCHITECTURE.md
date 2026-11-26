# ClipCutter Web — approved control architecture

Approved by owner on 2026-11-26. Planning only; no implementation or deployment is implied.

## Application boundary
- Existing repository: clipcutter, main, ClipCutterWeb/.
- Independent site: https://clip.scenebuilder.online; VPS DNS A record 137.74.162.143 (owner screenshot; propagation unverified).
- Exactly two processing tabs: Clip Extractor and Person Analyzer. Administrative controls and GPU configuration are supporting controls, not additional processing products.
- Browser-based centralized control, using Concat Web as the operational reference and Clipivo desktop as the processing reference.
- Independent VPS API, authenticated admin interface, persistent storage, job queue, logs, and worker orchestration.
- Separate SaladCloud worker image and container group; no change to Concat Web, its GPU worker, or desktop Clipivo. No dependency on Windows desktop runtime.

## Control requirements
- Google Drive input and output, verified staging on VPS before dispatch, and verified output delivery.
- Queue start, pause, resume, cancel; display actual state and actionable errors. Persist queue state and prevent duplicate dispatch.
- GPU configuration, worker enable/disable, automatic startup when eligible staged jobs are ready, readiness gating, automatic shutdown when queue and deliveries are complete.
- Inspect and adapt Concat's verified worker lifecycle, image-pull health checks, bounded reallocation/retries and cooldown. Exact defaults and thresholds must be audited and recorded before implementation rather than assumed.
- Show measurable progress, FPS, ETA, worker state and processing logs. Do not invent telemetry or imply live measurements where the worker cannot supply them.
- Preserve staged inputs on worker disconnect; verify outputs before completion; retry safely without duplicate output. Bound concurrency according to measured worker resources.
- Persist authorized person profiles and project results independently. Require authenticated access, scoped data access, secure secret storage, and retention/deletion controls. Verify model licensing and GPU compatibility.

## Implementation order
1. Audit current Clipivo headless extractor/analyzer code and Concat Web lifecycle interfaces, without modifying those projects.
2. Define API, queue state machine, storage and worker protocol; establish tests and resource/compatibility requirements.
3. Implement independent two-tab web UI, admin controls and backend on a development branch.
4. Implement independent GPU worker integration and run source-level tests including failure, cancellation, restart, and duplicate prevention.
5. Verify VPS resources, DNS, TLS, reverse proxy and isolated deployment; deploy only when authorized and tested.

No EXE builds, executable packaging, or GitHub Actions build workflows. This document does not authorize provisioning paid GPU resources or modifying existing production services.
