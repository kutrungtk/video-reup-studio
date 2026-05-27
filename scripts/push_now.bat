@echo off
chcp 65001 >nul
cd /d "E:\Aiagent\Projects\video-reup-studio-rebuild"

echo === Push Video Reup Studio to GitHub ===
echo.
echo Nhap GitHub Personal Access Token:
set /p TOKEN=

git remote remove origin 2>nul
git remote add origin https://kutrungtk:%TOKEN%@github.com/kutrungtk/video-reup-studio.git
git push -u origin master --force

echo.
echo Done! https://github.com/kutrungtk/video-reup-studio
pause
