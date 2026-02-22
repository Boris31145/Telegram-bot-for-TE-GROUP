@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
echo === TE GROUP Bot Push ===
echo.
git add -A
git status
echo.
git commit -m "fix: restore env vars, session recovery, improve phone input, drop_pending_updates=False"
git push origin main
echo.
echo === Done! ===
pause
