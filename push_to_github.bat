@echo off
chcp 65001 > nul
echo ===================================================
echo Отправка проекта на GitHub: Vladislav0122/ai-qa-agent-pipeline
echo ===================================================
cd /d "%~dp0"
git status
git push -u origin main
echo.
echo ===================================================
echo Готово! Нажмите любую клавишу для выхода.
pause
