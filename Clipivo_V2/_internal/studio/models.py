from pathlib import Path
from core.downloads import FACE_MODEL_FILES,_is_verified
from .storage import root
import json

def verified(folder):
    if not folder:return False
    p=root()/'verified-studio-models.json'
    try:cache=json.loads(p.read_text())
    except (OSError,ValueError):cache={}
    result=all(_is_verified(Path(folder)/item.name,item,cache) for item in FACE_MODEL_FILES)
    if result:p.write_text(json.dumps(cache),encoding='utf-8')
    return result
