@echo off
setlocal
cd /d "%~dp0"

echo [Parker] Initializing...

:: Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Docker Desktop is not running. Please start it first.
    pause
    exit /b
)

:: Start database if not already up
echo [Parker] Ensuring database is active...
docker compose up -d

:: Start the Gateway daemon in the background
echo [Parker] Launching Parker Gateway daemon...
start /b cmd /c "node gateway\openclaw.mjs --dev gateway run --force > gateway_daemon.log 2>&1"

:: Wait a brief moment for the gateway to initialize
timeout /t 3 /nobreak >nul

:: Run the application
echo [Parker] Launching Parker CLI...
venv\Scripts\python main.py

:: Shutdown background gateway on exit
echo [Parker] Shutting down Gateway daemon...
powershell -Command "Get-CimInstance Win32_Process -Filter \"CommandLine like '%%openclaw.mjs%%'\" | Remove-CimInstance" >nul 2>&1

if %errorlevel% neq 0 (
    echo [Error] Parker failed to start.
    pause
)
endlocal
