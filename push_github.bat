@echo off
setlocal

cd /d "%~dp0"
set "REMOTE=https://zyd180@github.com/zyd180/canscope.git"

git remote set-url origin "%REMOTE%"
if errorlevel 1 goto :fail

for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if not defined BRANCH (
    echo [FAIL] 当前不在本地分支上
    pause
    exit /b 1
)

set /p "MESSAGE=提交说明(留空使用默认说明): "
if not defined MESSAGE set "MESSAGE=Update project files"

git add -A
rem 运行时崩溃日志不属于源码发布内容,保留在本地不提交
git reset -- logs/crash.log >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git -c user.name="zyd180" -c user.email="45862230+zyd180@users.noreply.github.com" commit -m "%MESSAGE%"
    if errorlevel 1 goto :fail
) else (
    echo [INFO] 没有新的源码改动,直接推送
)

echo [WARN] 将用本地 %BRANCH% 强制覆盖 GitHub 同名分支
git push origin "%BRANCH%" --force
if errorlevel 1 goto :fail

echo.
echo [OK] 已推送到 %REMOTE% (%BRANCH%)
pause
exit /b 0

:fail
echo.
echo [FAIL] 推送失败,请检查 GitHub 登录凭据和网络连接
pause
exit /b 1
