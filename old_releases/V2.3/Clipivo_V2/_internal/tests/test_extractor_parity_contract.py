"""Source-only guardrails for the upstream extractor integration."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_original_extractor_model_constructor():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "InsightFaceEngine"]
    assert len(calls) == 1 and not calls[0].args and not calls[0].keywords

def test_analyzer_settings_do_not_mutate_extractor_engine():
    tree = ast.parse((ROOT / "studio/window.py").read_text(encoding="utf-8"))
    settings = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SettingsPage")
    save = next(n for n in settings.body if isinstance(n, ast.FunctionDef) and n.name == "save")
    assert not any(isinstance(n, ast.Attribute) and n.attr in {"face_engine", "wide_face_engine"}
                   for n in ast.walk(save))

def test_source_launcher_reconciles_requirements_in_appdata():
    text = (ROOT.parent / "START_V2.bat").read_text(encoding="utf-8")
    assert r"%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3" in text
    assert "requirements.sha256" in text and "hashlib.sha256" in text
    assert '-m pip install --disable-pip-version-check -r "%CLIPIVO_REQUIREMENTS%"' in text

def test_original_dependency_pins():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    for pin in ("PySide6-Essentials==6.11.1", "av==16.1.0", "numpy==2.4.6",
                "opencv-python-headless==5.0.0.93", "cryptography==49.0.0",
                "keyring==25.7.0", "python-vlc==3.0.21203", "certifi==2026.7.22",
                'onnxruntime==1.31.0; sys_platform != "win32"',
                'onnxruntime-directml==1.24.4; sys_platform == "win32"'):
        assert pin in lines
