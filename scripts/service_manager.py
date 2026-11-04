"""
service_manager.py
===================
API / Cloudflare Tunnel 服務生命週期管理共用模組 (供 deploy_server.py 與 watchdog.py 共用)：
  1. 可靠地以「脫離父行程」方式啟動 Uvicorn 與 Cloudflare Tunnel (輸出寫入日誌檔，避免管線中斷導致通道死亡)
  2. 本機 API 與對外穿透網址的端對端健康檢查 (/health)
  3. 發佈最新 API 網址至 dashboard/api-config.json 與 scratch/tunnel_status.json、.env
  4. 選擇性將最新設定部署至 Firebase Hosting，使雲端靜態儀表板自動指向最新 API
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH_DIR = os.path.join(ROOT_DIR, "scratch")
STATUS_FILE = os.path.join(SCRATCH_DIR, "tunnel_status.json")
API_CONFIG_FILE = os.path.join(ROOT_DIR, "dashboard", "api-config.json")
ENV_FILE = os.path.join(ROOT_DIR, ".env")
UVICORN_LOG = os.path.join(SCRATCH_DIR, "uvicorn_server.log")
TUNNEL_LOG = os.path.join(SCRATCH_DIR, "cloudflared.log")
WATCHDOG_PID_FILE = os.path.join(SCRATCH_DIR, "watchdog.pid")
WATCHDOG_LOG = os.path.join(SCRATCH_DIR, "watchdog.log")

API_PORT = 8000
TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

# Windows process creation flags
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def log(msg):
    print(msg, flush=True)


def get_python_bin():
    """回傳專案 .venv 的 Python；找不到時退回目前直譯器"""
    if sys.platform == "win32":
        venv_python = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(ROOT_DIR, ".venv", "bin", "python")
    return venv_python if os.path.exists(venv_python) else sys.executable


def read_env_value(key, default=""):
    """讀取設定值：優先環境變數，其次專案 .env (不依賴 python-dotenv，供啟動前期使用)"""
    val = os.environ.get(key)
    if val:
        return val.strip()
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default


def named_tunnel_config():
    """
    具名 Tunnel 設定 (Cloudflare Named Tunnel)。需同時設定於 .env：
      CLOUDFLARE_TUNNEL_TOKEN  Zero Trust 後台建立 Tunnel 後取得的 token
      TUNNEL_PUBLIC_URL        於該 Tunnel 設定的 Public Hostname，例如 https://api.example.com
    兩者齊備回傳 (token, url)，否則回傳 None (自動退回免帳號的 Quick Tunnel)。
    """
    token = read_env_value("CLOUDFLARE_TUNNEL_TOKEN")
    url = read_env_value("TUNNEL_PUBLIC_URL").rstrip("/")
    if not token or not url:
        return None
    if not url.startswith("https://"):
        url = "https://" + url.split("://")[-1]
    return token, url


def spawn_detached(cmd, log_path, cwd=ROOT_DIR, env=None):
    """
    以獨立行程群組啟動背景程序，標準輸出/錯誤寫入 log_path (不使用管線，避免父行程結束後管線中斷導致程序死亡)。
    Windows 下使用 CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP，關閉啟動用的終端機視窗後程序仍會持續運作。
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_fp = open(log_path, "a", encoding="utf-8", errors="replace")
    log_fp.write(f"\n--- Process Starting at {time.strftime('%Y-%m-%d %H:%M:%S')}: {' '.join(cmd)} ---\n")
    log_fp.flush()

    kwargs = {"cwd": cwd, "stdout": log_fp, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if env:
        kwargs["env"] = {**os.environ, **env}
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def kill_process_tree(pid):
    """結束指定 PID 及其子行程"""
    if not pid:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(pid), 15)
    except Exception:
        pass


def pid_alive(pid):
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def http_get_json(url, timeout=3.0):
    """GET 並解析 JSON，失敗時回傳 None"""
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "student-analytics-service-manager"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def api_healthy(base_url=f"http://127.0.0.1:{API_PORT}", timeout=3.0):
    """API 與資料庫皆正常時回傳 health 資料，否則回傳 None"""
    data = http_get_json(f"{base_url}/health", timeout=timeout)
    if data and data.get("status") == "healthy" and data.get("database", {}).get("status") == "connected":
        return data
    return None


# ---------------------------------------------------------------- API ---
def start_api():
    """背景啟動 Uvicorn，並回傳 Popen"""
    return spawn_detached(
        [get_python_bin(), "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", str(API_PORT)],
        UVICORN_LOG,
    )


