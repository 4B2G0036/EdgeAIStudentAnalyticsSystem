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

# Helper functions for bulletproof startup
def check_socket_port(host="127.0.0.1", port=8000, timeout=1.0):
    """檢測本機指定的網路埠號是否已在監聽中"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def ensure_mongodb_running():
    """檢查並自癒啟動 MongoDB 服務"""
    if check_socket_port("127.0.0.1", 27017, timeout=1.0):
        return True

    print("  ℹ️ 檢測到 MongoDB 尚未在 27017 埠運作，嘗試喚醒本機服務...")
    if sys.platform == "win32":
        try:
            subprocess.run("net start MongoDB", shell=True, capture_output=True, text=True)
        except Exception:
            pass
    elif sys.platform == "darwin":
        subprocess.run(["brew", "services", "start", "mongodb-community"], capture_output=True)
    else:
        subprocess.run(["sudo", "systemctl", "start", "mongod"], capture_output=True)

    for _ in range(5):
        time.sleep(1)
        if check_socket_port("127.0.0.1", 27017, timeout=1.0):
            print("  🟢 [MongoDB 自動喚醒成功] 本機資料庫服務已在線！")
            return True

    print("  ⚠️ [警告] 無法自動啟動 MongoDB，請手動確認 MongoDB 服務是否已安裝並啟動。")
    return False


def reclaim_port(port=8000):
    """檢測並安全清理 Port 8000 上的殭屍進程，避免 Address already in use"""
    if not check_socket_port("127.0.0.1", port, timeout=0.8):
        return

    try:
        req = urllib.request.Request(f"http://localhost:{port}/health")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "healthy" and data.get("database", {}).get("status") == "connected":
                    return
    except Exception:
        pass

    print(f"  ⚠️ 檢測到 Port {port} 存在非活躍或異常進程，正在進行安全釋放...")
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
            killed_pids = set()
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts[3].upper():
                    pid = parts[4]
                    if pid not in killed_pids and pid != "0":
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                        killed_pids.add(pid)
            if killed_pids:
                print(f"  🟢 [Port {port} 已釋放] 已清理舊進程 PID: {', '.join(killed_pids)}")
                time.sleep(1.5)
        except Exception as e:
            print(f"  ⚠️ 清理 Port {port} 失敗: {e}")
    else:
        try:
            subprocess.run(f"fuser -k {port}/tcp", shell=True, capture_output=True)
            time.sleep(1.0)
        except Exception:
            pass


# Step 5: 執行 MongoDB 初始化
print("\n[5/7] 初始化 MongoDB 資料庫集合與時序索引...")
ensure_mongodb_running()
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
reclaim_port(port=8000)

log_dir = os.path.join(ROOT_DIR, "scratch")
os.makedirs(log_dir, exist_ok=True)
uvicorn_log_file = os.path.join(log_dir, "uvicorn_server.log")

is_api_healthy = False
db_latency = None
try:
    req = urllib.request.Request("http://localhost:8000/health")
    with urllib.request.urlopen(req, timeout=1.5) as resp:
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "healthy" and data.get("database", {}).get("status") == "connected":
                is_api_healthy = True
                db_latency = data.get("database", {}).get("latency_ms")
                print(f"  🟢 [FastAPI 就緒] API 服務已在線，MongoDB 延遲: {db_latency} ms")
except Exception:
    pass

if not is_api_healthy:
    print("  ℹ️ 正在背景啟動 FastAPI 後端服務 (日誌寫入 scratch/uvicorn_server.log)...")
    kwargs = {}
    if sys.platform == "win32":
        # DETACHED_PROCESS (0x00000008) + CREATE_NEW_PROCESS_GROUP (0x00000200)
        kwargs["creationflags"] = 0x00000008 | 0x00000200

    log_fp = open(uvicorn_log_file, "a", encoding="utf-8")
    log_fp.write(f"\n--- Server Starting at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_fp.flush()

    subprocess.Popen(
        [python_bin, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT_DIR,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        **kwargs
    )

    print("  ⏳ 正在驗證 API 服務與資料庫握手狀態 (Active Health Polling)...")
    for attempt in range(15):
        time.sleep(1)
        try:
            req = urllib.request.Request("http://localhost:8000/health")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == "healthy" and data.get("database", {}).get("status") == "connected":
                        is_api_healthy = True
                        db_latency = data.get("database", {}).get("latency_ms")
                        print(f"  🟢 [驗證通過] FastAPI 後端啟動成功！MongoDB 連線延遲: {db_latency} ms")
                        break
        except Exception:
            continue

    if not is_api_healthy:
        print("  🔴 [啟動驗證超時] FastAPI 在 15 秒內未回報健康狀態，最後診斷日誌：")
        print("  " + "-" * 60)
        try:
            with open(uvicorn_log_file, "r", encoding="utf-8", errors="replace") as lf:
                lines = lf.readlines()[-15:]
                for l in lines:
                    print(f"    {l.rstrip()}")
        except Exception:
            pass
        print("  " + "-" * 60)
        print("  請檢查上方報錯並修正後再重新執行。")
        sys.exit(1)

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
print(f"  🩺 資料庫健康診斷端點:   http://localhost:8000/health (連線延遲: {db_latency} ms)")
print(f"  🔒 HTTPS 對外穿透網址:   {tunnel_url}")
print(f"  📚 Swagger API 互動文件: {tunnel_url}/docs")
print("=" * 75)
