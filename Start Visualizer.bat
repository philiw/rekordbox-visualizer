@echo off
rem Rekordbox Visualizer launcher.
rem The first start sets up its own Python environment (this window shows the progress).
rem After that the app starts without a console window; messages go to visualizer.log.
rem Any arguments are passed through, e.g.:  "Start Visualizer.bat" --fullscreen --monitor 1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First start: creating Python environment...
    python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)
rem install packages added by updates (fast no-op when everything is present)
".venv\Scripts\python.exe" -c "import importlib.util as u, sys; sys.exit(0 if all(u.find_spec(m) for m in ['numpy','soundcard','moderngl','glfw','PIL','aalink','pyrekordbox']) else 1)" || ".venv\Scripts\python.exe" -m pip install -r requirements.txt

rem --list-devices prints a table, so it needs this console
if /i "%~1"=="--list-devices" (
    ".venv\Scripts\python.exe" main.py %*
    pause
    exit /b
)
start "" ".venv\Scripts\pythonw.exe" main.py %*
