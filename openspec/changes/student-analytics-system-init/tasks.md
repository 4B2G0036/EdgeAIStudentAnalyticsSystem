## 1. 環境與基礎建置 (Environment and Infrastructure)

- [x] 1.1 建立工作目錄結構：`core/`, `engine/`, `database/`, `api/`, `dashboard/`, `report/`, `models/`, `reports/`
- [x] 1.2 初始化 Python 虛擬環境（venv），建立 `requirements.txt`，安裝所有相依套件：
      `opencv-python`, `ultralytics`, `onnxruntime-gpu` (或 `onnxruntime`),
      `fastapi`, `uvicorn[standard]`, `streamlit`, `streamlit-drawable-canvas`,
      `pymongo`, `pandas`, `matplotlib`, `plotly`, `reportlab`, `python-dotenv`, `requests`, `pillow`
- [x] 1.3 建立 `config.py` 集中管理所有可設定常數（含：`MONGO_URI`, `MONGO_DB_NAME`,
      `FASTAPI_BASE_URL`, `FASTAPI_PORT`, `CAMERA_ID`, `TARGET_FPS=5`, `IMG_SZ=640`,
      `POSE_CONF_THRESHOLD=0.45`, `SLEEPING_RATIO=0.20`, `PHONE_PITCH_THRESHOLD=-35`,
      `BOARD_YAW_THRESHOLD=30`, `BOARD_PITCH_THRESHOLD=25`, `FSM_NOISE_WINDOW=3`,
      `FSM_CONFIRM_WINDOW=10`, `DB_BATCH_SIZE=500`, `FLUSH_INTERVAL=3.0`, `CORS_ORIGINS=["http://localhost:8501"]`,
      `TIMEZONE="Asia/Taipei"`, `RETENTION_DAYS=365`, `PII_BLUR_KERNEL=(31,31)`,
      `AWAIT_FLUSH_TIMEOUT=10.0`, `HEARTBEAT_TIMEOUT=1.5`, `API_RATE_LIMIT="5/minute"`, `LOG_LEVEL="INFO"`)
- [x] 1.4 建立 `.env.example` 模板，列出所有環境變數鍵值，並設計 **結構化日誌 (Structured Logging)** 以便全案支援 `trace_id` 追蹤。
- [x] 1.5 部署本機 MongoDB 7.0+ 實例，驗證支援 Time Series Collection 功能（已安裝 MongoDB 8.3.7 並通過 Time Series Collection 驗證）
- [x] 1.6 下載或匯出 YOLOv8-Pose ONNX 模型至 `models/` 目錄：
      成功匯出 `models/yolov8n-pose.onnx` (12.9MB) 與 `models/yolov8m-pose.onnx` (101.2MB)，CPU 單次推論耗時分別為 21ms 與 103ms (≤ 200ms 標準)

## 2. 邊緣 AI 視覺核心實作 (Vision AI Core — `core/`)

- [x] 2.1 實作 `core/camera.py`：OpenCV 廣角攝影機讀取迴圈，主動丟幀緩衝鎖定（TARGET_FPS=5），10 次重試異常處理 (`CameraConnectionError`)。
- [x] 2.2 實作 `core/inference.py`：`InferenceEngine` 類別，以 `onnxruntime.InferenceSession` 載入 ONNX 模型。自動選擇 `CUDAExecutionProvider`，失敗則 fallback 至 `CPUExecutionProvider` 並明確記錄 WARNING 日誌。每一幀賦予唯一 `trace_id`。
- [x] 2.3 定義 `core/models.py`：`TrackedPerson` dataclass（`tracking_id`, `bbox`, `keypoints[17,3]`, `confidence`, `in_roi`），以及 `PoseFlag` Enum（`SLEEPING`, `PHONE_SUSPECTED`, `DISTRACTED`），`FrameResult` dataclass。
- [x] 2.4 實作 `core/tracker.py`：整合 ByteTrack 多目標追蹤，設定最大遮擋容忍 **30 幀**（6 秒 @ 5FPS）。加入 **ID 漂移防護 (ID Drift Protection)**：若新 ID 與剛消失 ID 之 Bbox IoU > 0.8，則繼承舊 ID 狀態。
- [x] 2.5 實作 `core/privacy.py`：依據 YOLO 推論後輸出的 BBox / 頭部節點，先對原始幀套用高斯模糊產生隱私版影像，**然後再繪製標籤**，絕對禁止未模糊人臉流出核心。
- [x] 2.6 實作 `core/head_pose.py`：三段式頭部朝向估計策略 (過濾 confidence < 0.45) - 策略 1（優先）：nose + left_eye + right_eye（均 confidence ≥ 0.45）→ 幾何 Yaw/Pitch - 策略 2（備用）：left_ear + right_ear + shoulders（均 confidence ≥ 0.45）→ 耳肩輔助算法 - 策略 3（最低）：僅有 shoulders (均 confidence ≥ 0.45) → 肩線水平角估算 Yaw，Pitch 設為 0。
- [x] 2.7 實作 `core/pose_analyzer.py`：骨架幾何異常判斷邏輯：- **趴睡**：`abs(avg_shoulder_y - nose_y) / bbox_height < SLEEPING_RATIO (0.20)` 或 `pitch > 60°` - **疑似手機**：任一手腕 `wrist_y > (shoulder_y + hip_y)/2` 且 `head_pitch < PHONE_PITCH_THRESHOLD`。
- [x] 2.8 實作 `core/roi.py`：`cv2.pointPolygonTest()` 過濾，bbox 中心不在 ROI 多邊形內則 `in_roi=False`。
- [x] 2.9 整合測試 `core/` 所有模組：完成 `tests/test_core.py` 7 項單元測試，驗證純 ONNX 推論、多目標追蹤、遮擋容忍、隱私模糊、頭部角度與姿態評分全數通過。

