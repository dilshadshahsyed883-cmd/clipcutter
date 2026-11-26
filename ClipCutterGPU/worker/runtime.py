"""GPU runtime verification, entirely offline model startup."""
import logging
import os
import subprocess
from pathlib import Path
from .model_pins import verify_models

def require_models(cancel=None):
    root=Path("/models")
    if os.environ.get("CLIPCUTTER_MODEL_DIR","/models") != "/models":
        raise RuntimeError("Worker requires packaged model directory /models")
    return verify_models(root,cancel)

def warmup():
    import numpy as np
    import onnxruntime as ort
    root=require_models()
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("CUDA execution provider unavailable")
    for name,size in (("det_10g.onnx",640),("w600k_r50.onnx",112)):
        session=ort.InferenceSession(str(root/name),providers=["CUDAExecutionProvider","CPUExecutionProvider"])
        if session.get_providers()[0]!="CUDAExecutionProvider":
            raise RuntimeError("CUDA initialization failed: "+name)
        session.disable_fallback()
        outputs=session.run(None,{session.get_inputs()[0].name:np.zeros((1,3,size,size),np.float32)})
        if not outputs or not all(np.isfinite(x).all() for x in outputs):
            raise RuntimeError("Invalid model warmup: "+name)
    for tool in ("ffmpeg","ffprobe"):
        subprocess.run([tool,"-version"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    return verify_encoders(os.environ.get("CLIPCUTTER_VIDEO_ENCODER","auto"))


def probe_nvenc(encoder):
    """Exercise real encoding with a supported HD frame size, not just encoder listing."""
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", "color=size=1280x720:rate=25",
               "-frames:v", "25", "-c:v", encoder, "-f", "null", "-"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.getLogger(__name__).warning("NVENC %s probe failed: %s", encoder, exc)
        return False
    if result.returncode != 0:
        logging.getLogger(__name__).warning(
            "NVENC %s probe failed (exit %s): %s", encoder,
            result.returncode, result.stderr.strip() or "(no stderr)")
        return False
    return True


def verify_encoders(mode):
    if mode not in {"auto", "cpu", "nvenc"}:
        raise RuntimeError("Invalid encoder policy")
    hevc = probe_nvenc("hevc_nvenc")
    h264 = probe_nvenc("h264_nvenc")
    # The actual extractor uses HEVC. Preserve the existing aggregate health
    # field and strict policy semantics; H264 is an independent diagnostic.
    if mode == "nvenc" and not hevc:
        raise RuntimeError("NVENC smoke test failed (hevc_nvenc)")
    return {"provider": "CUDAExecutionProvider", "nvenc_test_passed": hevc,
            "hevc_nvenc_test_passed": hevc, "h264_nvenc_test_passed": h264,
            "encoder_policy": mode}
