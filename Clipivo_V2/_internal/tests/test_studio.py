import copy,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from studio.footage import inspect_video,Index,build_plan,scene_candidates
from studio.render import reconstruct,verify
from studio.analysis import match_profiles,open_project
from studio.storage import Profiles
from core.character_store import CharacterStore
from v22.engine import Engine
from v22.model_locator import download_models

class StudioTests(unittest.TestCase):
    def test_uncertain_identity_is_not_named(self):
        d={'people':[{'id':'p','name':'Person 1','observations':[{'embedding':[1,0]}]}]}
        match_profiles(d,[{'id':'a','name':'A','embeddings':[[1,0]]},{'id':'b','name':'B','embeddings':[[.999,.001]]}]);self.assertEqual(d['people'][0]['name'],'Person 1');self.assertEqual(d['people'][0]['identity_status'],'uncertain')
    def test_reliable_identity_named(self):
        d={'people':[{'id':'p','name':'Person 1','observations':[{'embedding':[1,0]}]}]}
        match_profiles(d,[{'id':'a','name':'A','embeddings':[[1,0]]},{'id':'b','name':'B','embeddings':[[0,1]]}]);self.assertEqual(d['people'][0]['library_id'],'a')
    def test_gpu_runtime_cpu_fallback(self):
        e=Engine.__new__(Engine);e.gpu=True;e.warning='';calls=[]
        def get(img):
            calls.append(e.gpu)
            if e.gpu:raise RuntimeError('GPU device removed')
            return ['CPU result']
        def load(gpu):e.gpu=gpu
        e._get=get;e.load=load
        self.assertEqual(e.get(None),['CPU result']);self.assertEqual(calls,[True,False]);self.assertIn('GPU inference failed',e.warning)
    def test_models_reject_invalid_download(self):
        import io
        with tempfile.TemporaryDirectory() as tmp,patch('urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaises(RuntimeError):download_models(tmp)
            self.assertFalse(list(Path(tmp).glob('*.onnx')));self.assertFalse(list(Path(tmp).glob('*.part')))
    def test_models_download_retry_and_cache(self):
        import io,hashlib
        payload=b'valid fixture model';spec={'det_10g.onnx':(len(payload),hashlib.sha256(payload).hexdigest())}
        with tempfile.TemporaryDirectory() as tmp,patch('v22.model_locator.MODEL_FILES',spec),patch('urllib.request.urlopen',return_value=io.BytesIO(payload)) as call:
            download_models(tmp);self.assertEqual(call.call_count,1);download_models(tmp);self.assertEqual(call.call_count,1)
    def test_models_cancel_cleanup(self):
        import io
        with tempfile.TemporaryDirectory() as tmp,patch('urllib.request.urlopen',return_value=io.BytesIO(b'a')):
            with self.assertRaises(InterruptedError):download_models(tmp,cancel=lambda:True)
            self.assertFalse(list(Path(tmp).glob('*.part')))
    def test_project_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'analysis.json';path.write_text(json.dumps(dict(version=2,duration=2,sample_interval=.5,people=[dict(observations=[dict(image='../private.jpg')])])));
            with self.assertRaises(ValueError):open_project(path)
    def test_identity_requirement_blocks_wrong_people(self):
        s=dict(start=0,end=1,people=['A'],visual=[1,0]);ref=dict(path='ref',width=100,height=100,scenes=[s]);m=dict(path='other',width=100,height=100,scenes=[dict(start=0,end=3,people=['B'],visual=[1,0])]);self.assertEqual(scene_candidates(s,ref,[m]),[])
    def test_multi_person_requirement(self):
        s=dict(start=0,end=1,people=['A','B'],confirmed_people=['A','B'],visual=[1,0]);ref=dict(path='ref',width=100,height=100,scenes=[s]);m=dict(path='other',width=100,height=100,scenes=[dict(start=0,end=3,people=['A','B'],confirmed_people=['A','B'],visual=[1,0])]);self.assertEqual(len(scene_candidates(s,ref,[m])),1)
        m['scenes'][0].pop('confirmed_people');self.assertEqual(scene_candidates(s,ref,[m]),[])
    def test_no_automatic_approval(self):
        s=dict(start=0,end=1,people=[],visual=[1,0]);ref=dict(path='ref',width=100,height=100,scenes=[s]);m=dict(path='other',width=100,height=100,scenes=[dict(s,start=0,end=2)]);p=build_plan(ref,[m]);self.assertFalse(p['rows'][0]['approved']);self.assertTrue(p['rows'][0]['manual_review'])
    def test_short_footage_excluded(self):
        s=dict(start=0,end=3,people=[],visual=[1,0]);ref=dict(path='ref',width=100,height=100,scenes=[s]);m=dict(path='other',width=100,height=100,scenes=[dict(s,end=2)]);self.assertEqual(scene_candidates(s,ref,[m]),[])
    def test_repeat_penalty(self):
        s=dict(start=0,end=1,people=[],visual=[1,0]);ref=dict(path='ref',width=100,height=100,scenes=[s]);m=dict(path='other',width=100,height=100,scenes=[dict(s,end=3)]);a=scene_candidates(s,ref,[m])[0]['score'];b=scene_candidates(s,ref,[m],used={('other',0):2})[0]['score'];self.assertLess(b,a)
    def test_encrypted_profile_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'CLIPIVO_STUDIO_DATA':tmp}):
            store=CharacterStore(Path(tmp)/'people',encryption_key=b'k'*32);p=Profiles(store);ref=Path(tmp)/'face.jpg';ref.write_bytes(b'fixture');g=dict(id='p',name='Named',references=['face.jpg'],observations=[dict(embedding=[1,0],quality=1)])
            id=p.save(g,tmp);self.assertEqual(p.entries()[0]['name'],'Named');self.assertNotIn(b'embeddings',p.path(id).read_bytes())

class MediaIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.dir=Path(cls.temp.name);cls.sources=cls.dir/'sources';cls.sources.mkdir();cls.ref=cls.sources/'ref.mp4';cls.media=cls.sources/'footage.mp4'
        def ff(args):subprocess.run(['ffmpeg','-v','error','-y',*args],capture_output=True,check=True)
        ff(['-f','lavfi','-i','color=red:s=320x180:r=25:d=2','-f','lavfi','-i','color=blue:s=320x180:r=25:d=2','-f','lavfi','-i','sine=frequency=440:duration=4','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a','-c:v','libx264','-c:a','aac',str(cls.ref)])
        ff(['-f','lavfi','-i','testsrc2=s=180x320:r=25:d=6','-c:v','libx264',str(cls.media)])
        cls.reference=inspect_video(cls.ref)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def plan(self):
        return dict(version=1,reference=self.reference,rows=[dict(original=s,selected=dict(path=str(self.media),start=0,end=6,trim_start=i),approved=True,candidates=[]) for i,s in enumerate(self.reference['scenes'])])
    def test_hard_cut_detected(self):
        self.assertEqual(len(self.reference['scenes']),2);self.assertAlmostEqual(self.reference['scenes'][0]['end'],2,delta=.3)
    def test_persistent_index_no_reanalysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx=Index(Path(tmp)/'index.sqlite');idx.index(self.sources)
            with patch('studio.footage.inspect_video',side_effect=AssertionError('Should reuse cache')):self.assertEqual(len(idx.index(self.sources)),2)
    def test_real_render_original_audio_and_validation(self):
        out=self.dir/'rendered.mp4';reconstruct(self.plan(),out,audio='original');data=verify(out,4,25);self.assertTrue(any(s['codec_type']=='audio' for s in data['streams']));self.assertEqual(next(s for s in data['streams'] if s['codec_type']=='video')['width'],320)
    def test_real_render_no_audio(self):
        out=self.dir/'silent.mp4';reconstruct(self.plan(),out,audio='none');data=verify(out,4,25);self.assertFalse(any(s['codec_type']=='audio' for s in data['streams']))
    def test_external_audio(self):
        out=self.dir/'external.mp4';reconstruct(self.plan(),out,audio='external',audio_file=self.ref);data=verify(out,4,25);self.assertTrue(any(s['codec_type']=='audio' for s in data['streams']))
    def test_unapproved_blocks_before_output(self):
        p=self.plan();p['rows'][0]['approved']=False;out=self.dir/'blocked.mp4'
        with self.assertRaises(ValueError):reconstruct(p,out)
        self.assertFalse(out.exists())
    def test_cancel_preserves_existing_output(self):
        out=self.dir/'existing.mp4';out.write_bytes(b'existing')
        with self.assertRaises(InterruptedError):reconstruct(self.plan(),out,cancel=lambda:True)
        self.assertEqual(out.read_bytes(),b'existing')
    def test_source_overwrite_blocked(self):
        with self.assertRaises(ValueError):reconstruct(self.plan(),self.media)
    def test_real_capcut_editable_draft(self):
        from studio.capcut import export_plan
        result=export_plan(self.plan(),str(self.dir/'drafts'),name='Clipivo test',audio='original',launch=False)
        folder=Path(result['folder']);data=json.loads((folder/'draft_content.json').read_text());tracks=[t for t in data['tracks'] if t['type']=='video'];self.assertEqual(len(tracks),1);self.assertEqual(len(tracks[0]['segments']),2);self.assertEqual(result['verify_issues'],[]);self.assertAlmostEqual(data['duration']/1e6,4,places=2)
        # Re-export must create a unique folder, never replace an existing draft.
        other=export_plan(self.plan(),str(self.dir/'drafts'),name='Clipivo test',audio='none',launch=False);self.assertNotEqual(other['folder'],result['folder']);self.assertTrue(folder.is_dir())

if __name__=='__main__':unittest.main()
