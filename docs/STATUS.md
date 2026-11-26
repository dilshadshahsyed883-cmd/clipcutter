# Saved checkpoint — 26 November 2026

The owner instructed: focus on the separate **clipcutter repository**, with fixes later. This snapshot intentionally preserves current implementation work rather than claiming the complete original V2.3 scope is finished.

## Implemented source paths

- Original Clipivo Qt extractor/backend retained, with six-workspace integration.
- V2.2 analysis/filtering/model-location code reused; new Qt person analysis page, project reopening and profile matching.
- Persistent SQLite footage index, estimated hard scene cuts and HSV visual descriptors; semantic labels are manual.
- Replacement suggestions/review, missing report, trim, FFmpeg reconstruction and audio choice.
- Rajudesktop Z Builder draft writer/bridge reused, with a small optional speed extension and Clipcutter adapter. No runtime dependency on Rajudesktop.
- Video-only Python adaptation of Concat C Builder selection: xorshift seed, group-first selection, inverse usage penalty, source cooldown and random trims. Strict min/max feasibility added. No runtime dependency on Concat.
- Draft same-person multi-clip gap filling and bounded slowdown integration.
- Source startup and Windows executable build scripts.

## Partial or pending

- Final integration review after the latest clip-picker, limits, gap-fill and speed changes.
- Real Windows execution and compiled EXE verification; no compiled executable exists in this checkpoint.
- Real SCRFD/ArcFace inference on user footage, model downloads over the live network, GPU initialization/runtime fallback on hardware.
- Tracking between sampled frames, exact-frame appearance refinement, embedding inference cache, advanced clustering/duplicate correction.
- Automatic activity/environment/framing/angle understanding. The UI currently uses manual labels; histogram similarity is not semantic recognition.
- OpenCLIP/FAISS or equivalent semantic retrieval and production-calibrated match confidence.
- Automatic face analysis of all indexed footage. Current workflow links a completed analyzer project or manual labels to indexed scenes.
- Simultaneous live inference preview is sampled; original/reference reconstruction previews show still frames. Full replacement timeline playback is pending.
- Saved profiles created by the new analyzer have automatic embedding matching. Older profiles that contain only references need migration/embedding-cache population.
- Full V2.2 People_Library migration and complete encryption of project observations/crops.
- Strict min/max behavior under all export/filter/frame-rate combinations and CapCut speed playback acceptance.
- Final downloadable `Clipivo_V2_3_Windows.zip`, changelog and complete acceptance report.

## Storage decisions

Projects/settings stay outside the installation folder. Existing upstream project and people-store paths are reused where present; new Windows data uses the V2 data folder. Older V2.2 project JSON stays compatible. No automatic deletion of original footage.

## Scope additions captured from the owner

1. Match the provided original Clipivo UI screenshot.
2. Reuse models from the existing Windows Clipivo installation, including `_internal`.
3. Copy the relevant Open in CapCut logic from Rajudesktop's Z Builder.
4. Add minimum and maximum clip duration controls.
5. Reuse only Concat's clip-pick/rearrangement logic.
6. If one replacement clip is short, use another clip of the same person or bounded speed adjustment.
7. Save all work in the independent clipcutter repository; fixes later.

Reordering and speed changes are editing tools; they do not establish permission or copyright clearance.
