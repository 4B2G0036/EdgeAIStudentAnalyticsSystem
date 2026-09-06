@echo off
chcp 65001 >nul
title 學生專注度與異常行為分析系統 — 自動 API 對外穿透生成器

echo =======================================================================
echo 🌐 正在為您啟動 API 對外穿透通道生成器...
echo =======================================================================
echo.

cd /d "%~dp0"

:: Check python in venv or system
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

:: Run generate_tunnel.py
%PYTHON_BIN% scripts\generate_tunnel.py

pause
