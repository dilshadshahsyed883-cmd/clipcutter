import json,time,uuid,queue,shutil,os
from pathlib import Path
import cv2,psutil
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QPixmap,QIcon
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QLabel,QPushButton,QFileDialog,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QInputDialog,QMessageBox,QScrollArea,QSlider,QCheckBox,QDoubleSpinBox,QSpinBox,QFormLayout,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem)
from v22.analyzer import save_project,merge_groups,split_group,atomic_json,refresh
from v22.filters import DEFAULTS
from v22.model_locator import find_models,download_models,valid
from .storage import root,load_settings,save_settings,new_project,remember,Profiles
from .analysis import run,open_project
from .workers import Task
from .widgets import Preview,Timeline

def button(text,slot,layout):
    b=QPushButton(text);b.clicked.connect(slot);layout.addWidget(b);return b

def scroll(widget):
    s=QScrollArea();s.setWidgetResizable(True);s.setWidget(widget);return s

class AnalyzerPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.data=None;self.folder=None;self.video='';self.cap=None;self.position=0.;self.playing=False;self.solo=None;self.live_count=0;self.scanning=False;self.started=0.;self.cfg=load_settings();self.filters={**DEFAULTS,**self.cfg.get('filters',{}),'regions':self.cfg.get('filters',{}).get('regions',[])}
        self.task=Task(self);self.task.done.connect(self.completed);self.task.failed.connect(self.failed);self.task.progress.connect(self.progress);self.task.finished.connect(self.finished)
        layout=QVBoxLayout(self);head=QHBoxLayout();layout.addLayout(head)
        button('Open video',self.choose_video,head);button('Open project',self.choose_project,head);button('Recent',self.open_recent,head);self.file_label=QLabel('No video loaded');head.addWidget(self.file_label,1)
        self.analyze_button=button('Analyze people',self.analyze,head);self.cancel_button=button('Cancel',self.task.cancel,head);self.cancel_button.setEnabled(False)
        body=QSplitter();layout.addWidget(body,1);center=QWidget();cl=QVBoxLayout(center);self.preview=Preview();self.preview.regionAdded.connect(self.add_region);cl.addWidget(self.preview,1)
        transport=QHBoxLayout();cl.addLayout(transport);button('▶ / Ⅱ',self.toggle_play,transport);self.seekbar=QSlider(Qt.Horizontal);self.seekbar.setRange(0,10000);self.seekbar.sliderMoved.connect(lambda v:self.seek(v/10000*self.duration()));transport.addWidget(self.seekbar,1);self.clock=QLabel('0.00 s');transport.addWidget(self.clock)
        self.timeline=Timeline();self.timeline.seekRequested.connect(self.seek);cl.addWidget(scroll(self.timeline));body.addWidget(center)
        inspector=QWidget();inspector.setMinimumWidth(285);il=QVBoxLayout(inspector);il.addWidget(QLabel('Discovered people  •  Ctrl-click to select several'))
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Person','Seconds','State']);self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection);self.tree.itemSelectionChanged.connect(self.show_refs);il.addWidget(self.tree,1)
        row=QHBoxLayout();il.addLayout(row);button('Rename',self.rename,row);button('Merge',self.merge,row);button('Split',self.split,row)
        row=QHBoxLayout();il.addLayout(row);button('Ignore / Restore',self.ignore,row);button('Solo',self.toggle_solo,row);button('Delete',self.delete,row)
        row=QHBoxLayout();il.addLayout(row);button('Save person',self.save_person,row);button('Use in extractor',self.to_extractor,row)
        self.show_ignored=QCheckBox('Show ignored / filtered people');self.show_ignored.setChecked(True);self.show_ignored.toggled.connect(lambda _:self.refresh());il.addWidget(self.show_ignored)
        self.refs=QListWidget();self.refs.setViewMode(QListWidget.IconMode);self.refs.setMaximumHeight(145);self.refs.itemClicked.connect(lambda it:self.seek(it.data(Qt.UserRole)));il.addWidget(self.refs)
        row=QHBoxLayout();il.addLayout(row);button('Filters',self.filter_dialog,row);button('Ignore region',self.arm_region,row);button('Export files',self.export,row)
        body.addWidget(inspector);body.setSizes([950,340]);self.stats=QLabel('Ready  •  Local person analysis');self.stats.setWordWrap(True);layout.addWidget(self.stats)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(80);self.player_timer=QTimer(self);self.player_timer.timeout.connect(self.play_tick)
    def duration(self):return (self.data or {}).get('duration',getattr(self,'video_duration',0))
    def selected(self):
        ids={it.data(0,Qt.UserRole) for it in self.tree.selectedItems()};return [g for g in (self.data or {}).get('people',[]) if g['id'] in ids]
    def editable(self):return self.data is not None and not self.task.busy
    def choose_video(self):
        if self.task.busy:return
        path,_=QFileDialog.getOpenFileName(self,'Video','','Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)')
        if path:self.set_video(path)
    def set_video(self,path):
        self.pause();self.video=str(path);self.data=None;self.folder=None;self.solo=None;self.file_label.setText(Path(path).name)
        if self.cap:self.cap.release()
        self.cap=cv2.VideoCapture(self.video);fps=self.cap.get(cv2.CAP_PROP_FPS);self.video_duration=self.cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps>0 else 0;self.refresh();self.seek(0)
    def choose_project(self):
        if self.task.busy:return
        path,_=QFileDialog.getOpenFileName(self,'Open V2.2 / V2.3 project',str(root()/'Projects'),'Analysis (analysis.json)')
        if path:self.load(path)
    def open_recent(self):
        paths=load_settings().get('recent',[])
        if not paths:return
        selected,ok=QInputDialog.getItem(self,'Recent projects','Project',paths,0,False)
        if ok:self.load(selected)
    def load(self,path):
        if self.task.busy:return
        try:
            data=open_project(path);self.set_video(data['source']);self.data=data;self.folder=Path(path).parent;self.filters={**DEFAULTS,**data.get('filters',{})};self.preview.regions=self.filters.get('regions',[]);remember(path);self.refresh();self.seek(0)
        except Exception as e:self.failed(str(e))
    def analyze(self):
        if self.task.busy:return
        if not Path(self.video).is_file():return self.failed('Open a video first.')
        if self.window._video_job_running() or self.window.batch_page.is_running():return self.failed('Wait for extraction or batch processing to finish.')
        self.cfg=load_settings();models=find_models(self.cfg.get('models'))
        if not models:
            models=root()/'models/buffalo_l'
        # Existing compatible custom models are allowed without an InsightFace license assumption.
        if not self.cfg.get('custom_models') and not self.cfg.get('model_license_accepted'):
            msg='Default InsightFace buffalo_l weights are for non-commercial research. Commercial use requires a separate model license. Accept these terms for research use, or choose licensed compatible models in Settings.'
            if QMessageBox.question(self,'Face model terms',msg,QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
            save_settings({'model_license_accepted':True})
        self.pause();self.data=None;self.folder=new_project();self.started=time.monotonic();self.scanning=True;self.live_count=0;self.solo=None;self.refresh();self.analyze_button.setEnabled(False);self.cancel_button.setEnabled(True)
        cfg={**self.cfg,'filters':json.loads(json.dumps(self.filters))};folder=self.folder;video=self.video
        try:profiles=Profiles(self.window.character_store).entries()
        except Exception as e:return self.failed(str(e))
        def work(task):
            from .models import verified
            if valid(models) and not cfg.get('custom_models') and not verified(models):raise RuntimeError('Existing default models failed SHA-256 verification. Choose a verified model folder or remove damaged cached files and retry.')
            if not valid(models):download_models(models,lambda *args:task.report('download',*args),task.stop.is_set)
            return folder,run(video,folder,models,cfg,task.report,task.stop.is_set,task.preview,profiles)
        self.task.start(work)
    def progress(self,args):
        if args and args[0]=='download':
            _,name,n,total=args;self.stats.setText(f'Downloading {name}  •  {n/1048576:.1f} / {total/1048576:.1f} MB');return
        t,d,device,n,warning,*counts=args;elapsed=max(.001,time.monotonic()-self.started);speed=t/elapsed;frames,samples=counts if counts else (0,0);eta=(d-t)/speed if speed else 0
        self.stats.setText(f'{device}  •  {min(99,100*t/max(d,.001)):.1f}%  •  {frames:,} frames / {samples:,} samples  •  {samples/elapsed:.1f} analysis FPS  •  {speed:.2f}× realtime  •  elapsed {elapsed:.0f}s / ETA {max(0,eta):.0f}s  •  {n} people  •  CPU {psutil.cpu_percent():.0f}%  •  RAM {psutil.Process().memory_info().rss/1048576:.0f} MB'+('  •  '+warning if warning else ''))
    def completed(self,result):
        self.scanning=False
        while not self.task.live.empty():self.task.live.get_nowait()
        self.folder,self.data=result;remember(self.folder/'analysis.json');self.refresh();self.stats.setText(f"Analysis saved  •  {len(self.data['people'])} groups  •  {self.data['elapsed_seconds']:.1f}s  •  {self.data['device']}  •  sampled boundaries are estimates")
    def finished(self):self.analyze_button.setEnabled(True);self.cancel_button.setEnabled(False)
    def failed(self,msg):
        self.scanning=False;self.analyze_button.setEnabled(True);self.cancel_button.setEnabled(False);self.stats.setText(msg);QMessageBox.warning(self,'Person Analyzer',msg)
    def poll(self):
        try:
            t,frame,boxes,people,duration,folder=self.task.live.get_nowait()
            if not self.scanning:return
            self.data=dict(people=people,duration=duration);self.folder=folder;self.position=t;self.preview.show_frame(frame,boxes);self.refresh(live=True)
        except queue.Empty:pass
    def refresh(self,live=False):
        selected={g['id'] for g in self.selected()};self.tree.blockSignals(True);self.tree.clear()
        for g in (self.data or {}).get('people',[]):
            if not self.show_ignored.isChecked() and (g.get('ignored') or g.get('filtered')):continue
            state='Ignored' if g.get('ignored') else 'Filtered' if g.get('filtered') else g.get('identity_status','Unknown')
            item=QTreeWidgetItem([g['name'],f"{sum(b-a for a,b in g.get('segments',[])):.2f}",state]);item.setData(0,Qt.UserRole,g['id']);self.tree.addTopLevelItem(item);item.setSelected(g['id'] in selected)
        self.tree.blockSignals(False);self.timeline.data=self.data;self.timeline.position=self.position;self.timeline.solo=self.solo;self.timeline.ignored=self.show_ignored.isChecked();self.timeline.update();self.preview.regions=self.filters.get('regions',[]);self.preview.update();self.clock.setText(f'{self.position:.2f} s')
        if not live:self.show_refs()
    def show_refs(self):
        self.refs.clear()
        if self.task.busy:return
        gs=self.selected()
        if len(gs)!=1 or not self.folder:return
        for rel in gs[0].get('references',[]):
            pix=QPixmap(str(self.folder/rel));it=QListWidgetItem(QIcon(pix),Path(rel).name);o=next((o for o in gs[0]['observations'] if o['image']==rel),{});it.setData(Qt.UserRole,o.get('time',0));self.refs.addItem(it)
    def seek(self,t):
        if self.task.busy or not self.cap:return
        self.position=max(0,min(float(t),max(0,self.duration()-.001)));self.cap.set(cv2.CAP_PROP_POS_MSEC,self.position*1000);ok,frame=self.cap.read()
        if not ok:return
        boxes=[];tolerance=min(.15,(self.data or {}).get('sample_interval',.5)/2)
        for g in (self.data or {}).get('people',[]):
            if self.solo and g['id']!=self.solo:continue
            if not self.show_ignored.isChecked() and (g.get('ignored') or g.get('filtered')):continue
            for o in g.get('observations',[]):
                if abs(o['time']-self.position)<=tolerance and 'box_norm' in o:boxes.append((g['id'],g['name'],o['box_norm']))
        self.preview.show_frame(frame,boxes);self.timeline.position=self.position;self.timeline.update();self.seekbar.setValue(round(self.position/max(.001,self.duration())*10000));self.clock.setText(f'{self.position:.2f} / {self.duration():.2f} s')
        active={b[0] for b in boxes}
        from PySide6.QtGui import QColor,QBrush
        for i in range(self.tree.topLevelItemCount()):
            it=self.tree.topLevelItem(i);it.setForeground(0,QBrush(QColor('#ff7a5c' if it.data(0,Qt.UserRole) in active else '#f3f5f8')))
    def toggle_play(self):
        if self.task.busy:return
        if self.playing:self.pause();return
        self.playing=True;self.play_start=time.monotonic();self.play_offset=self.position;self.player_timer.start(40)
    def play_tick(self):
        t=self.play_offset+time.monotonic()-self.play_start
        if t>=self.duration():self.pause();return
        self.seek(t)
    def pause(self):self.playing=False;self.player_timer.stop()
    def persist(self):
        if self.data and self.folder:save_project(self.folder,self.data);self.refresh();self.seek(self.position)
    def rename(self):
        if not self.editable() or len(self.selected())!=1:return
        g=self.selected()[0];name,ok=QInputDialog.getText(self,'Rename','Person name',text=g['name'])
        if ok and name.strip():g['name']=name.strip();g['identity_status']='manual';self.persist()
    def merge(self):
        if not self.editable() or len(self.selected())<2:return
        merge_groups(self.data,[g['id'] for g in self.selected()]);self.persist()
    def split(self):
        if not self.editable() or len(self.selected())!=1:return
        g=self.selected()[0];dlg=QDialog(self);dlg.setWindowTitle('Split person: select observations');dlg.resize(550,500);l=QVBoxLayout(dlg);lst=QListWidget();lst.setSelectionMode(QAbstractItemView.ExtendedSelection);l.addWidget(lst)
        for o in g['observations']:lst.addItem(f"{o['time']:.3f}s  •  {o['image']}")
        image=QLabel();l.addWidget(image)
        lst.currentRowChanged.connect(lambda i:image.setPixmap(QPixmap(str(self.folder/g['observations'][i]['image'])).scaled(180,140,Qt.KeepAspectRatio)) if i>=0 else None)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);l.addWidget(box);box.accepted.connect(dlg.accept);box.rejected.connect(dlg.reject)
        if dlg.exec():
            try:split_group(self.data,g['id'],[lst.row(it) for it in lst.selectedItems()]);self.persist()
            except Exception as e:self.failed(str(e))
    def ignore(self):
        if not self.editable():return
        for g in self.selected():
            if g.get('ignored'):g['ignored']=False
            elif g.get('filtered'):g['force_include']=True
            else:g['ignored']=True
        self.persist()
    def delete(self):
        if not self.editable():return
        ids={g['id'] for g in self.selected()}
        if ids and QMessageBox.question(self,'Delete groups','Remove the selected groups? Reference files stay on disk.')==QMessageBox.Yes:self.data['people']=[g for g in self.data['people'] if g['id'] not in ids];self.persist()
    def toggle_solo(self):
        gs=self.selected();self.solo=None if self.solo else gs[0]['id'] if len(gs)==1 else None;self.refresh();self.seek(self.position)
    def save_person(self):
        if not self.editable() or len(self.selected())!=1:return
        try:Profiles(self.window.character_store).save(self.selected()[0],self.folder);self.stats.setText('Saved encrypted profile and references to People Library');self.window.people_page.refresh()
        except Exception as e:self.failed(str(e))
    def to_extractor(self):
        if not self.editable() or not self.selected():return
        from core.models import ClipRange
        self.window.open_video(Path(self.video));self.window._select_page(0)
        # Probe is asynchronous: transfer ranges once the same source is ready.
        from .picker import constrain_ranges
        cfg=load_settings().get('clip_limits',{})
        raw=[(a,b) for g in self.selected() for a,b in g['segments'] if not g.get('ignored')]
        if cfg.get('enabled'):
            raw,discarded=constrain_ranges(raw,cfg.get('minimum',2.5),cfg.get('maximum',4.))
            self.stats.setText(f'Clip limits applied; {discarded:.3f}s excluded because shorter than the minimum.')
        ranges=[ClipRange(round(a*1000),round(b*1000)) for a,b in raw]
        self.window._pending_analyzer_ranges=(str(Path(self.video).resolve()),ranges)
    def arm_region(self):
        if self.task.busy:return
        self.preview.armed=True;self.stats.setText('Drag a rectangle over the preview to exclude faces in that region.')
    def add_region(self,r):
        self.filters.setdefault('regions',[]).append(r);self.apply_filters()
    def apply_filters(self):
        save_settings({'filters':self.filters});self.preview.regions=self.filters.get('regions',[])
        if self.editable():self.data['filters']=self.filters;self.persist()
        self.preview.update()
    def filter_dialog(self):
        if self.task.busy:return
        d=QDialog(self);d.setWindowTitle('Reversible face filters');l=QFormLayout(d);bg=QCheckBox();bg.setChecked(self.filters['background']);static=QCheckBox();static.setChecked(self.filters['static']);l.addRow('Filter small / short / weak faces',bg);l.addRow('Filter static corner portraits (heuristic)',static)
        fields={}
        for key,label,maximum in [('min_face','Minimum face pixels',1000),('confidence','Minimum confidence',1),('min_duration','Minimum appearance seconds',1000)]:
            w=QDoubleSpinBox();w.setRange(0,maximum);w.setValue(self.filters[key]);l.addRow(label,w);fields[key]=w
        clear=QCheckBox('Clear manual ignore regions');l.addRow(clear);box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);l.addRow(box);box.accepted.connect(d.accept);box.rejected.connect(d.reject)
        if d.exec():
            self.filters.update({k:w.value() for k,w in fields.items()});self.filters.update(background=bg.isChecked(),static=static.isChecked())
            if clear.isChecked():self.filters['regions']=[]
            self.apply_filters()
    def export(self):
        if not self.editable():return
        dest=QFileDialog.getExistingDirectory(self,'Export JSON, CSV, TXT and references')
        if not dest:return
        try:
            self.persist();target=Path(dest)/('Clipivo_analysis_'+uuid.uuid4().hex[:8]);shutil.copytree(self.folder,target);self.stats.setText('Exported project and references: '+str(target))
        except Exception as e:self.failed(str(e))
    def shutdown(self):
        self.task.cancel();self.pause()
        if self.cap:self.cap.release()
