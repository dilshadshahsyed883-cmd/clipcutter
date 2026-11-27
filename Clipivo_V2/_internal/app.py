from __future__ import annotations

import os
import sys
from pathlib import Path

# Source runs should never write bytecode into the application folder.
sys.dont_write_bytecode = True

# Variables Clipivo, its packaging or its libraries change for this process, which programs
# it starts must not inherit. A packaged Linux build points LD_LIBRARY_PATH at its own Qt,
# GLib, OpenSSL and libstdc++; PySide6 sets QT_PLUGIN_PATH to its plugins; OpenCV sets
# LD_LIBRARY_PATH again when imported. kdialog, zenity, ffmpeg and xdg-open (Open folder,
# links) then load those libraries instead of their own and fail to start. The user's values
# are recorded here, before anything changes them, and restored once everything has loaded.
_INHERITED = ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
              "QT_QPA_PLATFORM", "RESOURCE_NAME")
_USER_ENVIRONMENT = {key: os.environ.get(key) for key in _INHERITED}
if getattr(sys, "frozen", False):
    # The bundle's own path is not the user's; PyInstaller keeps theirs here, if they had one.
    _USER_ENVIRONMENT["LD_LIBRARY_PATH"] = os.environ.get("LD_LIBRARY_PATH_ORIG")

# libVLC 3 embeds video in an X11 child window. Fedora's XWayland bridge keeps
# the rest of Clipivo native-looking while providing that reliable zero-copy
# playback surface on Wayland desktops.
if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
# Without this the X11 window class is "python", so the desktop shows a generic icon and name.
os.environ.setdefault("RESOURCE_NAME", "Clipivo")

# The optional Linux GPU download replaces the built-in ONNX Runtime, so it has to be on the
# import path before anything imports onnxruntime.
# Legacy GPU activation is intentionally not performed by the standalone timeline UI.

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFontDatabase, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.downloads import APP_DIR, ffmpeg_available  # noqa: E402
from studio.timeline_window import TimelineWindow as MainWindow  # noqa: E402
from version import __app_name__, __org_name__, __version__  # noqa: E402


# The app's own files: beside this script from source, inside the bundle when packaged.
PROJECT_DIR = APP_DIR


def restore_user_environment(app: QApplication) -> None:
    """Give programs Clipivo starts the user's own environment back. Call after the
    QApplication exists and OpenCV has been imported (it sets LD_LIBRARY_PATH on import)."""
    # Keep Qt finding its plugins without the variable: pin the paths it worked out.
    app.setLibraryPaths(app.libraryPaths())
    bundle = str(Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve())
    for key, value in _USER_ENVIRONMENT.items():
        # Packaging hooks run before this file, so a "user" value may already be the bundle's:
        # keep only the entries that are not inside Clipivo's own folder.
        if value and (key.endswith("PATH") or os.pathsep in value):
            kept = [entry for entry in value.split(os.pathsep)
                    if entry and not str(Path(entry).resolve()).startswith(bundle)]
            value = os.pathsep.join(kept) or None
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    os.environ.pop("LD_LIBRARY_PATH_ORIG", None)


def first_launch_checks(window: MainWindow) -> None:
    if not ffmpeg_available():
        QMessageBox.warning(window, 'Media tools missing', 'Install FFmpeg including ffprobe, or restore the existing Clipivo media tools before importing JSON or scanning footage.')


def load_fonts() -> None:
    for name in ("Inter-Regular.ttf", "Inter-Bold.ttf"):
        QFontDatabase.addApplicationFont(str(PROJECT_DIR / "assets" / "fonts" / name))


def self_test() -> int:
    """Timeline-only diagnostics; no recognition, GPU or encoding."""
    import json,subprocess
    from core.downloads import tool_path
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from studio import json_timeline
    report={'version':__version__,'workflow':'timeline','schema':json_timeline.FORMAT,'failures':[]}
    app=QApplication.instance() or QApplication(['clipivo','-platform','offscreen'])
    restore_user_environment(app)
    try:
        player=QMediaPlayer();video=QVideoWidget();player.setVideoOutput(video)
        report['qt_multimedia']='ok'
    except Exception as exc:report['failures'].append('Qt multimedia: '+str(exc))
    try:
        result=subprocess.run([tool_path('ffprobe'),'-version'],capture_output=True,text=True,timeout=20,check=True)
        report['ffprobe']=result.stdout.splitlines()[0]
    except Exception as exc:report['failures'].append('ffprobe: '+str(exc))
    print(json.dumps(report,indent=2))
    target=os.environ.get('CLIPIVO_SELF_TEST_FILE')
    if target:Path(target).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return int(bool(report['failures']))


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__org_name__)
    app.setStyle("Fusion")
    app.setDesktopFileName("io.longweekendlabs.Clipivo")
    app.setWindowIcon(QIcon.fromTheme("io.longweekendlabs.Clipivo", QIcon(str(PROJECT_DIR / "assets" / "clipivo.svg"))))
    load_fonts()
    restore_user_environment(app)
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, lambda: first_launch_checks(window))
    if len(sys.argv) > 1:
        source = Path(sys.argv[1]).expanduser()
        if source.is_file() and source.suffix.lower() == '.json':
            QTimer.singleShot(0, lambda: window.import_path(str(source)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
