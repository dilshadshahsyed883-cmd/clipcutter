"""Linux worker adaptation: use operator-provisioned binaries and licensed models only."""
from pathlib import Path
import os
import shutil

def tool_path(name: str) -> str:
    if name not in {"ffmpeg", "ffprobe"}:
        raise RuntimeError("Unsupported worker executable")
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is not installed")
    return path

def find_face_models() -> Path | None:
    raw = os.environ.get("CLIPCUTTER_MODEL_DIR")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir():
        return None
    return path if all((path / n).is_file() for n in ("det_10g.onnx", "w600k_r50.onnx")) else None

def preload_gpu_libraries():
    # GPU runtime and compatible CUDA libraries provisioned in Step 6.
    return None
