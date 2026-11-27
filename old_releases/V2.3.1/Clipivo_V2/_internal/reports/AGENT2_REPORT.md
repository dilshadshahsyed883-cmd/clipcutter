# Agent 2 — Replacement picker and reconstruction

## Scope and base
Branch: `work/replacement-picker`. Started at main `1973433746a0bc72e6513b428a4ea39df1d104f4`. Read AGENTS.md, README.md, docs/APPROVED_SCOPE.md, docs/STATUS.md and Clipivo_V2/TEST_REPORT.md. Only Agent 2's picker, footage, render, replacement page, core export, focused test and this report were changed. No EXE/build workflow, packaging, main merge or delegation.

## Changes
- **Picker:** stable source order, existing xorshift seed, keyword/group-first weighted draws, inverse usage penalty, source cooldown and random trims preserved. Source capacity is reserved for remaining picks before every draw. Count and durations are budgeted on the reference frame grid (microseconds only for legacy references without FPS). Reject mathematically impossible total/min/max/source/reuse combinations. Cooldown relaxation is reported; no silent short tail. No Concat runtime dependency.
- **Extractor:** split in millisecond-safe bounds after input range selection. Accurate mode, no post-split merging in export, strict mode rejects framing and active filters, disables repeat-frame removal, reports excluded short remainder seconds in progress and log, and rejects encoded segments outside bounds rather than silently publishing them. Named existing destinations and source paths are protected. The stitched output is a container of bounded physical segments; its entire duration can exceed the individual maximum by design.
- **Reference replacement:** retain reference scene boundaries; prioritize direct suitable footage, then distinct confirmed same-person pieces at 1x, then bounded slowdown down to 0.67x. Allocate gap pieces on reference FPS grid and enforce optional per-piece min/max. Unmatched/unknown identities do not match automatically. Identity constraints and approval are checked on every piece before render/export. Imported source identity requires continuous recorded appearance across the source scene; manually confirmed labels are explicit evidence, not model confidence. Unknown IDs are source-scoped. A manually chosen trim requires explicit identity confirmation; changed manual trim must be reconfirmed.
- **UI:** reference scene labels cannot accidentally modify a freely picked timeline, actual reference scenes retained separately, explicit approval checks, persisted keyword weights, candidate/manual selection reset review state. Matching uses shared clip limits if enabled.
- **Index:** persistent SQLite index remains; unchanged media reuse existing data, stale/removed media excluded until reindex, changed-during-index input rejected. Histograms remain visual ranking only; no semantic understanding or calibrated confidence claim.
- **Render:** validate canonical timeline, source bounds, per-piece speed, approval and identity; round cumulative boundaries to frame budget and reject any rounded piece outside limits. FFmpeg and FFprobe processes cancellable, exact frame counts checked per segment and final output, chosen audio checked and padded/trimmed to duration, final streams decoded. Output publication via atomic no-clobber hard link on same filesystem; refuse existing target and source/external-audio paths.

## Canonical replacement-plan contract (Agent 3)
Version remains 1 for existing integrations. All timeline/source times are seconds; speed is playback rate (0.67 = slowdown). Distinguish `mode: reference_preserving` from `mode: concat_picker`. Missing mode on a legacy plan means reference_preserving. `reference` is the original media metadata: path, duration, width, height, fps, original scenes. `rows` are the intended timeline, not the original reference's scene list in concat_picker mode. Example for a 4s scene:

```json
{
  "version": 1,
  "mode": "reference_preserving",
  "reference": {
    "path": "reference.mp4",
    "duration": 4,
    "width": 1920,
    "height": 1080,
    "fps": 25,
    "scenes": [{"start": 0, "end": 4, "people": ["profile-A"], "confirmed_people": ["profile-A"]}]
  },
  "rows": [{
    "original": {"start": 0, "end": 4, "people": ["profile-A"]},
    "identity_required": ["profile-A"],
    "approved": true,
    "manual_review": false,
    "candidates": [],
    "selected": {
      "path": "a.mp4",
      "start": 10,
      "end": 12,
      "trim_start": 10,
      "target_duration": 2.5,
      "speed": 0.8,
      "confirmed_people": ["profile-A"],
      "gap_fill": true,
      "pieces": [
        {"path": "a.mp4", "scene": 0, "start": 10, "end": 12, "trim_start": 10, "target_duration": 2.5, "speed": 0.8, "confirmed_people": ["profile-A"]},
        {"path": "b.mp4", "scene": 1, "start": 3, "end": 5, "trim_start": 3, "target_duration": 1.5, "speed": 1.0, "confirmed_people": ["profile-A"]}
      ]
    }
  }]
}
```

