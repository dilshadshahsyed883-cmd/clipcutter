"""Find existing models without touching the upstream installation."""
import os
from pathlib import Path
NAMES=('det_10g.onnx','w600k_r50.onnx')
def valid(folder):
    if not folder: return False
    p=Path(folder)
    return all((p/n).is_file() and (p/n).stat().st_size>0 for n in NAMES)
def model_candidates(saved=None, *, home=None, local=None, roaming=None):
    home=Path(home or Path.home())
    local=Path(local or os.environ.get('LOCALAPPDATA',home/'AppData/Local'))
    roaming=Path(roaming or os.environ.get('APPDATA',home/'AppData/Roaming'))
    install=local/'Programs/Clipivo'
    candidates=[saved,local/'Clipivo/models/buffalo_l',install/'models/buffalo_l',install/'_internal/models/buffalo_l',home/'.insightface/models/buffalo_l',local/'ClipivoV2/models/buffalo_l',local/'long-weekend-labs/models/buffalo_l',roaming/'Clipivo/models/buffalo_l']
    seen=set()
    for p in candidates:
        if valid(p) and Path(p) not in seen:
            seen.add(Path(p)); yield Path(p)
    for base in (local/'Clipivo',install,roaming/'Clipivo'):
        if base.is_dir():
            try:
                for p in base.rglob(NAMES[0]):
                    if valid(p.parent) and p.parent not in seen:
                        seen.add(p.parent); yield p.parent
            except OSError: pass
def find_models(saved=None, **kwargs):
    return next(model_candidates(saved,**kwargs),None)

MODEL_FILES={
 'det_10g.onnx':(16923827,'5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91'),
 'w600k_r50.onnx':(174383860,'4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43')}
def download_models(folder, progress=lambda *a:None, cancel=lambda:False):
    import hashlib,urllib.request
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    for name,(size,digest) in MODEL_FILES.items():
        if cancel(): raise InterruptedError('Model download cancelled')
        target=folder/name; tmp=folder/(name+'.part')
        if target.exists() and target.stat().st_size==size:
            with target.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()==digest: continue
        try:
            request=urllib.request.Request('https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/'+name,headers={'User-Agent':'ClipivoV2.2'})
            h=hashlib.sha256(); n=0
            with urllib.request.urlopen(request,timeout=30) as r,tmp.open('wb') as f:
                while True:
                    if cancel(): raise InterruptedError('Model download cancelled')
                    chunk=r.read(1024*256)
                    if not chunk:break
                    n+=len(chunk)
                    if n>size:raise RuntimeError('Model download exceeded expected size')
                    h.update(chunk);f.write(chunk);progress(name,n,size)
            if n!=size or h.hexdigest()!=digest:raise RuntimeError('Model verification failed: '+name)
            if cancel(): raise InterruptedError('Model download cancelled')
            os.replace(tmp,target)
        finally:tmp.unlink(missing_ok=True)
    return folder
