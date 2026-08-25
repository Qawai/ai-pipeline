@echo off
title AI-orchestrator (opencode)
cd /d "%~dp0"

rem убить старый сервер на порту 8787, если висит
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8787" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo Запуск сервера на http://127.0.0.1:8787 ...
start /b python "%~dp0server.py"
timeout /t 2 >nul
start "" http://127.0.0.1:8787
echo Сервер работает. Закрой это окно (Ctrl+C), чтобы остановить.
