@echo off
chcp 65001 >nul
title 學生專注度與異常行為分析系統 — 一鍵全自動啟動器

echo =======================================================================
echo 🚀 正在為您啟動【學生專注度與異常行為分析系統】...
echo =======================================================================
echo.

cd /d "%~dp0"

:: Select Python from .venv or PATH
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo 🔴 [錯誤] 系統未檢測到 Python 環境！
        echo 請先安裝 Python 3.10+ (勾選 Add Python to PATH) 後重試。
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

:: Run universal deploy_server.py
%PYTHON_CMD% scripts\deploy_server.py
set "DEPLOY_EXIT=%errorlevel%"

if %DEPLOY_EXIT% neq 0 (
    echo.
    echo 🔴 [啟動異常] 服務啟動未通過檢測驗證，請查閱上方診斷訊息。
    pause
    exit /b %DEPLOY_EXIT%
)

echo.
echo 🟢 [啟動程序完成] 服務已在背景持續運作中！
echo 按任意鍵關閉此主控台視窗 (服務會繼續於背景執行)...
pause >nul
