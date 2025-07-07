@echo off
cd /d C:\Users\rast8\Documents\discordbot
git add .
git commit -m "📝 자동 커밋: %date% %time%"
git push origin main
pause
