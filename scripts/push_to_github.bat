@echo off
REM === Push Video Reup Studio lên GitHub ===
REM Chạy file này 1 lần để push code lên GitHub.
REM Yêu cầu: GitHub account + Personal Access Token (PAT)

set /p USERNAME="GitHub username: "
set /p TOKEN="GitHub token (PAT): "
set REPO=video-reup-studio

echo.
echo Tạo repo trên GitHub...
curl -s -H "Authorization: token %TOKEN%" https://api.github.com/user/repos -d "{\"name\":\"%REPO%\",\"description\":\"Video Reup Studio - Tool chỉnh sửa video hàng loạt, anti-reup, batch download\",\"private\":false}" > nul

echo Cấu hình git...
cd /d "E:\Aiagent\Projects\video-reup-studio-rebuild"
git remote remove origin 2>nul
git remote add origin https://%USERNAME%:%TOKEN%@github.com/%USERNAME%/%REPO%.git
git branch -M main
git push -u origin main

echo.
echo ✅ Done! Repo: https://github.com/%USERNAME%/%REPO%
echo.
pause
