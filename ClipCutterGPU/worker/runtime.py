"""GPU runtime verification, entirely offline model startup."""
import os
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
    import subprocess
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
    # CPU encoding is permitted on GPU nodes if NVENC is not present; report it, do not claim GPU encoding.
    check=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","lavfi","-i","color=size=128x128:rate=25","-frames:v","1","-c:v","hevc_nvenc","-f","null","-"],capture_output=True,timeout=25)
    mode=os.environ.get("CLIPCUTTER_VIDEO_ENCODER","auto")
    if mode not in {"auto","cpu","nvenc"}: raise RuntimeError("Invalid encoder policy")
    if mode=="nvenc" and check.returncode!=0: raise RuntimeError("NVENC smoke test failed")
    return {"provider":"CUDAExecutionProvider","nvenc_test_passed":check.returncode==0,"encoder_policy":mode}
