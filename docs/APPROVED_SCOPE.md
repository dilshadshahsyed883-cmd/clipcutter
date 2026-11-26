# Clipivo V2.3 — Unified Video Intelligence Studio

Act as a senior software architect, Python developer, desktop UI/UX engineer, AI computer vision engineer, and QA engineer.

## 1. Objective

Build a complete, consolidated Clipivo V2.3 desktop application combining:

- Original Clipivo V1 functionality.
- All existing working Clipivo V2.2 functionality.
- Planned V3 intelligent footage replacement and video reconstruction functionality.

Do not create three independent applications. Build one unified application with shared backend components, project state, settings, and media management.

## 2. Reference Materials

Original Clipivo repository:
https://github.com/longweekendlabs/clipivo

Use the attached Clipivo V2.2 ZIP as the existing working baseline.

Use the attached original Clipivo v0.7.7 screenshot as the primary UI design reference.

Do not use any unrelated application as the UI reference.

## 3. Professional UI Design

Reproduce the original Clipivo visual style:

- Dark charcoal interface.
- Orange accent color.
- Compact professional toolbar.
- Modern buttons and dropdown controls.
- Large central video preview.
- Resizable right-side inspector.
- Interactive timeline below the preview.
- Bottom status bar.
- Consistent typography and spacing.
- Responsive layouts.
- Native Windows desktop experience.

Prefer PySide6/Qt for the professional interface.

Replace the current basic Tkinter appearance without losing existing functionality.

## 4. Application Tabs

Create the following integrated tabs:

1. **Clip Extractor**
2. **Person Analyzer**
3. **Replacement Studio**
4. **Batch**
5. **People Library**
6. **Settings**

Keep navigation compact and consistent with the original Clipivo application.

## 5. Clip Extractor — Original V1

Inspect the actual upstream Clipivo source code before implementation.

Preserve and integrate its relevant functionality:

- Reference-photo-based person recognition.
- Multiple reference photos.
- Saved people selection.
- Use current video frame as reference.
- Automatic appearance detection.
- Automatic clip extraction.
- Single stitched video output.
- Separate clip output.
- Manual A/B cutting.
- Timeline navigation.
- Original-quality stream copying.
- Exact-frame cutting.
- Output quality and resolution controls.
- Smart person framing and cropping.
- Include/exclude audio.
- Output folder and naming controls.
- Batch processing.
- Video filters.
- Output verification.

Reuse existing working upstream implementations wherever practical instead of unnecessarily rebuilding them.

## 6. Person Analyzer — V2.2

Preserve every working V2.2 feature:

- Automatic person discovery without reference photos.
- Face embedding generation.
- Automatic person grouping.
- Temporary Person 1, Person 2, Person 3 names.
- Automatic reference image extraction.
- Multiple persons in the same frame.
- Person-wise appearance timestamps.
- Color-coded timeline.
- Live video preview.
- Live bounding boxes.
- Currently detected person highlighting.
- Real-time group creation.
- Real-time timeline updates.
- Rename groups.
- Merge groups.
- Split groups.
- Ignore and restore groups.
- Solo person view.
- Delete groups.
- Save person to People Library.
- Manual ignore regions.
- Background face filtering.
- Static portrait and logo filtering.
- Adjustable minimum face size.
- Adjustable minimum appearance duration.
- Adjustable detection confidence.
- Duplicate reference image filtering.
- Interactive timeline seeking.
- Project saving and reopening.
- JSON, CSV and TXT exports.

Improve existing functionality without introducing regressions.

## 7. Advanced Person Analysis

Improve the detection pipeline with:

- Single-pass video decoding.
- Efficient multi-person detection.
- Face tracking between detection samples.
- Face embedding caching.
- Stable person IDs.
- Improved clustering.
- Duplicate identity prevention.
- Scene boundary refinement.
- Accurate appearance start and end timestamps.
- Confidence scores.
- Identification of uncertain matches.
- Manual correction workflow.
- Automatic matching against saved People Library profiles.

