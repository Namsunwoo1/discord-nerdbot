@echo off
git add .
git commit -m "Update bot files"
git push origin master --force
echo.
echo Done! Check your Railway dashboard.
pause