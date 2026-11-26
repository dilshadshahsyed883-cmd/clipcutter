@echo off
setlocal
cd /d "%~dp0"
if exist "Clipivo.exe" (
 start "" "%~dp0Clipivo.exe" %*
 exit /b 0
)
set "CLIPIVO_PYTHON=py -3"
%CLIPIVO_PYTHON% -c "import sys; assert sys.version_info >= (3,11) and sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 (
 echo Install Windows x64 Python 3.11 or newer from python.org with the Python launcher.
 pause
 exit /b 1
)
set "CLIPIVO_RUNTIME=%LOCALAPPDATA%\ClipivoV2\runtime\python-v2.3"
if not exist "%CLIPIVO_RUNTIME%\Scripts\python.exe" (
 %CLIPIVO_PYTHON% -m venv "%CLIPIVO_RUNTIME%"
 if errorlevel 1 goto :failed
)
"%CLIPIVO_RUNTIME%\Scripts\python.exe" -c "import PySide6,cv2,av,onnxruntime,cryptography,keyring,vlc,psutil" >nul 2>&1
if errorlevel 1 (
 "%CLIPIVO_RUNTIME%\Scripts\python.exe" -m pip install -r "%~dp0_internal\requirements.txt"
 if errorlevel 1 goto :failed
)
"%CLIPIVO_RUNTIME%\Scripts\python.exe" "%~dp0_internal\app.py" %*
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Clipivo could not start. Read the error above, check Internet access and retry.
pause
exit /b 1
