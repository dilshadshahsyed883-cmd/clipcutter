from pathlib import Path
import os, json, uuid
def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def root():
    override=os.environ.get('CLIPIVO_STUDIO_DATA')
    if override: p=Path(override)
    elif os.name=='nt': p=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'ClipivoV2'
    else: p=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'ClipivoV2'
    p.mkdir(parents=True,exist_ok=True)
    try: p.chmod(0o700)
    except OSError: pass
    return p

def load_settings():
    try: return json.loads((root()/'settings.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

def save_settings(updates):
    data=load_settings(); data.update(updates);atomic_json(root()/'settings.json',data)

