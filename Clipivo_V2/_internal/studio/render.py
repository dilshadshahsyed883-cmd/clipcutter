"""Cancellable, frame-budgeted reconstruction with atomic output publication."""
import subprocess, tempfile, json, os, math
from pathlib import Path
from core.downloads import tool_path

def execute(args,cancel=lambda:False):
    if cancel():raise InterruptedError('Rendering cancelled')
    with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as log:
        p=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=log,creationflags=0x08000000 if os.name=='nt' else 0)
        try:
            while True:
                if cancel():
                    p.terminate()
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:p.kill();p.wait()
                    raise InterruptedError('Rendering cancelled')
                try:code=p.wait(timeout=.15);break
                except subprocess.TimeoutExpired:continue
            if code:
                log.seek(0);raise RuntimeError(log.read()[-6000:] or 'Media command failed')
        finally:
            if p.poll() is None:p.kill();p.wait()

def verify(path,duration,fps,frames=None,audio_required=False):
    p=subprocess.run([tool_path('ffprobe'),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True)
    data=json.loads(p.stdout);videos=[s for s in data['streams'] if s['codec_type']=='video']
    actual=float(videos[0].get('duration',data['format']['duration'])) if videos else 0
    if not videos or abs(actual-duration)>max(.002,.51/fps):raise RuntimeError(f'Output validation failed: expected {duration:.3f}s, got {actual:.3f}s')
    if frames is not None and int(videos[0].get('nb_read_frames',0)) != frames:raise RuntimeError('Output frame count mismatch')
    if audio_required:
        tracks=[s for s in data['streams'] if s['codec_type']=='audio']
        if not tracks or abs(float(tracks[0].get('duration',0))-duration)>max(.05,1/fps):raise RuntimeError('Output audio missing or duration mismatch')
    return data

def reconstruct(plan,output,width=None,height=None,fps=None,audio='original',audio_file=None,encoder='libx264',cancel=lambda:False,progress=lambda *a:None):
    from .footage import expand_plan
    plan=expand_plan(plan)
    ref=plan['reference'];rows=plan['rows'];output=Path(output)
    if not rows or any(not row.get('approved') or not row.get('selected') for row in rows):raise ValueError('Approve a valid replacement for every scene before rendering')
    inputs={Path(ref['path']).resolve(),*(Path(r['selected']['path']).resolve() for r in rows)}
    if audio_file:inputs.add(Path(audio_file).resolve())
    if output.resolve() in inputs:raise ValueError('Output must differ from every input video or audio file')
    if cancel():raise InterruptedError('Rendering cancelled')
    if output.exists() or output.is_symlink():raise FileExistsError('Choose a new output filename; existing files are protected')
    if output.suffix.lower()!='.mp4':raise ValueError('Output filename must end in .mp4')
    if audio not in ('original','none','external'):raise ValueError('Invalid audio mode')
    if audio=='external' and (not audio_file or not Path(audio_file).is_file()):raise ValueError('Select an external audio file')
    if encoder not in ('libx264','h264_nvenc'):raise ValueError('Unsupported encoder')
    fps=float(fps or ref['fps']);w=int(width or ref['width']);h=int(height or ref['height']);w-=w%2;h-=h%2
    if min(w,h)<2 or not math.isfinite(fps) or not 0<fps<=240:raise ValueError('Invalid output dimensions or frame rate')
    limits=plan.get('picker') if plan.get('mode')=='concat_picker' else plan.get('clip_limits')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.clipivo-render-',dir=output.parent) as temp:
        temp=Path(temp);parts=[];total_frames=round(ref['duration']*fps);previous=0
        for i,row in enumerate(rows):
            sel=row['selected'];end=total_frames if i==len(rows)-1 else round(row['original']['end']*fps);frames=end-previous;previous=end
            needed=frames/fps
            if frames<=0:raise ValueError('Scene is shorter than one output frame')
            if limits and not float(limits['minimum'])-1e-9<=needed<=float(limits['maximum'])+1e-9:raise ValueError('Output frame rounding violates clip limits; change frame rate or clip limits')
            start=float(sel.get('trim_start',sel['start']));limit=float(sel['end'])
            speed=float(sel.get('speed',1.))
            if not .67<=speed<=1.5:raise ValueError('Speed must stay between 0.67× and 1.5×')
            if start<sel['start']-1e-5 or (limit-start)/speed+1/fps<needed:raise ValueError(f'Scene {i+1}: replacement trim is too short')
            part=temp/f'{i:05}.mp4';parts.append(part)
            vf=f'setpts=(PTS-STARTPTS)/{speed},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={1/fps}'
            execute([tool_path('ffmpeg'),'-nostdin','-v','error','-y','-ss',str(start),'-t',str(min(limit-start,needed*speed)),'-i',sel['path'],'-map','0:v:0','-an','-vf',vf,'-frames:v',str(frames),'-c:v',encoder,'-pix_fmt','yuv420p',str(part)],cancel)
            verify(part,needed,fps,frames);progress(i+1,len(rows)+1)
        listing=temp/'parts.txt';listing.write_text(''.join(f"file '{p.name}'\n" for p in parts),encoding='utf-8')
        candidate=temp/'final.mp4';duration=total_frames/fps
        args=[tool_path('ffmpeg'),'-nostdin','-v','error','-y','-f','concat','-safe','0','-i',str(listing)]
        if audio!='none':
            args+=['-i',str(audio_file if audio=='external' else ref['path']),'-map','0:v:0','-map','1:a:0','-c:a','aac','-af',f'aresample=async=1:first_pts=0,apad,atrim=duration={duration}','-t',str(duration)]
        else:args+=['-map','0:v:0','-an']
        args+=['-c:v','copy','-movflags','+faststart',str(candidate)];execute(args,cancel);verify(candidate,duration,fps,total_frames,audio!='none')
        # Decode the finished video as a final corruption check.
        execute([tool_path('ffmpeg'),'-nostdin','-v','error','-i',str(candidate),'-map','0:v:0','-map','0:a?','-f','null','-'],cancel)
        if cancel():raise InterruptedError('Rendering cancelled')
        # Atomic no-clobber publication: a concurrently created target is never replaced.
        os.link(candidate,output);progress(len(rows)+1,len(rows)+1)
    return str(output)
