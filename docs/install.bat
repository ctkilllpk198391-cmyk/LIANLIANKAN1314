@echo off
chcp 65001 > nul
title wechat_agent Installer
echo.
echo ===============================================
echo   wechat_agent One-Click Installer
echo   Server: http://120.26.208.212
echo ===============================================
echo.
echo  Starting installation, please wait...
echo  (5-8 minutes total)
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Remove-Item '$env:USERPROFILE\WechatAgent' -Recurse -Force -ErrorAction SilentlyContinue; $ps = Invoke-WebRequest -Uri 'http://120.26.208.212/download/install_client.ps1' -UseBasicParsing; Invoke-Expression $ps.Content } catch { Write-Host ''; Write-Host 'ERROR:' $_.Exception.Message -ForegroundColor Red; Write-Host ''; Write-Host 'Please send screenshot to support.' -ForegroundColor Yellow }"

echo.
echo ===============================================
echo   Press any key to close this window
echo ===============================================
pause > nul