def wait_for_api(timeout=30):
    for _ in range(int(timeout)):
        data = api_healthy()
        if data:
            return data
        time.sleep(1)
    return None


# ------------------------------------------------------------- Tunnel ---
def read_status():
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def tunnel_healthy(tunnel_url, timeout=6.0):
    """對外穿透網址能端對端連回本機 API (且資料庫已連線) 才算健康"""
    if not tunnel_url:
        return False
    return api_healthy(tunnel_url, timeout=timeout) is not None


def _tunnel_command():
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return [cloudflared, "tunnel", "--url", f"http://localhost:{API_PORT}", "--no-autoupdate"]
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        return None
    return [npx, "--yes", "cloudflared", "tunnel", "--url", f"http://localhost:{API_PORT}"]


def _cloudflared_base():
    """回傳啟動 cloudflared 的前綴指令 (優先本機安裝，其次 npx)"""
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return [cloudflared]
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    return [npx, "--yes", "cloudflared"] if npx else None


def start_named_tunnel(token, timeout=60):
    """
    啟動具名 Tunnel：token 以環境變數 TUNNEL_TOKEN 傳入 (不會出現在命令列、行程清單或日誌)。
    以日誌出現 'Registered tunnel connection' 判定已向 Cloudflare 註冊成功。
    回傳 (pid, error_message)；成功時 error_message 為 None。
    """
    base = _cloudflared_base()
    if not base:
        return None, "找不到 cloudflared 或 npx"

    os.makedirs(SCRATCH_DIR, exist_ok=True)
    offset = os.path.getsize(TUNNEL_LOG) if os.path.exists(TUNNEL_LOG) else 0
    proc = spawn_detached(base + ["tunnel", "--no-autoupdate", "run"], TUNNEL_LOG, env={"TUNNEL_TOKEN": token})

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        try:
            with open(TUNNEL_LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                content = f.read()
        except Exception:
            content = ""
        if "Registered tunnel connection" in content:
            return proc.pid, None
        if proc.poll() is not None:
            reason = [l for l in content.splitlines() if " ERR " in l or "error" in l.lower()][-1:] or ["cloudflared 已結束"]
            return None, reason[0].strip()[-200:]
    kill_process_tree(proc.pid)
    return None, "等待註冊逾時"


def start_tunnel(timeout=45):
    """
    啟動 Cloudflare Quick Tunnel (脫離父行程，日誌寫入 scratch/cloudflared.log)，
    由日誌擷取 trycloudflare 網址。回傳 (pid, url)，失敗時 url 為 None。
    """
    cmd = _tunnel_command()
    if not cmd:
        log("  ⚠️ 找不到 cloudflared 或 npx，無法建立對外穿透通道")
        return None, None

    # Only look at log content written after this launch
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    offset = os.path.getsize(TUNNEL_LOG) if os.path.exists(TUNNEL_LOG) else 0
    proc = spawn_detached(cmd, TUNNEL_LOG)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        if proc.poll() is not None:
            break
        try:
            with open(TUNNEL_LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                found = TUNNEL_URL_PATTERN.findall(f.read())
            if found:
                return proc.pid, found[-1]
        except Exception:
            continue
    kill_process_tree(proc.pid)
    return None, None


def wait_tunnel_reachable(url, timeout=45):
    """Quick Tunnel 的 DNS 需要數秒傳播，輪詢直到可由公網存取"""
    for _ in range(int(timeout / 2)):
        if tunnel_healthy(url):
            return True
        time.sleep(2)
    return False


def ensure_tunnel(restart=False):
    """
    確保對外穿透通道在線：既有通道健康則沿用；否則終止舊通道並重新建立。
    回傳穿透網址 (失敗為 None)，並同步發佈最新 API 網址。
    """
    status = read_status()
    old_url, old_pid = status.get("tunnel_url"), status.get("pid")
    named = named_tunnel_config()

    # 模式切換 (Quick <-> Named) 時不沿用舊通道
    expected_engine = "Cloudflare Named Tunnel" if named else "Cloudflare Tunnel"
    same_mode = status.get("engine") == expected_engine and (not named or old_url == named[1])

    if not restart and same_mode and old_url and pid_alive(old_pid) and tunnel_healthy(old_url):
        log(f"  🟢 [沿用既有穿透通道] {old_url}")
        publish_api_url(old_url, expected_engine, old_pid)
        return old_url

    if old_pid:
        kill_process_tree(old_pid)

    if named:
        token, public_url = named
        for attempt in range(1, 4):
            log(f"  🔐 正在連線 Cloudflare 具名 Tunnel -> {public_url} (第 {attempt}/3 次嘗試)...")
            pid, err = start_named_tunnel(token)
            if err:
                log(f"  ⚠️ 具名 Tunnel 啟動失敗: {err}")
                continue
            if wait_tunnel_reachable(public_url, timeout=60):
                log(f"  🟢 [具名 Tunnel 驗證通過] {public_url} (固定網址)")
                publish_api_url(public_url, "Cloudflare Named Tunnel", pid)
                return public_url
            log("  ⚠️ 具名 Tunnel 已註冊但固定網址無法連回本機 API，請檢查 Public Hostname 是否指向 http://localhost:8000")
            kill_process_tree(pid)
        log("  🔴 具名 Tunnel 無法使用，退回 Quick Tunnel (臨時網址)")

    for attempt in range(1, 4):
        log(f"  📡 正在建立 Cloudflare Tunnel 穿透通道 (第 {attempt}/3 次嘗試)...")
        pid, url = start_tunnel()
        if not url:
            continue
        if wait_tunnel_reachable(url):
            log(f"  🟢 [穿透通道驗證通過] {url}")
        else:
            log(f"  ⚠️ 穿透網址已產生但尚未可由公網存取，仍先行發佈: {url}")
        publish_api_url(url, "Cloudflare Tunnel", pid)
        return url
    log("  🔴 穿透通道建立失敗，已改用本機位址")
    publish_api_url(None, "none", None)
    return None


# ------------------------------------------------------------ Publish ---
def publish_api_url(tunnel_url, engine, pid):
    """寫入 tunnel_status.json、dashboard/api-config.json 與 .env 的 PUBLIC_API_URL"""
    now = datetime.now(timezone.utc).isoformat()
    os.makedirs(SCRATCH_DIR, exist_ok=True)

    status = {
        "status": "online" if tunnel_url else "offline",
        "tunnel_url": tunnel_url,
        "swagger_docs": f"{tunnel_url}/docs" if tunnel_url else None,
        "dashboard_url": f"{tunnel_url}/dashboard/" if tunnel_url else None,
        "engine": engine,
        "local_port": API_PORT,
        "pid": pid,
        "updated_at": now,
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    # 儀表板自動探索用設定檔 (由 FastAPI 與 Firebase Hosting 靜態提供)
    candidates = []
    if tunnel_url:
        candidates.append(tunnel_url)
    candidates += [f"http://localhost:{API_PORT}", f"http://127.0.0.1:{API_PORT}"]
    api_config = {"api_base": tunnel_url or f"http://localhost:{API_PORT}", "candidates": candidates, "updated_at": now}
    try:
        with open(API_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(api_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"  ⚠️ 無法寫入 api-config.json: {e}")

    if tunnel_url and os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            out, found = [], False
            for line in lines:
                if line.startswith("PUBLIC_API_URL="):
                    out.append(f"PUBLIC_API_URL={tunnel_url}\n")
                    found = True
                else:
                    out.append(line)
            if not found:
                out.append(f"\nPUBLIC_API_URL={tunnel_url}\n")
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(out)
        except Exception as e:
            log(f"  ⚠️ 更新 .env 失敗: {e}")


def deploy_firebase_hosting(timeout=120):
    """將含最新 api-config.json 的儀表板部署至 Firebase Hosting (失敗不影響啟動)"""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx or not os.path.exists(os.path.join(ROOT_DIR, "firebase.json")):
        return False
    try:
        res = subprocess.run(
            [npx, "--yes", "firebase-tools", "deploy", "--only", "hosting", "--non-interactive"],
            cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return True
        tail = (res.stdout + res.stderr).strip().splitlines()[-3:]
        log("  ⚠️ Firebase 部署未成功: " + " | ".join(tail))
    except Exception as e:
        log(f"  ⚠️ Firebase 部署略過: {e}")
    return False


# ----------------------------------------------------------- Watchdog ---
def watchdog_running():
    try:
        with open(WATCHDOG_PID_FILE, "r", encoding="utf-8") as f:
            return pid_alive(int(f.read().strip()))
    except Exception:
        return False


def start_watchdog():
    """啟動單一實例的背景監控行程 (scripts/watchdog.py)"""
    if watchdog_running():
        return False
    proc = spawn_detached([get_python_bin(), os.path.join(ROOT_DIR, "scripts", "watchdog.py")], WATCHDOG_LOG)
    with open(WATCHDOG_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    return True


def stop_watchdog():
    try:
        with open(WATCHDOG_PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        if pid != os.getpid():
            kill_process_tree(pid)
    except Exception:
        pass
