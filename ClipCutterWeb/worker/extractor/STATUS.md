# Step 4 checkpoint

Headless original scan, face matching, framing and FFmpeg export core adapted into an independent worker. Separate scan and reviewed export commands, input/output digest checks, optional strict duration limits, local browser preview and authenticated web options validation. No dispatch, file intake or production processing yet.

## Verification

- Exact GitHub blob 47140bf341d369deadd5172b4944b7e59bfbafd4 (limits.py) reproduced locally, git hash-object matched. 4,732 partition cases passed across seven min/max combinations; all bounds and maximal retained duration verified.
- Exact GitHub blob d5c9d7f3b15fb5d52532403dd82c6104b3cde68d (contracts.py) reproduced locally, git hash-object matched. Twelve validation cases passed (valid requests, invalid ranges, invalid limits and extra/nonfinite fields).
- Full web regression suite, FFmpeg export integration, model-based scan, browser review and GPU not run. Local DNS cannot resolve github.com; PyAV and ONNX Runtime absent. Tests added in tests/test_extractor_contracts.py and opt-in worker smoke test.
- Source review only: deployment/GPU, existing desktop and Concat remain unchanged. Do not merge until source regressions and worker acceptance pass. Runtime acceptance must use authorized reference media and licensed weights.
