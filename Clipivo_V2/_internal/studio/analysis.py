"""Conservative matching; unknown groups remain anonymous until reviewed."""
from pathlib import Path
import numpy as np
import sqlite3
from v22.engine import unit
from v22.analyzer import analyze, save_project, refresh

def match_profiles(data,profiles,threshold=.60,margin=.08):
    for g in data['people']:
        if g.get('identity_status')=='manual': continue
        previous=g.get('identity_status','unknown')
        for key in ('library_id','match_score','match_candidate'):
            g.pop(key,None)
        if previous=='matched':
            g['name']='Person (review)'
        g['identity_status']='uncertain' if previous=='uncertain' else 'unknown'
        if g.get('ignored') or g.get('filtered') or previous=='uncertain': continue
        embs=[o.get('embedding') for o in g['observations'] if o.get('embedding') is not None]
        if not embs: continue
        try: center=unit(np.mean([unit(e) for e in embs],axis=0))
        except (ValueError,TypeError): continue
        scores=[]
        for p in profiles:
            compatible=[]
            for e in p.get('embeddings',[]):
                try:
                    if len(e)==len(center): compatible.append(unit(e))
                except (ValueError,TypeError): continue
            if compatible:
                try:
                    profile_center=unit(np.mean(compatible,axis=0))
                    if all(float(np.dot(e,profile_center))>=threshold for e in compatible):
                        scores.append((float(np.dot(center,profile_center)),p))
                except ValueError: continue
        scores.sort(key=lambda x:-x[0])
        if not scores: continue
        score,p=scores[0];runner=scores[1][0] if len(scores)>1 else -1
        g['match_score']=round(score,4)
        # A group with contradictory observations cannot be confidently named.
        consistent=all(float(np.dot(unit(e),center))>=threshold for e in embs)
        if score>=threshold and score-runner>=margin and consistent:
            g['match_candidate']=p['id']
            g['identity_status']='candidate'
        elif score>=threshold-margin:g['identity_status']='uncertain'
    # Two groups with the same candidate and overlapping appearances are
    # ambiguous. Do not label either automatically.
    for g in data['people']:
        if g.get('identity_status')!='candidate': continue
        pid=g['match_candidate']
        others=[h for h in data['people'] if h is not g and h.get('match_candidate')==pid]
        conflict=any(a<d and c<b for h in others for a,b in g.get('segments',[]) for c,d in h.get('segments',[]))
        if conflict:
            g['identity_status']='uncertain'
        else:
            g['name']=next(p['name'] for p in profiles if p['id']==pid)
            g['library_id']=pid;g['identity_status']='matched'
    for g in data['people']:g.pop('match_candidate',None)
    return data

def run(video,folder,models,cfg,progress,cancel,live,profiles,engine=None):
    from .analysis_library import source_stamp, scan_key, AnalysisLibrary
    if cancel():raise InterruptedError('Cancelled; no completed project saved')
    stamp=source_stamp(video); scan=scan_key(cfg)
    data=analyze(video,folder,models,cfg.get('gpu',True),cfg.get('step',.5),cfg.get('threshold',.45),cfg.get('size',640),progress,cancel,live,cfg.get('filters',{}),engine=engine,persist=False)
    if cancel():raise InterruptedError('Cancelled; no completed project saved')
    refresh(data)
    match_profiles(data,profiles);data['studio_version']='2.3.1'
    if cfg.get('model_signature'):data['model_signature']=cfg['model_signature']
    if cfg.get('profile_warnings'):data['profile_warnings']=cfg['profile_warnings']
    if cancel():raise InterruptedError('Cancelled; no completed project saved')
    if source_stamp(video)!=stamp or scan_key(cfg)!=scan:
        raise ValueError('Source or model configuration changed during analysis; run again.')
    data['source_stamp']=stamp;data['scan_key']=scan
    save_project(folder,data)
    from .storage import root
    try:
        if Path(folder).resolve().is_relative_to((root()/'Projects').resolve()):
            if not AnalysisLibrary().register(Path(folder)/'analysis.json',data):
                data['cache_warning']='Analysis saved; source changed before cache registration.'
    except (OSError, sqlite3.Error, ValueError) as exc:
        data['cache_warning']='Analysis saved; automatic lookup unavailable: '+str(exc)
    return data

def open_project(path):
    import json
    path=Path(path); data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=2 or not isinstance(data.get('people'),list):raise ValueError('Not a supported V2/V2.2 project')
    if data.get('sample_interval',0)<=0 or data.get('duration',0)<0:raise ValueError('Invalid project timing')
    for g in data['people']:
        for o in g['observations']:
            if not (path.parent/o['image']).resolve().is_relative_to(path.parent.resolve()):raise ValueError('Unsafe reference path')
    refresh(data);return data
