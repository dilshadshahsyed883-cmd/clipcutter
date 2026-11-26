from pathlib import Path
import os, json, uuid
from v22.analyzer import atomic_json

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

def remember(path):
    cfg=load_settings(); recent=[str(path)]+[p for p in cfg.get('recent',[]) if p!=str(path)]
    save_settings({'recent':recent[:20]})

def new_project():
    return root()/'Projects'/uuid.uuid4().hex

class Profiles:
    """Embeddings use the same AES-GCM key as upstream encrypted reference images."""
    def __init__(self,store): self.store=store
    def path(self,id):
        folder=root()/'profile_embeddings';folder.mkdir(exist_ok=True);return folder/(id+'.enc')
    def save(self,group,folder):
        if self.store is None: raise RuntimeError('People Library is locked; configure the system credential store.')
        existing=next((c for c in self.store.characters() if c.name.casefold()==group['name'].casefold()),None)
        person=existing or self.store.create_character(group['name'])
        obs=sorted(group['observations'],key=lambda x:-x['quality'])[:30]
        for rel in group['references']:
            p=(Path(folder)/rel).resolve()
            if not p.is_relative_to(Path(folder).resolve()): raise ValueError('Reference path escapes project')
            self.store.add_reference_file(person.id,p)
        payload={'id':person.id,'embeddings':[o['embedding'] for o in obs]}
        self.path(person.id).write_bytes(self.store._encrypt(json.dumps(payload).encode()))
        return person.id
    def entries(self):
        if self.store is None:return []
        result=[]
        for c in self.store.characters():
            try:
                data=json.loads(self.store._decrypt(self.path(c.id).read_bytes()));data['name']=c.name;result.append(data)
            except FileNotFoundError: continue
        return result