Unknown persons must remain unknown until matched reliably or manually named.

Do not invent identities.

## 8. Replacement Studio — V3 Functionality

Implement a complete reference-based video reconstruction workflow.

### Reference Video Analysis

Analyze the input video to identify:

- Scene boundaries.
- Scene duration.
- Visible persons.
- Person appearance intervals.
- Activity type.
- Environment.
- Camera framing.
- Camera angle.
- Visual composition.
- Shot type.

### Footage Library

Allow users to import folders containing existing footage.

Automatically analyze and index footage using:

- Person identity.
- Face embeddings.
- Activity.
- Scene category.
- Camera framing.
- Duration.
- Resolution.
- Aspect ratio.
- Visual embeddings.

Save the footage index permanently so that unchanged media does not require repeated analysis.

### Intelligent Replacement

For every reference video scene, select suitable replacement footage using:

1. Person identity.
2. Activity similarity.
3. Visual similarity.
4. Camera framing similarity.
5. Scene duration compatibility.
6. Aspect ratio compatibility.

Use adjustable matching weights.

Avoid excessive clip repetition.

Support multiple people within a scene.

If a reliable replacement cannot be found, mark the scene for manual review instead of selecting unrelated footage.

### Replacement Review Interface

Provide:

- Original scene preview.
- Suggested replacement preview.
- Match confidence.
- Alternative replacement candidates.
- Approve/reject controls.
- Manual replacement selection.
- Trim controls.
- Replace all approved scenes.
- Missing footage report.
- Final timeline preview.

### Video Reconstruction

Generate a new video using approved replacement footage.

Preserve:

- Original timeline duration.
- Scene order.
- Scene boundaries.
- Selected audio track.
- Output aspect ratio.
- Output resolution.
- Frame rate.
- Audio/video synchronization.

Provide options to retain original audio, remove audio, or use a separate authorized audio file.

Use authorized footage and audio only.

## 9. Technology Requirements

Evaluate and reuse appropriate technologies:

- Clipivo upstream backend.
- SCRFD face detection.
- ArcFace face embeddings.
- ONNX Runtime.
- OpenCV.
- PySceneDetect.
- OpenCLIP or equivalent visual embedding model.
- FAISS or equivalent vector search.
- Optional lightweight vision-language model for semantic scene understanding.
- SQLite.
- FFmpeg.
- NVENC.
- PySide6.

Do not unnecessarily introduce large dependencies or expensive AI models.

Verify model licenses and document commercial-use restrictions. Provide a configurable model backend rather than assuming non-commercial models are licensed for production use.

## 10. GPU and CPU Performance

Support:

- NVIDIA CUDA where compatible.
- Windows DirectML.
- CPU processing.
- Automatic GPU detection.
- Automatic CPU fallback after runtime GPU errors.
- Configurable detection resolution.
- Configurable sampling interval.
- Batch inference where supported.
- Responsive background processing.
- Cancellation and safe shutdown.

Live preview must reuse existing inference results instead of running duplicate inference.

Show actual performance statistics:

- Active backend.
- Frames processed.
- Analysis FPS.
- Video processing speed.
- Elapsed time.
- Estimated remaining time.
- Progress percentage.
- Detected person count.
- GPU/CPU utilization where measurable.
- Memory usage.

## 11. Automatic Dependencies and Model Management

The application must work independently of the original Clipivo installation.

On first launch:

1. Automatically search for compatible existing AI models.
2. Reuse verified existing models.
3. Download missing models automatically after displaying applicable license terms.
4. Verify downloaded files using checksums where available.
5. Show download progress.
6. Support retry after failure.
7. Cache models permanently.

Do not hardcode Windows usernames or machine-specific paths.

Automatically locate FFmpeg or install the required trusted distribution when necessary.

## 12. Permanent Data Management

Save data outside the application installation directory using an appropriate Windows application-data location.

