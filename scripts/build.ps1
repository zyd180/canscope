# CANScope(CAN 总线分析仪)打包脚本(onedir,免安装交付)
# 用法: powershell -File scripts/build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = python -c "from version import VERSION; print(VERSION)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) { throw "读取版本失败" }
Write-Host "构建 CANScope v$version"

pyinstaller --noconfirm --clean `
    --onedir --windowed `
    --name CANScope `
    --icon assets/icon.ico `
    --hidden-import can.io.blf `
    --hidden-import cantools.database `
    main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

# 演示数据随包交付(--smoke 自检与开箱体验依赖它;缺失时现场生成)
$distData = Join-Path (Split-Path $PSScriptRoot -Parent) "dist\CANScope\data"
New-Item -ItemType Directory -Force -Path $distData | Out-Null
foreach ($f in @("data\test.blf", "data\test.dbc")) {
    if (-not (Test-Path $f)) {
        Write-Host "生成缺失的演示数据: $f"
        python scripts/make_test_data.py | Out-Null
        break
    }
}
Copy-Item "data\test.blf", "data\test.dbc" -Destination $distData -Force

Write-Host "`n[OK] dist\CANScope\CANScope.exe (v$version)" -ForegroundColor Green
Write-Host "冒烟验证: dist\CANScope\CANScope.exe --smoke"
