@echo off
title NetPulse Pro (Elevated Administrator)
cd /d "%~dp0"

:: Check for Administrative permissions
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with Administrator privileges...
    python run.py
) else (
    echo Requesting Administrator privileges to allow hardware-level adapter optimizations...
    powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoExit', '-Command', 'cd ''%~dp0''; python run.py'"
)
