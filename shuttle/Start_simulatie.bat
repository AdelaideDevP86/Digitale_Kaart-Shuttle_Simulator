@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m simulatie
) else (
    python -m simulatie
)
if errorlevel 1 pause
