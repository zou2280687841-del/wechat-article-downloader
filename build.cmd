@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call setup.cmd
if not exist .venv\Scripts\python.exe exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name WechatBackup --distpath build\dist --workpath build\temp --specpath build main.py
if errorlevel 1 exit /b 1
if not exist runtime mkdir runtime
xcopy build\dist\WechatBackup\* runtime\ /E /I /Y
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts\make_release.py --runtime build\dist\WechatBackup
if errorlevel 1 exit /b 1
echo Release ZIPs are ready in release-assets.
pause
