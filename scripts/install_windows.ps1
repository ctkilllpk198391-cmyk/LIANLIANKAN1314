# 白羊 wechat_agent · Windows 一键安装脚本
# 用法（管理员 PowerShell）:
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\install_windows.ps1 -ServerUrl http://your.server.ip:8327 -TenantId tenant_0001

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ServerUrl,
    [Parameter(Mandatory=$true)][string]$TenantId,
    [string]$InstallDir = "C:\baiyang",
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"

function Write-Step($text) { Write-Host "▶ $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "✓ $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "⚠ $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "✗ $text" -ForegroundColor Red }

# ─── 1. 检查 Python ────────────────────────────────────────────────────
Write-Step "检查 Python $PythonVersion"
$pyExe = Get-Command "python$PythonVersion" -ErrorAction SilentlyContinue
if (-not $pyExe) { $pyExe = Get-Command "python" -ErrorAction SilentlyContinue }
if (-not $pyExe) {
    Write-Err "未找到 Python · 请先装 https://www.python.org/downloads/ ($PythonVersion+)"
    exit 1
}
$pyVer = & $pyExe.Source --version
Write-Ok "$pyVer"

# ─── 2. 检查微信 PC ────────────────────────────────────────────────────
Write-Step "检查微信 PC"
$wxCandidates = @(
    "C:\Program Files\Tencent\WeChat\WeChat.exe",
    "C:\Program Files (x86)\Tencent\WeChat\WeChat.exe"
)
$wxExe = $null
foreach ($p in $wxCandidates) { if (Test-Path $p) { $wxExe = $p; break } }
if (-not $wxExe) {
    Write-Err "未找到微信 PC · 请先装并登录"
    exit 1
}
$wxVer = (Get-Item $wxExe).VersionInfo.FileVersion
Write-Ok "微信版本: $wxVer"
if ($wxVer -notmatch "^4\.") {
    Write-Warn "建议微信 4.0+ · 当前 $wxVer 可能不兼容"
}

# ─── 3. 创建安装目录 ───────────────────────────────────────────────────
Write-Step "创建 $InstallDir"
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null }
Set-Location $InstallDir
Write-Ok "目录就绪"

# ─── 4. 下载 / 同步项目代码 ────────────────────────────────────────────
Write-Step "同步白羊项目代码"
if (Test-Path "$InstallDir\wechat_agent\.git") {
    Push-Location "$InstallDir\wechat_agent"
    git pull
    Pop-Location
} else {
    Write-Warn "未发现 git 仓库 · 请先把 ~/wechat_agent/ 推到内网 git 服务器"
    Write-Warn "或手动 scp 复制 wechat_agent 目录到 $InstallDir\wechat_agent"
    if (-not (Test-Path "$InstallDir\wechat_agent\pyproject.toml")) {
        Write-Err "$InstallDir\wechat_agent\ 找不到 pyproject.toml · 请手动复制后重跑"
        exit 1
    }
}
Set-Location "$InstallDir\wechat_agent"
Write-Ok "代码就绪"

# ─── 5. 创建 venv ─────────────────────────────────────────────────────
Write-Step "创建 Python venv"
& $pyExe.Source -m venv .venv
$venvPy = "$InstallDir\wechat_agent\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip --quiet
Write-Ok "venv 就绪"

# ─── 6. 安装依赖（含 Windows 套件） ────────────────────────────────────
Write-Step "安装依赖（基础 + windows 套件）"
& $venvPy -m pip install -e ".[windows]" --quiet
Write-Ok "依赖安装完成"

# ─── 7. 配置文件 ──────────────────────────────────────────────────────
Write-Step "生成配置文件"
if (-not (Test-Path "config\config.yaml")) {
    Copy-Item "config\config.example.yaml" "config\config.yaml"
}
if (-not (Test-Path "config\tenants.yaml")) {
    Copy-Item "config\tenants.example.yaml" "config\tenants.yaml"
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
Write-Ok "配置就绪 · 请编辑 .env 填实际值"

# ─── 8. 注册启动任务（开机自启） ───────────────────────────────────────
Write-Step "注册 Windows 启动任务"
$taskName = "Baiyang-Client-$TenantId"
$action = New-ScheduledTaskAction `
    -Execute $venvPy `
    -Argument "-m client.main --tenant $TenantId --server $ServerUrl" `
    -WorkingDirectory "$InstallDir\wechat_agent"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Ok "已注册任务 $taskName · 下次登录自动启动"
} catch {
    Write-Warn "任务注册失败 · $_ · 可手动跑 .venv\Scripts\python -m client.main"
}

# ─── 9. 验证 ─────────────────────────────────────────────────────────
Write-Step "测试 server 连通性"
try {
    $resp = Invoke-RestMethod -Uri "$ServerUrl/v1/health" -Method Get -TimeoutSec 5
    Write-Ok "server 健康: $($resp.status) · tenants=$($resp.tenants_loaded)"
} catch {
    Write-Warn "server 不可达 · 请确认 $ServerUrl 已启动"
}

Write-Step "立即启动测试"
Write-Host ""
Write-Host "  $venvPy -m client.main --tenant $TenantId --server $ServerUrl" -ForegroundColor Yellow
Write-Host ""
Write-Ok "安装完成 · 重启电脑后自动运行 · 或手动跑上面那条命令"
