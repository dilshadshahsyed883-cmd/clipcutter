"""Clipivo adapter for the unchanged Rajudesktop Z Builder native draft writer."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
from .storage import root
from .render import execute
from core.downloads import tool_path

def find_node():
    exe=shutil.which('node')
    if exe:return exe
    for p in [Path(os.environ.get('ProgramFiles','C:/Program Files'))/'nodejs/node.exe']:
        if p.is_file():return str(p)
    from . import bootstrap_node
    # Keep the original checksum-verified bootstrap; use the application data directory.
    dest=bootstrap_node.install(root())
    return str(dest/'node.exe')

def probe(path):
    p=subprocess.run([tool_path('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True,creationflags=0x08000000 if os.name=='nt' else 0)
    d=json.loads(p.stdout);v=next((s for s in d['streams'] if s['codec_type']=='video'),{})
    a=next((s for s in d['streams'] if s['codec_type']=='audio'),{})
    fmt=d['format']
    def number(value, fallback):
        try: return float(value)
        except (ValueError, TypeError): return fallback
    duration=number(fmt.get('duration'),0)
    origin=number(fmt.get('start_time'),0)
    return dict(duration=duration,w=v.get('width',0),h=v.get('height',0),
                videoDuration=number(v.get('duration'),duration),
                videoStart=number(v.get('start_time'),origin)-origin,
                hasAudio=bool(a),audioDuration=number(a.get('duration'),duration),
                audioStart=number(a.get('start_time'),origin)-origin)

def _us(value, label):
    import math
    value=float(value)
    if not math.isfinite(value) or value<0:
        raise ValueError(f'{label}: expected finite non-negative seconds')
    return int(math.floor(value*1_000_000+.5))

def request_from_plan(plan,name='Clipivo Replacement',audio='original',audio_file=None):
    from .footage import expand_plan
    import math
    if audio not in ('original','none','external'):
        raise ValueError('Invalid CapCut audio mode')
    ref=plan['reference']
    total=_us(ref['duration'],'Reference duration')
    fps=float(ref['fps'])
    if total<=0 or not math.isfinite(fps) or fps<=0 or min(int(ref['width']),int(ref['height']))<2:
        raise ValueError('Invalid reference duration, dimensions or frame rate')
    # Check reviewed piece durations before expand_plan can absorb a residual into the last piece.
    for i,row in enumerate(plan['rows'],1):
        if not row.get('approved') or not row.get('selected'):
            raise ValueError(f'Scene {i}: approve a replacement before CapCut export')
        pieces=row['selected'].get('pieces')
        if pieces is not None:
            if not pieces or any(_us(p['target_duration'],f'Scene {i} piece')<=0 for p in pieces):
                raise ValueError(f'Scene {i}: invalid gap-fill pieces')
            s=row['original']
            if abs(sum(float(p['target_duration']) for p in pieces)-(s['end']-s['start']))>1e-6:
                raise ValueError(f'Scene {i}: gap-fill pieces do not exactly cover the reviewed scene')
    plan=expand_plan(plan)
    images=[];media={};previous=0
    def info_for(path):
        path=str(Path(path).expanduser().resolve(strict=True))
        if not Path(path).is_file(): raise ValueError(f'Media is not a file: {path}')
        if path not in media:media[path]=probe(path)
        return path,media[path]
    for i,row in enumerate(plan['rows'],1):
        c=row['selected'];s=row['original'];path,info=info_for(c['path'])
        target_start=_us(s['start'],f'Clip {i} target start')
        target_end=_us(s['end'],f'Clip {i} target end')
        duration=target_end-target_start
        if target_start!=previous or duration<=0:
            raise ValueError(f'Clip {i}: reviewed timeline contains a gap, overlap or empty clip')
        previous=target_end
        if duration/1_000_000*fps<1-1e-6:
            raise ValueError(f'Clip {i}: shorter than one output frame')
        start=_us(c.get('trim_start',c['start']),f'Clip {i} trim')
        low=_us(c['start'],f'Clip {i} source start')
        limit=_us(c['end'],f'Clip {i} source end')
        speed=float(c.get('speed',1))
        if not math.isfinite(speed) or not .67<=speed<=1.5:
            raise ValueError(f'Clip {i}: speed must be between 0.67× and 1.5×')
        if not info.get('w') or not info.get('h'):
            raise ValueError(f'Clip {i}: source contains no video')
        if abs(info.get('videoStart',0))>1e-6:
            raise ValueError(f'Clip {i}: nonzero video stream offset cannot be represented safely')
        source_duration=_us(duration/1_000_000*speed,f'Clip {i} source duration')
        available=_us(min(info['duration'],info.get('videoDuration',info['duration'])),f'Clip {i} media duration')
        if start<low or start+source_duration>min(limit,available):
            raise ValueError(f'Clip {i}: source trim is outside the approved or available range')
        images.append(dict(image=path,kind='video',start=target_start/1e6,end=target_end/1e6,
                           trimStart=start/1e6,speed=speed,zoom='none',hasAudio=False,muted=True,
                           transform=dict(scale=1,x=0,y=0),kfs={}))
    if not images or previous!=total:
        raise ValueError('Approved clips must cover the complete reference timeline')
    voice=None
    audio_path=ref['path'] if audio=='original' else audio_file if audio=='external' else None
    if audio=='external' and not audio_path:
        raise ValueError('Select an external audio file')
    if audio_path:
        audio_path,info=info_for(audio_path)
        if not info['hasAudio'] and audio=='external':
            raise ValueError('Selected external file contains no audio stream')
        if info['hasAudio']:
            if abs(info.get('audioStart',0))>1e-6:
                raise ValueError('Audio stream has a nonzero start offset; native synchronization cannot be guaranteed')
            if _us(min(info['duration'],info.get('audioDuration',info['duration'])),'Audio duration')<total:
                raise ValueError('Audio is shorter than the timeline; native silence padding is unsupported')
            voice=dict(file=audio_path,start=0,trimStart=0,dur=total/1e6,volume=1)
    payload=dict(name=name,W=ref['width'],H=ref['height'],fps=fps,images=images,captions=[],voice=voice,music=[],sfx=[],singleVisualTrack=True,separateLayers=False,strictTimeline=True)
    return dict(payload=payload,media=media)

def export_plan(plan,drafts_root='',name='Clipivo Replacement',audio='original',audio_file=None,launch=True,cancel=lambda:False):
    request=request_from_plan(plan,name,audio,audio_file);node=find_node();request.update(drafts_root=drafts_root,launch=False)
    js=Path(__file__).with_name('capcut_bridge.js')
    with tempfile.TemporaryDirectory(prefix='clipivo-capcut-') as temp:
        input=Path(temp)/'request.json';output=Path(temp)/'result.json';input.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        # Original writer creates a unique new folder and verifies top-level + nested timelines.
        execute([node,str(js),str(input),str(output)],cancel)
        result=json.loads(output.read_text(encoding='utf-8'))
        if result.get('verify_issues'):raise RuntimeError('CapCut draft verification failed: '+str(result['verify_issues']))
    if launch:
        code="const e=require(process.argv[1]);const i=e.detect();process.stdout.write(JSON.stringify({launched:!!(i.exe&&e.launch(i.exe))}));"
        done=subprocess.run([node,'-e',code,str(js.with_name('capcut-draft.js'))],capture_output=True,text=True,timeout=20,creationflags=0x08000000 if os.name=='nt' else 0)
        try:result.update(json.loads(done.stdout))
        except ValueError:result['launched']=False
    result['home_instruction']='Open CapCut Home and select the newly created project: '+result['name']
    return result
