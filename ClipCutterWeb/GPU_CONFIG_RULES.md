# ClipCutter Web GPU Config — Concat Web rule parity

Owner approved copying Concat Web's GPU Config rules on 2026-11-26. This is an implementation contract, not a functioning GPU integration. Keep Clip Extractor and Person Analyzer as the only processing products; GPU Config is a third, supporting Studio tab.

## Audited references
- [Current Salad worker controller](https://github.com/dilshadshahsyed883-cmd/concat-web/blob/main/app/modules/concat/engine/salad_worker.py)
- [GPU Config UI](https://github.com/dilshadshahsyed883-cmd/concat-web/blob/main/app/modules/concat/templates/cloud_render.html)
- [Lifecycle documentation](https://github.com/dilshadshahsyed883-cmd/concat-web/blob/main/deploy/SALAD_AUTO_WORKER.md)
- [Five-minute retry-cycle correction, PR #51](https://github.com/dilshadshahsyed883-cmd/concat-web/pull/51)
- [Idle stop rules](https://github.com/dilshadshahsyed883-cmd/concat-web/blob/main/deploy/SALAD_IDLE_AUTOSTOP.md)

Current controller overrides older documentation where they differ. Adapt existing reviewed logic to ClipCutter's independent job and worker protocols; never import Concat as a runtime dependency or copy its private credentials/data.

## Config and defaults
- Connection setup: independent Salad API key, organization/project/group identifiers, ClipCutter worker gateway and authentication token; secrets write-only and stored securely. Dedicated one-replica group; Salad autostart_policy=false. Container image/resources configured in SaladCloud.
- Automatic/Manual mode; initial default Manual (automatic opt-in, matching Concat). Explicit Save Automation Settings, Start Worker, Stop Worker, Retry Worker Action, real state and dynamic rule summary.
- Minimum image pull 8%, adjustable integer 1–100. Download window 20 seconds, adjustable 5–600 seconds. Start timing from instance downloading update_time, not allocating/creating.
- Maximum 3 reallocations per cycle (backend allowed 0–3); 30-second default cooldown between attempts (backend allowed 5–600 seconds).
- After the cycle budget is exhausted and replacement remains slow, persist a 300-second retry deadline, then reset the budget and retry automatically. Zero budget disables reallocation. Confirmed readiness resets budget/deadline; never repeat unresolved identical POSTs.
- Automatic shutdown 60 idle seconds after all queue work and deliveries finish. Manual mode disables automatic shutdown.
- Concurrency 1 or 2 on one worker only after ClipCutter-specific resource verification; Drive downloads do not use GPU slots.

## Intake, startup and dispatch
All nonterminal pending Drive intake, including scheduled retries, must complete and verify before GPU startup or new dispatch. Adapt to ClipCutter's file, ZIP, folder and reference inputs; verify each required input. Five Drive retries at 20-second intervals as in Concat. Terminal failed/cancelled intake does not block other jobs. Intake continues during Production pause; pause/disconnect block new GPU starts and submissions. Manual start respects intake gate and readiness, but does not automatically reallocate.

Start a dedicated stopped group once, then poll actual Salad state and worker health. Dispatch only when API ready=true and authenticated worker health succeeds; no duplicate submissions. Normalize progress 0–1 to percent (0.30 → 30%, 1.0 → 100%); >1 to 100 remains percent. Unknown/invalid data never means zero. Poll startup no more often than every three seconds; check freshness, monotonic timestamps, same instance/machine/version/download transition and exact instance GET immediately before reallocation. At/above threshold keep; below threshold at/after window reallocate only if still downloading and no active/submitted jobs. New download transition gets new window; no machine scoring/history.

## Durable orchestration and shutdown
Use one dispatcher for manual and automatic commands, owner-scoped persistence and cross-process locking. Commit start/reallocate/stop intent before POST; reconcile accepted or timed-out requests with GET. Do not repeat identical ambiguous actions; explicit authenticated/CSRF-protected retry allowed only when no GPU jobs active. Keep staged inputs on disconnect. Verified outputs require size/hash validation before publication; protect undelivered output, including failed post-submission jobs, until resolved. Manual stop blocks new jobs and drains active work. Idle timer requires terminal queue, no intake/output transfers, running group and confirmed active_renders=0; unreachable/busy/uncertain worker blocks stop. Reset idle timer on restart. Never infer successful stop from accepted POST alone.

## Implementation and acceptance gates
Implement UI and isolated scheduler/transport only against an agreed ClipCutter worker contract. Port relevant Concat tests for pending intake barrier, progress units and thresholds, stale state, retries across restart, duplicate action protection, pause/manual controls, verified outputs and idle shutdown. Add ClipCutter-specific input/worker and profile retention/deletion tests. Show actual progress and logs only; FPS/ETA only when measured. The uploader's separate five-minute YouTube upload cancellation grace is not a GPU lifecycle rule and is not copied here. No changes to Concat, desktop, GPU images, live Salad group or VPS; no EXE builds. Full runtime and external acceptance remain pending.

## Additional source implementation (26 November)

Queue pause/resume in GPU Config uses the same owner-scoped pause state as Studio, even when GPU lifecycle is gated. GPU status automatically refreshes with read-only Salad GETs every 10 seconds while visible. GPU lifecycle remains explicitly gated; one render slot only. YouTube dispatch requires `CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED=1`, an approved image built with the new worker contract and its authenticated `source_kinds` capability. Old images are not silently treated as compatible. Deleted requests no longer prevent idle shutdown. Unsupported inputs are held with verified data rather than failed.

Optional Drive delivery is separate from the intake bridge. Before enabling, configure a dedicated writable Drive identity using `/var/lib/clipcutter-web/drive-delivery/rclone.conf` (owner clipcutterweb, mode 0600, separate credentials), set `CLIPCUTTER_DRIVE_DELIVERY_REMOTE`, set comma-separated exact folder IDs in `CLIPCUTTER_APPROVED_DRIVE_OUTPUT_FOLDERS`, and explicitly set `CLIPCUTTER_DRIVE_DELIVERY_ENABLED=1` only after verifying permissions and live test. Rclone remote must be Drive. Outputs use stable `clipcutter-<job-id>-<artifact-name>` names in the approved folder. Each output is verified by remote size and MD5 against the locally SHA-verified output; the GPU result is not acknowledged until all requested delivery succeeds. Ambiguous uploads are reconciled by metadata only and held if unresolved; no overwrite or deletion. No production credential installation, writer activation, GPU rebuild, scheduler start or VPS deployment is performed by this source change. Physical GPU concurrency 2 remains unsupported.


## Capability-gated pipeline candidate (27 November 2026)

This section supersedes the older single-slot implementation checkpoint above, not the physical acceptance gate.

- The GPU worker defaults to one slot. A reviewed candidate may be configured with `CLIPCUTTER_GPU_CONCURRENCY=2` in the dedicated Salad group only for separately approved physical acceptance. The worker advertises its real configured capacity and pipeline_version=1; the Web scheduler will not admit work at Parallel=2 until the authenticated, exact-SHA worker advertises two slots. Legacy workers remain serial.
- One upload/start lane, one output delivery lane, and one observation/control lane; durable attempt identity and per-job file locks prevent concurrent operations on the same request. One preloaded job beyond the render slots, and no new admission while two output deliveries are pending. Drive intake does not consume a slot. Initial GPU start still requires all intake to finish; a verified job may reuse an already-ready worker while later intake runs. Drive retries use five 40-second delays.
- Pause prevents new create/start and further upload chunks at the next checkpoint; already-issued network operations may finish. Running jobs and verified output delivery continue. Cancel GPU is a durable owner request, reconciled against the same remote attempt. A completion racing cancellation is delivered rather than discarded. Confirmed failed/cancelled attempts retain the VPS source, terminal ledger and history; only their remote scratch is purged after identity and terminal state confirmation. Retry GPU revalidates retained source hashes and creates a fresh attempt after confirmed cleanup. Unknown/lost attempts and existing partial outputs remain held for manual reconciliation; no blind recreation.
- Acceptance before enabling two slots in production: new private image publication and digest verification; drain the old worker before changing approved SHA/image; test parallel 1 then 2 on an authorized GPU, measure actual GPU memory, both jobs' processing/results, preloading, upload/download overlap, cancellation, retry, and idle shutdown. No automatic Salad/VPS deployment or GPU start. No claim of physical performance from mocked tests.
