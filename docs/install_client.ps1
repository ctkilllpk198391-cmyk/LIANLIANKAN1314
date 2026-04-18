# wechat_agent client installer v3 (English-only output, full Python installer)
# One-liner:
#   Set-ExecutionPolicy Bypass -Scope Process -Force; iwr -UseBasicParsing http://120.26.208.212/download/install_client.ps1 | iex

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ─── Config (change per customer) ──────────────────
$ServerUrl      = "http://120.26.208.212"
$ActivationCode = "WXA-06BF-4E96-6D10-ACA1"
$TenantId       = "tenant_0001"

$InstallDir = "$env:USERPROFILE\WechatAgent"
$PyRoot     = "$env:LocalAppData\Programs\Python\Python311"
$PyExe      = "$PyRoot\python.exe"
# ────────────────────────────────────────────────────

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  wechat_agent client installer v3" -ForegroundColor Cyan
Write-Host "  Server: $ServerUrl" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\logs" | Out-Null

# ─── [1/5] Install Python 3.11.9 (full installer, user scope) ──
if (-not (Test-Path $PyExe)) {
    Write-Host "[1/5] Downloading Python 3.11.9 from Huawei mirror (~25 MB, 30s)..." -ForegroundColor Yellow
    $pyInstaller = "$env:TEMP\python-3.11.9-amd64.exe"
    $pyUrl = "https://mirrors.huaweicloud.com/python/3.11.9/python-3.11.9-amd64.exe"
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyInstaller -UseBasicParsing

    Write-Host "  Installing silently to user dir (no admin needed)..." -ForegroundColor Gray
    $pyArgs = "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0", "Include_launcher=0", "Include_doc=0"
    Start-Process -FilePath $pyInstaller -ArgumentList $pyArgs -Wait
    Remove-Item $pyInstaller

    if (-not (Test-Path $PyExe)) {
        Write-Host "  ERROR: Python installation failed. Expected at $PyExe" -ForegroundColor Red
        Write-Host "  Contact developer. Aborting." -ForegroundColor Red
        exit 1
    }
    $pyVer = & $PyExe --version 2>&1
    Write-Host "  OK: $pyVer" -ForegroundColor Green
} else {
    $pyVer = & $PyExe --version 2>&1
    Write-Host "[1/5] Python already installed: $pyVer" -ForegroundColor Green
}

# ─── [2/5] Download client code ─────────────────────
Write-Host "[2/5] Downloading wechat_agent client..." -ForegroundColor Yellow
$clientZip = "$env:TEMP\wechat_agent_client.zip"
Invoke-WebRequest -Uri "$ServerUrl/download/wechat_agent_client.zip" -OutFile $clientZip -UseBasicParsing
$extractTo = "$InstallDir\code"
if (Test-Path $extractTo) { Remove-Item -Recurse -Force $extractTo }
New-Item -ItemType Directory -Force -Path $extractTo | Out-Null
Expand-Archive -Path $clientZip -DestinationPath $extractTo -Force
Remove-Item $clientZip
Write-Host "  OK: extracted to $extractTo" -ForegroundColor Green

# ─── [3/5] Install Python dependencies (Tsinghua mirror) ────
Write-Host "[3/5] Installing Python deps (Tsinghua mirror, 1-3 min)..." -ForegroundColor Yellow
& $PyExe -m pip install --quiet --upgrade pip `
    -i https://pypi.tuna.tsinghua.edu.cn/simple `
    --trusted-host pypi.tuna.tsinghua.edu.cn 2>&1 | Out-Null

& $PyExe -m pip install --quiet `
    -i https://pypi.tuna.tsinghua.edu.cn/simple `
    --trusted-host pypi.tuna.tsinghua.edu.cn `
    fastapi pydantic aiohttp httpx `
    sqlalchemy aiosqlite python-dotenv pyyaml `
    wxautox humancursor 2>&1 | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

Write-Host "  OK: deps installed" -ForegroundColor Green

# ─── [4/5] Write config + launcher ─────────────────
Write-Host "[4/5] Writing config + launcher..." -ForegroundColor Yellow
$envFile = "$InstallDir\.env.client"
@"
BAIYANG_SERVER_URL=$ServerUrl
BAIYANG_ACTIVATION_CODE=$ActivationCode
BAIYANG_TENANT_ID=$TenantId
"@ | Out-File -Encoding ascii $envFile -Force

$startBat = "$InstallDir\start.bat"
@"
@echo off
chcp 65001 > nul
cd /d $extractTo
set PYTHONPATH=$extractTo
"$PyExe" -m client.main --tenant $TenantId --server $ServerUrl --auto-accept
pause
"@ | Out-File -Encoding ascii $startBat -Force

Write-Host "  OK: launcher at $startBat" -ForegroundColor Green

# ─── [5/5] Desktop shortcut + autostart ────────────
Write-Host "[5/5] Desktop shortcut + autostart..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\WechatAgent.lnk")
$shortcut.TargetPath = $startBat
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Save()

$regPath = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
Set-ItemProperty -Path $regPath -Name "WechatAgent" -Value $startBat -Force
Write-Host "  OK: desktop shortcut + autostart" -ForegroundColor Green

# ─── Done ──────────────────────────────────────────
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  INSTALLATION COMPLETE!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Install dir:  $InstallDir" -ForegroundColor White
Write-Host "  Launcher:     $startBat" -ForegroundColor White
Write-Host "  Desktop:      WechatAgent.lnk" -ForegroundColor White
Write-Host ""
Write-Host "  Next: make sure WeChat PC is logged in." -ForegroundColor Cyan
Write-Host "  Launching client in a new window..." -ForegroundColor Yellow
Write-Host ""

Start-Process -FilePath $startBat
