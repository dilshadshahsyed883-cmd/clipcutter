from pathlib import Path
from core.downloads import FACE_MODEL_FILES,_is_verified
from .storage import root
from v22.analyzer import atomic_json
import json

def verified(folder):
    if not folder:return False
    p=root()/'verified-studio-models.json'
    try:cache=json.loads(p.read_text())
    except (OSError,ValueError):cache={}
    result=all(_is_verified(Path(folder)/item.name,item,cache) for item in FACE_MODEL_FILES)
    if result:atomic_json(p,cache)
    return result

def resolve_models(cfg, progress, cancel):
    """Select default verified weights read-only, or an explicit custom pair."""
    from v22.model_locator import model_candidates, valid, download_models
    from core.downloads import find_face_models
    from hashlib import sha256
    if cancel():raise InterruptedError('Cancelled')
    saved=cfg.get('models')
    if cfg.get('custom_models'):
        if not valid(saved):
            raise ValueError('Select a custom model folder containing both ONNX files.')
        folder=Path(saved)
        digest=sha256()
        for item in FACE_MODEL_FILES:
            digest.update(item.name.encode()+b'\\0')
            digest.update(str((folder/item.name).stat().st_size).encode()+b'\\0')
            with (folder/item.name).open('rb') as f:
                for chunk in iter(lambda:f.read(1048576),b''):
                    if cancel(): raise InterruptedError('Cancelled')
                    digest.update(chunk)
        return folder,'custom:'+digest.hexdigest()
    if cancel(): raise InterruptedError('Cancelled')
    for folder in model_candidates(saved):
        if cancel(): raise InterruptedError('Cancelled')
        if verified(folder): return folder,'buffalo_l:'+FACE_MODEL_FILES[1].sha256
    found=find_face_models()
    if found and verified(found): return found,'buffalo_l:'+FACE_MODEL_FILES[1].sha256
    # Never repair or overwrite an installed application's models.
    folder=root()/'models/buffalo_l'
    download_models(folder,progress,cancel)
    if not verified(folder): raise RuntimeError('Default model checksum verification failed')
    return folder,'buffalo_l:'+FACE_MODEL_FILES[1].sha256
