# Step 4 source worker candidate

Reference: desktop Clipivo core at 4c1c7a8c282bc6fc1adf2cbf4713ca607399becb, original MIT notice in vendor/LICENSE. The scan/refinement, recognition, framing, FFmpeg export and validation modules are reused. Linux download/tool resolution and per-job duration settings are adapted; no desktop runtime dependency. No model weights are bundled or downloaded. Only operator-provisioned, authorized compatible SCRFD/ArcFace weights; do not use non-commercial-only weights for commercial work.

Run from ClipCutterWeb in a separate Linux worker venv with worker/requirements-cpu.txt and system ffmpeg/ffprobe. Set CLIPCUTTER_MODEL_DIR and CLIPCUTTER_MODEL_LICENSE_CONFIRMED=1 for face scans after verifying licensing. CPU is the baseline; Step 6 owns CUDA image and GPU acceptance.

A trusted future dispatcher provides an exclusive job directory with source.video, SHA-256 digests, reference-01.img ... reference-12.img (authorized reference photos only), and scan.json or review.json. See contracts.py for exact schemas. Run:
```
python -m worker.extractor.runner scan /absolute/staged-job
python -m worker.extractor.runner export /absolute/staged-job
```
Scan yields scan-result.json with suggested ranges for review or no_match. Export requires explicit reviewed ranges; manual A/B cuts can skip scan. It produces a completion manifest only after each output validates and hashes; incomplete outputs are not published. Fresh exclusive job directory required for each export attempt. Strict duration limits are optional, separate whole-picture accurate output only. Limits reject invalid combinations and verify actual durations. Source never moved/deleted. Cancellation is cooperative, not guaranteed to interrupt every native call instantly. Worker stderr/stdout is not yet exposed in UI.

No real processing test has run in this connector editing session. FFmpeg, models, installed pins, scan quality, export parity, cancellation and licensing still need runtime acceptance. Queue/Drive transport, upload/download, web review player, output delivery and worker lifecycle remain future work; no Docker image, VPS or Salad changes.

Before enabling untrusted media intake, the dispatcher must sandbox each job (exclusive read-only staged source, restricted writable output, no secrets or unrelated files, network disabled for media decoding, CPU/memory/disk/time limits). Current runner assumes trusted local staging; it is not a production admission boundary. The web service imports only lightweight Pydantic contracts, never PyAV/ONNX/FFmpeg processing. Run full web source regression with deploy/test-source.sh and manual synthetic export smoke with CLIPCUTTER_RUN_MEDIA_TESTS=1 python -m unittest discover -s tests -p test_extractor_media.py -v in the separate worker environment.
