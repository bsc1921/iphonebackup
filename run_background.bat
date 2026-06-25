@echo off
setlocal
cd /d "%~dp0backend"
for /d %%D in ("%~dp0libimobiledevice*") do set "PATH=%%D;%PATH%"
python run_service.py
