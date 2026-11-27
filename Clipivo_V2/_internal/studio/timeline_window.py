"""Standalone Timeline Builder UI; no Extractor or Person Analyzer launch."""
import copy
import random
import uuid
from bisect import bisect_right
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLabel,QPushButton,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,
    QCheckBox,QDoubleSpinBox,QMessageBox,QInputDialog,QScrollArea,QSlider,QMenu)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from version import __version__
from ui.styles import app_stylesheet
from ui.about_dialog import AboutDialog
from .timeline_storage import root,load_settings,save_settings
from .workers import Task
from . import json_timeline as t
from .capcut import probe,export_plan

class TimelineStrip(QWidget):
    selected=Signal(int)
    def __init__(self):
        super().__init__();self.plan=None;self.active=-1;self.starts=[];self.missing_rows=set();self.setMinimumHeight(88)
    def set_plan(self,plan,missing_rows):
        self.plan=plan;self.missing_rows=set(missing_rows);self.starts=[r['start'] for r in (plan or {}).get('rows',[])];self.active=-1;self.update()
    def color(self,row,index):
        if not row.get('selected') or index in self.missing_rows:return QColor('#a53b3b')
        pid=row.get('assigned_person') or (row['people'][0] if row['people'] else '')
        from zlib import crc32
        return QColor.fromHsv(crc32(str(pid).encode())%360,155,215)
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#171b22'))
        if not self.plan:return
        total=self.plan['reference']['duration'];w=max(1,self.width())
        area=event.rect();first=max(0,bisect_right(self.starts,int(area.left()/w*total))-1);last=bisect_right(self.starts,int((area.right()+1)/w*total))
        for i in range(first,min(last+1,len(self.starts))):
            row=self.plan['rows'][i];x=round(row['start']/total*w);z=round(row['end']/total*w)
            painter.fillRect(x,24,max(1,z-x),46,self.color(row,i))
            if z-x>24:
                painter.setPen(QColor('#fff'));label='Gap' if not row.get('selected') or i in self.missing_rows else ', '.join(self.plan['people'][p]['name'] for p in row['people']) or (self.plan['people'][row['assigned_person']]['name'] if row.get('assigned_person') else 'Manual')
                painter.save();painter.setClipRect(x,24,z-x,46)
                painter.drawText(x+3,42,label);painter.drawText(x+3,61,f"{(row['end']-row['start'])/t.US:.2f}s");painter.restore()
            if i==self.active:
                painter.setPen(QColor('#ffffff'));painter.drawRect(x,24,max(1,z-x-1),45)
        painter.setPen(QColor('#dce3ee'))
        for i in range(6):
            x=round((w-1)*i/5);painter.drawText(min(x,max(0,w-70)),16,f'{total/t.US*i/5:.1f}s')
    def mousePressEvent(self,event):
        if not self.plan:return
        at=max(0,min(self.plan['reference']['duration']-1,int(event.position().x()/max(1,self.width())*self.plan['reference']['duration'])))
        i=bisect_right(self.starts,at)-1
        if i>=0:self.selected.emit(i)

class TimelineWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'Clipivo V{__version__} • Timeline Builder')
        self.setStyleSheet(app_stylesheet());self.resize(1280,850)
        self.imported=None;self.plan=None;self.folder=None;self.autosave_path=None;self.saved_path=None;self.operation='';self.pending_import=None;self.scan_cache=[]
        self.task=Task(self);self.task.done.connect(self.done);self.task.failed.connect(self.task_error);self.task.finished.connect(self.finished);self.task.progress.connect(self.progress)
        self.buttons=[]
        center=QWidget();center.setObjectName('root');self.setCentralWidget(center);layout=QVBoxLayout(center)
        bar=QHBoxLayout();layout.addLayout(bar)
        for name,fn in [('Import analysis.json',self.import_json),('Main footage folder',self.choose_folder),('Generate / regenerate',self.generate),('Open timeline',self.open_saved),('Save timeline',self.save),('Relink folder',self.relink),('Relink reference',self.relink_reference),('Recover autosave',self.recover),('About',lambda:AboutDialog(self).exec())]:
            self.button(bar,name,fn)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(self.task.cancel);self.cancel.setEnabled(False);bar.addWidget(self.cancel)
        self.heading=QLabel('Import an existing Person Analyzer JSON. No face analysis is performed.');self.heading.setWordWrap(True);layout.addWidget(self.heading)
        settings=QHBoxLayout();layout.addLayout(settings)
        self.minimum=self.spin(settings,'Min seconds',2.5,.1,600);self.maximum=self.spin(settings,'Max seconds',4,.1,600)
        self.fill=self.check(settings,'Same-person gap fill',True);self.gap=self.spin(settings,'Gap max (s)',1,0,60)
        self.speed_on=self.check(settings,'Speed adjust',True);self.slow=self.spin(settings,'Min speed',.8,.67,1);self.fast=self.spin(settings,'Max speed',1.2,1,1.5)
        self.reuse=self.check(settings,'Allow clip reuse',True)
        self.video=QVideoWidget();self.video.setMinimumHeight(150);layout.addWidget(self.video,2)
        self.player=QMediaPlayer(self);self.audio_out=QAudioOutput(self);self.audio_out.setMuted(True);self.player.setAudioOutput(self.audio_out);self.player.setVideoOutput(self.video)
        self.preview_end=None;self.preview_start=0;self.player.positionChanged.connect(self.preview_position)
        self.player.mediaStatusChanged.connect(self.preview_loaded)
        controls=QHBoxLayout();layout.addLayout(controls)
        self.button(controls,'Play / pause preview',self.play)
        self.zoom=QSlider(Qt.Horizontal);self.zoom.setRange(1,12);self.zoom.setValue(1);self.zoom.valueChanged.connect(self.set_zoom);controls.addWidget(QLabel('Timeline zoom'));controls.addWidget(self.zoom)
        self.autosave=self.check(controls,'Auto save',True);self.autosave.toggled.connect(lambda checked:self.persist() if checked else None)
        self.audio=self.check(controls,'Original audio in CapCut',True);self.audio.toggled.connect(self.audio_changed)
        self.button(controls,'Open in CapCut',self.capcut)
        self.strip=TimelineStrip();self.strip.selected.connect(self.select_row)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.strip);scroll.setFixedHeight(112);layout.addWidget(scroll)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Person','Start','End','Duration','Footage','Trim','Speed','Status'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.selection);self.table.setContextMenuPolicy(Qt.CustomContextMenu);self.table.customContextMenuRequested.connect(self.context_menu);layout.addWidget(self.table,3)
        edit=QHBoxLayout();layout.addLayout(edit)
        for name,fn in [('Replace / fill gap',self.manual),('Remove clip',self.remove),('Trim / speed',self.adjust)]:
            self.button(edit,name,fn)
        self.status=QLabel('Ready');self.status.setWordWrap(True);layout.addWidget(self.status)
    def button(self,row,name,fn):
        button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button);self.buttons.append(button);return button
    def spin(self,row,label,value,minimum,maximum):
        row.addWidget(QLabel(label));w=QDoubleSpinBox();w.setRange(minimum,maximum);w.setDecimals(3);w.setValue(value);row.addWidget(w);return w
    def check(self,row,label,value):
        w=QCheckBox(label);w.setChecked(value);row.addWidget(w);return w
    def run(self,operation,fn):
        if self.task.busy:return
        self.operation=operation;self.player.stop()
        for w in self.buttons+[self.table,self.strip,self.audio,self.autosave,self.minimum,self.maximum,self.fill,self.gap,self.speed_on,self.slow,self.fast,self.reuse]:w.setEnabled(False)
        self.cancel.setEnabled(True);self.status.setText(operation+'…')
        try:self.task.start(fn)
        except Exception as exc:self.finished();self.error(str(exc))
    def finished(self):
        from PySide6.QtCore import QTimer
        if self.task.busy:QTimer.singleShot(20,self.finished);return
        for w in self.buttons+[self.table,self.strip,self.audio,self.autosave,self.minimum,self.maximum,self.fill,self.gap,self.speed_on,self.slow,self.fast,self.reuse]:w.setEnabled(True)
        self.cancel.setEnabled(False)
    def progress(self,args):
        if len(args)>=2:self.status.setText(f'{self.operation}: {args[0]} / {args[1]}')
    def error(self,message):
        self.status.setText(str(message));QMessageBox.warning(self,'Timeline Builder',str(message))
    def task_error(self,message):
        if self.operation=='Import JSON' and message.startswith('ReferenceRelinkRequired:') and not self.task.stop.is_set():
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50,self.import_relocated);return
        self.error(message)
    def import_relocated(self):
        from PySide6.QtCore import QTimer
        if self.task.busy:QTimer.singleShot(50,self.import_relocated);return
        if not self.pending_import:return
        p=self.confirm_reference_file()
        if p:self.import_path(self.pending_import,p)
        else:self.status.setText('Import cancelled; existing timeline preserved.')
    def confirm_reference_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Select the same original reference video at its new location','','Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mts *.m2ts *.mpg *.mpeg)')
        if p and QMessageBox.question(self,'Confirm original video','Confirm this is the same original video, not a replacement. Metadata and known file size will be checked.')==QMessageBox.Yes:return p
        return None
    def relink_reference(self):
        if not self.imported:return self.error('Import analysis JSON or open a timeline first.')
        p=self.confirm_reference_file()
        if p:
            snapshot=copy.deepcopy(self.plan or self.imported)
            self.run('Relink reference',lambda task:t.relink_reference(snapshot,p,probe))
    def confirm_replace(self):
        return not self.plan or QMessageBox.question(self,'Replace timeline','Replace the current timeline? Save it first if needed.')==QMessageBox.Yes
    def import_json(self):
        if not self.confirm_replace():return
        p,_=QFileDialog.getOpenFileName(self,'Existing analysis.json','','JSON (*.json)')
        if p:self.import_path(p)
    def import_path(self,path,reference_path=None):
        self.pending_import=path;self.run('Import JSON',lambda task:t.load_analysis(path,probe,reference_path))
    def choose_folder(self):
        p=QFileDialog.getExistingDirectory(self,'Main footage folder',self.folder or '')
        if p:self.folder=p;self.status.setText('Selected: '+p+' • Root and all subfolders will be scanned.')
    def generate(self):
        if not self.imported:return self.error('Import Person Analyzer JSON first.')
        if not self.folder:self.choose_folder()
        if not self.folder or not self.confirm_replace():return
        try:cfg=t.options(self.minimum.value(),self.maximum.value(),self.fill.isChecked(),self.gap.value(),self.speed_on.isChecked(),self.slow.value(),self.fast.value(),self.reuse.isChecked())
        except ValueError as exc:return self.error(str(exc))
        imp=copy.deepcopy(self.imported);folder=self.folder;seed=random.SystemRandom().randrange(2**63);audio=self.audio.isChecked();cached=copy.deepcopy(self.scan_cache)
        def work(task):
            media,warnings=t.scan_folder(folder,imp['people'],probe,task.stop.is_set,task.report,cached)
            result=t.generate(imp,folder,media,cfg,seed,task.stop.is_set,warnings)
            result['audio']=audio;return result
        self.run('Generate',work)
    def new_autosave(self):
        self.autosave_path=root()/'Timelines'/('autosave-'+uuid.uuid4().hex+'.json');self.saved_path=None
    def done(self,result):
        if self.task.stop.is_set():self.status.setText('Cancelled; existing timeline preserved.');return
        if self.operation=='Import JSON':
            self.imported=result;self.plan=None;self.new_autosave();self.refresh()
            self.heading.setText(f"{Path(result['analysis_path']).name} • {len(result['people'])} people • {result['reference']['duration']/t.US:.3f}s")
            self.status.setText('JSON imported read-only. Choose footage and generate.')
        elif self.operation=='Relink reference':
            if result.get('format')==t.FORMAT:self.plan=result;self.imported['reference']=copy.deepcopy(result['reference']);self.refresh();self.persist()
            else:self.imported=result
            self.status.setText('Original reference relinked; analyzer timestamps unchanged.')
        elif self.operation in ('Generate','Relink'):
            self.plan=result;self.folder=result['root'];self.scan_cache=result.get('media',[])
            if self.operation=='Generate':self.new_autosave()
            self.refresh();self.persist()
            gaps=sum(not r.get('selected') or t.missing(r) for r in result['rows'])
            self.status.setText(f'{len(result["rows"])} rows • {gaps} gaps / missing. '+ ' | '.join(result.get('warnings',[])[:8]))
        elif self.operation=='CapCut':
            self.status.setText('Verified draft written: '+result['folder']+(' • CapCut launched.' if result.get('launched') else ' • Open CapCut Home → Projects.')+' '+ ' '.join(result.get('notes',[])))
    def refresh(self,index=None):
        self.player.stop();self.player.setSource(QUrl());self.preview_end=None
        self.table.blockSignals(True);self.table.setUpdatesEnabled(False);rows=(self.plan or {}).get('rows',[]);self.table.setRowCount(len(rows));missing_rows=set();checked={}
        for i,row in enumerate(rows):
            c=row.get('selected');key=(c['path'],tuple(c['stamp'])) if c else None
            if key is not None and key not in checked:checked[key]=t.missing(row)
            missing=checked.get(key,False)
            if missing:missing_rows.add(i)
            name=', '.join(self.plan['people'][p]['name'] for p in row['people']) or ('Gap fill: '+self.plan['people'][row['assigned_person']]['name'] if row.get('assigned_person') else 'Gap')
            vals=[name,f'{row["start"]/t.US:.3f}',f'{row["end"]/t.US:.3f}',f'{(row["end"]-row["start"])/t.US:.3f}',Path(c['path']).name if c else 'Gap',f'{c["trim"]/t.US:.3f}' if c else '—',f'{c["speed"]:.3f}x' if c else '—','Missing/changed media' if missing else row.get('reason') or 'Ready']
            for j,value in enumerate(vals):
                item=QTableWidgetItem(value)
                if missing or not c:item.setForeground(QColor('#ff7272'))
                elif j==0:item.setForeground(self.strip.color(row,i))
                self.table.setItem(i,j,item)
        self.table.setUpdatesEnabled(True);self.table.blockSignals(False);self.strip.set_plan(self.plan,missing_rows)
        if index is not None and 0<=index<len(rows):self.select_row(index)
        self.set_zoom(self.zoom.value())
    def set_zoom(self,value):self.strip.setMinimumWidth(700*value);self.strip.update()
    def select_row(self,i):self.table.selectRow(i);self.table.scrollToItem(self.table.item(i,0))
    def row(self):
        i=self.table.currentRow()
        return (i,self.plan['rows'][i]) if self.plan and 0<=i<len(self.plan['rows']) else (None,None)
    def selection(self):
        i,row=self.row();self.strip.active=-1 if i is None else i;self.strip.update()
        self.player.stop();self.player.setSource(QUrl());self.preview_end=None
        if not row or not row.get('selected') or t.missing(row):return
        c=row['selected'];self.preview_start=round(c['trim']/1000);self.preview_end=self.preview_start+round((row['end']-row['start'])*c['speed']/1000)
        self.player.setSource(QUrl.fromLocalFile(c['path']));self.player.setPlaybackRate(c['speed'])
    def preview_loaded(self,status):
        if status==QMediaPlayer.MediaStatus.LoadedMedia and self.preview_end is not None:self.player.setPosition(self.preview_start)
    def preview_position(self,position):
        if self.preview_end is not None and position>=self.preview_end:self.player.pause()
    def play(self):
        if self.preview_end is None:return
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:
            if self.player.position()>=self.preview_end or self.player.position()<self.preview_start:self.player.setPosition(self.preview_start)
            self.player.play()
    def context_menu(self,pos):
        item=self.table.itemAt(pos)
        if item is None or self.task.busy:return
        self.table.selectRow(item.row());menu=QMenu(self)
        for label,fn in [('Replace clip / fill gap',self.manual),('Remove clip',self.remove),('Trim / speed',self.adjust)]:menu.addAction(label,fn)
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def manual(self):
        i,row=self.row()
        if row is None:return
        choices={m['relative']:m['path'] for m in self.plan.get('media',[]) if Path(m['path']).is_file()}
        browse='[Browse other authorized footage]'
        if choices:
            label,ok=QInputDialog.getItem(self,'Scanned footage','Choose root or person-subfolder footage',[browse]+sorted(choices),0,False)
            if not ok:return
            p=choices.get(label)
        else:p=None
        if not p:p,_=QFileDialog.getOpenFileName(self,'Manual footage (including main folder)',self.folder or '', 'Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mts *.m2ts *.mpg *.mpeg)')
        if not p:return
        try:
            path=Path(p).resolve();info=probe(str(path));length=row['end']-row['start'];duration=min(t.us(info['duration']),t.us(info['videoDuration']))
            if not info['w'] or not info['h'] or abs(info.get('videoStart',0))>1e-6:raise ValueError('Invalid video stream')
            if length/t.US*self.plan['reference']['fps']<1-1e-6:raise ValueError('Shorter than one output frame; leave this row empty.')
            speed=t.fit_speed(duration,length,self.plan['options'])
            if speed is None:raise ValueError('Clip is too short within speed limits')
            plan_root=Path(self.plan['root']).resolve();relative=path.relative_to(plan_root).as_posix() if path.is_relative_to(plan_root) else None
            row['selected']=dict(path=str(path),relative=relative,stamp=t.stamp(path),duration=duration,trim=0,speed=speed,manual=True,person=None)
            row['reason']='';self.refresh(i);self.persist()
        except Exception as exc:self.error(str(exc))
    def remove(self):
        i,row=self.row()
        if row is None:return
        row['selected']=None;row['reason']='Manual gap';self.refresh(i);self.persist()
    def adjust(self):
        i,row=self.row()
        if not row or not row.get('selected'):return
        c=row['selected'];cfg=self.plan['options'];length=row['end']-row['start']
        if cfg['speed_adjust']:
            speed,ok=QInputDialog.getDouble(self,'Playback speed','Speed (x)',c['speed'],cfg['min_speed'],cfg['max_speed'],6)
            if not ok:return
        else:speed=1.
        available=c['duration']-t.us(length/t.US*speed)
        if available<0:return self.error('Clip too short at this speed.')
        trim,ok=QInputDialog.getDouble(self,'Source trim','Start seconds',min(c['trim'],available)/t.US,0,available/t.US,3)
        if not ok:return
        candidate=dict(c,trim=t.us(trim),speed=speed)
        if candidate['trim']+t.us(length/t.US*speed)>c['duration']:return self.error('Trim exceeds source.')
        row['selected']=candidate;self.refresh(i);self.persist()
    def audio_changed(self,value):
        if self.plan:self.plan['audio']=value;self.persist()
    def persist(self):
        if self.plan and self.autosave.isChecked() and self.autosave_path:
            try:t.save_plan(self.autosave_path,self.plan)
            except Exception as exc:self.status.setText('Autosave failed: '+str(exc))
    def save(self):
        if not self.plan:return
        p,_=QFileDialog.getSaveFileName(self,'Separate timeline JSON',self.saved_path or str(root()/'timeline.json'),'JSON (*.json)')
        if not p:return
        try:t.save_plan(p,self.plan);self.saved_path=p;self.status.setText('Saved: '+p)
        except Exception as exc:self.error(str(exc))
    def open_saved(self):
        if not self.confirm_replace():return
        p,_=QFileDialog.getOpenFileName(self,'Saved timeline','','JSON (*.json)')
        if p:self.restore_plan(p)
    def recover(self):
        if not self.confirm_replace():return
        folder=root()/'Timelines';folder.mkdir(parents=True,exist_ok=True)
        files=sorted(folder.glob('autosave-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if not files:return self.error('No autosaved timelines found.')
        p,_=QFileDialog.getOpenFileName(self,'Recover autosave',str(files[0]),'JSON (*.json)')
        if p:self.restore_plan(p)
    def restore_plan(self,p):
        try:
            loaded=t.open_plan(p);imported={k:loaded[k] for k in ('analysis_path','analysis_sha256','reference','people','intervals')}
            cfg=loaded['options'];folder=loaded['root']
            self.plan=loaded;self.imported=imported;self.folder=folder;self.scan_cache=loaded.get('media',[]);self.new_autosave();self.saved_path=p
            cfg=self.plan['options'];self.minimum.setValue(cfg['minimum']/t.US);self.maximum.setValue(cfg['maximum']/t.US);self.fill.setChecked(cfg['gap_fill']);self.gap.setValue(cfg['gap_max']/t.US);self.speed_on.setChecked(cfg['speed_adjust']);self.slow.setValue(cfg['min_speed']);self.fast.setValue(cfg['max_speed']);self.reuse.setChecked(cfg['reuse']);self.audio.setChecked(self.plan.get('audio',True))
            self.heading.setText(Path(p).name);self.refresh();self.persist();self.status.setText('Timeline reopened; missing footage is red.')
        except Exception as exc:self.error(str(exc))
    def relink(self):
        if not self.plan:return
        p=QFileDialog.getExistingDirectory(self,'Relocated main footage folder',self.folder or '')
        if not p:return
        if QMessageBox.question(self,'Relink','Relink by relative path, file size and duration. Confirm this is the same footage collection.')!=QMessageBox.Yes:return
        snapshot=copy.deepcopy(self.plan)
        self.run('Relink',lambda task:t.relink(snapshot,p,probe,task.stop.is_set))
    def capcut(self):
        if not self.plan:return self.error('Generate a timeline first.')
        if any(t.missing(r) for r in self.plan['rows']):return self.error('Relink or remove missing clips before export.')
        count=sum(not r.get('selected') for r in self.plan['rows'])
        if QMessageBox.question(self,'Review timeline',f'Export current selections with {count} empty gap rows and original duration?')!=QMessageBox.Yes:return
        cfg=load_settings();folder=cfg.get('capcut_drafts','')
        if not folder:
            folder=QFileDialog.getExistingDirectory(self,'CapCut projects folder (Cancel = auto detect)')
            if folder:save_settings({'capcut_drafts':folder})
        plan=copy.deepcopy(self.plan);name=Path(plan['reference']['path']).stem+' Timeline'
        self.run('CapCut',lambda task:export_plan(plan,folder,name,'original' if plan.get('audio',True) else 'none',launch=True,cancel=task.stop.is_set))
    def closeEvent(self,event):
        if self.task.busy:self.task.cancel();event.ignore();self.status.setText('Cancelling task; close again when finished.');return
        self.persist();self.player.stop();super().closeEvent(event)
