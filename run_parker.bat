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

:: Run the application
echo [Parker] Launching Parker UI...
python app.py

if %errorlevel% neq 0 (
    echo [Error] Parker failed to start.
    pause
)
endlocal
