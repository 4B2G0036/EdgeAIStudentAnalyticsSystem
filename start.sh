#!/usr/bin/env bash

# 學生專注度與異常行為分析系統 — Linux / macOS 一鍵啟動檔
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "======================================================================="
echo "🚀 正在為您啟動【學生專注度與異常行為分析系統】..."
echo "======================================================================="
echo ""

# Find python3 or python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "🔴 [錯誤] 系統未檢測到 Python 3 環境！請先安裝 Python 3.10+"
    exit 1
fi

$PYTHON_CMD scripts/deploy_server.py

echo ""
echo "🟢 [啟動程序完成] 服務已在背景持續運作中！"
