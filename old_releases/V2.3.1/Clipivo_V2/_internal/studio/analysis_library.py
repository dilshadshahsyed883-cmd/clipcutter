"""Persistent, conservative analysis lookup. Never delete or rewrite old projects."""
import json
import sqlite3
from pathlib import Path
from .storage import root

def source_stamp(video):
    path = Path(video).resolve(strict=True)
    stat = path.stat()
    if not path.is_file():
        raise ValueError("Source is not a file")
    return [str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]

def scan_key(cfg):
    # Filters are reviewable after analysis; do not discard reviewed edits.
    custom = bool(cfg.get("custom_models"))
    weights = []
    if custom:
        folder = Path(cfg.get("models") or "")
        weights = [source_stamp(folder / name) for name in ("det_10g.onnx", "w600k_r50.onnx")]
    return {"schema": 1, "step": float(cfg.get("step", .5)),
            "threshold": float(cfg.get("threshold", .45)),
            "size": int(cfg.get("size", 640)), "custom": custom, "weights": weights}

class AnalysisLibrary:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else root()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / "analysis_library.sqlite"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS projects (source TEXT, scan TEXT, stamp TEXT, project TEXT, PRIMARY KEY(source, scan))")
    def connect(self):
        return sqlite3.connect(self.db, timeout=10)
    def register(self, project, data):
        # Only a completed analysis with captured provenance is eligible.
        project = Path(project).resolve()
        stamp = data.get("source_stamp")
        scan = data.get("scan_key")
        if not stamp or not scan or not project.is_file():
            return False
        if source_stamp(data["source"]) != stamp:
            return False
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?,?)",
                       (stamp[0], json.dumps(scan, sort_keys=True), json.dumps(stamp), str(project)))
        return True
    def find(self, video, cfg):
        from .analysis import open_project
        stamp = source_stamp(video)
        scan = scan_key(cfg)
        with self.connect() as db:
            row = db.execute("SELECT stamp, project FROM projects WHERE source=? AND scan=?",
                             (stamp[0], json.dumps(scan, sort_keys=True))).fetchone()
        if not row:return None
        try:
            if json.loads(row[0]) != stamp:return None
            path = Path(row[1])
            data = open_project(path)
            if data.get("source_stamp") != stamp or data.get("scan_key") != scan:
                return None
            return path, data
        except (OSError, ValueError, KeyError, TypeError):
            return None
