"""GPU runtime verification; no network or automatic model downloads."""
import hashlib
import os
from pathlib import Path
import re
from threading import Event

def require_models(cancel=None):
    if os.environ.get("CLIPCUTTER_MODEL_LICENSE_CONFIRMED")!="1":
        raise RuntimeError("Operator must confirm authorized model weights")
    root=Path(os.environ.get("CLIPCUTTER_MODEL_DIR","/models"))
    if not root.is_absolute() or root.resolve()!=root or not root.is_dir():
        raise RuntimeError("Model directory unavailable or unsafe")
    for name,key in (("det_10g.onnx","CLIPCUTTER_DETECTOR_SHA256"),("w600k_r50.onnx","CLIPCUTTER_RECOGNIZER_SHA256")):
        expected=os.environ.get(key,"")
        p=root/name
        if not re.fullmatch(r"[0-9a-f]{64}",expected) or p.is_symlink() or not p.is_file():
            raise RuntimeError("Missing model or pinned digest: "+name)
        digest=hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):
                if cancel is not None and cancel.is_set(): raise InterruptedError("Cancelled")
                digest.update(chunk)
        if digest.hexdigest()!=expected: raise RuntimeError("Model digest mismatch: "+name)
    return root

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
