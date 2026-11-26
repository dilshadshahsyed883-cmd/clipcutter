# Clipivo V2.2 — Person Timeline Analyzer (prototype)

Independent local Windows research prototype inspired by Clipivo; not an official release or modification of the upstream installed application. The SCRFD/ArcFace processing approach in engine.py is adapted from https://github.com/longweekendlabs/clipivo/blob/main/core/face_models.py (MIT; see LICENSE.txt). Models are NOT distributed. InsightFace buffalo_l weights are restricted to non-commercial research; check permissions before using them commercially.

## Windows setup
1. Install 64-bit Python 3.11 from https://www.python.org/downloads/ if not already installed (including the Python launcher and Tcl/Tk).
2. Extract the entire ZIP into a writable folder. Double click START_V2.bat. First launch installs dependencies into a local virtual environment and requires Internet access.
3. V2 automatically searches the existing Clipivo model cache (`%LOCALAPPDATA%\Clipivo\models\buffalo_l`), installation and other common locations. If not found, Analyze downloads the two ONNX files (~191 MB) into the V2 cache with size and SHA-256 verification. Internet access is required for missing files. Manual Browse remains available. No reference photos are required.

Optional: run `BUILD_EXE.bat` on Windows to attempt a local PyInstaller one-folder build. Keep the whole `dist\ClipivoV2` directory together. This build script has not been tested on Windows.
4. Select a short local video. Leave GPU unchecked for the first run. Click Analyze video.
5. Review automatically discovered person groups and images. Rename, merge (Ctrl-click groups), split selected sample observations, ignore/restore or remove groups. Save person writes a reusable profile locally. Open output shows saved files. Open analysis reloads analysis.json.

## Settings
- 0.5 sec sampling default; 0.25 sec for short appearances, 1–2 sec for faster sampling. Timing is estimated from positive sample cells; no exact-frame refinement or tracking yet. Unseen or occluded faces can be missed. Smart filters suppress small, low-confidence and short appearances and stable small corner portraits by default. They are heuristics, not semantic background classification; real faces can be filtered and overlays missed. Review ignored groups and restore them or tune Filters. Draw a manual ignore region in preview.
- Similarity 0.45 is a provisional cosine threshold, not calibrated. Increase if distinct people merge; decrease if same person splits. Clustering is online centroid matching, not a trained or validated identity classifier. People get anonymous labels; no automatic real-name lookup.
- 640 detector default; 1280 for small faces, potentially slower. Optional DirectML provider on Windows with CPU fallback when GPU initialization or inference raises. Actual performance not verified.

## V2.2 review controls
Live preview shows sampled frames and colored face boxes, with active groups highlighted. Click timeline bars or reference images to seek; use Play/pause for silent local review. Zoom, Solo, Show ignored and manual region exclusion are available. Group edits and filter changes are made after scanning. Filters preserve raw observations and are reapplied without inference. Reference selection removes near-duplicate crops heuristically. Timeline boundaries remain sampled estimates.

## Outputs and privacy
`%LOCALAPPDATA%\ClipivoV2\Projects\<run>\analysis.json`, `timeline.csv`, `timeline.txt`, `references/` (local plaintext). `People_Library/<id>/profile.json` and selected images store a named profile and embeddings. Automatic reuse across videos is not wired yet. All analysis is local; settings, images and embeddings are not encrypted in this prototype. Use only footage and personal data you are authorized to process. Delete project/profile directories to remove saved images/embeddings. Cancelled or failed runs may leave partial reference images, but no completed analysis.json. Source video is never modified. Delete group removes it from analysis, not reference images. CSV/TXT omit ignored groups. No automatic clip replacement, video editing or rendering is included.

## Validation
Nine automated tests passed (grouping, persistence, model discovery, static overlay heuristics, region filtering, restore and reference deduplication). Syntax and GUI startup/filter-dialog smoke checks passed on a Linux virtual display. Real Windows inference, GPU fallback, model download over the network, and Windows EXE build remain unverified. This is runnable source, not a compiled or signed Windows executable. Full People Library browser, automatic cross-video identity matching and exact boundary refinement are not yet implemented.
