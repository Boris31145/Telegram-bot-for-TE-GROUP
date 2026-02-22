@echo off
chcp 65001 >nul
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
git add -A
git status
git commit -m "fix: prevent dropped messages on restart, add session recovery, secure token, improve phone input"
git push origin main
pause
