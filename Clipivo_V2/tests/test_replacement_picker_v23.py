"""Agent 2 source-only regression tests; no executable packaging."""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_internal"))
from studio.picker import build_picked_plan, constrain_ranges
from studio.footage import Index, build_plan, expand_plan, fill_same_people
from studio import render


def scene(start, end, people=(), confirmed=True):
    return dict(start=start, end=end, people=list(people),
                confirmed_people=list(people) if confirmed else [],
                visual=[1.] + [0.]*127, activity='', framing='', environment='', angle='')


def media(path, duration, people=(), confirmed=True):
    return dict(path=str(path), duration=duration, width=64, height=64, fps=10,
                scenes=[scene(0, duration, people, confirmed)])


def approve(plan):
    for row in plan['rows']:
        row.update(approved=True, manual_review=False)
    return plan


def test_capacity_seed_and_impossible():
    ref = media('reference.mp4', 9)
    sources = [media('Eala1.mp4', 3), media('Eala2.mp4', 4), media('Osaka1.mp4', 2)]
    for seed in range(1, 51):
        plan = build_picked_plan(ref, sources, 2, 4, seed=seed, allow_repeats=False)
        assert plan == build_picked_plan(ref, list(reversed(sources)), 2, 4, seed=seed, allow_repeats=False)
        rows = expand_plan(approve(plan))['rows']
        assert len({r['selected']['path'] for r in rows}) == 3
        assert sum(r['selected']['target_duration'] for r in rows) == pytest.approx(9)
    with pytest.raises(ValueError, match='cannot be covered'):
        build_picked_plan(media('r', 5), sources, 3, 4)
    with pytest.raises(ValueError, match='cannot be covered'):
        build_picked_plan(media('r', 10), sources, 2, 4, allow_repeats=False)


def test_split_tail():
    pieces, excluded = constrain_ranges([(0, 9)], 4, 4)
    assert pieces == [(0, 4), (4, 8)]
    assert excluded == pytest.approx(1)


def test_same_person_and_slowdown():
    ref = media('reference.mp4', 4, ['A'])
    sources = [media('one.mp4', 2, ['A']), media('two.mp4', 1, ['A']),
               media('unknown.mp4', 5, ['A'], False), media('wrong.mp4', 5, ['B'])]
    plan = build_plan(ref, sources)
    rows = expand_plan(approve(plan))['rows']
    assert {r['selected']['path'] for r in rows} == {'one.mp4','two.mp4'}
    assert sum(r['selected']['target_duration'] for r in rows) == pytest.approx(4)
    assert all(.67 <= r['selected']['speed'] <= 1 for r in rows)
    assert build_plan(ref, sources[2:])['rows'][0]['selected'] is None
    assert fill_same_people(ref['scenes'][0],ref,sources,clip_minimum=3,clip_maximum=3) is None
    bad = copy.deepcopy(plan)
    bad['rows'][0]['selected']['pieces'][0]['confirmed_people'] = []
    with pytest.raises(ValueError, match='identity'):
        expand_plan(bad)


