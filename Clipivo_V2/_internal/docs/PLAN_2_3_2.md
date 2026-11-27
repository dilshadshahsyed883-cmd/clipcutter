# Clipivo 2.3.2 — JSON-driven timeline building

Owner-directed scope: focus desktop 2.3.2 on timeline building using Person Analyzer JSON as the authority. Preserve archived V2.3 and V2.3.1, the original Clip Extractor, existing user data and the independent Web/GPU applications. No desktop EXE build, deploy, or merge without separate approval.

## Strict scope boundary

Only Timeline Builder / Replacement Studio, read-only import of existing Person Analyzer JSON, person-wise footage selection, clip duration, gap filling, speed adjustment, editable timeline and existing CapCut export. Clip Extractor and Person Analyzer are removed from the active 2.3.2 desktop UI per the latest owner instruction. Their archived source and existing data remain intact. No analyzer changes, automatic re-analysis for this JSON workflow, Concat integration/API, Rust compilation or GPU rendering integration. Source ZIP delivery only after acceptance; no EXE.

## Verified current contract

Desktop `v22/analyzer.py` saves `analysis.json` with `version: 2`, `source`, `duration`, `sample_interval`, and `people`. Person records include stable project-local `id`, `name`, accepted `segments` as [start,end] seconds, `raw_segments`, `ignored`, `filtered`, and observations. `studio/analysis.py` currently reloads and refreshes a project. `studio/automation.py` currently builds scenes via video inspection and can re-run analysis on cache misses; this is distinct from the intended JSON-first workflow.

## Implementation plan (pending)

- Load a previously saved Person Analyzer JSON explicitly. Validate supported schema, source binding, finite timing, valid ranges and stable unique IDs. Never silently regenerate analysis when a JSON is selected. Do not use embeddings or infer names from filenames.
- Treat accepted segments, not raw segments, as timeline inputs; omit ignored/filtered people. Preserve exact boundaries, order, gaps, and overlapping person membership. Show missing/ambiguous coverage as unassigned, not fabricated footage. Do not bridge rejected intervals.
- Build a deterministic editable timeline with person labels, source time, duration and gap rows; keep the original JSON unchanged. Use compatible existing Replacement Studio/CapCut export only after review, and verify duration/round-trip precision. Selection, minimum/maximum clip duration and replacement rules remain subject to owner clarification where they would change analyzer timing.
- Add tests for single/multiple persons, overlap, gaps, invalid JSON/timing, ignored/filtered records, repeated builds, source mismatch, backward compatibility and cancellation. Test desktop UI and existing extractor/picker behavior before delivery.
- GPU JSON adapters and all GPU integration are out of scope for 2.3.2.

## Ten owner-approved rules

1. Read-only existing analysis.json import; no re-analysis.
2. Exact accepted timestamps, person sequence, names, explicit gaps, duration preserved.
3. Scan one main folder recursively including root videos; exact case-insensitive person-folder matches only; unassigned root footage available for manual selection; missing matches become gaps.
4. Adjustable 2.5–4s defaults; original person boundaries take priority. Infeasible short pieces remain manual gaps.
5. Optional same-person gap filling, default maximum 1s; never fill different-person or missing-footage gaps automatically.
6. Optional speed adjustment, default 0.8x–1.2x; trim long footage; otherwise alternate or gap.
7. Random selection and trims, avoid reuse until alternatives exhausted, optional reuse, regenerate with new seed.
8. Color-coded editable timeline, gap highlight, preview, replace/remove/fill, trim/speed, zoom.
9. Separate timeline JSON, reopen, missing media, relink and autosave; source immutable.
10. CapCut draft with empty gap positions, optional original audio and full duration; no video encoding.

Status: initial JSON core and tests added; UI and native CapCut integration are separate implementation steps. No build or release certification.
