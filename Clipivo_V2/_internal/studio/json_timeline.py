"""Read-only Person Analyzer JSON to editable, standalone timeline (microseconds)."""
import hashlib
import json
import math
import os
import random
import subprocess
import uuid
from pathlib import Path

FORMAT = 'clipivo.timeline.v1'
US = 1_000_000
VIDEO = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mts', '.m2ts', '.mpg', '.mpeg'}

def us(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid timestamp')
    return int(math.floor(value * US + .5))

def stamp(path):
    p = Path(path).resolve(strict=True)
    s = p.stat()
    if not p.is_file():
        raise ValueError('Expected a file: ' + str(p))
    return [str(p), s.st_size, s.st_mtime_ns, s.st_ctime_ns]

class ReferenceRelinkRequired(ValueError):
    pass

def reference_info(path, probe, total, expected_stamp=None, expected=None):
    source=stamp(path)
    if expected_stamp and source[1]!=expected_stamp[1]:
        raise ValueError('Reference file size does not match original')
    info=probe(source[0]);fps=float(info['fps'])
    if not math.isfinite(fps) or fps<=0 or min(info['w'],info['h'])<2:
        raise ValueError('Invalid reference video metadata')
    if abs(us(info['videoDuration'])-total)>max(1000,round(US/fps)):
        raise ValueError('Reference duration does not match analysis')
    if expected and (int(info['w']),int(info['h']))!=(expected['width'],expected['height']):
        raise ValueError('Reference resolution does not match original')
    if expected and abs(fps-expected['fps'])>0.001:
        raise ValueError('Reference frame rate does not match original')
    if stamp(source[0])!=source: raise ValueError('Reference changed during import')
    return dict(path=source[0],stamp=source,duration=total,fps=fps,width=int(info['w']),height=int(info['h']))

def load_analysis(path, probe, reference_path=None):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('version') != 2 or not isinstance(data.get('people'), list):
        raise ValueError('Expected desktop Person Analyzer version 2 analysis.json')
    total = us(data['duration'])
    if not 0 < total <= 86400 * US or us(data['sample_interval']) <= 0:
        raise ValueError('Invalid analysis duration or sampling interval')
    expected=data.get('source_stamp')
    if reference_path is None:
        try: source=stamp(data['source'])
        except (OSError,ValueError) as exc: raise ReferenceRelinkRequired('Original reference not found; select the same video at its new location') from exc
        if expected and source!=expected:
            raise ReferenceRelinkRequired('Original reference changed or moved; explicitly confirm the same source video')
    reference=reference_info(reference_path or data['source'],probe,total,expected if reference_path else None)
    people, events = {}, {0: [], total: []}
    for g in data['people']:
        pid, name = g['id'], g['name']
        if not isinstance(pid, str) or not pid or pid in people or not isinstance(name, str) or not name.strip():
            raise ValueError('Invalid or duplicate person ID/name')
        people[pid] = {'name': name, 'ignored': bool(g.get('ignored') or g.get('filtered'))}
        if people[pid]['ignored']:
            continue
        if not isinstance(g['segments'], list):
            raise ValueError('Invalid accepted segments')
        for pair in g['segments']:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError('Invalid appearance interval')
            a, z = map(us, pair)
            if not 0 <= a < z <= total:
                raise ValueError('Appearance outside reference or empty')
            events.setdefault(a, []).append((pid, 1))
            events.setdefault(z, []).append((pid, -1))
    active, intervals = {}, []
    points = sorted(events)
    for i, a in enumerate(points[:-1]):
        for pid, delta in events[a]:
            active[pid] = active.get(pid, 0) + delta
        intervals.append({'start': a, 'end': points[i+1], 'people': sorted(p for p, n in active.items() if n > 0)})
    return {'analysis_path': str(path), 'analysis_sha256': hashlib.sha256(raw).hexdigest(),
            'reference': reference,
            'people': people, 'intervals': intervals}

def normalize(name):
    return ' '.join(name.casefold().split())

def scan_folder(folder, people, probe, cancel=lambda: False, progress=lambda *args: None, cached=()):
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose a main footage folder')
    names = {}
    for pid, person in people.items():
        if not person['ignored']:
            names.setdefault(normalize(person['name']), []).append(pid)
    files = []
    for base, dirs, entries in os.walk(root, followlinks=False):
        if cancel(): raise InterruptedError('Cancelled')
        dirs[:] = sorted(d for d in dirs if not (Path(base)/d).is_symlink())
        for name in sorted(entries):
            p = Path(base)/name
            if p.suffix.lower() in VIDEO and not p.is_symlink():
                files.append(p)
    cache={m['path']:m for m in cached if isinstance(m,dict) and m.get('path')}
    media, warnings = [], []
    for i, p in enumerate(files):
        if cancel(): raise InterruptedError('Cancelled')
        rel = p.relative_to(root)
        found = {pid for part in rel.parts[:-1] for pid in names.get(normalize(part), [])}
        try:
            before = stamp(p)
            old=cache.get(str(p))
            if old and old.get('stamp')==before:
                duration=old['duration']
            else:
                info = probe(str(p))
                duration = min(us(info['duration']), us(info['videoDuration']))
                if not duration or min(info['w'], info['h']) < 2 or abs(info.get('videoStart', 0)) > 1e-6:
                    raise ValueError('Unsupported video metadata')
            if stamp(p) != before:
                raise ValueError('Video changed during scan')
            media.append({'path': str(p), 'relative': rel.as_posix(), 'duration': duration,
                          'person': next(iter(found)) if len(found) == 1 else None, 'stamp': before})
            if len(found)>1: warnings.append('Ambiguous folder: ' + rel.as_posix())
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
            warnings.append(str(rel) + ': ' + str(exc))
        progress(i+1, len(files))
    return media, warnings

def options(minimum=2.5, maximum=4., gap_fill=True, gap_max=1., speed_adjust=True,
            min_speed=.8, max_speed=1.2, reuse=True):
    lo, hi, gap = us(minimum), us(maximum), us(gap_max)
    if not 0 < lo <= hi <= 600*US or not .67 <= min_speed <= 1 <= max_speed <= 1.5:
        raise ValueError('Invalid clip or speed limits (native export supports 0.67x–1.5x)')
    return dict(minimum=lo, maximum=hi, gap_fill=bool(gap_fill), gap_max=gap,
                speed_adjust=bool(speed_adjust), min_speed=float(min_speed), max_speed=float(max_speed), reuse=bool(reuse))

def split_range(a, z, lo, hi):
    length = z-a
    n = (length+hi-1)//hi
    if length < n*lo:
        # Never move an analyzer boundary just to meet clip limits.
        # Keep a short remainder visible as a manual gap.
        while z-a > hi:
            yield a, a+hi
            a += hi
        if a<z: yield a,z
        return
    for i in range(n):
        yield a+length*i//n, a+length*(i+1)//n

def fit_speed(available, length, cfg):
    if length<=0 or available<=0:return None
    ratio=available/length
    if not cfg['speed_adjust']:return 1. if ratio>=1 else None
    if ratio<cfg['min_speed']:return None
    # Use the whole source when it is close to the target; otherwise trim normally.
    return ratio if ratio<=cfg['max_speed'] else 1.

def generate(imported, folder, media, cfg, seed, cancel=lambda:False, warnings=()):
    rng=random.Random(seed);rows=[];intervals=imported['intervals']
    minimum_frame=max(1,math.ceil(US/imported['reference'].get('fps',30)-.0001))
    by_person={}
    for m in media:
        if m['person'] and m['path']!=imported['reference']['path']:
            by_person.setdefault(m['person'],[]).append(m)
    for i, interval in enumerate(intervals):
        if cancel():raise InterruptedError('Cancelled')
        a,z,ids=interval['start'],interval['end'],interval['people']
        pid=ids[0] if len(ids)==1 else None;fill=False
        if not ids and cfg['gap_fill'] and z-a<=cfg['gap_max'] and 0<i<len(intervals)-1:
            left,right=intervals[i-1]['people'],intervals[i+1]['people']
            if len(left)==1 and left==right:pid=left[0];fill=True
        parts=split_range(a,z,cfg['minimum'],cfg['maximum']) if pid else [(a,z)]
        for start,end in parts:
            if cancel():raise InterruptedError('Cancelled')
            row=dict(start=start,end=end,people=list(ids),assigned_person=pid,auto_gap_fill=fill,
                     selected=None,reason='No detected person' if not ids else 'Ambiguous persons' if len(ids)>1 else 'Missing matching footage')
            if end-start<minimum_frame:row['reason']='Shorter than one output frame; manual gap'
            rows.append(row)
    # Allocate unique footage longest-first per person so a short target cannot consume
    # the only source capable of covering a longer target. Random among equally feasible sources.
    assignments={};used=set()
    demand=sorted((i for i,row in enumerate(rows) if row['assigned_person'] and row['end']-row['start']>=minimum_frame),
                  key=lambda i: (-(rows[i]['end']-rows[i]['start']),i))
    # A source eligible for a longer target is also eligible for every shorter target.
    for i in demand:
        if cancel():raise InterruptedError('Cancelled')
        row=rows[i];length=row['end']-row['start']
        candidates=[m for m in by_person.get(row['assigned_person'],[]) if m['path'] not in used and fit_speed(m['duration'],length,cfg) is not None]
        if candidates:
            m=rng.choice(candidates);assignments[i]=m;used.add(m['path'])
    previous=None
    for i,row in enumerate(rows):
        if cancel():raise InterruptedError('Cancelled')
        length=row['end']-row['start'];m=assignments.get(i)
        if m is None and cfg['reuse'] and row['assigned_person'] and length>=minimum_frame:
            pool=[c for c in by_person.get(row['assigned_person'],[]) if fit_speed(c['duration'],length,cfg) is not None]
            next_path=assignments.get(i+1,{}).get('path')
            alternatives=[c for c in pool if c['path'] not in (previous,next_path)]
            pool=alternatives or [c for c in pool if c['path']!=previous] or pool
            if pool:m=rng.choice(pool)
        if m:
            speed=fit_speed(m['duration'],length,cfg)
            trim=rng.randint(0,max(0,m['duration']-int(math.floor(length*speed+.5))))
            row.update(selected={**m,'trim':trim,'speed':speed},reason='Short boundary preserved' if length<cfg['minimum'] and not row['auto_gap_fill'] else '')
            previous=m['path']
        else:previous=None
    plan={**imported,'format':FORMAT,'root':str(Path(folder).resolve()),'options':dict(cfg),
          'seed':seed,'rows':rows,'media':list(media),'warnings':list(warnings),'audio':True}
    return validate(plan)

def relink_reference(plan_or_imported, path, probe):
    import copy
    new=copy.deepcopy(plan_or_imported);old=new['reference']
    new['reference']=reference_info(path,probe,old['duration'],old['stamp'],old)
    return validate(new) if new.get('format')==FORMAT else new

def validate(plan):
    if plan.get('format') != FORMAT:
        raise ValueError('Unsupported timeline format')
    total=plan['reference']['duration']
    if type(total) is not int or not 0<total<=86400*US: raise ValueError('Invalid duration')
    if type(plan['rows']) is not list or not plan['rows']: raise ValueError('Empty timeline')
    intervals=plan['intervals'];people=plan['people'];i=0;cursor=0
    boundary=0
    for interval in intervals:
        a,z=interval['start'],interval['end']
        if type(a) is not int or type(z) is not int or a!=boundary or not a<z<=total or not isinstance(interval['people'],list) or len(set(interval['people']))!=len(interval['people']) or any(p not in people for p in interval['people']):
            raise ValueError('Invalid stored analyzer intervals')
        boundary=z
    if boundary!=total: raise ValueError('Incomplete analyzer intervals')
    for row in plan['rows']:
        a,z=row['start'],row['end']
        if type(a) is not int or type(z) is not int or a!=cursor or not a<z<=total:
            raise ValueError('Timeline gap, overlap or invalid range')
        while i<len(intervals) and a==intervals[i]['end']: i+=1
        if i>=len(intervals) or not intervals[i]['start']<=a<z<=intervals[i]['end'] or row['people']!=intervals[i]['people']:
            raise ValueError('Analyzer boundary or person membership changed')
        if any(p not in people for p in row['people']): raise ValueError('Unknown person')
        c=row.get('selected')
        if c:
            speed=c['speed'];trim=c['trim'];length=c['duration']
            if not isinstance(speed,(float,int)) or not math.isfinite(speed) or not .67<=speed<=1.5 or type(trim) is not int or type(length) is not int or trim<0 or trim+int(math.floor((z-a)*speed+.5))>length:
                raise ValueError('Invalid clip speed or trim')
            if not isinstance(c['path'],str): raise ValueError('Invalid media path')
            cfg=plan.get('options')
            if cfg and (not cfg['min_speed']<=speed<=cfg['max_speed'] or (not cfg['speed_adjust'] and speed!=1.)):
                raise ValueError('Selected speed violates timeline settings')
        cursor=z
    if cursor!=total: raise ValueError('Timeline duration changed')
    return plan

def save_plan(path, plan):
    validate(plan)
    p=Path(path).resolve()
    if p==Path(plan['analysis_path']).resolve() or p==Path(plan['reference']['path']).resolve():
        raise ValueError('Never overwrite the original analysis or video')
    if p.suffix.lower()!='.json': raise ValueError('Use a separate timeline JSON filename')
    if p.exists():
        old=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(old,dict) or old.get('format')!=FORMAT: raise ValueError('Refusing to overwrite non-timeline JSON')
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        os.replace(tmp,p)
    finally: tmp.unlink(missing_ok=True)

def open_plan(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))

def missing(row):
    c=row.get('selected')
    if not c: return False
    try: return stamp(c['path'])!=c['stamp']
    except (OSError,ValueError): return True

def relink(plan, folder, probe, cancel=lambda:False):
    import copy
    new=copy.deepcopy(plan)
    root=Path(folder).resolve(strict=True)
    if not root.is_dir(): raise ValueError('Choose a folder')
    entries=[row.get('selected') for row in new['rows']]+new.get('media',[])
    cache={}
    for c in entries:
        if cancel():raise InterruptedError('Cancelled')
        if not c or not c.get('relative'): continue
        p=(root/c['relative']).resolve()
        if not p.is_relative_to(root) or not p.is_file(): continue
        try:
            if str(p) not in cache:
                before=stamp(p);info=probe(str(p));duration=min(us(info['duration']),us(info['videoDuration']))
                if not info['w'] or not info['h'] or abs(info.get('videoStart',0))>1e-6 or stamp(p)!=before:continue
                cache[str(p)]=(duration,before)
            duration,before=cache[str(p)]
            if duration!=c['duration'] or before[1]!=c['stamp'][1]:continue
            c.update(path=str(p),stamp=before)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError):continue
    new['root']=str(root)
    return validate(new)
