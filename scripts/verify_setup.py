"""
verify_setup.py
================
Verify tasks 1.5/1.6:
  - MongoDB connection and Time Series Collection support
  - ONNX model integrity (yolov8n-pose.onnx / yolov8m-pose.onnx)
  - onnxruntime dummy inference

Usage:
  .venv\\Scripts\\python.exe scripts/verify_setup.py
"""
import sys, os, time

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OK  = "\033[92m✅\033[0m"
ERR = "\033[91m❌\033[0m"
WARN= "\033[93m⚠️\033[0m"

results = []

# ─────────────────────────────────────────────
# 1.5  MongoDB 驗證
# ─────────────────────────────────────────────
print("\n=== [1.5] MongoDB 驗證 ===")
try:
    import pymongo
    from config import MONGO_URI, MONGO_DB_NAME

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    server_info = client.server_info()
    version_str = server_info.get("version", "unknown")
    major = int(version_str.split(".")[0])
    print(f"  連線成功 — MongoDB {version_str}")

    if major >= 7:
        print(f"  {OK} 版本 >= 7.0，支援 Time Series Collection")
        results.append(("MongoDB 版本", True))
    else:
        print(f"  {ERR} 版本 {version_str} < 7.0，不支援 Time Series Collection")
        results.append(("MongoDB 版本", False))

    # 驗證 Time Series Collection 可建立
    db = client["_ts_verify_db_"]
    try:
        db.drop_collection("ts_test")
        db.create_collection(
            "ts_test",
            timeseries={
                "timeField": "timestamp",
                "metaField": "metadata",
                "granularity": "seconds",
            },
        )
        db.drop_collection("ts_test")
        print(f"  {OK} Time Series Collection 建立/刪除成功")
        results.append(("Time Series Collection", True))
    except Exception as e:
        print(f"  {ERR} Time Series Collection 測試失敗: {e}")
        results.append(("Time Series Collection", False))

    client.close()

except pymongo.errors.ServerSelectionTimeoutError:
    print(f"  {ERR} 無法連線至 MongoDB（{MONGO_URI}）— 請確認服務已啟動")
    results.append(("MongoDB 連線", False))
    results.append(("Time Series Collection", False))
except Exception as e:
    print(f"  {ERR} 未知錯誤: {e}")
    results.append(("MongoDB 連線", False))
    results.append(("Time Series Collection", False))

# ─────────────────────────────────────────────
# 1.6  ONNX 模型驗證
# ─────────────────────────────────────────────
print("\n=== [1.6] ONNX 模型驗證 ===")
models = {
    "yolov8n-pose.onnx": "輕量主用",
    "yolov8m-pose.onnx": "高精度備用",
}
for fname, label in models.items():
    path = os.path.join("models", fname)
    if not os.path.exists(path):
        print(f"  {ERR} {fname} ({label}) — 檔案不存在")
        results.append((fname, False))
        continue

    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"  {OK} {fname} ({label}) — {size_mb:.1f} MB")
    results.append((f"{fname} 檔案", True))

    # onnxruntime dummy 推論
    try:
        import onnxruntime as ort
        import numpy as np

        providers = ort.get_available_providers()
        chosen = "CUDAExecutionProvider" if "CUDAExecutionProvider" in providers else "CPUExecutionProvider"

        sess = ort.InferenceSession(path, providers=[chosen])
        input_name = sess.get_inputs()[0].name
        dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)

        t0 = time.time()
        sess.run(None, {input_name: dummy})
        elapsed = (time.time() - t0) * 1000

        print(f"       推論後端: {chosen} | 首次推論: {elapsed:.0f}ms")

        if elapsed <= 200:
            print(f"       {OK} 單次推論 ≤ 200ms")
        else:
            print(f"       {WARN} 單次推論 {elapsed:.0f}ms > 200ms（CPU 模式預期，GPU 會更快）")
        results.append((f"{fname} 推論", True))

    except ImportError:
        print(f"       {WARN} onnxruntime 未安裝，跳過推論驗證")
        results.append((f"{fname} 推論", None))
    except Exception as e:
        print(f"       {ERR} 推論測試失敗: {e}")
        results.append((f"{fname} 推論", False))

# ─────────────────────────────────────────────
# 結果摘要
# ─────────────────────────────────────────────
print("\n" + "=" * 50)
print("驗證結果摘要")
print("=" * 50)
all_pass = True
for name, ok in results:
    if ok is True:
        icon = OK
    elif ok is False:
        icon = ERR
        all_pass = False
    else:
        icon = WARN
    print(f"  {icon}  {name}")

print()
if all_pass:
    print(f"{OK} 所有項目通過！第 1.5/1.6 章環境就緒，可開始實作第 2 章。")
else:
    print(f"{ERR} 部分項目未通過，請依上述錯誤訊息修正後重新執行。")
