@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\WechatBackup.exe" (
    start "" "%~dp0runtime\WechatBackup.exe"
    exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
    exit /b 0
)
echo Please run setup.cmd first.
pause