## 3. 專注度評分引擎 (Attention Scoring Engine — `core/pose_analyzer.py`)

- [x] 3.1 實作每幀專注度評分公式（基於 `active_penalty_flags`）：看黑板（`|Yaw| ≤ 30°` 且 `|Pitch| ≤ 25°`）→ +50 分；無趴睡 → +50 分；`PHONE_SUSPECTED` → -50 分；`SLEEPING` → -30 分；`HEAD_SUPPORT` → -15 分；`HAND_RAISED` → 維持 100 分滿分；數值鉗制於 `[0, 100]`。
- [x] 3.2 實作時序狀態濾波與防抖防閃爍機制：趴睡連續 6 幀確認、3 幀解除；支援天花板俯角埋頭趴睡檢測。
- [x] 3.3 系統重啟自我修復 (Self-Healing)：API 啟動時自動掃描未閉合異常事件並依生命週期修正。
- [x] 3.4 實作多學生追蹤滑動濾波與追蹤狀態清理 (`_prune_sleep_state`)。
- [x] 3.5 實作每幀全班指標聚合與即時狀態共享。

## 4. 資料庫層 (Database Layer — `database/`)

- [x] 4.1 實作 `database/connection.py`：MongoDB 連線初始化與連線池管理。
- [x] 4.2 實作 `database/collections.py`：建立三個集合與索引：`Classes_Session`、`Attention_Metrics` (Time Series Collection)、`Abnormal_Events`，含自動 TTL 索引維護。
- [x] 4.3 實作 `database/writer.py`：非同步指標批量寫入器 (`MetricBatchWriter`)，佇列暫存以 15 筆或 2 秒週期批次寫入，支援主動阻塞排空 (`AWAIT_QUEUE_FLUSH`) 與記憶體溢位防護。
- [x] 4.4 實作 `database/queries.py`：統計查詢、時序指標聚合、分頁課程列表與生命週期事件維護。

## 5. FastAPI 後端 (API Layer — `api/`)

- [x] 5.1 實作 `api/main.py`：加上 **CORS Middleware**，讀取 `config.CORS_ORIGINS`。日誌支援 `trace_id` 紀錄。
- [x] 5.2 實作 `api/routers/sessions.py`：Session 生命週期端點。支援列表端點的分頁查詢 `limit/offset`。`PATCH /sessions/{id}/end` 必須觸發 `AWAIT_QUEUE_FLUSH` 確保資料一致。
- [x] 5.3 實作 `api/routers/stream.py`：`GET /api/v1/stream` 推送符合 RFC 1341 之 MJPEG Boundary 串流。
- [x] 5.4 實作 `api/routers/realtime.py`：每秒讀取 GlobalSafeStorage / DB 返回 `ClassMetrics`，供儀表板輪詢。
- [x] 5.5 實作 `api/routers/reports.py`：`GET /api/v1/report/{session_id}`，加上 **速率限制 (Rate Limiting)** (`API_RATE_LIMIT`)。

## 6. 即時儀表板 (Dashboard — `dashboard/`)

- [x] 6.1 建構現代化響應式 Web 儀表板 (`dashboard/index.html`)，部署至 Firebase Hosting，時間本地化轉換。
- [x] 6.2 實作「課程設定與開課」：重複 Session 防護、即時表單校驗。
- [x] 6.3 實作「實時 AI 監控 (Live Stream)」：支援隱私保護模式、心跳監測、自動重連與 API 探測、動態分類徽章 (`🙋‍♂️ 課堂互動`、`💡 注意提醒`、`🚨 異常告警`)。
- [x] 6.4 實作「歷史記錄」與「報告下載」：分頁載入課程、歷史摘要統計卡片。

## 7. PDF 報表生成 (Report Generation — `api/routers/reports.py`)

- [x] 7.1 實作 ReportLab 報表排版，支援 PDF 與純文字雙格式。
- [x] 7.2 實作摘要指標提取：最高在線人數、平均專注度、累積異常次數。
- [x] 7.3 實作課後 PDF 背景預產快取 (`scratch/reports/`)，點擊即時下載。
- [x] 7.4 整合測試：驗證觸發生成至 PDF 完成時間 ≤ 5 秒，文字顯示無亂碼。

## 8. 系統整合測試與最佳化 (Integration Testing & Optimization)

- [x] 8.1 整合所有模組：攝影機每 0.2s → YOLO (帶 Trace ID) → 評分 → MJPEG 串流 + DB 批次寫入完整管線通跑。
- [x] 8.2 自動化測試套件：`tests/test_core.py` (23項)、`scripts/test_api_v1.py` (7項)、`scripts/test_all_features.py` (13項)、`scripts/lint_and_check.py` (47檔案) 全數 100% 通過。
- [x] 8.3 撰寫 `README.md`、`VERSION.md`、`CHANGELOG.md` 完整操作手冊與版本發布包。
