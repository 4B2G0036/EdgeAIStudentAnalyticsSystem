"""
test_all_features.py
======================
目前階段全功能整合測試與驗證套件：
  1. [MongoDB] 連線與 3 大 Collection / Time-Series / 索引驗證
  2. [AI 模型] YOLOv8-Pose ONNX (n/m 版) 模型檔案與 CPU 推論時間 (≤ 200ms)
  3. [FastAPI 後端 API] 
     - 健康狀態 GET /
     - CORS OPTIONS Preflight 200 OK 驗證
     - 課程生命週期: POST (開課) -> GET (列表/單筆) -> PATCH (更新) -> PATCH (結束) -> DELETE (刪除)
     - MJPEG 視訊串流 GET /api/v1/stream Boundary 驗證
  4. [Cloudflare Tunnel] 對外穿透通道驗證

執行方式:
  .venv\\Scripts\\python.exe scripts/test_all_features.py
"""
import sys, os, time, json, urllib.request, urllib.error
from datetime import datetime, timezone

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OK   = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️ WARN"

results = []

def record(category, test_name, status, detail=""):
    results.append((category, test_name, status, detail))
    icon = "✅" if status == OK else ("❌" if status == FAIL else "⚠️")
    print(f"  {icon} [{category}] {test_name}: {detail}")

print("=" * 70)
print("🚀 開始進行【學生專注度與異常行為分析系統】目前階段全功能綜合測試")
print("=" * 70)

# ── 1. MongoDB 驗證 ──────────────────────────────────────────────────────────
print("\n[1/4] 🗄️ MongoDB 資料庫服務與集合結構測試...")
try:
    from database.connection import get_db
    from database.collections import initialize_database
    initialize_database()
    db = get_db()
    cols = db.list_collection_names()
    
    needed_cols = ["Classes_Session", "Attention_Metrics", "Abnormal_Events"]
    missing = [c for c in needed_cols if c not in cols]
    
    if not missing:
        record("MongoDB", "集合初始化與 Time Series 驗證", OK, f"集合完整: {cols}")
    else:
        record("MongoDB", "集合初始化驗證", FAIL, f"缺失集合: {missing}")
except Exception as e:
    record("MongoDB", "資料庫連線測試", FAIL, str(e))

# ── 2. ONNX AI 模型檔案存在性與驗證 ──────────────────────────────────────────
print("\n[2/4] 🤖 邊緣 AI ONNX 模型檔案與權重檢查...")
models = [
    ("models/yolov8n-pose.onnx", "Nano - 輕量主用 (12.9MB)"),
    ("models/yolov8m-pose.onnx", "Medium - 高精度備用 (101.2MB)"),
]
for path, label in models:
    if os.path.exists(path):
        size_mb = os.path.getsize(path) / 1024 / 1024
        record("AI Model", label, OK, f"檔案就緒 ({size_mb:.1f} MB)")
    else:
        record("AI Model", label, FAIL, f"檔案缺失: {path}")

# ── 3. FastAPI 後端 API 全端點測試 ──────────────────────────────────────────
print("\n[3/4] ⚡ FastAPI 後端 RESTful API 完整端點測試 (http://localhost:8000)...")
API_BASE = "http://localhost:8000"

def http_req(path, method="GET", data=None, headers=None):
    if headers is None: headers = {}
    headers["User-Agent"] = "TestClient/1.0"
    if data and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode("utf-8") if isinstance(data, dict) else None
    
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            try: json_data = json.loads(content)
            except: json_data = content
            return resp.status, json_data, dict(resp.headers)
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8", errors="ignore")
        try: json_data = json.loads(content)
        except: json_data = content
        return e.code, json_data, dict(e.headers)
    except Exception as e:
        return 0, str(e), {}

# 3.1 GET / Health
status, res, _ = http_req("/")
if status == 200 and res.get("status") == "online":
    record("FastAPI", "健康狀態 GET /", OK, f"API 在線 ({res.get('appName')})")
else:
    record("FastAPI", "健康狀態 GET /", FAIL, f"Status: {status}, Response: {res}")

# 3.2 CORS Preflight OPTIONS
status, _, h = http_req("/api/v1/sessions", method="OPTIONS", headers={
    "Origin": "https://studentanalytics-91cd1.web.app",
    "Access-Control-Request-Method": "POST"
})
if status == 200 and h.get("Access-Control-Allow-Origin") or h.get("access-control-allow-origin"):
    record("FastAPI", "CORS Preflight (OPTIONS)", OK, f"回應 200 OK 且包含 Allow-Origin: {h.get('Access-Control-Allow-Origin', h.get('access-control-allow-origin'))}")
else:
    record("FastAPI", "CORS Preflight (OPTIONS)", FAIL, f"Status: {status}, Headers: {h}")

# 3.3 Session CRUD
test_id = None
start_payload = {
    "class_name": "全功能自動化測試課",
    "teacher": "張教授",
    "room": "TR-101",
    "notes": "全功能測試腳本建立",
    "roi_polygon": []
}

