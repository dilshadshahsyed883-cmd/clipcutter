from pathlib import Path
from version import __version__
import sys,os
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QCheckBox,QDoubleSpinBox,QSpinBox,QLineEdit,QFileDialog,QMessageBox,QComboBox
from ui.main_window import MainWindow
from core.downloads import find_face_models
from v22.model_locator import find_models
from .storage import load_settings,save_settings,root
from .analyzer_page import AnalyzerPage,button
from .replacement_page import ReplacementPage

class SettingsPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;cfg=load_settings();l=QVBoxLayout(self);l.addWidget(QLabel('Analysis settings'));form=QFormLayout();l.addLayout(form)
        self.models=QLineEdit(cfg.get('models',''));row=QHBoxLayout();row.addWidget(self.models);button('Browse',self.browse,row);button('Auto detect',self.detect,row);form.addRow('Person Analyzer model folder',row)
        limits=cfg.get('clip_limits',{})
        self.limits_on=QCheckBox('Apply min/max to extraction, batch and reference matching (extraction: accurate cutting; Whole picture)');self.limits_on.setChecked(limits.get('enabled',False));form.addRow(self.limits_on)
        self.clip_min=QDoubleSpinBox();self.clip_min.setDecimals(3);self.clip_min.setRange(.1,600);self.clip_min.setValue(limits.get('minimum',2.5));form.addRow('Minimum clip seconds',self.clip_min)
        self.clip_max=QDoubleSpinBox();self.clip_max.setDecimals(3);self.clip_max.setRange(.1,600);self.clip_max.setValue(limits.get('maximum',4.));form.addRow('Maximum clip seconds',self.clip_max)
        self.custom=QCheckBox('I supply compatible SCRFD + ArcFace weights with my own license');self.custom.setChecked(cfg.get('custom_models',False));form.addRow(self.custom)
        self.gpu=QCheckBox('Use available GPU; fall back to CPU on runtime errors');self.gpu.setChecked(cfg.get('gpu',True));form.addRow(self.gpu)
        self.step=QDoubleSpinBox();self.step.setRange(.1,10);self.step.setSingleStep(.1);self.step.setValue(cfg.get('step',.5));form.addRow('Sampling interval (seconds)',self.step)
        self.threshold=QDoubleSpinBox();self.threshold.setDecimals(2);self.threshold.setRange(.1,.95);self.threshold.setSingleStep(.05);self.threshold.setValue(cfg.get('threshold',.45));form.addRow('Grouping cosine threshold',self.threshold)
        self.size=QComboBox();self.size.addItems(['320','640','960','1280']);self.size.setCurrentText(str(cfg.get('size',640)));form.addRow('Detector resolution',self.size)
        self.capcut_drafts=QLineEdit(cfg.get('capcut_drafts',''));row=QHBoxLayout();row.addWidget(self.capcut_drafts);button('Browse',self.browse_drafts,row);form.addRow('CapCut drafts folder (blank = auto)',row)
        self.notice=QLabel('Default InsightFace buffalo_l models: non-commercial research use. Commercial use needs separately licensed weights. This build supports compatible ONNX file replacement; it does not bundle model weights.\n\nPerson Analyzer can reuse compatible models or use its own licensed weights. Clip Extractor and Batch independently use the original Clipivo verified model discovery. Their recognition controls are in Extraction / media settings.\n\nGPU choice follows the installed ONNX Runtime provider: Windows DirectML by default; CUDA requires the compatible GPU runtime and drivers. GPU utilization is not reported unless measured.');self.notice.setWordWrap(True);l.addWidget(self.notice)
        row=QHBoxLayout();l.addLayout(row);button('Save analysis settings',self.save,row);button('Extraction / media settings',lambda:window.open_settings(),row);button('Open data folder',self.open_data,row);l.addStretch()
        button('Import V2.2 People Library',self.import_legacy,l)
    def browse_drafts(self):
        p=QFileDialog.getExistingDirectory(self,'CapCut Projects / com.lveditor.draft folder')
        if p:self.capcut_drafts.setText(p)
    def browse(self):
        p=QFileDialog.getExistingDirectory(self,'Folder containing det_10g.onnx and w600k_r50.onnx')
        if p:self.models.setText(p)
    def detect(self):
        if self.custom.isChecked():return QMessageBox.information(self,'Custom model','Choose your licensed model folder with Browse.')
        found=find_models(self.models.text()) or find_face_models()
        if found:self.models.setText(str(found))
    def save(self):
        if self.window._video_job_running() or self.window.batch_page.is_running():return QMessageBox.warning(self,'Settings','Wait for person analysis to finish before changing models.')
        if self.clip_min.value()>self.clip_max.value():return QMessageBox.warning(self,'Clip limits','Minimum cannot exceed maximum.')
        chosen=Path(self.models.text()) if self.models.text().strip() else None
        if self.custom.isChecked():
            from v22.model_locator import valid
            if not valid(chosen):return QMessageBox.warning(self,'Custom model','Choose a folder containing both compatible ONNX files.')
        elif chosen:
            from .models import verified
            try:ok=verified(chosen)
            except OSError as exc:return QMessageBox.warning(self,'Model verification',str(exc))
            if not ok:return QMessageBox.warning(self,'Model verification','Default weights failed checksum verification. Clear the folder for automatic discovery, or choose verified weights.')
        save_settings({'clip_limits':dict(enabled=self.limits_on.isChecked(),minimum=self.clip_min.value(),maximum=self.clip_max.value())})
        save_settings(dict(capcut_drafts=self.capcut_drafts.text(),models=self.models.text(),custom_models=self.custom.isChecked(),gpu=self.gpu.isChecked(),step=self.step.value(),threshold=self.threshold.value(),size=int(self.size.currentText())))
        # Analyzer settings must never override the upstream extractor's model engine.
        QMessageBox.information(self,'Settings','Settings saved for future analyses.')
    def import_legacy(self):
        if self.window._video_job_running() or self.window.batch_page.is_running():return QMessageBox.warning(self,'People Library','Finish active work before importing profiles.')
        folder=QFileDialog.getExistingDirectory(self,'Select V2.2 People_Library',str(root()/'People_Library'))
        if not folder:return
        try:
            from .storage import Profiles
            imported,skipped=Profiles(self.window.character_store).import_v22(folder)
            self.window.people_page.refresh()
            QMessageBox.information(self,'V2.2 profile import',f'Imported {len(imported)} profiles; skipped {len(skipped)}. Original files are unchanged. Embeddings will be rebuilt during analysis.'+('\\n'+'\\n'.join(skipped[:15]) if skipped else ''))
        except Exception as exc:QMessageBox.warning(self,'Profile import failed',str(exc))
    def open_data(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root())))

