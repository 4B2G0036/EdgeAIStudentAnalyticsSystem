@echo off
chcp 65001 >nul
title 學生專注度與異常行為分析系統 — 一鍵全自動啟動器

echo =======================================================================
echo 🚀 正在為您啟動【學生專注度與異常行為分析系統】...
echo =======================================================================
echo.

cd /d "%~dp0"

:: Check if Python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 🔴 [錯誤] 系統未檢測到 Python 環境！
    echo 請先安裝 Python 3.10+ (勾選 Add Python to PATH) 後重試。
    pause
    exit /b 1
)

:: Run universal deploy_server.py
python scripts\deploy_server.py

echo.
echo 🟢 [啟動程序完成] 服務已在背景持續運作中！
echo 按任意鍵關閉此主控台視窗 (服務會繼續於背景執行)...
pause >nul
