@echo off
title AIED Local Agent Installer
color 0A
echo.
echo  ==========================================
echo   AIED Local Agent - Installer
echo  ==========================================
echo.

REM --- Find Python ---
echo [1/3] Checking Python installation...
set PYTHON=
REM Check known install paths first (skip Microsoft Store alias)
if exist "C:\Users\Digital\AppData\Local\Programs\Python\Python311\python.exe" (
    set PYTHON=C:\Users\Digital\AppData\Local\Programs\Python\Python311\python.exe
    goto :found_python
)
if exist "C:\Python311\python.exe" (
    set PYTHON=C:\Python311\python.exe
    goto :found_python
)
REM Fallback: try py launcher
where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON=py
    goto :found_python
)

color 0C
echo.
echo  ERROR: Python not found.
echo.
echo  Download Python from: https://www.python.org/downloads/
echo  IMPORTANT: Check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:found_python
for /f "tokens=*" %%i in ('%PYTHON% --version 2^>^&1') do echo   Found: %%i

REM --- Install dependencies ---
echo.
echo [2/3] Installing dependencies...
%PYTHON% -m pip install websockets aiohttp --quiet
if %errorlevel% neq 0 (
    color 0C
    echo  ERROR: Failed to install dependencies.
    echo  Try running: %PYTHON% -m pip install websockets aiohttp
    pause
    exit /b 1
)
echo   Dependencies installed.

REM --- Run setup ---
echo.
echo [3/3] Running interactive setup...
echo.
echo  You will be asked for:
echo    - VPS URL (press Enter for default)
echo    - Auth token
echo    - User ID
echo    - Project folder (e.g. D:\my-project)
echo.
%PYTHON% "%~dp0agent.py" --setup
if %errorlevel% neq 0 (
    color 0C
    echo  Setup failed.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   Installation complete!
echo.
echo   To start the agent, double-click:
echo     start.bat
echo  ==========================================
echo.
pause
