@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build.ps1"
if errorlevel 1 (
    echo.
    echo [FAIL] 打包失败
    pause
    exit /b 1
)

echo.
echo [OK] 打包完成: dist\CANScope\CANScope.exe
pause