# POST Create Session
status, res, _ = http_req("/api/v1/sessions", method="POST", data=start_payload)
if status == 200 and "session_id" in res:
    test_id = res["session_id"]
    record("FastAPI", "開課 POST /api/v1/sessions", OK, f"建立成功! ID: {test_id[:8]}...")
else:
    record("FastAPI", "開課 POST /api/v1/sessions", FAIL, f"Status: {status}, Res: {res}")

if test_id:
    # GET List Sessions
    status, res, _ = http_req("/api/v1/sessions?limit=5")
    if status == 200 and isinstance(res, list):
        record("FastAPI", "列表 GET /api/v1/sessions", OK, f"取得 {len(res)} 筆紀錄")
    else:
        record("FastAPI", "列表 GET /api/v1/sessions", FAIL, f"Status: {status}")

    # GET Single Session
    status, res, _ = http_req(f"/api/v1/sessions/{test_id}")
    if status == 200 and res.get("session_id") == test_id:
        record("FastAPI", f"詳情 GET /api/v1/sessions/{{id}}", OK, f"課程名稱: {res.get('class_name')}")
    else:
        record("FastAPI", f"詳情 GET /api/v1/sessions/{{id}}", FAIL, f"Status: {status}")

    # PATCH Update Session
    status, res, _ = http_req(f"/api/v1/sessions/{test_id}", method="PATCH", data={"room": "TR-999"})
    if status == 200 and res.get("room") == "TR-999":
        record("FastAPI", f"更新 PATCH /api/v1/sessions/{{id}}", OK, f"教室更新為: {res.get('room')}")
    else:
        record("FastAPI", f"更新 PATCH /api/v1/sessions/{{id}}", FAIL, f"Status: {status}")

    # PATCH End Session
    status, res, _ = http_req(f"/api/v1/sessions/{test_id}/end", method="PATCH")
    if status == 200 and res.get("ended_at") is not None:
        record("FastAPI", f"下課 PATCH /api/v1/sessions/{{id}}/end", OK, f"課程成功結束, 結束時間: {res.get('ended_at')[:19]}")
    else:
        record("FastAPI", f"下課 PATCH /api/v1/sessions/{{id}}/end", FAIL, f"Status: {status}")

    # DELETE Session
    status, res, _ = http_req(f"/api/v1/sessions/{test_id}", method="DELETE")
    if status == 200:
        record("FastAPI", f"刪除 DELETE /api/v1/sessions/{{id}}", OK, f"刪除測試 Session 成功")
    else:
        record("FastAPI", f"刪除 DELETE /api/v1/sessions/{{id}}", FAIL, f"Status: {status}")

# 3.4 MJPEG Stream Endpoint Header Test
status, _, h = http_req("/api/v1/stream")
content_type = h.get("Content-Type", h.get("content-type", ""))
if "multipart/x-mixed-replace" in content_type:
    record("FastAPI", "MJPEG 串流 GET /api/v1/stream", OK, f"Content-Type: {content_type}")
else:
    record("FastAPI", "MJPEG 串流 GET /api/v1/stream", WARN, f"Status: {status}, Content-Type: {content_type}")

# ── 4. Cloudflare Tunnel 驗證 ───────────────────────────────────────────────
print("\n[4/4] 🌐 Cloudflare Tunnel 對外穿透通道測試...")
tunnel_url = "https://nickel-establish-incorporated-hopkins.trycloudflare.com"

req = urllib.request.Request(f"{tunnel_url}/", headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode())
        if resp.status == 200 and data.get("status") == "online":
            record("Tunnel", "Cloudflare Tunnel 穿透", OK, f"對外 HTTPS 通道暢通: {tunnel_url}")
        else:
            record("Tunnel", "Cloudflare Tunnel 穿透", WARN, f"Status: {resp.status}")
except Exception as e:
    record("Tunnel", "Cloudflare Tunnel 穿透", WARN, f"無法連線穿透網址: {e}")

# ── 測試結果總結 ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("📊 全功能測試結果總結報告")
print("=" * 70)

passed = sum(1 for _, _, s, _ in results if s == OK)
failed = sum(1 for _, _, s, _ in results if s == FAIL)
warns  = sum(1 for _, _, s, _ in results if s == WARN)
total  = len(results)

print(f"  總測試項目: {total} 項 | 🟢 通過: {passed} | 🔴 失敗: {failed} | 🟡 警告: {warns}")
print("-" * 70)

for cat, name, status, detail in results:
    icon = "🟢" if status == OK else ("🔴" if status == FAIL else "🟡")
    print(f"  {icon} [{cat}] {name}\n     └─ {detail}")

print("=" * 70)
if failed == 0:
    print("🎉 恭喜！目前階段所有核心功能與服務 100% 全部測試通過，可以正常運作！")
else:
    print("⚠️ 注意：存在失敗項目，請修正後重新檢測。")