- `original.start/end`: intended scene timeline; contiguous from 0 to reference.duration. In reference_preserving mode they must equal corresponding reference scenes.
- `selected`: null means missing; otherwise single physical clip or a wrapper whose nonempty `pieces` array is authoritative. Wrapper's path/start/end/trim/speed/target_duration describe first piece for legacy preview only; never render both wrapper and children.
- Each physical piece contains path, source scene index when indexed, source start/end, trim_start, target_duration, speed, confirmed_people. Source consumption = target_duration * speed. Source trim end = trim_start + consumption and must not exceed source end. Pieces sum to original scene duration. Single-clip legacy plans without explicit speed/target_duration infer 1 and scene duration.
- `approved=true`, `manual_review=false` required on every row; each physical piece must cover all IDs in union of original.people and identity_required. Empty confirmed_people is not identity evidence. Old identity-labelled plans lacking confirmation must be reviewed again.
- Optional `clip_limits:{minimum,maximum}` (reference mode) or `picker:{minimum,maximum,seed,cooldown,allow_repeats,group_weights}` (free picking) applies to physical target duration. Warnings list records cooldown relaxation. `score` is optional ranking, not confidence.
- Call `studio.footage.expand_plan(plan)` once on the unexpanded plan to validate and receive one row per physical piece. Flattened row original.start/end are the piece's absolute timeline times; do not re-expand a flattened reference plan. Use selected.trim_start, selected.target_duration, selected.speed. Preserve reference duration/audio selection; source audio muted. Separate external audio selection belongs to the export request, not an invented per-piece field.
- Agent 3 owns CapCut. Existing adapter calls expand_plan already; it must independently validate CapCut time-unit conversion, speed/audio behavior and installed playback. No CapCut files modified.

## Agent 1 integration handoff
Preserve existing storage keys: `clip_limits.enabled` (bool), `minimum`, `maximum` (positive seconds, min <= max); `picker.minimum`, `maximum`, `seed` (integer), `cooldown` (nonnegative integer clip count), `allow_repeats` (bool), `group_weights` (keyword -> nonnegative finite weight). Settings merge must retain sibling keys. Reference scene preservation and free picking are separate actions. Display explicit errors for infeasible frame budgets; display excluded remainder seconds; don't merge split ranges after max-duration splitting. Keep task cancellation and safe shutdown; library_id must only be assigned to reliably matched or explicitly confirmed profile identities, project-local unknown IDs must not be treated as global IDs. Agent 1 owns analyzer, shell and storage.

## Tests actually run
Added `Clipivo_V2/tests/test_replacement_picker_v23.py` (6 focused pytest tests). The local runtime has no DNS/network access to GitHub, so a normal clone and full repository test run were not possible. GitHub connector provided source; manually mirrored three backend modules and test file locally, verified exact Git blob hashes against the pushed branch:
- picker.py `3c734b9d5482310e0ec2742193d78b60ea18ce48`
- footage.py `a56fd2fbbf8fc100586e09a9a470826a63ad81eb`
- render.py `31eeed8405adf0d5f112fcafb67e1ef66ee21e17`
- test_replacement_picker_v23.py `c6f2c5d9a24ddf62e3b8bc20f615d1b291907ee5`

Only the storage root and FFmpeg tool-discovery imports were stubbed; actual OpenCV, SQLite, FFmpeg/FFprobe and libx264 ran. Command: `PYTHONPATH=. pytest -q tests/test_replacement_picker_v23.py` from isolated mirror. Latest result: **6 passed in 2.89s**. Tests cover 50 deterministic seeds and feasible/no-repeat constraints, impossible combinations, explicit 9s split into 4+4 with excluded 1s, identity rejection and multi-piece slowdown, real 4-second/40-frame reconstruction with original and external AAC audio, cancellation, destination/source preservation and persistent index reuse. Synthetic identity labels exercise gating, not recognition accuracy.

## Remaining limitations / acceptance
- No full checkout: original extractor regression suite, Qt review flow, real storage integration, Windows, NVENC and CapCut were not executed. Core/export.py and replacement_page.py changes were statically reviewed, not runtime-validated. Run from Clipivo_V2: `python -m pytest -q tests/test_replacement_picker_v23.py` then full source suite after agents integrate.
- Strict extractor mode rejects filters and non-whole framing rather than promising durations those operations can change. At nonaligned source frame rates, strict encoded segment validation may reject even when a different cut allocation would be possible; no invalid physical segment is accepted. Existing upstream extractor multi-output export is not a transactional all-or-nothing batch.
- Reference/freely picked plans use reference frame grid; a different render FPS can make constraints impossible and is rejected. Total duration is representable to nearest output frame; AAC has normal codec rounding. VFR, long renders, fractional frame rates and GPU still need acceptance testing. Original/external audio must have an audio stream; external short tracks are padded in renderer (Agent 3 must decide equivalent CapCut behavior).
- No-clobber publication requires a destination filesystem supporting hard links (e.g. NTFS); unsupported filesystems fail safely. Source files may change after a saved plan was approved; full content fingerprint pinning per plan is not implemented. Index uses path/size/mtime fingerprint, not full file hash.
- No automatic semantic analysis, calibrated confidence, or real face recognition testing. Confirmed profile labels rely on Agent 1's correctness and manual review; sampled appearances are not proof of every frame. Manual same-person multi-piece editing UI remains limited to generated combinations; insufficient/uncertain combinations remain manual review. Matching and picker can still be synchronous in the UI; large-library responsiveness not validated.
- Editing/reordering or speed changes do not establish authorization or copyright clearance. No EXE build or GitHub Actions change; no merge to main.
