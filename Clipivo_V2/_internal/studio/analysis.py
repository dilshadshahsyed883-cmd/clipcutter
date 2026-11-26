"""V2.2 single-pass analyzer with stable correction IDs and reliable library matching."""
from pathlib import Path
import numpy as np
from v22.engine import unit
from v22.analyzer import analyze, save_project, refresh
from .storage import Profiles

def match_profiles(data,profiles,threshold=.60,margin=.08):
    # A label is only attached after both absolute and runner-up margin checks.
    for g in data['people']:
        embs=[o['embedding'] for o in g['observations']]
        if not embs: continue
        center=unit(np.mean(embs,axis=0)); scores=[]
        for p in profiles:
            compatible=[e for e in p['embeddings'] if len(e)==len(center)]
            if compatible: scores.append((float(np.dot(center,unit(np.mean(compatible,axis=0)))),p))
        scores.sort(key=lambda x:-x[0]);g['identity_status']='unknown'
        if not scores: continue
        score,p=scores[0];runner=scores[1][0] if len(scores)>1 else -1
        g['match_score']=round(score,4)
        if score>=threshold and score-runner>=margin:
            g['name']=p['name'];g['library_id']=p['id'];g['identity_status']='matched'
        elif score>=threshold-margin:g['identity_status']='uncertain'
    return data

def run(video,folder,models,cfg,progress,cancel,live,profiles):
    data=analyze(video,folder,models,cfg.get('gpu',True),cfg.get('step',.5),cfg.get('threshold',.45),cfg.get('size',640),progress,cancel,live,cfg.get('filters',{}))
    match_profiles(data,profiles);data['studio_version']='2.3';save_project(folder,data);return data

def open_project(path):
    import json
    path=Path(path); data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=2 or not isinstance(data.get('people'),list):raise ValueError('Not a supported V2/V2.2 project')
    if data.get('sample_interval',0)<=0 or data.get('duration',0)<0:raise ValueError('Invalid project timing')
    for g in data['people']:
        for o in g['observations']:
            if not (path.parent/o['image']).resolve().is_relative_to(path.parent.resolve()):raise ValueError('Unsafe reference path')
    refresh(data);return data
