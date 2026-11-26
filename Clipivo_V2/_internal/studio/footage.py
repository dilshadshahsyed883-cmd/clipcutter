"""Persistent local footage index. Descriptors are measured, semantic labels are manual."""
import sqlite3, json, hashlib, math
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
            if target_people and (not target_people.issubset(set(scene.get('confirmed_people',[]))) or not target_people.issubset(set(s.get('confirmed_people',[])))):continue
            scores={'duration':min(target_len/available,1),'aspect':min((video['width']/video['height'])/(reference['width']/reference['height']),(reference['width']/reference['height'])/(video['width']/video['height']))}
            a=np.asarray(scene['visual']);b=np.asarray(s['visual']);scores['visual']=max(0,float(np.dot(a,b)))
            if target_people:scores['identity']=1.
            for k in ['activity','framing']:
                if scene.get(k):scores[k]=float(scene[k].casefold()==s.get(k,'').casefold())
            total=sum(weights.get(k,0) for k in scores)
            score=sum(v*weights.get(k,0) for k,v in scores.items())/max(total,1e-9)
            key=(video['path'],n);score-=min(.3,used.get(key,0)*.1)
            out.append(dict(path=video['path'],scene=n,start=s['start'],end=s['end'],score=round(score,4),scores=scores,confirmed_people=list(s.get('confirmed_people',[]))))
    out.sort(key=lambda c:-c['score'])
    return out[:20]

def build_plan(reference, media, weights=None, minimum=.70, clip_minimum=None, clip_maximum=None, min_speed=.67):
    rows, used = [], {}
    for scene in reference['scenes']:
        duration = scene['end']-scene['start']
        choices = scene_candidates(scene,reference,media,weights,used,minimum)
        required = list(scene.get('people',[]))
        selected = None
        if clip_minimum is None or clip_minimum <= duration <= clip_maximum:
            if choices and choices[0]['score'] >= minimum:
                selected = dict(choices[0],trim_start=choices[0]['start'],target_duration=duration,speed=1.)
        if selected is None:
            selected = fill_same_people(scene,reference,media,minimum,min_speed,weights,used,clip_minimum,clip_maximum)
        if selected:
            for p in selected.get('pieces') or [selected]:
                key = (p['path'],p['scene'])
                used[key] = used.get(key,0)+1
        rows.append(dict(original=scene,candidates=choices,selected=selected,approved=False,
                         manual_review=True,identity_required=required))
    plan = dict(version=1,reference=reference,rows=rows,mode='reference_preserving')
    if clip_minimum is not None:
        plan['clip_limits'] = dict(minimum=clip_minimum,maximum=clip_maximum)
    return plan


def fill_same_people(scene,reference,media,minimum_score=.70,min_speed=.67,weights=None,used=None,
                     clip_minimum=None,clip_maximum=None):
    """Allocate distinct, confirmed same-person footage at normal speed first."""
    if not scene.get('people') or not .67 <= min_speed <= 1:
        return None
    duration = scene['end']-scene['start']
    lo = clip_minimum if clip_minimum is not None else .000001
    hi = clip_maximum if clip_maximum is not None else duration
    if not 0 < lo <= hi or duration < lo:
        return None
    candidates = scene_candidates(scene,reference,media,weights,used,allow_short=True)
    candidates = [c for c in candidates if c['score'] >= minimum_score]
    # Capacity-first ordering prevents a short, high-ranked clip from stranding a gap.
    for floor_speed in (1.,min_speed):
        eligible = [(c,min(hi,(c['end']-c['start'])/floor_speed)) for c in candidates]
        eligible = sorted((x for x in eligible if x[1] >= lo),key=lambda x:(-x[1],-x[0]['score'],x[0]['path'],x[0]['scene']))
        for count in range(1,len(eligible)+1):
            chosen = eligible[:count]
            if count*lo > duration+1e-8 or sum(cap for _,cap in chosen) < duration-1e-8:
                continue
            remaining = duration
            pieces = []
            for i,(c,cap) in enumerate(chosen):
                target = min(cap,remaining-(count-i-1)*lo)
                speed = min(1.,(c['end']-c['start'])/target)
                pieces.append(dict(c,trim_start=c['start'],target_duration=target,speed=speed))
                remaining -= target
            if abs(remaining) > 1e-7:
                continue
            return dict(pieces[0],pieces=pieces,gap_fill=True,
                        score=round(sum(p['score']*p['target_duration'] for p in pieces)/duration,4))
    return None


