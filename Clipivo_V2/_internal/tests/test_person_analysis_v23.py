"""Source-level tests. Face inference, GPU providers and HTTP are mocked."""
import io
import hashlib
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from studio.analysis import match_profiles, run, open_project
from studio.storage import Profiles
from v22.analyzer import assign, merge_groups, split_group, save_project
from v22.engine import Engine
from v22.model_locator import download_models, model_candidates, NAMES


def group(id, t, embedding=(1., 0.)):
    return dict(id=id, name='Person '+id, observations=[
        dict(time=t, image=id+'.jpg', quality=1, embedding=list(embedding))],
        ignored=False, segments=[[t-.25, t+.25]])


def test_ambiguous_centroids_start_review_group():
    groups=[dict(_sum=np.array([1.,0.])),dict(_sum=np.array([.999,.02]))]
    idx=assign(groups,np.array([1.,0.]),set(),.45)
    assert idx==2 and groups[idx]['identity_status']=='uncertain'


def test_overlapping_matches_are_not_confirmed():
    data=dict(people=[group('1',1),group('2',1)])
    match_profiles(data,[dict(id='p',name='Known',embeddings=[[1,0]])])
    assert all(g['identity_status']=='uncertain' for g in data['people'])
    assert all('library_id' not in g for g in data['people'])


def test_clear_manual_correction_provenance():
    a,b=group('1',1),group('2',3)
    a.update(identity_status='matched',library_id='p',match_score=.9)
    data=dict(duration=5,sample_interval=.5,people=[a,b])
    merge_groups(data,['1','2'])
    assert data['people'][0]['id']=='1'
    assert 'library_id' not in a
    split_group(data,'1',[1])
    assert all(g['identity_status']=='uncertain' for g in data['people'])
    with pytest.raises(ValueError):split_group(data,'1',[99])


def test_cancel_before_publish(monkeypatch,tmp_path):
    data=dict(duration=5,sample_interval=.5,people=[group('1',1)])
    monkeypatch.setattr('studio.analysis.analyze',lambda *a,**kw:data)
    with pytest.raises(InterruptedError):
        run('source.mp4',tmp_path,None,{},lambda *a:None,lambda:True,None,[])
    assert not (tmp_path/'analysis.json').exists()


def test_v22_reopen_preserves_custom_fields(tmp_path):
    source=tmp_path/'source.mp4';source.write_bytes(b'original')
    data=dict(version=2,source=str(source),duration=5,sample_interval=.5,
              people=[group('1',1)],legacy_field={'keep':True})
    save_project(tmp_path,data)
    before=(tmp_path/'analysis.json').read_bytes()
    opened=open_project(tmp_path/'analysis.json')
    assert opened['legacy_field']=={'keep':True}
    assert (tmp_path/'analysis.json').read_bytes()==before
    assert source.read_bytes()==b'original'


def test_profile_reference_only_migration_and_cache(monkeypatch,tmp_path):
    from core.character_store import CharacterStore
    monkeypatch.setenv('CLIPIVO_STUDIO_DATA',str(tmp_path))
    store=CharacterStore(tmp_path/'people',encryption_key=b'k'*32)
    person=store.create_character('Known')
    ok,encoded=cv2.imencode('.jpg',np.zeros((48,48,3),np.uint8))
    assert ok
    store.add_reference(person.id,'reference.jpg',encoded.tobytes())
    engine=Mock();engine.get.return_value=[(np.array([1.,0.]),None,None,None,None)]
    profiles=Profiles(store)
    entries=profiles.entries('model-a',engine)
    assert entries[0]['id']==person.id and engine.get.call_count==1
    assert b'embeddings' not in profiles.path(person.id).read_bytes()
    assert profiles.entries('model-a',engine)==entries
    assert engine.get.call_count==1
    assert profiles.entries('model-b',engine)[0]['model_signature']=='model-b'
    assert engine.get.call_count==2
    assert len(store.references(person.id))==1


