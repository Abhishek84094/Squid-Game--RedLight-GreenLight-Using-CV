@echo off
title Red Light Green Light - Web Server
echo ============================================
echo   Red Light, Green Light - Web Server
echo ============================================
echo.
echo Starting server on http://localhost:8000
echo Open your browser and go to: http://localhost:8000
echo.
echo Press CTRL+C to stop the server.
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000
) else (
    python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
)
echo.
echo Server stopped. Press any key to close.
pause

