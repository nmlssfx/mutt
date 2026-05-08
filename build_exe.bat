@echo off &
REM Build script for Mutt TTS Generator &
REM Run from: D:\clouds\ncloud\Dev\ttsgenerator &

echo === Checking Python === &
python --version &
if errorlevel 1 (
    echo Python not found! Please install Python 3.10+
    pause &
    exit /b 1
)

echo === Installing PyInstaller === &
pip install pyinstaller -q &

echo === Cleaning previous builds === &
if exist build rmdir /s /q build &
if exist dist rmdir /s /q dist &
if exist __pycache__ rmdir /s /q __pycache__ &
if exist *.pyc del /s /q *.pyc &

echo === Building EXE (output to project root) === &
pyinstaller MuttTTS.spec --distpath=. --workpath=build --clean 2>&1 &

echo === Cleaning build artifacts === &
if exist build rmdir /s /q build &
if exist mutt_tts.tmp del /q mutt_tts.tmp &
if exist warn-mutt_tts.txt del /q warn-mutt_tts.txt &

echo === Build complete! === &
if exist "MuttTTS.exe" (
    echo. &
    echo SUCCESS! EXE created at: %CD%\MuttTTS.exe &
    echo. &
    echo Next steps: &
    echo 1. Copy MuttTTS.exe to any folder you want &
    echo 2. Create .env file in the SAME folder as MuttTTS.exe &
    echo 3. Add your API keys to .env (see dist_README.txt) &
    echo 4. Run MuttTTS.exe &
    echo. &
) else (
    echo BUILD FAILED - check output above &
)

pause &