Persist:

- Projects.
- Analysis results.
- Person profiles.
- Reference images.
- Face embeddings.
- Footage library indexes.
- Replacement plans.
- User settings.
- Ignore regions.
- Recent projects.
- Batch queues.

Protect locally stored biometric reference data appropriately.

Application upgrades must not erase previous projects, models, preferences or saved people.

## 13. Packaging Requirements

The ZIP filename must be:

Clipivo_V2_3_Windows.zip

The outer folder inside the ZIP must remain exactly:

Clipivo_V2

Use a clean application structure:

```text
Clipivo_V2/
    START_V2.bat
    _internal/
        app.py, requirements.txt, assets and application modules
        docs/
        licenses/
        reports/
        tests/
        dev/
```

Historical executable preference is superseded: PC testing is source-only; do not build or package an executable.

Do not place numerous Python source files directly in the root folder.

Provide a runnable source package. Retain the old build script as inactive development material; do not execute it.

Do not bundle virtual environments, cache directories, unnecessary development artifacts or large redundant models in the ZIP.

Windows source launch must create/reuse its Python environment and installed dependencies only under `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3`. Do not create or reuse a source-local `.venv` or `venv`. If LocalAppData is unavailable, fail clearly instead of falling back to a relative path. Existing local virtual environments are ignored and are not automatically deleted. Replacing the application folder must not remove the AppData runtime.

## 14. Testing and Quality Assurance

Before delivery:

- Inspect all existing V2.2 source code.
- Verify upstream functionality.
- Run existing regression tests.
- Add tests for new features.
- Test person grouping.
- Test overlapping appearances.
- Test ignore and restore.
- Test static logo filtering.
- Test project persistence.
- Test missing model downloads.
- Test GPU failure and CPU fallback.
- Test footage indexing.
- Test replacement matching.
- Test duration-preserving reconstruction.
- Test output video validation.
- Test UI responsiveness.
- Verify upgrade compatibility.
- Verify the final ZIP structure.

Never claim successful testing that was not actually performed.

## 15. Execution Instructions

Implement the application, not just a development plan or UI mockup.

Preserve the working V2.2 baseline.

Use modular, maintainable architecture with shared backend services.

Complete as much of the approved scope as the available environment supports.

Do not silently omit requested features. Clearly identify implemented, tested, partially implemented and pending features.

Deliver the actual downloadable V2.3 ZIP, source code, build instructions, changelog and test report.

The final product should be a unified, professional video intelligence application combining person extraction, person timeline analysis, searchable footage management and intelligent video reconstruction.
## Clean, location-independent Windows PC-testing source layout

- `Clipivo_V2/` must contain exactly `START_V2.bat` and `_internal/`. Keep documentation in `_internal/docs/`, licenses in `_internal/licenses/`, reports in `_internal/reports/`, tests in `_internal/tests/`, and inactive development scripts in `_internal/dev/`.
- Default extraction is the Windows Downloads folder, but the launcher must run from any writable or read-only source location with spaces; all dependencies are installed only in `%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3\`. Ignore legacy source-local virtual environments; recreate the runtime in AppData from Python, never relocate or delete the legacy environment automatically.
- AppData stores pip cache, launcher temp files and export cache. Preserve verified upstream model/FFmpeg caches at `%LOCALAPPDATA%\Clipivo` and Studio models, Node, settings, projects and profiles at `%LOCALAPPDATA%\ClipivoV2`; retain existing legacy data read paths without moving/deleting user data. Existing external model files may be reused read-only. User-selected media/export paths remain user-controlled.
- Source replacement never requires clearing persistent AppData. EXE builds and GitHub Actions build workflows remain prohibited. Keep package documentation snapshots aligned with repository docs.

## Approved 2.3.1 follow-up

See PLAN_2_3_1.md for the approved simplification and automation plan, implementation checkpoint and outstanding acceptance. The prior V2.3 source is archived unchanged.
