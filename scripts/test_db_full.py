"""
test_db_full.py
================
完整驗證 MongoDB 資料庫運作狀態：
  1. 連線驗證 (Ping)
  2. 集合與索引自動初始化 (Classes_Session, Attention_Metrics, Abnormal_Events)
  3. Classes_Session 寫入、查詢與 Unique Index 約束測試
  4. Attention_Metrics (Time Series Collection) 批次寫入與聚合查詢測試
  5. Abnormal_Events 寫入與狀態更新 (FSM 事件) 測試
  6. 測試資料清理

執行方式：
  .venv\\Scripts\\python.exe scripts/test_db_full.py
"""
import sys
import os
import time
from datetime import datetime, timezone

# 確保輸出與檔案路徑在 Windows UTF-8 環境運作
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db
from database.collections import initialize_database
from pymongo.errors import DuplicateKeyError

def run_tests():
    print("=" * 60)
    print("🚀 開始 MongoDB 資料庫完整功能與資料流驗證")
    print("=" * 60)

    # Step 1: 連線與初始化集合
    print("\n[測試 1/5] 資料庫連線與集合/索引初始化...")
    try:
        initialize_database()
        db = get_db()
        cols = db.list_collection_names()
        print(f"  ✅ 初始化完成！現有集合: {cols}")
    except Exception as e:
        print(f"  ❌ 連線或初始化失敗: {e}")
        return False

    test_session_id = f"test_sess_{int(time.time())}"

    # Step 2: Classes_Session 操作與約束測試
    print("\n[測試 2/5] Classes_Session 寫入與 Unique Index 約束測試...")
    try:
        session_doc = {
            "session_id": test_session_id,
            "class_name": "深度學習實務測試課",
            "teacher": "張教授",
            "started_at": datetime.now(timezone.utc),
            "status": "ACTIVE",
            "student_count": 40
        }
        res = db["Classes_Session"].insert_one(session_doc)
        print(f"  ✅ 寫入課程 Session 成功, Mongo ID: {res.inserted_id}")

        # 測試 Unique Index
        try:
            db["Classes_Session"].insert_one(session_doc)
            print("  ❌ 錯誤：未擋下重複 session_id (Unique constraint 失敗)")
            return False
        except DuplicateKeyError:
            print("  ✅ 成功觸發 DuplicateKeyError：Unique Index 唯一性約束完美防護！")
    except Exception as e:
        print(f"  ❌ Session 測試失敗: {e}")
        return False

    # Step 3: Attention_Metrics (Time Series) 批次寫入與聚合查詢
    print("\n[測試 3/5] Attention_Metrics (Time Series) 寫入與時序聚合測試...")
    try:
        metrics_batch = []
        now = datetime.now(timezone.utc)
        for i in range(10):
            metrics_batch.append({
                "timestamp": now,
                "metadata": {
                    "session_id": test_session_id,
                    "tracking_id": f"std_{i+1}"
                },
                "attention_score": 80 + (i % 5) * 4,
                "yaw": (i % 3) * 5,
                "pitch": (i % 2) * -3,
                "flags": ["SLEEPING"] if i == 3 else []
            })
        
        insert_res = db["Attention_Metrics"].insert_many(metrics_batch)
        print(f"  ✅ 成功批次寫入 {len(insert_res.inserted_ids)} 筆時序指標至 Time Series Collection")

        # 時序聚合查詢 (Aggregator 計算平均專注度)
        pipeline = [
            {"$match": {"metadata.session_id": test_session_id}},
            {"$group": {"_id": "$metadata.session_id", "avg_score": {"$avg": "$attention_score"}, "count": {"$sum": 1}}}
        ]
        agg_res = list(db["Attention_Metrics"].aggregate(pipeline))
        if agg_res and agg_res[0]["count"] == 10:
            avg_val = agg_res[0]["avg_score"]
            print(f"  ✅ Time Series 聚合查詢成功！平均專注度: {avg_val:.2f} (樣本數: {agg_res[0]['count']})")
        else:
            print("  ❌ 聚合查詢結果不符預期")
            return False
    except Exception as e:
        print(f"  ❌ Time Series 測試失敗: {e}")
        return False

    # Step 4: Abnormal_Events (FSM 事件) 寫入與更新測試
    print("\n[測試 4/5] Abnormal_Events 狀態與 FSM 生命週期更新測試...")
    try:
        event_doc = {
            "session_id": test_session_id,
            "tracking_id": "std_3",
            "event_type": "SLEEPING",
            "started_at": datetime.now(timezone.utc),
            "ended_at": None,
            "max_confidence": 0.92,
            "status": "CONFIRMED"
        }
        event_id = db["Abnormal_Events"].insert_one(event_doc).inserted_id
        print(f"  ✅ 新增趴睡告警事件成功, ID: {event_id}")

        # 更新事件結束時間
        end_time = datetime.now(timezone.utc)
        update_res = db["Abnormal_Events"].update_one(
            {"_id": event_id},
            {"$set": {"ended_at": end_time, "status": "RESOLVED"}}
        )
        if update_res.modified_count == 1:
            print("  ✅ 更新告警事件結束時間 (FSM 狀態更新) 成功！")
        else:
            print("  ❌ 更新事件失敗")
            return False
    except Exception as e:
        print(f"  ❌ Abnormal_Events 測試失敗: {e}")
        return False

    # Step 5: 清理測試資料
    print("\n[測試 5/5] 清理測試資料...")
    try:
        db["Classes_Session"].delete_many({"session_id": test_session_id})
        db["Attention_Metrics"].delete_many({"metadata.session_id": test_session_id})
        db["Abnormal_Events"].delete_many({"session_id": test_session_id})
        print("  ✅ 測試資料已乾淨清理，未留殘餘測試髒資料。")
    except Exception as e:
        print(f"  ⚠️ 清理過程有警告: {e}")

    print("\n" + "=" * 60)
    print("🎉 MongoDB 資料庫所有功能與讀寫邏輯驗證 100% 通過！")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
