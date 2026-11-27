"""Gap-preserving CapCut payload for the standalone timeline only."""
from pathlib import Path
from .json_timeline import US, validate, stamp, missing, us

def request(plan, name, audio, audio_file, probe):
    validate(plan)
    if audio not in ('original','none'):
        raise ValueError('Timeline Builder supports original audio or no audio')
    ref=plan['reference'];total=ref['duration'];media={};images=[]
    if stamp(ref['path'])!=ref['stamp']:
        raise ValueError('Original reference changed or is missing')
    def info_for(path):
        p=str(Path(path).resolve(strict=True))
        if p not in media:media[p]=probe(p)
        return p,media[p]
    for i,row in enumerate(plan['rows'],1):
        c=row.get('selected')
        if not c:continue
        if missing(row):raise ValueError(f'Clip {i}: missing or changed media; relink or remove it')
        p,info=info_for(c['path'])
        if not info.get('w') or not info.get('h') or abs(info.get('videoStart',0))>1e-6:
            raise ValueError(f'Clip {i}: invalid video stream or offset')
        length=row['end']-row['start']
        if length/US*ref['fps']<1-1e-6:
            raise ValueError(f'Clip {i}: shorter than an output frame; leave it as a gap')
        if c['trim']+us(length/US*c['speed'])>min(us(info['duration']),us(info['videoDuration'])):
            raise ValueError(f'Clip {i}: selected source range is no longer available')
        images.append(dict(image=p,kind='video',start=row['start']/US,end=row['end']/US,
                           trimStart=c['trim']/US,speed=c['speed'],zoom='none',hasAudio=False,
                           muted=True,transform=dict(scale=1,x=0,y=0),kfs={}))
    voice=None
    if audio=='original':
        p,info=info_for(ref['path'])
        if info['hasAudio']:
            if abs(info.get('audioStart',0))>1e-6 or min(us(info['duration']),us(info['audioDuration']))<total:
                raise ValueError('Original audio cannot cover the exact timeline; disable audio to export')
            voice=dict(file=p,start=0,trimStart=0,dur=total/US,volume=1)
    payload=dict(name=name,W=ref['width'],H=ref['height'],fps=ref['fps'],images=images,
                 captions=[],voice=voice,music=[],sfx=[],singleVisualTrack=True,separateLayers=False,
                 strictTimeline=True,allowTimelineGaps=True,timelineDuration=total/US)
    return dict(payload=payload,media=media)
