@echo off
TITLE RoboGreet AI — Startup Orchestrator
COLOR 0B

:: Ensure working directory is the script's directory
cd /d "%~dp0"

echo ===================================================
echo   ROBOGREET AI: Interactive Robot System
echo ===================================================
echo.

:: 1. Set Ollama CORS Origins (Global fallback)
set OLLAMA_ORIGINS=*
echo [1/2] Launching RoboGreet Control Server...

:: 2. Start the Control Server (it will open its own window)
start "RoboGreet Server" python control_server.py --auto

:: 3. Wait for the server to start up
echo Waiting for server to start...
timeout /t 3 /nobreak >nul

:: 4. Open the UI in the default browser
echo [2/2] Opening Web UI...
start http://localhost:8000

exit
