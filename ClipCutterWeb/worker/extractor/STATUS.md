# Step 4 checkpoint

Original scan/export core ported into a headless worker with scan/review/export contract. Authenticated web settings validation and browser-local preview are now provided. No media transfer or server job admission. No real runtime tests executed yet; GitHub DNS not available in local container, PyAV and ONNX Runtime not installed locally. Run existing web source tests plus worker tests in a separate worker environment. Validate actual synthetic and authorized reference video with FFmpeg and licensed models before approving parity. No GPU image or deploy in this step.
