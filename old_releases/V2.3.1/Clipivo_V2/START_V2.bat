@echo off
setlocal
rem Source-only PC testing. Paths are independent of the source folder and caller directory.
if not defined LOCALAPPDATA (
 echo LOCALAPPDATA is not set. Cannot create the Clipivo runtime safely.
 goto :failed
)
set "CLIPIVO_HOME=%LOCALAPPDATA%\ClipivoV2"
set "CLIPIVO_RUNTIME=%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3"
set "CLIPIVO_REQUIREMENTS=%~dp0_internal\requirements.txt"
set "CLIPIVO_ENTRY=%~dp0_internal\app.py"
set "PIP_CACHE_DIR=%CLIPIVO_HOME%\cache\pip"
set "TEMP=%CLIPIVO_HOME%\cache\temp"
set "TMP=%TEMP%"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PIP_TARGET="
set "PIP_PREFIX="
set "PIP_USER="
set "PIP_CONFIG_FILE=NUL"
set "CLIPIVO_STUDIO_DATA=%CLIPIVO_HOME%"
if not exist "%CLIPIVO_REQUIREMENTS%" (
 echo Missing _internal\requirements.txt. Extract the complete source folder.
 goto :failed
)
if not exist "%CLIPIVO_ENTRY%" (
 echo Missing _internal\app.py. Extract the complete source folder.
 goto :failed
)
if not exist "%TEMP%\" mkdir "%TEMP%"
if not exist "%TEMP%\" goto :failed
if not exist "%PIP_CACHE_DIR%\" mkdir "%PIP_CACHE_DIR%"
if not exist "%PIP_CACHE_DIR%\" goto :failed
rem Never use or relocate a source-local .venv. Create a new AppData runtime if absent.
if not exist "%CLIPIVO_RUNTIME%\Scripts\python.exe" (
 if exist "%CLIPIVO_RUNTIME%\pyvenv.cfg" (
  echo Existing AppData runtime is incomplete. Preserve it and repair or rename it manually.
  goto :failed
 )
 py -3 -c "import sys; assert sys.version_info >= (3,11) and sys.maxsize > 2**32" >nul 2>&1
 if errorlevel 1 (
  echo Install Windows x64 Python 3.11 or newer from python.org with the Python launcher.
  goto :failed
 )
 py -3 -m venv "%CLIPIVO_RUNTIME%"
 if errorlevel 1 goto :failed
)
"%CLIPIVO_RUNTIME%\Scripts\python.exe" -c "import os,sys; assert sys.version_info >= (3,11) and sys.maxsize > 2**32 and sys.prefix != sys.base_prefix and os.path.samefile(sys.prefix,os.environ['CLIPIVO_RUNTIME'])" >nul 2>&1
if errorlevel 1 (
 echo AppData Python runtime is invalid. Preserve it and repair or rename it manually.
 goto :failed
)
rem Reconcile pins once whenever requirements change. No source-local installs.
"%CLIPIVO_RUNTIME%\Scripts\python.exe" -c "import hashlib,os,pathlib; p=pathlib.Path(os.environ['CLIPIVO_REQUIREMENTS']); stamp=pathlib.Path(os.environ['CLIPIVO_RUNTIME'])/'requirements.sha256'; assert stamp.read_text().strip()==hashlib.sha256(p.read_bytes()).hexdigest(); import PySide6,cv2,av,onnxruntime,cryptography,keyring,vlc,psutil" >nul 2>&1
if errorlevel 1 (
 "%CLIPIVO_RUNTIME%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%CLIPIVO_REQUIREMENTS%"
 if errorlevel 1 goto :failed
 "%CLIPIVO_RUNTIME%\Scripts\python.exe" -c "import PySide6,cv2,av,onnxruntime,cryptography,keyring,vlc,psutil; import hashlib,os,pathlib; p=pathlib.Path(os.environ['CLIPIVO_REQUIREMENTS']); (pathlib.Path(os.environ['CLIPIVO_RUNTIME'])/'requirements.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest())"
 if errorlevel 1 goto :failed
)
"%CLIPIVO_RUNTIME%\Scripts\python.exe" "%CLIPIVO_ENTRY%" %*
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Clipivo could not start. Read the error above, check Internet access and retry.
pause
exit /b 1
