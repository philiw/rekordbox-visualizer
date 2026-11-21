@echo off
rem Rekordbox Visualizer launcher - first run sets up its own Python environment.
rem Any arguments are passed through, e.g.:  "Start Visualizer.bat" --fullscreen --monitor 1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First start: creating Python environment...
    python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