@pytest.fixture
def real_media(tmp_path, monkeypatch):
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        pytest.skip('FFmpeg and FFprobe are required')
    monkeypatch.setattr(render,'tool_path',lambda name: {'ffmpeg':ffmpeg,'ffprobe':ffprobe}[name])
    def make(name, seconds, color, audio=False):
        path=tmp_path/name
        args=[ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color={color}:size=64x64:rate=10:duration={seconds}']
        if audio:
            args += ['-f','lavfi','-i',f'sine=frequency=440:sample_rate=48000:duration={seconds}','-c:a','aac']
        subprocess.run(args+['-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
        return path
    ref=media(make('reference.mp4',4,'black',True),4,['A'])
    a=media(make('a.mp4',2,'red'),2,['A'])
    b=media(make('b.mp4',1,'blue'),1,['A'])
    return ref,[a,b]


def test_real_render_gap_audio_and_protection(tmp_path,real_media):
    ref,sources=real_media
    plan=approve(build_plan(ref,sources))
    output=tmp_path/'out.mp4'
    originals={Path(m['path']):Path(m['path']).read_bytes() for m in [ref,*sources]}
    render.reconstruct(plan,output,audio='original')
    data=render.verify(output,4,10,40,True)
    audio=next(s for s in data['streams'] if s['codec_type']=='audio')
    assert abs(float(audio.get('start_time',0))) <= .05
    before=output.read_bytes()
    with pytest.raises(FileExistsError):
        render.reconstruct(plan,output)
    assert output.read_bytes()==before
    with pytest.raises(ValueError,match='input'):
        render.reconstruct(plan,Path(ref['path']))
    for path,content in originals.items():
        assert path.read_bytes()==content


def test_real_cancel_and_external_audio(tmp_path,real_media):
    ref,sources=real_media
    plan=approve(build_plan(ref,sources))
    output=tmp_path/'cancel.mp4'
    calls=0
    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 4
    with pytest.raises(InterruptedError):
        render.reconstruct(plan,output,cancel=cancel)
    assert not output.exists()
    render.reconstruct(plan,output,audio='external',audio_file=ref['path'])
    render.verify(output,4,10,40,True)


def test_index_reuses_unchanged(tmp_path,real_media,monkeypatch):
    import studio.footage as footage
    index=Index(tmp_path/'db'/'index.sqlite')
    first=index.index(tmp_path)
    assert len(first)==3
    def unexpected(*args,**kwargs):
        pytest.fail('unchanged video was reindexed')
    monkeypatch.setattr(footage,'inspect_video',unexpected)
    assert Index(index.path).index(tmp_path)==first


def test_no_reuse_is_per_source_file_not_per_scene():
    ref = media('reference.mp4', 6)
    a = media('source-a.mp4', 8)
    a['scenes'] = [scene(0, 4), scene(4, 8)]
    b = media('source-b.mp4', 3)
    for seed in range(1, 51):
        plan = approve(build_picked_plan(ref, [a,b], 2, 4, seed=seed, allow_repeats=False))
        rows = expand_plan(plan)['rows']
        assert len(rows) == 2
        assert {r['selected']['path'] for r in rows} == {'source-a.mp4','source-b.mp4'}
    with pytest.raises(ValueError, match='cannot be covered'):
        build_picked_plan(ref, [a], 2, 4, allow_repeats=False)
    plan = approve(build_picked_plan(ref, [a], 2, 4, allow_repeats=True))
    plan['picker']['allow_repeats'] = False
    with pytest.raises(ValueError, match='Source reuse'):
        expand_plan(plan)


def test_cancel_selection_and_match():
    ref = media('reference.mp4', 4, ['A'])
    sources = [media('source.mp4', 4, ['A'])]
    with pytest.raises(InterruptedError):
        build_picked_plan(ref, sources, 2, 4, cancel=lambda:True)
    with pytest.raises(InterruptedError):
        build_plan(ref, sources, cancel=lambda:True)


def test_capcut_request_from_reviewed_replacement_and_picker(real_media):
    from studio.capcut import request_from_plan
    ref,sources=real_media
    plan=approve(build_plan(ref,sources))
    pieces=expand_plan(plan)['rows']
    request=request_from_plan(plan,audio='original')['payload']
    assert len(request['images'])==len(pieces)==2
    assert request['images'][0]['start']==0
    assert request['images'][-1]['end']==4
    for image,row in zip(request['images'],pieces):
        assert image['image']==row['selected']['path']
        assert image['speed']==row['selected']['speed']
        assert image['trimStart']==pytest.approx(row['selected']['trim_start'],abs=1e-6)
        assert image['muted'] is True
    assert request['voice']['dur']==4
    assert request_from_plan(plan,audio='none')['payload']['voice'] is None
    assert request_from_plan(plan,audio='external',audio_file=ref['path'])['payload']['voice']['file']==ref['path']
    picked=approve(build_picked_plan(ref,sources,1,2,seed=42,allow_repeats=True))
    payload=request_from_plan(picked,audio='none')['payload']
    assert len(payload['images'])==len(picked['rows'])
    assert payload['images'][-1]['end']==4
    assert all(1<=c['end']-c['start']<=2 for c in payload['images'])
