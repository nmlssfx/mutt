@echo off
chcp 65001 >nul
title TTS CLI

:: ─── Загружаем ключи из .env ───
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do (
        if not "%%a"=="" set "%%a=%%b"
    )
)

if exist "venv\Scripts\python.exe" ( set PYTHON=venv\Scripts\python.exe
) else ( set PYTHON=python )

"%PYTHON%" "%~dp0mutt_cli.py" %*
if errorlevel 1 ( echo. & pause )
