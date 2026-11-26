"""Clipivo adapter for the unchanged Rajudesktop Z Builder native draft writer."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
from .storage import root
from .render import execute
from core.downloads import tool_path

def find_node():
    exe=shutil.which('node')
    if exe:return exe
    for p in [root()/'runtime/node/node.exe',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'nodejs/node.exe']:
        if p.is_file():return str(p)
    from . import bootstrap_node
    bootstrap_node.ROOT=root()
    # Keep the original checksum-verified bootstrap; use the application data directory.
    dest=bootstrap_node.install()
    return str(dest/'node.exe')

def probe(path):
    p=subprocess.run([tool_path('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True,creationflags=0x08000000 if os.name=='nt' else 0)
    d=json.loads(p.stdout);v=next((s for s in d['streams'] if s['codec_type']=='video'),{})
    return dict(duration=float(d['format'].get('duration',0)),w=v.get('width',0),h=v.get('height',0),hasAudio=any(s['codec_type']=='audio' for s in d['streams']))

def request_from_plan(plan,name='Clipivo Replacement',audio='original',audio_file=None):
    from .footage import expand_plan
    plan=expand_plan(plan)
    ref=plan['reference'];images=[];media={}
    for i,row in enumerate(plan['rows']):
        if not row.get('approved') or not row.get('selected'):raise ValueError('Approve every scene before CapCut export')
        c=row['selected'];s=row['original'];path=c['path'];start=c.get('trim_start',c['start']);duration=s['end']-s['start'];speed=c.get('speed',1)
        if not .67<=speed<=1.5:raise ValueError('Speed must be between 0.67× and 1.5×')
        if path not in media:media[path]=probe(path)
        if start<0 or start+duration*speed>min(c['end'],media[path]['duration'])+.035:raise ValueError(f'Scene {i+1}: source trim is too short')
        images.append(dict(image=path,kind='video',start=s['start'],end=s['end'],trimStart=start,speed=speed,zoom='none',hasAudio=False,muted=True,transform=dict(scale=1,x=0,y=0),kfs={}))
    if not images:raise ValueError('No scenes to export')
    voice=None
    audio_path=ref['path'] if audio=='original' else audio_file if audio=='external' else None
    if audio_path:
        if audio_path not in media:media[audio_path]=probe(audio_path)
        if media[audio_path]['hasAudio']:
            duration=ref['duration']
            if media[audio_path]['duration']+.05<duration:raise ValueError('Audio is shorter than the timeline')
            voice=dict(file=audio_path,start=0,trimStart=0,dur=duration,volume=1)
    payload=dict(name=name,W=ref['width'],H=ref['height'],fps=ref['fps'],images=images,captions=[],voice=voice,music=[],sfx=[],singleVisualTrack=True,separateLayers=False)
    return dict(payload=payload,media=media)

def export_plan(plan,drafts_root='',name='Clipivo Replacement',audio='original',audio_file=None,launch=True,cancel=lambda:False):
    node=find_node();request=request_from_plan(plan,name,audio,audio_file);request.update(drafts_root=drafts_root,launch=False)
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
    return result
