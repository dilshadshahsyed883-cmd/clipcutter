"""Static layout and AppData source launcher contracts (no build)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_source_root_and_resources():
    # Ignore any pre-existing untracked user files; the ZIP/repo is checked separately.
    for name in ("README.md", "CHANGELOG.md", "TEST_REPORT.md", "THIRD_PARTY.md", "BUILD_EXE.bat", "LICENSE-AGPL-3.0.txt"):
        assert not (ROOT.parent / name).exists()
    for name in ("app.py", "requirements.txt", "docs/README.md", "licenses/LICENSE",
                 "licenses/LICENSE-AGPL-3.0.txt", "reports/TEST_REPORT.md",
                 "dev/BUILD_EXE.bat", "tests/test_replacement_picker_v23.py"):
        assert (ROOT / name).is_file()

def test_launcher_paths_and_build_guard():
    script = (ROOT.parent / "START_V2.bat").read_text(encoding="utf-8")
    for value in (r"%~dp0_internal\requirements.txt", r"%~dp0_internal\app.py",
                  r"%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3",
                  r"%CLIPIVO_HOME%\cache\pip", r"%CLIPIVO_HOME%\cache\temp"):
        assert value in script
    assert 'py -3 -m venv "%CLIPIVO_RUNTIME%"' in script
    assert "PYTHONDONTWRITEBYTECODE=1" in script
    assert "Clipivo.exe" not in script
    build = (ROOT / "dev/BUILD_EXE.bat").read_text(encoding="utf-8")
    assert build.index("exit /b 1") < build.index("PyInstaller")