def expand_plan(plan, require_approval=True):
    """Validate canonical timeline and return one row per physical piece.

    Legacy single selections may omit target_duration/speed. Identity-requiring
    rows must carry explicit confirmation on every piece, including manual picks.
    """
    import copy
    expanded = copy.deepcopy(plan)
    rows = []
    ref = expanded['reference']
    total = float(ref['duration'])
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Invalid reference duration')
    mode = expanded.get('mode','reference_preserving')
    if mode not in ('reference_preserving','concat_picker'):
        raise ValueError('Unknown replacement mode')
    original_rows = expanded['rows']
    if mode == 'reference_preserving':
        if len(original_rows) != len(ref['scenes']):
            raise ValueError('Reference scene count changed')
        for row,scene in zip(original_rows,ref['scenes']):
            if any(abs(float(row['original'][k])-float(scene[k])) > 1e-6 for k in ('start','end')):
                raise ValueError('Reference scene boundaries changed')
    limits = expanded.get('picker') if mode == 'concat_picker' else expanded.get('clip_limits')
    if limits and not 0 < float(limits['minimum']) <= float(limits['maximum']):
        raise ValueError('Invalid clip limits')
    at = 0.
    for row in original_rows:
        original = row['original']
        start,end = float(original['start']),float(original['end'])
        if not all(math.isfinite(v) for v in (start,end)) or abs(start-at)>1e-6 or end<=start:
            raise ValueError('Timeline has a gap, overlap or invalid scene')
        if require_approval and (not row.get('approved') or row.get('manual_review')):
            raise ValueError('Approve every valid scene before export')
        sel = row.get('selected')
        if not sel:
            raise ValueError('Missing replacement footage')
        required = set(original.get('people',[])) | set(row.get('identity_required',[]))
        pieces = sel.get('pieces') or [sel]
        t = start
        for n,p in enumerate(pieces):
            if required and not required.issubset(set(p.get('confirmed_people',[]))):
                raise ValueError('Same-person identity is unconfirmed; manual review required')
            target = float(p.get('target_duration',end-start if len(pieces)==1 else 0))
            a,b = float(p['start']),float(p['end'])
            trim = float(p.get('trim_start',a))
            speed = float(p.get('speed',1.))
            if not all(math.isfinite(v) for v in (target,a,b,trim,speed)) or target<=0 or a<0 or b<=a or trim<a-1e-7 or trim+target*speed>b+1e-6 or not .67<=speed<=1.5:
                raise ValueError('Invalid replacement trim, speed or duration')
            if limits and not float(limits['minimum'])-1e-6<=target<=float(limits['maximum'])+1e-6:
                raise ValueError('Replacement piece violates clip duration limits')
            next_t=t+target
            if next_t>end+1e-6:
                raise ValueError('Replacement pieces exceed scene duration')
            piece=dict(p,trim_start=trim,target_duration=target,speed=speed)
            piece.pop('pieces',None)
            rows.append(dict(original={**original,'start':t,'end':next_t},selected=piece,
                             approved=row.get('approved',False),manual_review=row.get('manual_review',False),
                             identity_required=sorted(required),candidates=[]))
            t=next_t
        if abs(t-end)>1e-6:
            raise ValueError('Replacement pieces do not cover their original scene')
        rows[-1]['original']['end']=end
        at=end
    if abs(at-total)>1e-6:
        raise ValueError('Timeline does not cover reference duration')
    expanded['rows']=rows
    return expanded
