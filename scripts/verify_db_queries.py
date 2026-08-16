"""
verify_db_queries.py
======================
測試高階資料庫 CRUD 介面 (database/queries.py):
  1. create_session
  2. update_session
  3. get_active_session & get_session_by_id
  4. list_sessions (含 status/search 過濾與分頁)
  5. get_active_session_metrics
  6. get_session_summary
  7. end_session
  8. delete_session
"""
import sys, os, time
from datetime import datetime, timezone

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.queries import (
    create_session,
    update_session,
    get_session_by_id,
    get_active_session,
    list_sessions,
    get_session_summary,
    get_active_session_metrics,
    end_session,
    delete_session
)

def run_queries_test():
    print("=" * 60)
    print("🔍 開始應用層 queries.py 高階介面整合測試")
    print("=" * 60)

    test_id = f"test_api_session_{int(time.time())}"

    # 1. Create Session
    print("\n[測試 1/7] create_session()...")
    sess = create_session(
        session_id=test_id,
        class_name="邊緣計算與 AI 應用實作",
        teacher="李教授",
        room="TR-301",
        notes="測試用 Session"
    )
    if sess and sess["session_id"] == test_id:
        print(f"  ✅ 建立成功! Class: {sess['class_name']}, Teacher: {sess['teacher']}")
    else:
        print("  ❌ 建立失敗")
        return False

    # 2. Get Active Session & Get by ID
    print("\n[測試 2/7] get_active_session() & get_session_by_id()...")
    active = get_active_session()
    by_id = get_session_by_id(test_id)
    if active and active["session_id"] == test_id and by_id and by_id["session_id"] == test_id:
        print("  ✅ 成功查詢活躍 Session 與指定 ID Session！")
    else:
        print(f"  ❌ 查詢失敗: active={active}, by_id={by_id}")
        return False

    # 3. Update Session
    print("\n[測試 3/7] update_session()...")
    updated = update_session(test_id, {"room": "TR-305", "notes": "已修訂教室"})
    if updated and updated["room"] == "TR-305":
        print("  ✅ 成功更新 Session 教室號碼與備註！")
    else:
        print("  ❌ 更新失敗")
        return False

    # 4. List Sessions with filters
    print("\n[測試 4/7] list_sessions() (狀態與關鍵字過濾)...")
    sessions = list_sessions(limit=5, search_query="邊緣計算", status_filter="active")
    if len(sessions) > 0 and sessions[0]["session_id"] == test_id:
        print(f"  ✅ 成功列表並過濾, 找到 {len(sessions)} 筆符合資料！")
    else:
        print(f"  ❌ 列表過濾失敗: {sessions}")
        return False

    # 5. Live Metrics & Summary
    print("\n[測試 5/7] get_active_session_metrics() & get_session_summary()...")
    metrics = get_active_session_metrics(test_id)
    summary = get_session_summary(test_id)
    if metrics and summary:
        print(f"  ✅ 成功取得實時指標 (Score: {metrics['attention_score']}) 與總結報告 (Score: {summary['avg_attention_score']})！")
    else:
        print("  ❌ 指標或總結取得失敗")
        return False

    # 6. End Session
    print("\n[測試 6/7] end_session()...")
    ended = end_session(test_id)
    if ended and ended["ended_at"] is not None:
        print(f"  ✅ 成功結束 Session! 結束時間: {ended['ended_at']}")
    else:
        print("  ❌ 結束 Session 失敗")
        return False

    # 7. Delete Session Cleanup
    print("\n[測試 7/7] delete_session()...")
    deleted = delete_session(test_id)
    if deleted:
        print("  ✅ 成功刪除測試 Session 及周邊關聯記錄！")
    else:
        print("  ❌ 刪除失敗")
        return False

    print("\n" + "=" * 60)
    print("🎉 queries.py 所有高階應用介面測試 100% 成功！")
    print("=" * 60)
    return True

if __name__ == "__main__":
    if not run_queries_test():
        sys.exit(1)
