"""
generate_tunnel.py
===================
全自動 API 對外穿透網址生成與管理工具：
  1. 自動檢測本地 FastAPI 服務狀態 (預設 http://localhost:8000)
  2. 若服務未啟動，支援自動於背景開啟 Uvicorn API
  3. 多重穿透通道引擎備援 (Cloudflare Tunnel -> Pinggy SSH -> LocalTunnel)
  4. 精準正則表達式擷取 HTTPS 對外穿透網址
  5. 自動寫入狀態檔 (scratch/tunnel_status.json) 與 .env (PUBLIC_API_URL)

用法:
  python scripts/generate_tunnel.py            # 保持連線並持續提供穿透網址
  python scripts/generate_tunnel.py --once     # 擷取網址後寫入狀態檔即離開
"""

import os
import sys
import time
import re
import json
import argparse
import subprocess
import urllib.request
from datetime import datetime, timezone

# UTF-8 encoding configuration
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

STATUS_FILE = os.path.join(ROOT_DIR, "scratch", "tunnel_status.json")
ENV_FILE = os.path.join(ROOT_DIR, ".env")


def check_api_running(host="localhost", port=8000):
    """檢查 API 服務是否於指定的 Port 運作中"""
    try:
        url = f"http://{host}:{port}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_local_api(port=8000):
    """背景啟動 FastAPI 後端 API"""
    print(f"  ℹ️ 檢測到埠號 {port} 尚未啟動 API，正在自動於背景啟動 Uvicorn 服務...")
    python_bin = sys.executable
    venv_python = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(ROOT_DIR, ".venv", "bin", "python")
    if os.path.exists(venv_python):
        python_bin = venv_python

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [python_bin, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs
    )
    
    # 等待服務就緒
    for _ in range(10):
        time.sleep(1)
        if check_api_running(port=port):
            print("  🟢 [FastAPI 啟動成功] 本地 API 已正常在線運作！")
            return True
    print("  ⚠️ API 啟動超時，請檢查背景程式或日誌。")
    return False


def update_tunnel_status(tunnel_url, engine_name, port=8000):
    """更新持久化檔案與 .env 環境變數"""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    status_data = {
        "status": "online",
        "tunnel_url": tunnel_url,
        "swagger_docs": f"{tunnel_url}/docs",
        "dashboard_url": f"{tunnel_url}/dashboard/",
        "engine": engine_name,
        "local_port": port,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
        print(f"  🟢 [狀態已存檔] {STATUS_FILE}")
    except Exception as e:
        print(f"  ⚠️ 無法寫入狀態檔: {e}")

    # 更新 .env 檔中的 PUBLIC_API_URL
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            found = False
            new_lines = []
            for line in lines:
                if line.startswith("PUBLIC_API_URL="):
                    new_lines.append(f"PUBLIC_API_URL={tunnel_url}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"\nPUBLIC_API_URL={tunnel_url}\n")

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print("  🟢 [.env 已同步] 設定檔 PUBLIC_API_URL 已更新。")
        except Exception as e:
            print(f"  ⚠️ 更新 .env 失敗: {e}")


def try_cloudflare_tunnel(port=8000, timeout_sec=15):
    """引擎 1: Cloudflare Tunnel (cloudflared)"""
    print("  📡 正在嘗試透過 Cloudflare Tunnel 建立穿透通道...")
    cmd = ["npx", "--yes", "cloudflared", "tunnel", "--url", f"http://localhost:{port}"]
    
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=(sys.platform == "win32")
    )
    
    tunnel_url = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    while time.time() - start_time < timeout_sec:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.3)
            continue
        matches = url_pattern.findall(line)
        if matches:
            tunnel_url = matches[0]
            break
            
    return proc, tunnel_url


def try_pinggy_tunnel(port=8000, timeout_sec=10):
    """引擎 2: Pinggy SSH 穿透"""
    print("  📡 正在嘗試透過 Pinggy SSH 建立穿透通道...")
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{port}", "free.pinggy.online"]
    
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=(sys.platform == "win32")
    )
    
    tunnel_url = None
    start_time = time.time()
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.free\.pinggy\.link")
    
    while time.time() - start_time < timeout_sec:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.3)
            continue
        matches = url_pattern.findall(line)
        if matches:
            tunnel_url = matches[0]
            break

    return proc, tunnel_url


def generate_tunnel(port=8000, once=False):
    print("=" * 70)
    print(f"🌐 自動生成 API 對外穿透網址工具 (目標 Port: {port})")
    print("=" * 70)

    # Step 1: 檢查本地 API
    if not check_api_running(port=port):
        started = start_local_api(port=port)
        if not started:
            print("❌ 無法啟動本地 API 服務，穿透程序中斷。")
            return None

    # Step 2: 依序試用穿透引擎
    proc, tunnel_url = try_cloudflare_tunnel(port=port)
    engine_name = "Cloudflare Tunnel"

    if not tunnel_url:
        print("  ⚠️ Cloudflare 穿透未回應，轉用 Pinggy SSH 備援引擎...")
        if proc:
            proc.terminate()
        proc, tunnel_url = try_pinggy_tunnel(port=port)
        engine_name = "Pinggy SSH"

    if not tunnel_url:
        print("❌ 穿透通道建立失敗，請檢查網路連線或防火牆。")
        if proc:
            proc.terminate()
        return None

    # Step 3: 更新狀態檔與環境變數
    update_tunnel_status(tunnel_url, engine_name, port=port)

    print("\n" + "=" * 70)
    print("🎉 【API 對外穿透網址生成成功！】")
    print("=" * 70)
    print(f"  🔒 穿透網址 (Public URL): {tunnel_url}")
    print(f"  📚 Swagger API 文件:      {tunnel_url}/docs")
    print(f"  💻 儀表板入口:            {tunnel_url}/dashboard/")
    print(f"  ⚡ 穿透引擎:              {engine_name}")
    print("=" * 70)

    if once:
        if proc:
            # 放離背景繼續運行通道
            pass
        return tunnel_url

    print("\n💡 穿透通道持續維護中... (按 Ctrl+C 可停止穿透)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 正在關閉穿透通道...")
        if proc:
            proc.terminate()
        print("🟢 穿透通道已順利關閉。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自動生成 API 穿透網址工具")
    parser.add_argument("--port", type=int, default=8000, help="本地 API 埠號 (預設: 8000)")
    parser.add_argument("--once", action="store_true", help="僅生成並儲存網址後立刻離開")
    args = parser.parse_args()

    generate_tunnel(port=args.port, once=args.once)
