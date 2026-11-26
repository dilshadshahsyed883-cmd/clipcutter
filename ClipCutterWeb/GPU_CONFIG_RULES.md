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
