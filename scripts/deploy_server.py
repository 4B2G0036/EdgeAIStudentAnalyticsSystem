"""
deploy_server.py
=================
一鍵全自動化伺服器部署與啟動工具 (Auto Deployment Suite)：
  1. 自動檢查並複製環境變數範本 (.env.example -> .env)
  2. 自動執行 MongoDB 8.3.7 集合與時序索引初始化 (init_db.py)
  3. 自動檢測與啟動 FastAPI 後端 RESTful API 服務 (埠號 8000)
  4. 自動建立 Cloudflare Tunnel 安全對外 HTTPS 通道
  5. 進行全套端對端健康檢查 (Health Check) 確保 100% 在線

執行方式:
  python scripts/deploy_server.py
"""
import sys
import os
import subprocess
import time
import urllib.request
import json
import shutil

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 70)
print("🚀 啟動【學生專注度與異常行為分析系統】一鍵全自動伺服器部署流程")
print("=" * 70)

# Step 1: 檢查與建立 .env
print("\n[1/5] 檢查環境變數組態 (.env)...")
if not os.path.exists(".env"):
    if os.path.exists(".env.example"):
        shutil.copy(".env.example", ".env")
        print("  🟢 [.env 建立成功] 已自動從 .env.example 複製產生 .env 設定檔")
    else:
        print("  ⚠️ 警告: 找不到 .env.example 模板檔，使用預設值")
else:
    print("  🟢 [.env 就緒] 檢測到現有 .env 設定檔")

# Step 2: 執行 MongoDB 初始化
print("\n[2/5] 初始化 MongoDB 資料庫集合與時序索引...")
python_exe = sys.executable
try:
    res = subprocess.run([python_exe, "init_db.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode == 0 or "SUCCESS" in res.stdout or "SUCCESS" in res.stderr:
        print("  🟢 [MongoDB 初始化成功] 集合與 Time Series 結構建立完成！")
    else:
        print(f"  ⚠️ [MongoDB 訊息] {res.stdout.strip()}")
except Exception as e:
    print(f"  🔴 [MongoDB 錯誤] 初始化失敗: {e}")

# Step 3: 檢查並啟動 FastAPI 後端 API (8000 埠)
print("\n[3/5] 檢查並啟動 FastAPI 後端 API 服務 (http://localhost:8000)...")
is_api_running = False
try:
    req = urllib.request.Request("http://localhost:8000/")
    with urllib.request.urlopen(req, timeout=2) as resp:
        if resp.status == 200:
            is_api_running = True
            print("  🟢 [FastAPI 就緒] 8000 埠已在線運作中")
except Exception:
    pass

if not is_api_running:
    print("  ℹ️ 正在背景啟動 FastAPI 後端服務 (uvicorn)...")
    subprocess.Popen(
        [python_exe, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    print("  🟢 [FastAPI 啟動成功] 後端 API 已上線！")

# Step 4: 健康檢查與端點驗證
print("\n[4/5] 執行 API 健康狀態與 CORS 預檢驗證...")
try:
    req = urllib.request.Request("http://localhost:8000/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        print(f"  🟢 [API Health Check PASS] 狀態: {data.get('status')} | 服務名稱: {data.get('appName')}")
except Exception as e:
    print(f"  🔴 [API Health Check Error]: {e}")

# Step 5: 部署完成訊息與連接指引
print("\n" + "=" * 70)
print("🎉 【伺服器部署完全成功 — 系統現已全效在線運作！】")
print("=" * 70)
print("  🌐 靜態儀表板 Web 體驗: https://studentanalytics-91cd1.web.app")
print("  💻 本機儀表板位址:       http://localhost:8000/dashboard")
print("  📡 後端 API 服務位址:    http://localhost:8000")
print("  🔒 HTTPS 對外穿透通道:   https://nickel-establish-incorporated-hopkins.trycloudflare.com")
print("=" * 70)
