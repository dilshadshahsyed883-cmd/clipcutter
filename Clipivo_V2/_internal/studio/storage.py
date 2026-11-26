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
    """Cache encrypted embeddings, tied to model and reference fingerprints."""
    def __init__(self,store): self.store=store
    def path(self,id):
        folder=root()/'profile_embeddings';folder.mkdir(exist_ok=True);return folder/(id+'.enc')
    def _read(self,id):
        try:
            return json.loads(self.store._decrypt(self.path(id).read_bytes()))
        except FileNotFoundError: return {}
    def _write(self,id,payload):
        target=self.path(id);tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            tmp.write_bytes(self.store._encrypt(json.dumps(payload).encode()))
            os.replace(tmp,target)
        finally:tmp.unlink(missing_ok=True)
    def save(self,group,folder,model_signature=None):
        if self.store is None: raise RuntimeError('People Library is locked; configure the system credential store.')
        from hashlib import sha256
        # Validate all references before changing the encrypted library.
        paths=[]
        for rel in group['references']:
            p=(Path(folder)/rel).resolve()
            if not p.is_relative_to(Path(folder).resolve()): raise ValueError('Reference path escapes project')
            paths.append((p,p.read_bytes()))
        if group.get('ignored') or group.get('filtered'):raise ValueError('Restore this person before saving a reusable profile.')
        if not paths:raise ValueError('No reference images to save.')
        if group.get('identity_status','manual') not in ('manual','matched'):
            raise ValueError('Rename or confirm this person before saving a reusable identity.')
        linked=group.get('library_id')
        existing=self.store.character(linked) if linked else None
        if existing and existing.scope!='persistent':raise ValueError('Not a reusable profile')
        # Never silently join different people because their names happen to match.
        if not existing and any(c.name.casefold()==group['name'].casefold() for c in self.store.characters()):
            raise ValueError('A profile with this name exists. Use a distinct name or the matched profile.')
        person=existing or self.store.create_character(group['name'])
        before=self.store.fingerprint(person.id)
        old=self._read(person.id) if model_signature and existing else {}
        known={r.digest for r in self.store.references(person.id)}
        for p,blob in paths:
            digest=sha256(blob).hexdigest()
            if digest not in known:
                self.store.add_reference(person.id,p.name,blob);known.add(digest)
        # Existing reference-only/unknown-model data is rebuilt on the next analysis.
        # Never relabel older vectors as belonging to the current model.
        if model_signature:
            chosen=set(group['references'])
            obs=sorted((o for o in group['observations'] if o.get('image') in chosen),key=lambda x:-x['quality'])[:30]
            embeddings=[o['embedding'] for o in obs if o.get('embedding') is not None]
            if not embeddings:return person.id
            previous=old.get('embeddings',[]) if old.get('model_signature')==model_signature else []
            if existing and previous and old.get('fingerprint')==before:
                embeddings=previous+embeddings
            elif existing:
                # Missing vectors for existing references: let entries() rebuild all.
                return person.id
            embeddings=list({tuple(e):e for e in embeddings}.values())
            self._write(person.id,{'id':person.id,'embeddings':embeddings[-60:],
                'model_signature':model_signature,'fingerprint':self.store.fingerprint(person.id)})
        elif not existing:
            # Backward-compatible cache for callers without model provenance; never
            # used by the studio's provenance-aware matcher.
            obs=sorted(group['observations'],key=lambda x:-x['quality'])[:30]
            self._write(person.id,{'id':person.id,'embeddings':[o['embedding'] for o in obs]})
        return person.id
    def entries(self,model_signature=None,engine=None,cancel=lambda:False):
        if self.store is None:return []
        result=[]
        for c in self.store.characters():
            if cancel():raise InterruptedError('Cancelled')
            old=self._read(c.id)
            fingerprint=self.store.fingerprint(c.id)
            if model_signature is None:
                # Compatibility for existing callers; analysis always supplies provenance.
                if old.get('embeddings'):
                    result.append(dict(old,name=c.name))
                continue
            if old.get('model_signature')==model_signature and old.get('fingerprint')==fingerprint:
                if old.get('embeddings'):result.append(dict(old,name=c.name))
                continue
            if engine is None:continue
            import cv2,numpy as np
            embeddings=[]
            for _,blob in self.store.iter_reference_bytes(c.id):
                if cancel():raise InterruptedError('Cancelled')
                img=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_COLOR)
                if img is None:continue
                faces=engine.get(img)
                # Multiple faces in an old reference cannot establish identity.
                if len(faces)==1:embeddings.append(faces[0][0].tolist())
            if cancel():raise InterruptedError('Cancelled')
            if not embeddings:continue
            payload={'id':c.id,'embeddings':embeddings,'model_signature':model_signature,'fingerprint':fingerprint}
            # References may have been edited in the People Library during analysis.
            # Do not publish a stale fingerprint or reuse an obsolete identity.
            if self.store.fingerprint(c.id)!=fingerprint:continue
            self._write(c.id,payload);result.append(dict(payload,name=c.name))
        return result
