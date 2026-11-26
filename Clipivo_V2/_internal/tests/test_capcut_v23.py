"""Native CapCut source-level regressions; never launches CapCut or packages an EXE."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from studio.capcut import export_plan, request_from_plan

NODE=shutil.which('node')
BRIDGE=Path(__file__).resolve().parents[1]/'studio'/'capcut_bridge.js'
WRITER=BRIDGE.with_name('capcut-draft.js')


@unittest.skipUnless(NODE, 'Installed Node required; do not bootstrap during tests')
class CapCutV23Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.drafts=self.root/'drafts'
        self.drafts.mkdir()
        self.video=self.root/'source.mp4'
        self.other=self.root/'second.mp4'
        self.external=self.root/'audio.wav'
        # Probe is mocked here to isolate the real Node writer from FFmpeg and Windows.
        # The writer copies these bytes; this does not test playable media.
        for p in (self.video,self.other,self.external):
            p.write_bytes(p.name.encode())
        self.probes={
            str(self.video):dict(duration=5,w=1280,h=720,hasAudio=True),
            str(self.other):dict(duration=5,w=1280,h=720,hasAudio=False),
            str(self.external):dict(duration=5,w=0,h=0,hasAudio=True),
        }
        patcher=patch('studio.capcut.probe',side_effect=lambda p:self.probes[str(p)])
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher=patch('studio.capcut.find_node',return_value=NODE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def plan(self):
        first=dict(path=str(self.video),start=.25,end=3,trim_start=.5,
                   target_duration=1.123456,speed=.8)
        second=dict(path=str(self.other),start=.1,end=3,trim_start=.25,
                    target_duration=.876544,speed=1.25)
        selected=dict(first,pieces=[first,second],gap_fill=True)
        return dict(version=1,reference=dict(path=str(self.video),duration=2,
            width=1280,height=720,fps=30),rows=[
            dict(original=dict(start=0,end=2,people=['person']),selected=selected,approved=True)])

    def run_export(self,mode='original',audio_file=None):
        return export_plan(self.plan(),str(self.drafts),'Reviewed timeline',mode,audio_file,False)

    def read(self,result):
        folder=Path(result['folder'])
        c=json.loads((folder/'draft_content.json').read_text(encoding='utf-8'))
        nested=json.loads((folder/'Timelines'/c['id']/'draft_content.json').read_text(encoding='utf-8'))
        self.assertEqual(c,nested)
        self.assertEqual(c['duration'],2_000_000)
        self.assertEqual(result['verify_issues'],[])
        self.assertIn('Home',result['home_instruction'])
        return c

    def test_multi_piece_speed_precision_and_same_file_audio(self):
        result=self.run_export()
        c=self.read(result)
        clips=c['tracks'][0]['segments']
        self.assertEqual(len(clips),2)
        self.assertEqual([s['target_timerange'] for s in clips],[
            dict(start=0,duration=1123456),dict(start=1123456,duration=876544)])
        self.assertEqual([s['source_timerange'] for s in clips],[
            dict(start=500000,duration=898765),dict(start=250000,duration=1095680)])
        speeds={m['id']:m['speed'] for m in c['materials']['speeds']}
        for seg,expected in zip(clips,(.8,1.25)):
            self.assertEqual(seg['speed'],expected)
            self.assertEqual([speeds[r] for r in seg['extra_material_refs'] if r in speeds],[expected])
            self.assertEqual(seg['volume'],0)
        audio=c['tracks'][1]['segments'][0]
        self.assertNotEqual(audio['material_id'],clips[0]['material_id'])
        self.assertEqual(audio['target_timerange'],dict(start=0,duration=2000000))
        self.assertEqual(c['materials']['audios'][0]['path'],c['materials']['videos'][0]['path'])

    def test_optional_audio_and_unique_unchanged_drafts(self):
        existing=self.drafts/'Reviewed timeline'
        existing.mkdir()
        sentinel=existing/'draft_content.json'
        sentinel.write_bytes(b'existing project must not be changed')
        first=self.run_export('none')
        snapshot={p.relative_to(first['folder']):p.read_bytes() for p in Path(first['folder']).rglob('*') if p.is_file()}
        self.assertEqual([t['type'] for t in self.read(first)['tracks']],['video'])
        second=self.run_export('external',str(self.external))
        c=self.read(second)
        self.assertEqual([t['type'] for t in c['tracks']],['video','audio'])
        self.assertTrue(c['materials']['audios'][0]['path'].endswith('.wav'))
        self.assertNotEqual(first['folder'],second['folder'])
        self.assertEqual(sentinel.read_bytes(),b'existing project must not be changed')
        for p,data in snapshot.items():
            self.assertEqual((Path(first['folder'])/p).read_bytes(),data)

    def test_invalid_plan_does_not_publish(self):
        p=self.plan()
        p['rows'][0]['selected']['pieces'][1]['target_duration']-=.01
        with self.assertRaisesRegex(ValueError,'gap-fill'):
            request_from_plan(p,audio='none')
        p=self.plan()
        p['rows'][0]['selected']['pieces'][0]['trim_start']=.1
        with self.assertRaisesRegex(ValueError,'source trim'):
            request_from_plan(p,audio='none')
        with self.assertRaisesRegex(ValueError,'external audio'):
            request_from_plan(self.plan(),audio='external')
        self.probes[str(self.external)]['duration']=1
        with self.assertRaisesRegex(ValueError,'shorter'):
            request_from_plan(self.plan(),audio='external',audio_file=self.external)
        self.assertEqual(list(self.drafts.iterdir()),[])

    def test_nested_corruption_detected(self):
        result=self.run_export('none')
        folder=Path(result['folder'])
        nested=folder/'Timelines'/result['timelineId']/'draft_content.json'
        data=json.loads(nested.read_text(encoding='utf-8'))
        data['duration']-=1
        nested.write_text(json.dumps(data),encoding='utf-8')
        request=request_from_plan(self.plan(),audio='none')
        code=("const e=require(process.argv[1]); const r=JSON.parse(process.argv[2]);"
              "const p=e.makePlan(r.request.payload,r.request.media);"
              "console.log(JSON.stringify(e.verifyStrictProject(r.result.folder,p,r.result.files)));")
        run=subprocess.run([NODE,'-e',code,str(WRITER),json.dumps(dict(request=request,result=result))],
                           check=True,capture_output=True,text=True)
        self.assertTrue(any('Nested timeline differs' in s for s in json.loads(run.stdout)))

    def test_detect_custom_drafts_and_missing_path(self):
        capcut=self.root/'CapCut'
        config=capcut/'User Data'/'Config'
        config.mkdir(parents=True)
        custom=self.root/'custom drafts'
        custom.mkdir()
        setting=config/'globalSetting'
        code="console.log(JSON.stringify(require(process.argv[1]).detect()));"
        def detect():
            result=subprocess.run([NODE,'-e',code,str(WRITER)],env=dict(os.environ,ZS_CAPCUT_ROOT=str(capcut)),
                                  check=True,capture_output=True,text=True)
            return json.loads(result.stdout)
        setting.write_text(f'currentCustomDraftPath="{custom}"\n',encoding='utf-8')
        self.assertEqual(Path(detect()['draftsRoot']),custom)
        setting.write_text(f'currentCustomDraftPath={custom}/missing\n',encoding='utf-8')
        self.assertTrue(detect()['draftsSettingError'])
