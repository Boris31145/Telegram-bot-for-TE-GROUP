@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
echo.
echo === Отправка исправлений на GitHub ===
echo.
git add -A
git commit -m "fix: city parsing + menu button + remove deleted modules"
git push origin main
echo.
echo === Готово! Render подхватит через 2-3 минуты ===
echo.
pause