class StudioWindow(MainWindow):
    def __init__(self,*args,**kwargs):
        self.studio_ready=False;self._pending_analyzer_ranges=None
        super().__init__(*args,**kwargs)
        self.analyzer_page=AnalyzerPage(self);self.replacement_page=ReplacementPage(self);self.studio_settings=SettingsPage(self)
        self.pages.addWidget(self.analyzer_page);self.pages.addWidget(self.replacement_page);self.pages.addWidget(self.studio_settings)
        self.page_tabs.blockSignals(True)
        while self.page_tabs.count():self.page_tabs.removeTab(0)
        for name in ['Clip Extractor','Person Analyzer','Replacement Studio','Batch','People Library','Settings']:self.page_tabs.addTab(name)
        self.page_tabs.setCurrentIndex(0);self.page_tabs.blockSignals(False);self.studio_ready=True
        for key,fn in [('video_page',lambda:self._select_page(0)),('filters_page',self._open_filters_dialog),('batch_page',lambda:self._select_page(3)),('people_page',lambda:self._select_page(4)),('settings',lambda:self._select_page(5))]:
            self.actions[key].triggered.disconnect();self.actions[key].triggered.connect(fn)
        self.setStyleSheet(self.styleSheet()+'''QTreeWidget,QTableWidget,QListWidget {background:#1e222a;alternate-background-color:#252c35;color:#f3f5f8;border:1px solid #333b48;} QHeaderView::section {background:#272c35;color:#ccd3db;padding:5px;border:1px solid #333b48;} QTreeWidget::item:selected,QTableWidget::item:selected,QListWidget::item:selected {background:#4e3c35;color:#ffffff;} QScrollArea {border:1px solid #333b48;background:#14161b;}''')
        self.setWindowTitle(f'Clipivo V{__version__} • Unified Video Intelligence Studio');self._set_video_controls_enabled(False)
        self.transfer_timer=QTimer(self);self.transfer_timer.timeout.connect(self.transfer_ranges);self.transfer_timer.start(200)
    def _select_page(self,index):
        if not getattr(self,'studio_ready',False):return super()._select_page(index)
        mapping={0:0,1:3,2:4,3:1,4:2,5:5}
        if index not in mapping:return
        self._content_tab=index;self.pages.setCurrentIndex(mapping[index]);self.page_tabs.blockSignals(True);self.page_tabs.setCurrentIndex(index);self.page_tabs.blockSignals(False)
        if index==3:self.batch_page.refresh_characters()
        if index==0:self.video_job.refresh_people()
        if index==1 and self.video_info and not self.analyzer_page.video:self.analyzer_page.set_video(self.video_info.path)
        if index==4:self.people_page.refresh()
    def _filters_changed(self,filters,persist=True):
        super()._filters_changed(filters,persist)
        if getattr(self,'studio_ready',False):self.page_tabs.setTabText(1,'Person Analyzer')
    def _set_video_controls_enabled(self,enabled):
        super()._set_video_controls_enabled(enabled)
        if getattr(self,'studio_ready',False):
            for index in range(6):self.page_tabs.setTabEnabled(index,True)
    def _open_filters_dialog(self):
        if not hasattr(self,'filters_dialog') or not self.video_info:return
        self.filters_page.show_manager();self.filters_page.set_source_frame(self.preview.source,self.current_ms,refresh=False);self.filters_dialog.show();self.filters_dialog.raise_();self.filters_dialog.activateWindow()
    def _filters_dialog_closed(self):
        if getattr(self,'studio_ready',False):self.page_tabs.setCurrentIndex(self._content_tab)
        else:super()._filters_dialog_closed()
    def request_analyzer_ranges(self,path,ranges):
        path=Path(path).resolve()
        if not path.is_file() or not ranges:
            QMessageBox.warning(self,'Transfer clips','Source video or eligible clips are missing.');return False
        if self._video_job_running() or self.batch_page.is_running() or any(w and w.isRunning() for w in (self.probe_worker,self.find_worker)):
            QMessageBox.warning(self,'Transfer clips','Wait for the active video job to finish.');return False
        self._pending_analyzer_ranges=None
        if self.video_info and self.video_info.path.resolve()==path:
            return self._load_transferred(ranges)
        previous=self.probe_worker
        self.open_video(path)
        if self.probe_worker is previous:return False
        self._pending_analyzer_ranges=(path,ranges,self.probe_worker)
        return True
    def _video_open_failed(self,detail):
        self._pending_analyzer_ranges=None
        super()._video_open_failed(detail)
    def transfer_ranges(self):
        if not self._pending_analyzer_ranges:return
        path,ranges,worker=self._pending_analyzer_ranges
        if self.probe_worker is not worker:
            self._pending_analyzer_ranges=None;return
        if worker.isRunning():return
        self._pending_analyzer_ranges=None
        if not self.video_info or self.video_info.path.resolve()!=path:return
        if self._video_job_running() or self.batch_page.is_running():return
        self._load_transferred(ranges)
    def _load_transferred(self,ranges):
        from core.project_state import load_ranges,save_ranges
        path=self.video_info.path
        existing=load_ranges(path)
        if existing and existing!=ranges:
            if QMessageBox.question(self,'Replace extractor clips','Replace existing extractor clip ranges with the selected person appearances?',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return False
        try:save_ranges(path,ranges)
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'Transfer failed',str(exc));return False
        self.right_panel.set_clips(ranges)
        self.timeline.detections=[r.start_ms for r in ranges]
        self.timeline.update()
        return True
    def _video_job_running(self):
        upstream=super()._video_job_running()
        return upstream or (getattr(self,'studio_ready',False) and (self.analyzer_page.busy or self.replacement_page.busy))
    def closeEvent(self,event):
        if getattr(self,'studio_ready',False):
            tasks=[self.analyzer_page.task,self.replacement_page.task]
            if self.analyzer_page.busy or self.replacement_page.busy or any(t.busy for t in tasks):
                self.analyzer_page.cancel_analysis()
                for t in tasks:t.cancel()
                event.ignore();self.statusBar().showMessage('Cancelling active work; close again when it finishes.');return
            self.analyzer_page.shutdown()
        super().closeEvent(event)
