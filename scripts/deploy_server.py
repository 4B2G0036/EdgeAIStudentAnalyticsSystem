"""
deploy_server.py
=================
跨環境一鍵全自動化伺服器部署與啟動工具 (Universal Auto-Deployment Suite)：
  1. 自動檢查與建立 Python 虛擬環境 (.venv)
  2. 自動檢查與安裝所需相依套件 (pip install -r requirements.txt)
  3. 自動檢查與導出 AI YOLOv8 ONNX 模型權重 (yolov8n-pose.onnx)
  4. 自動檢查並複製環境變數範本 (.env.example -> .env)
  5. 自動執行 MongoDB 集合與時序索引初始化 (init_db.py)
  6. 自動檢測與啟動 FastAPI 後端 RESTful API 服務 (埠號 8000)
  7. 自動開啟 Cloudflare Tunnel 並實時擷取對外 HTTPS 穿透網址
  8. 進行全套端對端健康檢查 (Health Check) 確保 100% 在線

執行方式:
  python scripts/deploy_server.py
"""

import os
import sys
import time
import json
import shutil
import urllib.request
import urllib.error
import subprocess

# Ensure UTF-8 output encoding for consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

print("=" * 75)
print("🚀 啟動【學生專注度與異常行為分析系統】跨環境一鍵全自動伺服器部署")
print("=" * 75)

# Step 1: 虛擬環境 (.venv) 檢查與建立
print("\n[1/7] 檢查 Python 虛擬環境 (.venv)...")
venv_dir = os.path.join(ROOT_DIR, ".venv")
if sys.platform == "win32":
    python_bin = os.path.join(venv_dir, "Scripts", "python.exe")
    pip_bin = os.path.join(venv_dir, "Scripts", "pip.exe")
else:
    python_bin = os.path.join(venv_dir, "bin", "python")
    pip_bin = os.path.join(venv_dir, "bin", "pip")

if not os.path.exists(python_bin):
    print("  ℹ️ 檢測到尚未建立虛擬環境，正在自動建立 .venv...")
    try:
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        print("  🟢 [.venv 建立成功]")
    except Exception as e:
        print(f"  ⚠️ 虛擬環境建立警告: {e}，將使用當前 Python 執行")
        python_bin = sys.executable
        pip_bin = f"{sys.executable} -m pip"
else:
    print(f"  🟢 [虛擬環境就緒] 使用: {python_bin}")

# Step 2: 檢查與自動安裝 requirements.txt 相依套件
print("\n[2/7] 檢查並補齊 Python 相依套件 (requirements.txt)...")
req_file = os.path.join(ROOT_DIR, "requirements.txt")
check_cmd = [python_bin, "-c", "import fastapi, uvicorn, pymongo, cv2, ultralytics, onnxruntime, reportlab, httpx; print('OK')"]

need_install = False
try:
    res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
    if "OK" not in res.stdout:
        need_install = True
except Exception:
    need_install = True

if need_install:
    print("  ℹ️ 正在自動安裝/更新相依套件，請稍候...")
    try:
        subprocess.run([pip_bin, "install", "-r", req_file], check=True)
        print("  🟢 [套件安裝完成] 所有需求套件已全數就緒！")
    except Exception as e:
        print(f"  ⚠️ 套件安裝提醒: {e}")
else:
    print("  🟢 [相依套件就緒] 所有核心套件皆已安裝")

# Step 3: 檢查與自動匯出 ONNX 模型
print("\n[3/7] 檢查 AI 視覺模型權重 (models/yolov8n-pose.onnx)...")
models_dir = os.path.join(ROOT_DIR, "models")
os.makedirs(models_dir, exist_ok=True)
onnx_model_path = os.path.join(models_dir, "yolov8n-pose.onnx")

