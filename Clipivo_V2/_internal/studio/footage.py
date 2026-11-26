"""Persistent local footage index. Descriptors are measured, semantic labels are manual."""
import sqlite3, json, hashlib
from pathlib import Path
import cv2, numpy as np
from .storage import root
VIDEO_EXT={'.mp4','.mkv','.mov','.webm','.avi','.m4v'}

def describe(frame):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0,1],None,[16,8],[0,180,0,256]).ravel()
    norm=np.linalg.norm(hist)
    return (hist/max(norm,1e-9)).tolist()

def inspect_video(path,cancel=lambda:False,progress=lambda *a:None,min_scene=1.,cut_threshold=.48):
    cap=cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():raise ValueError('Cannot open '+str(path))
        fps=cap.get(cv2.CAP_PROP_FPS);count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps<=0 or count<=0:raise ValueError('Cannot determine video duration')
        duration=count/fps; boundaries=[0.]; previous=None;last_cut=0.;features=[];i=0;next_sample=0.
        # Sequential decoding. Hard cut detection every .25 s; boundaries are estimates.
        while cap.grab():
            if cancel():raise InterruptedError('Cancelled')
            t=i/fps;i+=1
            if t<next_sample:continue
            next_sample=t+.25;ok,frame=cap.retrieve()
            if not ok:raise ValueError('Video frame decode failed')
            vec=describe(frame);v=np.asarray(vec)
            if previous is not None and t-last_cut>=min_scene and duration-t>=min_scene and 1-float(np.dot(previous,v))>cut_threshold:
                boundaries.append(t);last_cut=t
            features.append((t,vec));previous=v;progress(t,duration)
        if i+1<count:raise ValueError('Truncated video: indexing incomplete')
        boundaries.append(duration);out=[]
        for a,b in zip(boundaries,boundaries[1:]):
            items=[v for t,v in features if a<=t<b]
            v=np.mean(items,axis=0) if items else np.zeros(128);v=v/max(np.linalg.norm(v),1e-9)
            out.append(dict(start=a,end=b,visual=v.tolist(),people=[],activity='',environment='',framing='',angle=''))
        return dict(path=str(Path(path).resolve()),duration=duration,width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),fps=fps,scenes=out)
    finally:cap.release()

class Index:
    def __init__(self,path=None):
        self.path=Path(path) if path else root()/'footage.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS media(path TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT)')
    def connect(self):return sqlite3.connect(self.path,timeout=30)
    def index(self,folder,cancel=lambda:False,progress=lambda *a:None):
        paths=sorted(p for p in Path(folder).rglob('*') if p.suffix.lower() in VIDEO_EXT and p.is_file());done=0
        for path in paths:
            if cancel():raise InterruptedError('Cancelled')
            stat=path.stat();key=hashlib.sha256(f'{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:hist-v1'.encode()).hexdigest()
            with self.connect() as db:old=db.execute('SELECT fingerprint FROM media WHERE path=?',(str(path.resolve()),)).fetchone()
            if not old or old[0]!=key:
                data=inspect_video(path,cancel)
                with self.connect() as db:db.execute('INSERT OR REPLACE INTO media VALUES(?,?,?)',(str(path.resolve()),key,json.dumps(data)))
            done+=1;progress(done,len(paths))
        return self.all()
    def all(self):
        with self.connect() as db:return [json.loads(row[0]) for row in db.execute('SELECT payload FROM media ORDER BY path') if Path(json.loads(row[0])['path']).is_file()]
    def save(self,media):
        with self.connect() as db:db.execute('UPDATE media SET payload=? WHERE path=?',(json.dumps(media),media['path']))

