@echo off
chcp 65001 >nul
title TTS Generator

:: ─── Загружаем ключи из .env ───
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do (
        if not "%%a"=="" set "%%a=%%b"
    )
)

if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON=python
)

"%PYTHON%" -c "import ttkbootstrap" 2>nul
if errorlevel 1 (
    echo [*] Устанавливаю зависимости...
    "%PYTHON%" -m pip install -q -r "%~dp0requirements.txt"
)

echo ==========================================
echo   TTS Generator
echo   MiMo (бесплатный) + OpenRouter
echo   Ключи: .env или переменные окружения
echo ==========================================
echo.

"%PYTHON%" "%~dp0mutt_gui.py"
if errorlevel 1 ( echo. & pause )