def test_reference_migration_skips_ambiguous_face_images(monkeypatch,tmp_path):
    from core.character_store import CharacterStore
    monkeypatch.setenv('CLIPIVO_STUDIO_DATA',str(tmp_path))
    store=CharacterStore(tmp_path/'people',encryption_key=b'k'*32)
    person=store.create_character('Known')
    ok,encoded=cv2.imencode('.jpg',np.zeros((48,48,3),np.uint8))
    assert ok
    store.add_reference(person.id,'reference.jpg',encoded.tobytes())
    engine=Mock();engine.get.return_value=[(np.array([1.,0.]),),(np.array([0.,1.]),)]
    assert Profiles(store).entries('model-a',engine)==[]
    assert not Profiles(store).path(person.id).exists()


def test_model_candidates_do_not_stop_at_first_unverified_folder(tmp_path):
    bad=tmp_path/'bad';installed=tmp_path/'local/Programs/Clipivo/_internal/models/buffalo_l'
    for p in [bad,installed]:
        p.mkdir(parents=True)
        for name in NAMES:(p/name).write_bytes(b'fixture')
    paths=list(model_candidates(bad,home=tmp_path/'home',local=tmp_path/'local',roaming=tmp_path/'roaming'))
    assert paths[:2]==[bad,installed]


def test_cancelled_download_never_publishes_fixture(monkeypatch,tmp_path):
    payload=b'fixture';spec={'det_10g.onnx':(len(payload),hashlib.sha256(payload).hexdigest())}
    monkeypatch.setattr('v22.model_locator.MODEL_FILES',spec)
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**kw:io.BytesIO(payload))
    state={'cancel':False}
    def report(*args):state['cancel']=True
    with pytest.raises(InterruptedError):
        download_models(tmp_path,report,lambda:state['cancel'])
    assert not list(tmp_path.glob('*.onnx'))
    assert not list(tmp_path.glob('*.part'))


def test_mixed_provider_initialization_falls_back(monkeypatch,tmp_path):
    sessions=[]
    class Options:pass
    def session(path,sess_options,providers):
        sessions.append(tuple(providers))
        selected=providers[0] if 'det_10g' in path else 'CPUExecutionProvider'
        return SimpleNamespace(get_providers=lambda:[selected])
    ort=SimpleNamespace(get_available_providers=lambda:['CUDAExecutionProvider','CPUExecutionProvider'],
                        SessionOptions=Options,InferenceSession=session)
    monkeypatch.setitem(sys.modules,'onnxruntime',ort)
    engine=Engine(tmp_path,True)
    assert engine.device=='CPUExecutionProvider'
    assert not engine.gpu and 'fallback' in engine.warning
    assert sessions[-2:]==[('CPUExecutionProvider',),('CPUExecutionProvider',)]


def test_inference_exception_retries_on_cpu():
    engine=Engine.__new__(Engine);engine.gpu=True;engine.warning=''
    calls=[]
    def infer(img):
        calls.append(engine.gpu)
        if engine.gpu:raise RuntimeError('simulated GPU failure')
        return []
    engine._get=infer
    engine.load=lambda gpu:setattr(engine,'gpu',gpu)
    assert engine.get(None)==[] and calls==[True,False]
    assert 'CPU fallback' in engine.warning


def test_late_preview_cannot_overwrite_completed_project():
    pytest.importorskip('PySide6')
    pytest.importorskip('psutil')
    from studio.analyzer_page import AnalyzerPage
    completed={'version':2,'people':[]}
    q=queue.Queue()
    q.put((1,None,[],[],2,Path('old')))
    fake=SimpleNamespace(task=SimpleNamespace(live=q),scanning=False,_active=False,
                         folder=Path('completed'),data=completed)
    AnalyzerPage.poll(fake)
    assert fake.data is completed and q.empty()


