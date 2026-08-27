@echo off
title AIED Local Agent
color 0B
echo.
echo  Starting AIED Local Agent...
echo  Press Ctrl+C to stop.
echo.

REM --- Find Python ---
set PYTHON=
if exist "C:\Users\Digital\AppData\Local\Programs\Python\Python311\python.exe" (
    set PYTHON=C:\Users\Digital\AppData\Local\Programs\Python\Python311\python.exe
    goto :run
)
where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON=py
    goto :run
)
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON=python
    goto :run
)

color 0C
echo  ERROR: Python not found. Run install.bat first.
pause
exit /b 1

:run
%PYTHON% "%~dp0agent.py"

if %errorlevel% neq 0 (
    echo.
    echo  Agent stopped with an error.
    echo  If not configured, run install.bat first.
    echo.
)
pause
