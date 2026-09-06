import sys
import os
import time

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from fastapi.testclient import TestClient
from api.main import app
import database

def run_api_v1_tests():
    print("=" * 60)
    print("開始執行 FastAPI RESTful API (api/) 全端點單元與整合測試...")
    print("=" * 60)
    
    # Initialize TestClient
    client = TestClient(app)
    
    # 1. Test Root endpoint and Trace ID header
    print("\n[1/7] 測試 API 根目錄與 Trace ID Header 中介軟體...")
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "X-Trace-ID" in res.headers, "X-Trace-ID header missing from response"
    print(f"  [OK] Root OK, Status: {res.json().get('status')}, X-Trace-ID: {res.headers.get('X-Trace-ID')}")


    # 2. Test Realtime endpoint when no active session
    print("\n[2/7] 測試 即時指標輪詢端點 (/api/v1/realtime)...")
    res = client.get("/api/v1/realtime")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "is_active" in data, "is_active key missing"
    assert "attention_score" in data, "attention_score key missing"
    print(f"  [OK] Realtime Metrics OK (is_active: {data['is_active']}, score: {data['attention_score']})")

    # 3. Test Session Lifecycle (Start -> Query -> Update -> Metrics/Events -> End -> Delete)
    print("\n[3/7] 測試 課程 Session 生命週期 (開課 -> 查詢 -> 狀態)...")
    # Start Session
    session_payload = {
        "class_name": "API 測試課程",
        "teacher": "張教授",
        "room": "資工 101",
        "roi_polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        "notes": "FastAPI 自動化測試建立"
    }
    res = client.post("/api/v1/sessions", json=session_payload)
    if res.status_code == 409:
        # If active session already exists, end it first then retry
        active_sess = database.get_active_session()
        if active_sess:
            database.end_session(active_sess["session_id"])
        res = client.post("/api/v1/sessions", json=session_payload)
        
    assert res.status_code == 201, f"Failed to start session: {res.status_code} - {res.text}"
    session_id = res.json()["session_id"]
    print(f"  [OK] 成功建立新課程 Session ID: {session_id}")

    # Query Sessions List with limit/offset
    print("\n[4/7] 測試 課程列表分頁查詢 (/api/v1/sessions?limit=5&offset=0)...")
    res = client.get("/api/v1/sessions?limit=5&offset=0&status=active")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    sessions_list = res.json()
    assert len(sessions_list) > 0, "Expected at least 1 session in active list"
    print(f"  [OK] 成功查詢課程列表，筆數: {len(sessions_list)}")

    # Query Session Details & Summary
    res_details = client.get(f"/api/v1/sessions/{session_id}")
    assert res_details.status_code == 200
    res_summary = client.get(f"/api/v1/sessions/{session_id}/summary")
    assert res_summary.status_code == 200
    print(f"  [OK] 課程詳情與摘要查詢 OK: {res_summary.json().get('class_name')}")

    # Query Time Series Metrics & Events
    print("\n[5/7] 測試 時序分數 (/metrics) 與異常事件 (/events) 查詢...")
    res_m = client.get(f"/api/v1/sessions/{session_id}/metrics")
    assert res_m.status_code == 200
    res_e = client.get(f"/api/v1/sessions/{session_id}/events")
    assert res_e.status_code == 200
    print(f"  [OK] Metrics ({len(res_m.json())} 筆) 與 Events ({len(res_e.json())} 筆) 端點 OK")

    # 4. Test Report Generation & Rate Limiter
    print("\n[6/7] 測試 報表生成 (/api/v1/report/{{id}}) 與 速率限制 (Rate Limiter)...")
    res_rep = client.get(f"/api/v1/report/{session_id}")
    assert res_rep.status_code == 200, f"Report download failed: {res_rep.status_code}"
    assert "content-disposition" in res_rep.headers
    print(f"  [OK] 報表下載成功，Header: {res_rep.headers.get('content-disposition')}")

    # Test Rate Limiting by sending 6 rapid requests
    rate_limited = False
    for i in range(6):
        r = client.get(f"/api/v1/report/{session_id}")
        if r.status_code == 429:
            rate_limited = True
            print(f"  [OK] Rate Limiter 成功攔截第 {i+1} 次請求 (HTTP 429 Too Many Requests)")
            break
    assert rate_limited, "Rate Limiter did not trigger on excess requests!"

    # 5. End & Cleanup Session
    print("\n[7/7] 測試 結束課程 (下課 /end) 與 刪除課程 (/delete)...")
    res_end = client.patch(f"/api/v1/sessions/{session_id}/end")
    assert res_end.status_code == 200, f"End session failed: {res_end.status_code}"
    print(f"  [OK] 成功結束課程 ended_at: {res_end.json().get('ended_at')}")

    res_del = client.delete(f"/api/v1/sessions/{session_id}")
    assert res_del.status_code == 200, f"Delete session failed: {res_del.status_code}"
    print(f"  [OK] 成功清理測試課程 Session {session_id}")

    print("\n" + "=" * 60)
    print("[SUCCESS] 所有 7 項 FastAPI RESTful API 測試皆 100% 通過！")
    print("=" * 60)


if __name__ == "__main__":
    run_api_v1_tests()
