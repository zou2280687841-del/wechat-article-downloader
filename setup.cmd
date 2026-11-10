@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 goto python311
py -3.12 -m venv .venv
goto install
:python311
py -3.11 -c "import sys" >nul 2>nul
if errorlevel 1 goto fail
py -3.11 -m venv .venv
goto install
:python_fallback
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)"
if errorlevel 1 goto fail
python -m venv .venv
:install
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Setup complete. Run the launcher CMD file, or: .venv\Scripts\python.exe main.py
pause
exit /b 0
:fail
echo Setup failed. Install 64-bit Python 3.11 or 3.12 and Microsoft Edge, then retry.
pause
exit /b 1
