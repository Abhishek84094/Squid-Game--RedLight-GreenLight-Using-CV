@echo off
title Red Light Green Light - Launcher
echo Starting Red Light, Green Light...
echo Please wait, loading MediaPipe and camera...
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe main.py
) else (
    python main.py
)
echo.
echo Game exited. Press any key to close.
pause

