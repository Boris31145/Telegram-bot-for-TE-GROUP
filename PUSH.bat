@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
echo === TE GROUP Bot Push ===
echo.
git add -A
git status
echo.
git commit -m "fix: robust funnel (try/except all edits), correct user identity, premium admin notifications"
git push origin main
echo.
echo === Done! ===
pause