def scene_candidates(scene,reference,media,weights=None,used=None,minimum=.70,allow_short=False):
    weights=weights or dict(identity=4,activity=2,visual=2,framing=1,duration=1,aspect=1)
    used=used or {};out=[]
    target_people=set(scene.get('people',[]));target_len=scene['end']-scene['start']
    for video in media:
        if video['path']==reference['path']:continue
        for n,s in enumerate(video['scenes']):
            available=s['end']-s['start']
            if available<=0 or (not allow_short and available+.001<target_len):continue
            # Explicitly labelled people are a hard eligibility constraint.
            if target_people and not target_people.issubset(set(s.get('people',[]))):continue
            scores={'duration':min(target_len/available,1),'aspect':min((video['width']/video['height'])/(reference['width']/reference['height']),(reference['width']/reference['height'])/(video['width']/video['height']))}
            a=np.asarray(scene['visual']);b=np.asarray(s['visual']);scores['visual']=max(0,float(np.dot(a,b)))
            if target_people:scores['identity']=1.
            for k in ['activity','framing']:
                if scene.get(k):scores[k]=float(scene[k].casefold()==s.get(k,'').casefold())
            total=sum(weights.get(k,0) for k in scores)
            score=sum(v*weights.get(k,0) for k,v in scores.items())/max(total,1e-9)
            key=(video['path'],n);score-=min(.3,used.get(key,0)*.1)
            out.append(dict(path=video['path'],scene=n,start=s['start'],end=s['end'],score=round(score,4),scores=scores))
    out.sort(key=lambda c:-c['score'])
    return out[:20]

def build_plan(reference,media,weights=None,minimum=.70):
    rows=[];used={}
    for scene in reference['scenes']:
        choices=scene_candidates(scene,reference,media,weights,used,minimum)
        # Histogram similarity alone cannot establish semantic suitability. Never auto-approve.
        selected=choices[0] if choices and choices[0]['score']>=minimum else None
        if selected is None:
            selected=fill_same_people(scene,reference,media,minimum)
        if selected and 'scene' in selected:
            key=(selected['path'],selected['scene']);used[key]=used.get(key,0)+1
        rows.append(dict(original=scene,candidates=choices,selected=selected,approved=False,manual_review=True))
    return dict(version=1,reference=reference,rows=rows)

def fill_same_people(scene,reference,media,minimum_score=.70,min_speed=.67):
    """Combine verified same-person candidates, then bounded slowdown if necessary."""
    if not scene.get('people'):return None
    duration=scene['end']-scene['start']
    candidates=scene_candidates(scene,reference,media,allow_short=True)
    candidates=[c for c in candidates if c['score']>=minimum_score and c['end']>c['start']]
    if not candidates:return None
    picked=[];available=0.
    for c in candidates:
        picked.append(c);available+=c['end']-c['start']
        if available>=duration:break
    if available<duration*min_speed:return None
    speed=min(1.,available/duration);remaining=duration;pieces=[]
    for c in picked:
        target=min(remaining,(c['end']-c['start'])/speed)
        if target<=1e-6:break
        pieces.append(dict(path=c['path'],start=c['start'],end=c['end'],trim_start=c['start'],target_duration=target,speed=speed,score=c['score']))
        remaining-=target
    if remaining>1e-4:return None
    return dict(path=pieces[0]['path'],start=pieces[0]['start'],end=pieces[0]['end'],score=round(sum(p['score']*p['target_duration'] for p in pieces)/duration,4),pieces=pieces,gap_fill=True,speed=speed)

def expand_plan(plan):
    """One renderable row per physical clip; original scene duration remains authoritative."""
    import copy
    expanded=copy.deepcopy(plan);rows=[]
    for row in expanded['rows']:
        selected=row.get('selected') or {};pieces=selected.get('pieces')
        if not pieces:rows.append(row);continue
        t=row['original']['start']
        for n,p in enumerate(pieces):
            end=row['original']['end'] if n==len(pieces)-1 else t+p['target_duration']
            if end<=t:raise ValueError('Invalid gap-fill piece duration')
            rows.append(dict(original={**row['original'],'start':t,'end':end},selected=p,approved=row.get('approved',False),candidates=[]));t=end
        if abs(sum(p['target_duration'] for p in pieces)-(row['original']['end']-row['original']['start']))>.01:raise ValueError('Gap-fill pieces do not cover their original scene')
    expanded['rows']=rows;return expanded
