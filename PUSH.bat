@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
echo === TE GROUP Bot Push ===
echo.
git add -A
git status
echo.
git commit -m "fix: admin notifications — correct user identity, premium design, action buttons, no empty fields"
git push origin main
echo.
echo === Done! ===
pause
