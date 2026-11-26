"""Fetch only operator-authorized, SHA256-pinned ONNX files at startup."""
import hashlib
import os
from pathlib import Path
import re
import tempfile
import urllib.request
from urllib.parse import urlsplit

MODELS=(("det_10g.onnx","CLIPCUTTER_DETECTOR_SHA256"),("w600k_r50.onnx","CLIPCUTTER_RECOGNIZER_SHA256"))
MAX_BYTES=512*1024*1024
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def provision():
    if os.environ.get("CLIPCUTTER_MODEL_LICENSE_CONFIRMED")!="1":
        raise RuntimeError("Authorized model license confirmation required")
    root=Path(os.environ.get("CLIPCUTTER_MODEL_DIR","/models"))
    if not root.is_absolute() or root.resolve()!=root or not root.is_dir():
        raise RuntimeError("Unsafe or unavailable model directory")
    expected={name:os.environ.get(key,"") for name,key in MODELS}
    if any(not re.fullmatch(r"[0-9a-f]{64}",v) for v in expected.values()):
        raise RuntimeError("Both model SHA256 pins required")
    missing=[]
    for name,sha in expected.items():
        p=root/name
        if p.is_symlink():raise RuntimeError("Unsafe model path: "+name)
        if p.exists():
            if not p.is_file() or digest(p)!=sha:
                raise RuntimeError("Existing model invalid: "+name)
        else:missing.append(name)
    if not missing:return root
    base=os.environ.get("CLIPCUTTER_MODEL_BASE_URL","").rstrip("/")
    u=urlsplit(base)
    if u.scheme!="https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise RuntimeError("Approved HTTPS model base URL required")
    token=os.environ.get("CLIPCUTTER_MODEL_DOWNLOAD_TOKEN","")
    if "\r" in token or "\n" in token:raise RuntimeError("Invalid download credential")
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({}))
    for name in missing:
        temp=None
        try:
            headers={"Authorization":"Bearer "+token} if token else {}
            req=urllib.request.Request(base+"/"+name,headers=headers)
            with opener.open(req,timeout=30) as response:
                length=response.headers.get("Content-Length")
                if length is not None and not 0<int(length)<=MAX_BYTES:
                    raise ValueError("Invalid model size")
                h=hashlib.sha256();count=0
                with tempfile.NamedTemporaryFile(prefix=".model-",dir=root,delete=False) as f:
                    temp=Path(f.name)
                    while True:
                        chunk=response.read(1024*1024)
                        if not chunk:break
                        count+=len(chunk)
                        if count>MAX_BYTES:raise ValueError("Model size limit exceeded")
                        h.update(chunk);f.write(chunk)
                    f.flush();os.fsync(f.fileno())
                if not count or (length is not None and count!=int(length)) or h.hexdigest()!=expected[name]:
                    raise ValueError("Model digest or length mismatch")
            # Atomic no-overwrite publication; an existing file never gets replaced.
            os.link(temp,root/name)
        except Exception:
            # No URL, token or HTTP exception text in logs.
            raise RuntimeError("Model provisioning failed: "+name) from None
        finally:
            if temp is not None:temp.unlink(missing_ok=True)
    return root
