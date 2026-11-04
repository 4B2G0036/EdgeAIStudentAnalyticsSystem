"""
watchdog.py
============
背景監控守護程序 (由 deploy_server.py 自動啟動，單一實例)：
  - 每 10 秒檢查本機 FastAPI /health，連續失敗即自動重啟 Uvicorn
  - 每 30 秒檢查對外 Cloudflare Tunnel，失效即自動重建、更新 api-config.json / .env，
    並 (可選) 重新部署 Firebase Hosting，讓網頁端儀表板自動指向最新 API 網址

環境變數:
  WATCHDOG_FIREBASE_DEPLOY=0   停用穿透網址變更時自動部署 Firebase (預設啟用)
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service_manager as sm  # noqa: E402

API_CHECK_INTERVAL = 10
TUNNEL_CHECK_INTERVAL = 30
FAIL_THRESHOLD = 2
FIREBASE_DEPLOY = os.getenv("WATCHDOG_FIREBASE_DEPLOY", "1") != "0"


def stamp(msg):
    sm.log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def free_api_port():
    """釋放被卡死的舊 Uvicorn 佔用之 8000 埠"""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(f"netstat -ano | findstr :{sm.API_PORT}", shell=True, text=True)
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts[3].upper() and parts[4] != "0":
                    sm.kill_process_tree(int(parts[4]))
        else:
            subprocess.run(f"fuser -k {sm.API_PORT}/tcp", shell=True, capture_output=True)
    except Exception:
        pass


def restart_api():
    stamp("🔴 偵測到 API 離線，正在自動重啟 FastAPI...")
    free_api_port()
    time.sleep(1)
    sm.start_api()
    data = sm.wait_for_api(timeout=30)
    stamp("🟢 FastAPI 已恢復在線" if data else "⚠️ FastAPI 重啟後仍未通過健康檢查，下一輪將再次嘗試")
    return bool(data)


def main():
    stamp("🛡️ Watchdog 守護程序已啟動")
    api_fails = tunnel_fails = 0
    last_tunnel_check = 0.0

    while True:
        time.sleep(API_CHECK_INTERVAL)

        if sm.api_healthy():
            api_fails = 0
        else:
            api_fails += 1
            if api_fails >= FAIL_THRESHOLD:
                restart_api()
                api_fails = 0
            continue

        if time.time() - last_tunnel_check < TUNNEL_CHECK_INTERVAL:
            continue
        last_tunnel_check = time.time()

        status = sm.read_status()
        url = status.get("tunnel_url")
        if url and sm.tunnel_healthy(url):
            tunnel_fails = 0
            continue

        tunnel_fails += 1
        if tunnel_fails >= FAIL_THRESHOLD or not url:
            stamp("🔴 對外穿透通道失效，正在重建...")
            new_url = sm.ensure_tunnel(restart=True)
            tunnel_fails = 0
            if new_url and new_url != url:
                stamp(f"🟢 新穿透網址: {new_url}")
                if FIREBASE_DEPLOY and sm.deploy_firebase_hosting():
                    stamp("🟢 Firebase Hosting 已同步最新 API 網址")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

