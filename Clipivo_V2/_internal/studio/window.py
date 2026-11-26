from pathlib import Path
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
        self.models=QLineEdit(cfg.get('models',''));row=QHBoxLayout();row.addWidget(self.models);button('Browse',self.browse,row);button('Auto detect',self.detect,row);form.addRow('Model folder',row)
        limits=cfg.get('clip_limits',{})
        self.limits_on=QCheckBox('Apply min/max to every extractor and batch export (accurate cutting; Whole picture)');self.limits_on.setChecked(limits.get('enabled',False));form.addRow(self.limits_on)
        self.clip_min=QDoubleSpinBox();self.clip_min.setDecimals(3);self.clip_min.setRange(.1,600);self.clip_min.setValue(limits.get('minimum',2.5));form.addRow('Minimum clip seconds',self.clip_min)
        self.clip_max=QDoubleSpinBox();self.clip_max.setDecimals(3);self.clip_max.setRange(.1,600);self.clip_max.setValue(limits.get('maximum',4.));form.addRow('Maximum clip seconds',self.clip_max)
        self.custom=QCheckBox('I supply compatible SCRFD + ArcFace weights with my own license');self.custom.setChecked(cfg.get('custom_models',False));form.addRow(self.custom)
        self.gpu=QCheckBox('Use available GPU; fall back to CPU on runtime errors');self.gpu.setChecked(cfg.get('gpu',True));form.addRow(self.gpu)
        self.step=QDoubleSpinBox();self.step.setRange(.1,10);self.step.setSingleStep(.1);self.step.setValue(cfg.get('step',.5));form.addRow('Sampling interval (seconds)',self.step)
        self.threshold=QDoubleSpinBox();self.threshold.setDecimals(2);self.threshold.setRange(.1,.95);self.threshold.setSingleStep(.05);self.threshold.setValue(cfg.get('threshold',.45));form.addRow('Grouping cosine threshold',self.threshold)
        self.size=QComboBox();self.size.addItems(['320','640','960','1280']);self.size.setCurrentText(str(cfg.get('size',640)));form.addRow('Detector resolution',self.size)
        self.capcut_drafts=QLineEdit(cfg.get('capcut_drafts',''));row=QHBoxLayout();row.addWidget(self.capcut_drafts);button('Browse',self.browse_drafts,row);form.addRow('CapCut drafts folder (blank = auto)',row)
        self.notice=QLabel('Default InsightFace buffalo_l models: non-commercial research use. Commercial use needs separately licensed weights. This build supports compatible ONNX file replacement; it does not bundle model weights.\n\nFace models are reused from your Clipivo installation when compatible. The original installed application remains independent.\n\nGPU choice follows the installed ONNX Runtime provider: Windows DirectML by default; CUDA requires the compatible GPU runtime and drivers. GPU utilization is not reported unless measured.');self.notice.setWordWrap(True);l.addWidget(self.notice)
        row=QHBoxLayout();l.addLayout(row);button('Save analysis settings',self.save,row);button('Extraction / media settings',lambda:window.open_settings(),row);button('Open data folder',self.open_data,row);l.addStretch();self.detect()
    def browse_drafts(self):
        p=QFileDialog.getExistingDirectory(self,'CapCut Projects / com.lveditor.draft folder')
        if p:self.capcut_drafts.setText(p)
    def browse(self):
        p=QFileDialog.getExistingDirectory(self,'Folder containing det_10g.onnx and w600k_r50.onnx')
        if p:self.models.setText(p)
    def detect(self):
        found=find_models(self.models.text()) or find_face_models()
        if found:self.models.setText(str(found))
    def save(self):
        if self.window.analyzer_page.busy:return QMessageBox.warning(self,'Settings','Wait for person analysis to finish before changing models.')
        if self.clip_min.value()>self.clip_max.value():return QMessageBox.warning(self,'Clip limits','Minimum cannot exceed maximum.')
        save_settings({'clip_limits':dict(enabled=self.limits_on.isChecked(),minimum=self.clip_min.value(),maximum=self.clip_max.value())})
        save_settings(dict(capcut_drafts=self.capcut_drafts.text(),models=self.models.text(),custom_models=self.custom.isChecked(),gpu=self.gpu.isChecked(),step=self.step.value(),threshold=self.threshold.value(),size=int(self.size.currentText())))
        # Reuse selected model folder in upstream extraction as well.
        self.window.face_engine.model_dir=Path(self.models.text()) if self.models.text() else None
        self.window.face_engine._application=None
        QMessageBox.information(self,'Settings','Settings saved for future analyses.')
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
        self.setWindowTitle('Clipivo V2.3 • Unified Video Intelligence Studio');self._set_video_controls_enabled(False)
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
    def transfer_ranges(self):
        if not self._pending_analyzer_ranges or not self.video_info:return
        path,ranges=self._pending_analyzer_ranges
        if str(self.video_info.path.resolve())!=path:return
        self._pending_analyzer_ranges=None
        # Preserve overlapping people appearances as one union for extraction.
        merged=[]
        from core.models import ClipRange
        for r in sorted(ranges,key=lambda r:r.start_ms):
            if merged and r.start_ms<merged[-1].end_ms:merged[-1]=ClipRange(merged[-1].start_ms,max(merged[-1].end_ms,r.end_ms))
            else:merged.append(r)
        self.right_panel.set_clips(merged) if hasattr(self.right_panel,'set_clips') else None
        # The upstream right panel owns clip storage through its model.
        self._load_transferred(merged)
    def _load_transferred(self,ranges):
        from core.project_state import save_ranges
        save_ranges(self.video_info.path,ranges)
        self.right_panel.set_clips(ranges)
        self.timeline.detections=[r.start_ms for r in ranges]
        self.timeline.update()
    def _video_job_running(self):
        upstream=super()._video_job_running()
        return upstream or (getattr(self,'studio_ready',False) and (self.analyzer_page.busy or self.replacement_page.task.busy))
    def closeEvent(self,event):
        if getattr(self,'studio_ready',False):
            tasks=[self.analyzer_page.task,self.replacement_page.task]
            if self.analyzer_page.busy or any(t.busy for t in tasks):
                self.analyzer_page.cancel_analysis()
                for t in tasks:t.cancel()
                event.ignore();self.statusBar().showMessage('Cancelling active work; close again when it finishes.');return
            self.analyzer_page.shutdown()
        super().closeEvent(event)
