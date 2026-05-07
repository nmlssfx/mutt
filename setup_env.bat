@echo off
chcp 65001 >nul

echo ==================================
echo   TTS Generator — установка
echo ==================================
echo.

if not exist "venv" (
    echo [*] Создаю виртуальное окружение...
    python -m venv venv
)

echo [*] Устанавливаю зависимости...
call venv\Scripts\activate.bat
pip install -U pip -q
pip install -r requirements.txt

echo.
echo [*] Готово!
echo.
echo   Скопируйте .env.example в .env и укажите ключи
echo   или задайте переменные окружения.
echo.
echo   Запуск:  start_gui.bat
echo.
pause
