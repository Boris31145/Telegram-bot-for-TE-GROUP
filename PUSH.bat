@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
echo.
echo === Отправка на GitHub ===
git add -A
git commit -m "feat: single-message funnel with back buttons and correct company description"
git push origin main
echo.
echo === Готово! Render обновит бот за 2-3 минуты ===
pause
