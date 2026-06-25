@echo off
setlocal
title iPhone Backup Manager
cd /d "%~dp0"

if exist "%~dp0environment.cmd" call "%~dp0environment.cmd"

cd /d "%~dp0backend"

for /d %%D in ("%~dp0libimobiledevice*") do set "LIBIMOBILE=%%D"
if defined LIBIMOBILE set "PATH=%LIBIMOBILE%;%PATH%"

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

where idevicebackup2 >nul 2>&1
if errorlevel 1 (
  echo.
  echo [WARNING] idevicebackup2 not found on PATH.
  echo Place libimobiledevice binaries in the project folder or set libimobiledevice_path in backend\config.json
  echo.
)

echo.
echo Starting iPhone Backup Manager...
echo Default URL: http://127.0.0.1:5055
echo.
python run_service.py
pause
