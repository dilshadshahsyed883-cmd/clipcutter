import json,copy,uuid
from pathlib import Path
import cv2
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QLabel,QPushButton,QFileDialog,QTableWidget,QTableWidgetItem,QComboBox,QDoubleSpinBox,QFormLayout,QDialog,QDialogButtonBox,QMessageBox,QInputDialog,QHeaderView
from v22.analyzer import atomic_json
from .storage import root
from .workers import Task
from .widgets import Preview
from .analyzer_page import button
from .footage import Index,inspect_video,build_plan,expand_plan
from .render import reconstruct

class ReplacementPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.reference=None;self.plan=None;self.index=Index();self.operation='';self.saved_plan=None
        self.task=Task(self);self.task.done.connect(self.done);self.task.failed.connect(self.error);self.task.progress.connect(self.progress);self.task.finished.connect(self.finished)
        l=QVBoxLayout(self);bar=QHBoxLayout();l.addLayout(bar);self.actions=[]
        for text,slot in [('Reference video',self.open_reference),('Index footage folder',self.index_folder),('Footage labels',self.labels),('Use analyzer identities',self.import_identities),('Match scenes',self.match),('Pick / rearrange clips',self.pick_clips),('Open plan',self.open_plan),('Save plan',self.save_plan)]:self.actions.append(button(text,slot,bar))
        self.cancel=button('Cancel',self.task.cancel,bar);self.cancel.setEnabled(False)
        self.heading=QLabel('Reference → reviewed footage → reconstruction');l.addWidget(self.heading)
        split=QSplitter();l.addWidget(split,1)
        a=QWidget();al=QVBoxLayout(a);al.addWidget(QLabel('Original scene'));self.original=Preview();al.addWidget(self.original,1);split.addWidget(a)
        b=QWidget();bl=QVBoxLayout(b);bl.addWidget(QLabel('Suggested replacement'));self.replacement=Preview();bl.addWidget(self.replacement,1);split.addWidget(b)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Scene','Start','End','Replacement','Score*','Review']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.itemSelectionChanged.connect(self.selection);l.addWidget(self.table,1)
        row=QHBoxLayout();l.addLayout(row);self.candidates=QComboBox();self.candidates.currentIndexChanged.connect(self.candidate_changed);row.addWidget(self.candidates,1)
        for text,slot in [('Approve',self.approve),('Reject',self.reject),('Manual footage',self.manual),('Trim start',self.trim),('Scene labels',self.scene_labels),('Missing report',self.report),('Render approved plan',self.render),('Open in CapCut',self.open_capcut)]:self.actions.append(button(text,slot,row))
        weights=QHBoxLayout();l.addLayout(weights);self.weights={}
        for name,value in [('identity',4),('activity',2),('visual',2),('framing',1),('duration',1),('aspect',1)]:
            weights.addWidget(QLabel(name.title()));spin=QDoubleSpinBox();spin.setRange(0,10);spin.setValue(value);spin.setSingleStep(.5);weights.addWidget(spin);self.weights[name]=spin
        self.status=QLabel('* Similarity score is a ranking, not a calibrated confidence. Hard cuts and visual histograms are estimates; semantic labels require review.');self.status.setWordWrap(True);l.addWidget(self.status)
    def run(self,operation,fn):
        if self.task.busy:return
        self.operation=operation
        for a in self.actions:a.setEnabled(False)
        self.cancel.setEnabled(True);self.task.start(fn)
    def finished(self):
        for a in self.actions:a.setEnabled(True)
        self.cancel.setEnabled(False)
    def progress(self,args):
        a,b=args[:2];self.status.setText(f'{self.operation}: {a:.1f} / {b:.1f} ({100*a/max(.001,b):.1f}%)')
    def error(self,message):self.status.setText(message);QMessageBox.warning(self,'Replacement Studio',message)
    def open_reference(self):
        p,_=QFileDialog.getOpenFileName(self,'Reference video','','Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)')
        if p:self.run('Analyze reference',lambda t:inspect_video(p,t.stop.is_set,t.report))
    def index_folder(self):
        p=QFileDialog.getExistingDirectory(self,'Folder of authorized replacement footage')
        if p:self.run('Index footage',lambda t:Index().index(p,t.stop.is_set,t.report))
    def done(self,result):
        if self.operation=='Analyze reference':
            self.reference=result;self.plan=None
            # Reuse a matching analyzer project's reliable identity labels and intervals.
            a=self.window.analyzer_page
            if a.data and a.data.get('source')==result['path']:
                for scene in result['scenes']:self.link_scene_people(scene,a.data)
            self.heading.setText(Path(result['path']).name+f"  •  {len(result['scenes'])} estimated scenes  •  {result['duration']:.2f}s");self.populate();self.show_video(self.original,result['path'],0)
        elif self.operation in ('Match scenes','Pick clips'):
            self.plan=result;self.populate()
            self.status.setText('Timeline created; approve each clip. '+ ' '.join(result.get('warnings',[])))
        elif self.operation=='Index footage':self.status.setText(f'Index saved: {len(result)} videos. Unchanged videos reuse cached descriptors. Add identity/activity/framing labels before matching.')
        elif self.operation=='CapCut':self.status.setText('Editable draft verified: '+result['folder']+'  •  Open it from CapCut Home → Projects.'+(' CapCut launched.' if result.get('launched') else ' Start CapCut manually.'))
        elif self.operation=='Render':self.status.setText('Validated reconstruction saved: '+str(result))
    @staticmethod
    def link_scene_people(scene,data,source_footage=False):
        groups=[g for g in data['people'] if not g.get('ignored') and not g.get('filtered') and any(x<scene['end'] and y>scene['start'] for x,y in g['segments'])]
        known=[g for g in groups if g.get('library_id') and g.get('identity_status') in ('matched','manual')]
        confirmed={str(g['library_id']) for g in known}
        unknown={f"unknown:{data['source']}:{g['id']}" for g in groups if g not in known}
        scene['people']=sorted(confirmed|unknown)
        if source_footage:
            # A partial appearance does not establish identity for the full source trim.
            covered=set()
            for identity in confirmed:
                at=scene['start']
                intervals=sorted((x,y) for g in known if str(g.get('library_id'))==identity for x,y in g['segments'])
                for x,y in intervals:
                    if x>at+1e-6:break
                    at=max(at,y)
                    if at>=scene['end']-1e-6:
                        covered.add(identity);break
            confirmed=covered
        scene['confirmed_people']=sorted(confirmed)

    def match(self):
        if not self.reference:return self.error('Open a reference video first.')
        media=self.index.all()
        if not media:return self.error('Index a footage folder first.')
        weights={k:v.value() for k,v in self.weights.items()}
        if sum(weights.values())<=0:return self.error('Set at least one positive matching weight.')
        from .storage import load_settings
        limits=load_settings().get('clip_limits',{})
        kwargs={}
        if limits.get('enabled'):
            kwargs=dict(clip_minimum=float(limits.get('minimum',2.5)),clip_maximum=float(limits.get('maximum',4.0)))
            if not 0<kwargs['clip_minimum']<=kwargs['clip_maximum']:return self.error('Invalid clip duration limits.')
        reference=copy.deepcopy(self.reference)
        def work(task):
            media=Index().all()
            if not media:raise ValueError('Index footage first.')
            return build_plan(reference,media,weights,**kwargs,cancel=task.stop.is_set)
        self.run('Match scenes',work)
    def populate(self):
        scenes=self.plan['rows'] if self.plan else [{'original':s} for s in (self.reference or {}).get('scenes',[])];self.table.blockSignals(True);self.table.setRowCount(len(scenes))
        for i,row in enumerate(scenes):
            s=row['original'];sel=row.get('selected');texts=[str(i+1),f"{s['start']:.3f}",f"{s['end']:.3f}",(Path(sel['path']).name+(f" + {len(sel['pieces'])-1} clips / {sel.get('speed',1):.2f}×" if sel.get('pieces') else '')) if sel else 'Missing / manual review',f"{sel['score']:.3f}" if sel and sel.get('score') is not None else 'Manual','Approved' if row.get('approved') else 'Review required']
            for j,text in enumerate(texts):self.table.setItem(i,j,QTableWidgetItem(text))
        self.table.blockSignals(False)
        if scenes:self.table.selectRow(0)
    def row(self):
        i=self.table.currentRow();return self.plan['rows'][i] if self.plan and 0<=i<len(self.plan['rows']) else None
    def selection(self):
        i=self.table.currentRow();row=self.row();self.candidates.blockSignals(True);self.candidates.clear()
        if i>=0 and self.reference:
            s=row['original'] if row else self.reference['scenes'][i];self.show_video(self.original,self.reference['path'],s['start'])
        if row:
            for c in row['candidates']:self.candidates.addItem(f"{Path(c['path']).name}  •  {c['start']:.2f}s  •  {c['score']:.3f}",c)
            if row.get('selected'):self.show_video(self.replacement,row['selected']['path'],row['selected'].get('trim_start',row['selected']['start']))
        self.candidates.blockSignals(False)
    def show_video(self,preview,path,t):
        cap=cv2.VideoCapture(str(path))
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
            if ok:preview.show_frame(frame)
        finally:cap.release()
    def candidate_changed(self,index):
        row=self.row();c=self.candidates.currentData()
        if row and c:row['selected']=dict(copy.deepcopy(c),trim_start=c['start'],speed=1.,target_duration=row['original']['end']-row['original']['start']);row['approved']=False;row['manual_review']=True;self.show_video(self.replacement,c['path'],c['start']);self.update_row()
    def update_row(self):
        i=self.table.currentRow();self.populate()
        if i>=0:self.table.selectRow(i)
    def approve(self):
        row=self.row()
        if not row or not row.get('selected'):return self.error('Choose replacement footage for this scene.')
        # Validate the selected scene using the same contract as rendering/export.
        if row['selected'].get('manual') and row['original'].get('people') and not set(row['original']['people']).issubset(set(row['selected'].get('confirmed_people',[]))):
            if QMessageBox.question(self,'Verify person identity','Confirm that every required person appears throughout this manual trim?')!=QMessageBox.Yes:return
            row['selected']['confirmed_people']=list(row['original']['people'])
        candidate=copy.deepcopy(row)
        duration=candidate['original']['end']-candidate['original']['start']
        candidate['original'].update(start=0.,end=duration)
        candidate.update(approved=True,manual_review=False)
        test=dict(self.plan,rows=[candidate],reference=dict(self.reference,duration=duration,scenes=[candidate['original']]))
        try:expand_plan(test)
        except (ValueError,KeyError,TypeError) as e:return self.error(str(e))
        row['approved']=True;row['manual_review']=False;self.update_row()
    def reject(self):
        row=self.row()
        if row:row['approved']=False;row['selected']=None;row['manual_review']=True;self.update_row()
    def manual(self):
        row=self.row()
        if not row:return
        p,_=QFileDialog.getOpenFileName(self,'Manual replacement','','Videos (*.mp4 *.mkv *.mov *.avi *.webm)')
        if not p:return
        cap=cv2.VideoCapture(p)
        try:fps=cap.get(cv2.CAP_PROP_FPS);duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps else 0
        finally:cap.release()
        if duration<row['original']['end']-row['original']['start']:return self.error('Replacement is too short for this scene.')
        required=list(row['original'].get('people',[]))
        if required:
            answer=QMessageBox.question(self,'Verify person identity','Have you personally verified that the selected footage contains every required person throughout the selected trim?')
            if answer!=QMessageBox.Yes:return
        row['selected']=dict(path=p,start=0,end=duration,trim_start=0.,target_duration=row['original']['end']-row['original']['start'],speed=1.,score=None,manual=True,confirmed_people=required)
        row['approved']=False;row['manual_review']=True;self.update_row()
    def trim(self):
        row=self.row()
        if not row or not row.get('selected'):return
        sel=row['selected']
        if sel.get('pieces'):return self.error('This scene combines clips. Select a single alternative or choose Manual footage to replace it.')
        needed=row['original']['end']-row['original']['start'];maximum=sel['end']-needed*sel.get('speed',1.)
        if maximum<sel['start']:return self.error('Replacement is too short.')
        value,ok=QInputDialog.getDouble(self,'Replacement trim','Start seconds',sel.get('trim_start',sel['start']),sel['start'],maximum,3)
        if ok:
            sel['trim_start']=value;row['approved']=False;row['manual_review']=True
            if sel.get('manual'):sel['confirmed_people']=[]  # A changed manual trim requires fresh confirmation.
            self.update_row()
    def edit_labels(self,scene):
        d=QDialog(self);d.setWindowTitle('Confirm scene labels: same IDs across videos; people must cover the entire source scene');l=QFormLayout(d);fields={}
        from PySide6.QtWidgets import QLineEdit
        for key in ['people','activity','environment','framing','angle']:
            v=', '.join(scene.get(key,[])) if key=='people' else scene.get(key,'');w=QLineEdit(v);fields[key]=w;l.addRow(key.title(),w)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);box.accepted.connect(d.accept);box.rejected.connect(d.reject);l.addRow(box)
        if d.exec():
            for key,w in fields.items():scene[key]=[s.strip() for s in w.text().split(',') if s.strip()] if key=='people' else w.text().strip()
            scene['confirmed_people']=list(scene['people'])
            return True
        return False
    def scene_labels(self):
        i=self.table.currentRow()
        if i<0 or not self.reference:return
        if self.plan and self.plan.get('mode')=='concat_picker':return self.error('Reference scene labels are unavailable in freely picked mode. Match scenes to return to the reference timeline.')
        scene=self.plan['rows'][i]['original'] if self.plan else self.reference['scenes'][i]
        if self.edit_labels(scene):
            self.reference['scenes'][i]=copy.deepcopy(scene)
            if self.plan:
                self.plan['reference']['scenes'][i]=copy.deepcopy(scene)
                self.plan['rows'][i].update(approved=False,manual_review=True,identity_required=list(scene['people']),selected=None,candidates=[])
            self.status.setText('Scene labels updated. Match scenes again to refresh candidates.');self.update_row()
    def labels(self):
        media=self.index.all()
        if not media:return self.error('Index footage first.')
        names=[m['path'] for m in media];name,ok=QInputDialog.getItem(self,'Footage labels','Video',names,0,False)
        if not ok:return
        m=media[names.index(name)];options=[f"{i+1}: {s['start']:.2f}–{s['end']:.2f}s" for i,s in enumerate(m['scenes'])];selected,ok=QInputDialog.getItem(self,'Footage scene','Scene',options,0,False)
        if ok and self.edit_labels(m['scenes'][options.index(selected)]):self.index.save(m);self.status.setText('Footage labels saved in persistent index.')
    def save_plan(self):
        if not self.plan:return
        p,_=QFileDialog.getSaveFileName(self,'Save replacement plan',str(root()/'replacement_plan.json'),'JSON (*.json)')
        if p:atomic_json(p,self.plan);self.saved_plan=p;self.status.setText('Plan saved: '+p)
    def open_plan(self):
        p,_=QFileDialog.getOpenFileName(self,'Open replacement plan',str(root()),'JSON (*.json)')
        if not p:return
        try:
            data=json.loads(Path(p).read_text(encoding='utf-8'))
            if data.get('version')!=1 or not isinstance(data.get('rows'),list):raise ValueError('Unsupported plan')
            self.plan=data;self.reference=data['reference'];self.saved_plan=p;self.populate()
        except Exception as e:self.error(str(e))
    def report(self):
        if not self.plan:return
        p,_=QFileDialog.getSaveFileName(self,'Missing footage report',str(root()/'missing_footage.txt'),'Text (*.txt)')
        if p:
            text='\n'.join(f"Scene {i+1}: {r['original']['start']:.3f}–{r['original']['end']:.3f}s | {'missing footage' if not r.get('selected') else 'approval required'}" for i,r in enumerate(self.plan['rows']) if not r.get('approved') or not r.get('selected'))
            Path(p).write_text(text or 'All scenes approved.',encoding='utf-8');self.status.setText('Report saved: '+p)
    def render(self):
        if not self.plan or any(not r.get('approved') or not r.get('selected') for r in self.plan['rows']):return self.error('Review and approve every scene before rendering.')
        try:expand_plan(self.plan)
        except (ValueError,KeyError,TypeError) as e:return self.error(str(e))
        d=QDialog(self);d.setWindowTitle('Reconstruct video');l=QFormLayout(d);audio=QComboBox();audio.addItems(['Original audio','No audio','Separate audio file']);l.addRow('Audio',audio);encoder=QComboBox();encoder.addItems(['libx264','h264_nvenc']);l.addRow('Encoder',encoder)
        resolution=QComboBox();resolution.addItems(['Original','1920 × 1080','1080 × 1920','1280 × 720']);l.addRow('Canvas (fit + pad)',resolution);fps=QDoubleSpinBox();fps.setRange(1,240);fps.setDecimals(3);fps.setValue(self.reference['fps']);l.addRow('Frames / second',fps)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);box.accepted.connect(d.accept);box.rejected.connect(d.reject);l.addRow(box)
        if not d.exec():return
        audio_file=None;mode=['original','none','external'][audio.currentIndex()]
        if mode=='external':
            audio_file,_=QFileDialog.getOpenFileName(self,'Separate authorized audio')
            if not audio_file:return
        p,_=QFileDialog.getSaveFileName(self,'Save reconstructed video','','Video (*.mp4)')
        if not p:return
        size=[(None,None),(1920,1080),(1080,1920),(1280,720)][resolution.currentIndex()];plan=copy.deepcopy(self.plan);rate=fps.value();enc=encoder.currentText()
        self.run('Render',lambda t:reconstruct(plan,p,*size,fps=rate,audio=mode,audio_file=audio_file,encoder=enc,cancel=t.stop.is_set,progress=t.report))

    def open_capcut(self):
        if not self.plan or any(not r.get('approved') or not r.get('selected') for r in self.plan['rows']):return self.error('Approve every scene first.')
        name,ok=QInputDialog.getText(self,'Open in CapCut','New editable project name',text='Clipivo Replacement')
        if not ok or not name.strip():return
        audio,ok=QInputDialog.getItem(self,'CapCut audio','Audio track',['Original audio','No audio','Separate audio file'],0,False)
        if not ok:return
        mode={'Original audio':'original','No audio':'none','Separate audio file':'external'}[audio];audio_file=None
        if mode=='external':
            audio_file,_=QFileDialog.getOpenFileName(self,'Authorized audio file')
            if not audio_file:return
        try:expand_plan(self.plan)
        except (ValueError,KeyError,TypeError) as e:return self.error(str(e))
        from .capcut import export_plan
        from .storage import load_settings
        cfg=load_settings();drafts=cfg.get('capcut_drafts','')
        plan=copy.deepcopy(self.plan)
        self.run('CapCut',lambda t:export_plan(plan,drafts,name.strip(),mode,audio_file,True,t.stop.is_set))

    def pick_clips(self):
        if not self.reference:return self.error('Open a reference video first to set the total timeline duration and audio.')
        from PySide6.QtWidgets import QSpinBox,QCheckBox,QLineEdit
        from .storage import load_settings,save_settings
        from .picker import build_picked_plan
        cfg=load_settings();d=QDialog(self);d.setWindowTitle('Concat clip picker — video selection logic');l=QFormLayout(d);fields={}
        for key,label,default in [('minimum','Minimum clip seconds',2.5),('maximum','Maximum clip seconds',4.)]:
            w=QDoubleSpinBox();w.setDecimals(3);w.setRange(.1,600);w.setValue(cfg.get('picker',{}).get(key,default));l.addRow(label,w);fields[key]=w
        seed=QSpinBox();seed.setRange(1,2147483647);seed.setValue(cfg.get('picker',{}).get('seed',1));l.addRow('Shuffle seed (change for new choices)',seed)
        cooldown=QSpinBox();cooldown.setRange(0,100);cooldown.setValue(cfg.get('picker',{}).get('cooldown',2));l.addRow('Source cooldown (clips)',cooldown)
        repeats=QCheckBox('Allow source reuse');repeats.setChecked(cfg.get('picker',{}).get('allow_repeats',True));l.addRow(repeats)
        weights=QLineEdit();weights.setText(', '.join(f'{k}={v}' for k,v in (cfg.get('picker',{}).get('group_weights') or {}).items()));weights.setPlaceholderText('Optional: Alex Eala=60, Osaka=40');l.addRow('Keyword weights (filename prefixes)',weights)
        note=QLabel('Builds a new shot order with random source trims and the same total duration. Review approvals reset. Reference scene boundaries are replaced for this picked timeline.');note.setWordWrap(True);l.addRow(note)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);box.accepted.connect(d.accept);box.rejected.connect(d.reject);l.addRow(box)
        if not d.exec():return
        try:
            options={k:w.value() for k,w in fields.items()};options.update(seed=seed.value(),cooldown=cooldown.value(),allow_repeats=repeats.isChecked());group_weights={}
            for pair in weights.text().split(','):
                if not pair.strip():continue
                name,value=pair.rsplit('=',1);value=float(value)
                if not name.strip() or not 0<=value<=100:raise ValueError('Keyword weights must be between 0 and 100')
                group_weights[name.strip()]=value
            reference=copy.deepcopy(self.reference)
            save_settings({'picker':dict(options,group_weights=group_weights)})
            def work(task):
                media=Index().all()
                if not media:raise ValueError('Index footage first.')
                return build_picked_plan(reference,media,**options,group_weights=group_weights or None,cancel=task.stop.is_set)
            self.run('Pick clips',work)
        except Exception as e:self.error(str(e))

    def import_identities(self):
        a=self.window.analyzer_page
        if not a.editable() or not a.data:return self.error('Analyze the footage video in Person Analyzer first. Save and match named profiles for cross-video identities.')
        source=a.data.get('source');m=next((m for m in self.index.all() if m['path']==source),None)
        if self.reference and self.reference['path']==source:
            for scene in self.reference['scenes']:self.link_scene_people(scene,a.data)
            self.plan=None;self.populate()
            if m is None:
                self.status.setText('Reference identities updated. Match scenes again.');return
        if m is None:return self.error('This analyzed video is not in the footage index yet.')
        for scene in m['scenes']:
            self.link_scene_people(scene,a.data,source_footage=True)
        self.index.save(m);self.status.setText('Analyzer identities linked. Unmatched people require manual confirmation.')
