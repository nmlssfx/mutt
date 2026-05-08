@echo off &
REM Build and package Mutt TTS Generator &
REM Run from: D:\clouds\ncloud\Dev\ttsgenerator &

echo === Building EXE === &
call build_exe.bat &

echo === Packaging for distribution === &
if exist "dist\MuttTTS.exe" (
    copy /y "dist_README.txt" "dist\READ_ME.txt" >nul &
    echo. &
    echo SUCCESS! Distribution files ready in dist\ folder: &
    echo  - MuttTTS.exe (the application) &
    echo  - READ_ME.txt (instructions) &
    echo. &
    echo Next steps for distribution: &
    echo 1. Copy dist\ folder to target machine &
    echo 2. User creates .env file next to MuttTTS.exe &
    echo 3. User runs MuttTTS.exe &
) else (
    echo BUILD FAILED - check output above &
)
