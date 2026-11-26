"""Exact existing PC model pins; verify local files only."""
import hashlib
from pathlib import Path
MODELS = {
    "det_10g.onnx": (16923827, "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91"),
    "w600k_r50.onnx": (174383860, "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43"),
}

def verify_models(root, cancel=None):
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root or not root.is_dir():
        raise RuntimeError("Unsafe or missing model directory")
    for name, (size, expected) in MODELS.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise RuntimeError("Missing or invalid packaged model: " + name)
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024*1024), b""):
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("Cancelled")
                digest.update(block)
        if digest.hexdigest() != expected:
            raise RuntimeError("Packaged model digest mismatch: " + name)
    return root

if __name__ == "__main__":
    import sys
    verify_models(Path(sys.argv[1]))
    print("PACKAGED_MODELS=VERIFIED")
