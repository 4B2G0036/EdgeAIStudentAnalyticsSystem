# 學生專注度與異常行為分析系統 — PowerShell 一鍵自動化伺服器部署腳本 (deploy_server.ps1)
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🚀 啟動【學生專注度與異常行為分析系統】PowerShell 一鍵部署流程" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. 檢查並複製 .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "🟢 已自動從 .env.example 建立 .env 設定檔" -ForegroundColor Green
    }
}

# 2. 執行 Python 全自動部署工具
.venv\Scripts\python.exe scripts/deploy_server.py

Write-Host "`n✅ PowerShell 部署程序執行完成！" -ForegroundColor Green
