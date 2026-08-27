@echo off
echo ========================================
echo   AIED Local Agent - Installer
echo ========================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH.
    echo Install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo Installing dependencies...
pip install websockets aiohttp
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Running setup...
python "%~dp0agent.py" --setup

echo.
echo ========================================
echo   Installation complete!
echo   To start the agent: python agent.py
echo ========================================
pause
