from PySide6.QtCore import QObject, Signal
import threading,queue

class Task(QObject):
    done=Signal(object)
    failed=Signal(str)
    progress=Signal(object)
    finished=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.stop=threading.Event();self.thread=None;self.live=queue.Queue(maxsize=1)
    @property
    def busy(self):return self.thread is not None and self.thread.is_alive()
    def start(self,fn):
        if self.busy:raise RuntimeError('A task is already running')
        self.stop.clear()
        def target():
            try:self.done.emit(fn(self))
            except Exception as exc:self.failed.emit(f'{type(exc).__name__}: {exc}')
            finally:self.finished.emit()
        self.thread=threading.Thread(target=target,daemon=True);self.thread.start()
    def report(self,*args):self.progress.emit(args)
    def preview(self,*args):
        try:self.live.get_nowait()
        except queue.Empty:pass
        try:self.live.put_nowait(args)
        except queue.Full:pass
    def cancel(self):self.stop.set()