def test_spatial_tiebreaker_stabilizes_ambiguous_recent_groups():
    groups=[dict(_sum=np.array([1.,0.]),observations=[dict(time=1,box_norm=[0,0,.3,.3])]),
            dict(_sum=np.array([.999,.02]),observations=[dict(time=1,box_norm=[.7,.7,1,1])])]
    idx=assign(groups,np.array([1.,0.]),set(),.45,box=[.01,.01,.31,.31],timestamp=1.5,step=.5)
    assert idx==0 and len(groups)==2
    assert groups[idx]['identity_status']=='uncertain'
    idx=assign(groups,np.array([1.,0.]),set(),.45,box=[.01,.01,.31,.31],timestamp=10,step=.5)
    assert idx==2


def test_failed_staged_save_preserves_previous_analysis(monkeypatch,tmp_path):
    data=dict(version=2,duration=5,sample_interval=.5,people=[group('1',1)])
    save_project(tmp_path,data)
    prior=(tmp_path/'analysis.json').read_bytes()
    data['people'][0]['name']='changed'
    original=Path.write_text
    def fail_txt(path,*a,**kw):
        if path.name.startswith('timeline.txt.'):raise OSError('simulated disk write failure')
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'write_text',fail_txt)
    with pytest.raises(OSError):save_project(tmp_path,data)
    assert (tmp_path/'analysis.json').read_bytes()==prior
    assert not list(tmp_path.glob('*.tmp'))


def test_import_v22_non_destructive_and_idempotent(monkeypatch,tmp_path):
    from core.character_store import CharacterStore
    import json
    monkeypatch.setenv('CLIPIVO_STUDIO_DATA',str(tmp_path))
    store=CharacterStore(tmp_path/'people',encryption_key=b'k'*32)
    legacy=tmp_path/'People_Library'/'legacy-id';legacy.mkdir(parents=True)
    source=legacy/'profile.json';source.write_text(json.dumps(dict(name='Legacy',embeddings=[[9,9]])))
    image=legacy/'face.jpg';image.write_bytes(b'fixture')
    before=source.read_bytes()
    profiles=Profiles(store)
    imported,skipped=profiles.import_v22(legacy.parent)
    assert len(imported)==1 and not skipped
    assert store.character(imported[0]).name=='Legacy'
    assert profiles.entries('new-model')==[]
    assert profiles.import_v22(legacy.parent)[0]==[]
    assert source.read_bytes()==before and image.read_bytes()==b'fixture'


def test_fixture_download_checksum_and_retry(monkeypatch,tmp_path):
    payload=b'valid model fixture';spec={'det_10g.onnx':(len(payload),hashlib.sha256(payload).hexdigest())}
    monkeypatch.setattr('v22.model_locator.MODEL_FILES',spec)
    transport=Mock(side_effect=[io.BytesIO(b'bad'),io.BytesIO(payload)])
    monkeypatch.setattr('urllib.request.urlopen',transport)
    with pytest.raises(RuntimeError):download_models(tmp_path)
    assert not list(tmp_path.glob('*.part'))
    download_models(tmp_path)
    assert (tmp_path/'det_10g.onnx').read_bytes()==payload
    download_models(tmp_path)
    assert transport.call_count==2


def test_real_video_decode_with_mock_inference(tmp_path):
    # Real OpenCV video IO; no real biometric model or GPU.
    source=tmp_path/'fixture.avi'
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,64))
    if not writer.isOpened():pytest.skip('MJPG encoder unavailable')
    for i in range(20):writer.write(np.full((64,64,3),i,np.uint8))
    writer.release()
    before=source.read_bytes()
    engine=Mock(device='mock-CPU',warning='')
    engine.get.return_value=[(np.array([1.,0.]),np.zeros((40,40,3),np.uint8),10.,(5,5,45,45),.9)]
    dest=tmp_path/'project'
    data=run(source,dest,None,dict(step=.5,filters=dict(background=False,static=False)),
             lambda *a:None,lambda:False,None,[],engine=engine)
    assert data['decoded_frames']==20
    assert data['analyzed_frames']==4==engine.get.call_count
    assert len(data['people'])==1
    assert data['duration']==pytest.approx(2,abs=.11)
    assert (dest/'analysis.json').exists()
    assert source.read_bytes()==before
