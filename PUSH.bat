@echo off
cd /d "C:\Users\games\Desktop\Ford\Oli\Код\TE\te-bot"
git add -A
git commit -m "fix: html-escape user fields in admin notify, add DB error handling and plain-text fallback"
git push origin main
pause
