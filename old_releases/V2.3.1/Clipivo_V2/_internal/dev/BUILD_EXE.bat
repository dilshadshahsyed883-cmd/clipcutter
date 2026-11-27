@echo off
rem Historical build recipe retained for reference only. Owner prohibits executable builds.
echo EXE builds are disabled by repository policy.
exit /b 1

rem Inactive historical recipe below. Do not remove the guard without owner authorization.
setlocal
cd /d "%~dp0..\.."
set "CLIPIVO_BUILD_RUNTIME=%LOCALAPPDATA%\ClipivoV2\runtime\build-v2.3"
if not exist "%CLIPIVO_BUILD_RUNTIME%\Scripts\python.exe" (
 py -3 -m venv "%CLIPIVO_BUILD_RUNTIME%"
 if errorlevel 1 goto :failed
)
set "CLIPIVO_BUILD_PY=%CLIPIVO_BUILD_RUNTIME%\Scripts\python.exe"
"%CLIPIVO_BUILD_PY%" -m pip install -r "%~dp0..\\requirements.txt" pyinstaller
if errorlevel 1 goto :failed
"%CLIPIVO_BUILD_PY%" -m PyInstaller --noconfirm --clean --onedir --contents-directory _internal --windowed --name Clipivo --paths "%~dp0..\" --distpath "%~dp0..\..\dist" --workpath "%TEMP%\ClipivoV23Build" --specpath "%TEMP%\ClipivoV23Spec" --collect-all onnxruntime --hidden-import keyring.backends.Windows --hidden-import studio.window --add-data "%~dp0..\\assets;assets" --add-data "%~dp0..\\licenses\LICENSE;licenses" --add-data "%~dp0..\\studio\capcut-draft.js;studio" --add-data "%~dp0..\\studio\capcut_bridge.js;studio" "%~dp0..\\app.py"
if errorlevel 1 goto :failed
copy /y "_internal\docs\README.md" "dist\Clipivo\README.md" >nul
copy /y "_internal\docs\CHANGELOG.md" "dist\Clipivo\CHANGELOG.md" >nul
copy /y "_internal\reports\TEST_REPORT.md" "dist\Clipivo\TEST_REPORT.md" >nul
copy /y "_internal\docs\THIRD_PARTY.md" "dist\Clipivo\THIRD_PARTY.md" >nul
copy /y "START_V2.bat" "dist\Clipivo\START_V2.bat" >nul
set "CLIPIVO_SELF_TEST_FILE=%~dp0..\..\dist\Clipivo\self-test.json"
start /wait "" "%~dp0..\..\dist\Clipivo\Clipivo.exe" --self-test
if errorlevel 1 goto :failed
echo Build complete: dist\Clipivo\Clipivo.exe. Keep its entire _internal folder.
echo Check self-test.json and verify playback and face inference on Windows.
pause
exit /b 0
:failed
echo Build or self-test failed. Read the error above. No verified Windows build was produced.
pause
exit /b 1
