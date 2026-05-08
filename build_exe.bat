@echo off
REM Build script for Mutt TTS Generator
REM Run this from the project directory: D:\clouds\ncloud\Dev\ttsgenerator

echo === Checking Python ===
python --version
if errorlevel 1 (
    echo Python not found! Please install Python 3.10+
    pause
    exit /b 1
)

echo === Installing PyInstaller ===
pip install pyinstaller

echo === Cleaning previous builds ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
if exist *.pyc del /s /q *.pyc

echo === Building EXE with PyInstaller ===
pyinstaller MuttTTS.spec

echo === Build complete! ===
if exist "dist\MuttTTS.exe" (
    echo.
    echo SUCCESS! EXE created at: dist\MuttTTS.exe
    echo.
    echo Next steps:
    echo 1. Copy .env file next to the EXE in dist\ folder
    echo 2. Run MuttTTS.exe
    echo.
) else (
    echo BUILD FAILED - check output above
)

pause
