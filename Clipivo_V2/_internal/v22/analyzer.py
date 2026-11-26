import json, csv, uuid, time, os
from pathlib import Path
import cv2
import numpy as np
from .engine import Engine,unit
from .filters import filter_observations, diverse_refs

def atomic_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8'); os.replace(tmp,path)

def intervals(samples,duration,step):
    # Each positive sample represents its surrounding sampling cell, not an exact boundary.
    out=[]
    for t in sorted(set(samples)):
        a=max(0,t-step/2); b=min(duration,t+step/2)
        if b<=a: continue
        if out and a<=out[-1][1]+.005: out[-1][1]=max(out[-1][1],b)
        else: out.append([a,b])
    return [[round(a,3),round(b,3)] for a,b in out]

def assign(groups,embedding,used,threshold):
    candidates=[(float(np.dot(unit(g['_sum']),embedding)),i) for i,g in enumerate(groups) if i not in used]
    candidates.sort(key=lambda pair:(-pair[0],pair[1]))
    score,i=candidates[0] if candidates else (-1,-1)
    runner=candidates[1][0] if len(candidates)>1 else -1
    if score>=threshold and score-runner>=.08: return i
    groups.append({'id':uuid.uuid4().hex[:12],'name':f'Person {len(groups)+1}','_sum':np.zeros_like(embedding),'observations':[],'references':[],'ignored':False,'identity_status':'uncertain' if score>=threshold-.08 else 'unknown'}); return len(groups)-1

def analyze(video,folder,models,gpu,step,threshold,size,progress,cancel,live=None,filters=None,engine=None,persist=True):
    if step<=0 or not 0<threshold<1: raise ValueError('Invalid analysis settings')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False); refs=folder/'references'; refs.mkdir()
    started=time.perf_counter(); engine=engine or Engine(models,gpu,size); cap=cv2.VideoCapture(str(video)); groups=[]; frames=0; last=-1.; next_t=0.; observed=0; last_live=0
    try:
        if not cap.isOpened(): raise RuntimeError('Cannot decode video')
        fps=cap.get(cv2.CAP_PROP_FPS); count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps<=0: raise RuntimeError('Invalid video frame rate')
        duration=count/fps if count>0 else 0
        while not cancel():
            ok=cap.grab()
            if not ok: break
            timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000; nominal=frames/fps; frames+=1
            t=timestamp if timestamp>=0 and timestamp>last else max(nominal,last+1/fps)
            last=t
            if t+1e-6<next_t: continue
            while next_t<=t+1e-6: next_t+=step
            ok,img=cap.retrieve()
            if not ok: raise RuntimeError('Frame decode failed')
            observed+=1; used=set()
            boxes=[]; h,w=img.shape[:2]
            for e,crop,q,box,confidence in engine.get(img):
                i=assign(groups,e,used,threshold); used.add(i); g=groups[i]; g['_sum']+=e
                refdir=refs/g['id']; refdir.mkdir(exist_ok=True)
                # Keep each sampled face so groups can be corrected after analysis.
                path=refdir/f'{observed:07d}.jpg'; ok,data=cv2.imencode('.jpg',crop)
                if not ok: raise RuntimeError('Could not encode reference crop')
                path.write_bytes(data.tobytes()); rel=path.relative_to(folder).as_posix()
                x,y,X,Y=box; sig=cv2.resize(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(8,8)).ravel().tolist()
                g['observations'].append({'time':round(t,3),'image':rel,'quality':q,'embedding':e.tolist(),'box_norm':[x/w,y/h,X/w,Y/h],'face_size':min(X-x,Y-y),'confidence':confidence,'signature':sig})
                boxes.append((g['id'],g['name'],[x/w,y/h,X/w,Y/h]))
            if live and time.monotonic()-last_live>=.25:
                last_live=time.monotonic()
                view={'duration':max(duration,t+step),'sample_interval':step,'filters':filters or {},'people':[dict(id=g['id'],name=g['name'],ignored=False,observations=g['observations']) for g in groups]}
                refresh(view)
                summary=[{k:g[k] for k in ('id','name','ignored','segments','references','filter_reasons','filtered','raw_segments')} for g in view['people']]
                small=cv2.resize(img,(min(w,960),max(1,round(h*min(w,960)/w))))
                live(t,small,boxes,summary,view['duration'],folder)
            progress(t,duration,engine.device,len(groups),engine.warning,frames,observed)
        if cancel(): raise InterruptedError('Cancelled; no completed project saved')
        if frames==0: raise RuntimeError('No decoded frames')
        if duration and frames+1<count: raise RuntimeError('Video ended before reported frame count; analysis incomplete')
        duration=max(last+1/fps, duration)
        data={'decoded_frames':frames,'analyzed_frames':observed,'version':2,'source':str(Path(video).resolve()),'duration':round(duration,3),'sample_interval':step,'threshold':threshold,'detector_size':size,'device':engine.device,'warning':engine.warning,'elapsed_seconds':round(time.perf_counter()-started,2),'people':groups,'filters':filters or {}}
        for g in groups: g.pop('_sum')
        if persist: save_project(folder,data)
        return data
    finally: cap.release()

def refresh(data):
    for g in data['people']:
        active,reasons=filter_observations(g,data,intervals)
        g['raw_segments']=intervals([o['time'] for o in g['observations']],data['duration'],data['sample_interval'])
        g['segments']=intervals([o['time'] for o in active],data['duration'],data['sample_interval'])
        g['filter_reasons']=reasons; g['filtered']=not bool(active) and bool(g['observations'])
        g['references']=diverse_refs(active or g['observations'])

def save_project(folder,data):
    refresh(data); folder=Path(folder); atomic_json(folder/'analysis.json',data)
    with (folder/'timeline.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['person_id','person','start_seconds','end_seconds'])
        for g in data['people']:
            if not g.get('ignored'):
                for a,b in g['segments']: w.writerow([g['id'],g['name'],a,b])
    rows=sorted((a,b,g['name']) for g in data['people'] if not g.get('ignored') for a,b in g['segments'])
    (folder/'timeline.txt').write_text('\n'.join(f'{a:.3f} - {b:.3f} | {n}' for a,b,n in rows),encoding='utf-8')

def merge_groups(data, ids):
    gs=[g for g in data['people'] if g['id'] in ids]
    if len(gs)<2: raise ValueError('Select at least two groups')
    for g in gs[1:]: gs[0]['observations'].extend(g['observations'])
    gs[0]['observations'].sort(key=lambda o:o['time'])
    clear_identity(gs[0])
    gs[0]['name']='Merged person (review)'
    removed={g['id'] for g in gs[1:]}
    data['people']=[g for g in data['people'] if g['id'] not in removed]; refresh(data)

def clear_identity(group):
    for key in ('library_id','match_score','match_candidate'):
        group.pop(key,None)
    group['identity_status']='uncertain'

def split_group(data,id,indices):
    g=next(g for g in data['people'] if g['id']==id); chosen=set(indices)
    if not chosen or len(chosen)>=len(g['observations']) or any(i<0 or i>=len(g['observations']) for i in chosen): raise ValueError('Select some, but not all observations')
    new=dict(id=uuid.uuid4().hex[:12],name='Split person (review)',identity_status='uncertain',observations=[o for i,o in enumerate(g['observations']) if i in chosen],ignored=False)
    g['observations']=[o for i,o in enumerate(g['observations']) if i not in chosen]; clear_identity(g); g['name']='Person (review)'; data['people'].append(new); refresh(data)