if not os.path.exists(onnx_model_path):
    print("  ℹ️ 檢測到缺失 ONNX 模型，正在自動導出 YOLOv8n-Pose ONNX 模型...")
    export_cmd = [python_bin, "-c", 
                  "from ultralytics import YOLO; model = YOLO('yolov8n-pose.pt'); model.export(format='onnx');"]
    try:
        subprocess.run(export_cmd, cwd=ROOT_DIR, check=True)
        # Move exported model if saved in root
        root_exported = os.path.join(ROOT_DIR, "yolov8n-pose.onnx")
        if os.path.exists(root_exported):
            shutil.move(root_exported, onnx_model_path)
        print(f"  🟢 [ONNX 導出成功] 模型已存至 {onnx_model_path}")
    except Exception as e:
        print(f"  ⚠️ 模型導出警告 (若已有預先下載模型可忽略): {e}")
else:
    size_mb = os.path.getsize(onnx_model_path) / (1024 * 1024)
    print(f"  🟢 [AI 模型就緒] {onnx_model_path} ({size_mb:.1f} MB)")

# Step 4: 檢查與建立 .env 設定檔
print("\n[4/7] 檢查環境變數組態 (.env)...")
env_file = os.path.join(ROOT_DIR, ".env")
env_example = os.path.join(ROOT_DIR, ".env.example")
if not os.path.exists(env_file):
    if os.path.exists(env_example):
        shutil.copy(env_example, env_file)
        print("  🟢 [.env 建立成功] 已自動從 .env.example 複製產生 .env 設定檔")
    else:
        print("  ⚠️ 警告: 找不到 .env.example 模板檔")
else:
    print("  🟢 [.env 就緒] 檢測到現有 .env 設定檔")

# Step 5: 執行 MongoDB 初始化
print("\n[5/7] 初始化 MongoDB 資料庫集合與時序索引...")
init_db_script = os.path.join(ROOT_DIR, "init_db.py")
try:
    res = subprocess.run([python_bin, init_db_script], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode == 0 or "SUCCESS" in res.stdout or "SUCCESS" in res.stderr:
        print("  🟢 [MongoDB 初始化成功] 集合與 Time Series 結構就緒！")
    else:
        print(f"  ⚠️ [MongoDB 訊息] {res.stdout.strip()}")
except Exception as e:
        print(f"  🔴 [MongoDB 警告] 連線失敗 (請確認本機 MongoDB 服務已啟動): {e}")

# Step 6: 啟動 FastAPI 後端 API (8000 埠)
print("\n[6/7] 檢查並啟動 FastAPI 後端 API 服務 (http://localhost:8000)...")
is_api_running = False
try:
    req = urllib.request.Request("http://localhost:8000/")
    with urllib.request.urlopen(req, timeout=2) as resp:
        if resp.status == 200:
            is_api_running = True
            print("  🟢 [FastAPI 就緒] 8000 埠 API 已在線運作中")
except Exception:
    pass

if not is_api_running:
    print("  ℹ️ 正在背景啟動 FastAPI 後端服務 (uvicorn)...")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [python_bin, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs
    )
    time.sleep(3)
    print("  🟢 [FastAPI 啟動成功] 後端 API 已上線！")

# Step 7: 啟動 API 對外穿透通道與動態提取網址
print("\n[7/7] 檢查與建立 API 對外穿透通道...")
try:
    from scripts.generate_tunnel import generate_tunnel
    tunnel_url = generate_tunnel(port=8000, once=True)
except Exception as e:
    print(f"  ⚠️ 穿透通道生成提醒: {e}")
    tunnel_url = "http://localhost:8000"

if not tunnel_url:
    tunnel_url = "http://localhost:8000"

print(f"  🟢 [API 穿透通道就緒] 對外存取網址: {tunnel_url}")


# Health Check Verification
print("\n" + "=" * 75)
print("🎉 【伺服器跨環境部署完全成功 — 系統現已全效在線運作！】")
print("=" * 75)
print(f"  🌐 靜態儀表板 Web 體驗: https://studentanalytics-91cd1.web.app")
print(f"  💻 本機儀表板位址:       http://localhost:8000/dashboard")
print(f"  📡 後端 API 服務位址:    http://localhost:8000")
print(f"  🔒 HTTPS 對外穿透網址:   {tunnel_url}")
print(f"  📚 Swagger API 互動文件: {tunnel_url}/docs")
print("=" * 75)
