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

- [ ] 2.1 實作 `core/camera.py`：OpenCV 廣角攝影機讀取迴圈，內建 `time.sleep()` 幀率鎖定（TARGET_FPS=5）。
      加入 **優雅停機 (Graceful Shutdown)**：處理 `SIGTERM`/`SIGINT` 信號，排空推論迴圈。
- [ ] 2.2 實作 `core/inference.py`：`InferenceEngine` 類別，以 `onnxruntime.InferenceSession` 載入 ONNX 模型。
      自動選擇 `CUDAExecutionProvider`，失敗則 fallback 至 `CPUExecutionProvider` 並明確記錄 WARNING 日誌。每一幀賦予唯一 `trace_id`。
- [ ] 2.3 定義 `core/models.py`：`TrackedPerson` dataclass（`tracking_id`, `bbox`, `keypoints[17,3]`, `confidence`, `in_roi`），
      以及 `PoseFlag` Enum（`SLEEPING`, `PHONE_SUSPECTED`），`FrameResult` dataclass
- [ ] 2.4 實作 `core/tracker.py`：整合 ByteTrack，設定最大遮擋容忍 **30 幀**（6 秒 @ 5FPS）。
      加入 **ID 漂移防護 (ID Drift Protection)**：若新 ID 與剛消失 ID 之 Bbox IoU > 0.8，則繼承舊 ID 狀態。
- [ ] 2.5 實作 `core/privacy.py`：依據 YOLO 推論後輸出的 BBox，先對原始幀套用高斯模糊產生隱私版影像，**然後再繪製標籤**，絕對禁止未模糊人臉流出核心。
- [ ] 2.6 實作 `core/head_pose.py`：三段式頭部朝向估計策略 (需過濾 confidence < 0.45) - 策略 1（優先）：nose + left_eye + right_eye（均 confidence ≥ 0.45）→ 幾何 Yaw/Pitch - 策略 2（備用）：left_ear + right_ear + shoulders（均 confidence ≥ 0.45）→ 耳肩輔助算法 - 策略 3（最低）：僅有 shoulders (均 confidence ≥ 0.45) → 肩線水平角估算 Yaw，Pitch 設為 0
- [ ] 2.7 實作 `core/pose_analyzer.py`：骨架幾何異常判斷邏輯 (限手腕 confidence ≥ 0.45)：- **趴睡**：`abs(avg_shoulder_y - nose_y) / bbox_height < SLEEPING_RATIO (0.20)` 或 `pitch > 60°` - **疑似手機**：`min(wrist_y) > (shoulder_y + hip_y)/2` 且 `head_pitch < PHONE_PITCH_THRESHOLD (-35°)`
- [ ] 2.8 實作 `core/roi.py`：`cv2.pointPolygonTest()` 過濾，bbox 中心不在 ROI 多邊形內則 `in_roi=False`
- [ ] 2.9 整合測試 `core/` 所有模組：驗證單次執行時間 ≤ 200ms，確認 `FrameResult` MJPEG 輸出與純節點分離。

## 3. 專注度評分引擎 (Attention Scoring Engine — `engine/`)

- [ ] 3.1 實作 `engine/scorer.py`：每幀評分公式（基於 `active_penalty_flags`）：- 看黑板（`|Yaw| ≤ 30°` 且 `|Pitch| ≤ 25°`）→ +50 分 - 無趴睡 penalty flag → +50 分 - WARNING 或 CONFIRMED 的 `PHONE_SUSPECTED` flag → -50 分 - WARNING 或 CONFIRMED 的 `SLEEPING` flag → -30 分 - `final_score = max(0, min(100, base_score))`
- [ ] 3.2 實作 `engine/fsm.py`：`FSMInstance` dataclass 與狀態轉換邏輯：- 狀態：`NORMAL → PENDING → WARNING → CONFIRMED` (10s 寫 DB)，最終進入 `TERMINATED` 時銷毀記憶體。- 當 FSM 從 `CONFIRMED → NORMAL` 時更新 `ended_at`。
- [ ] 3.3 系統重啟自我修復 (Self-Healing)：API 啟動時掃描 `Abnormal_Events` 內 `ended_at=null` 之記錄，重新接續 FSM 狀態。
- [ ] 3.4 實作 `engine/smoother.py`：每個 `tracking_id` 維護長度 30 的滑動佇列（= 6 秒平滑），當 ID `TERMINATED` 時，**必須同步銷毀 Smoother 緩衝記憶體**。
- [ ] 3.5 實作 `engine/aggregator.py`：每幀輸出 `ClassMetrics`。並實作 **GlobalSafeStorage** 使用 `asyncio.Lock` 保障 API 端讀取的原子性。

## 4. 資料庫層 (Database Layer — `database/`)

- [ ] 4.1 實作 `database/connection.py`：MongoDB 連線初始化。
- [ ] 4.2 實作 `database/collections.py`：建立三個集合與索引：- `Classes_Session`：`session_id` 唯一索引；`class_name+teacher+started_at` 複合防重複索引。- `Attention_Metrics`：Time Series Collection (Granularity=seconds)。建立 `session_id+timestamp` 複合索引。- **TTL 索引**：在 `Attention_Metrics` 建立 `expireAfterSeconds = RETENTION_DAYS * 86400` 以實作自動資料過期。- `Abnormal_Events`：建立 `session_id + started_at` 複合索引。
- [ ] 4.3 實作 `database/writer.py`：非同步寫入處理：- 全班混合筆數量滿 **500 筆** 或超時 **3 秒** 強制 Flush。- 實作 Queue.join() 之 **AWAIT_QUEUE_FLUSH** 機制，提供優雅停機或報表生成前的主動阻塞排空。
- [ ] 4.4 實作 `database/queries.py`：統計查詢函式（供報表及 API 分頁呼叫使用）。

## 5. FastAPI 後端 (API Layer — `api/`)

- [ ] 5.1 實作 `api/main.py`：加上 **CORS Middleware**，讀取 `config.CORS_ORIGINS`。日誌支援 `trace_id` 紀錄。
- [ ] 5.2 實作 `api/routers/sessions.py`：Session 生命週期端點。支援列表端點的分頁查詢 `limit/offset`。
      `PATCH /sessions/{id}/end` 必須觸發 `AWAIT_QUEUE_FLUSH` 確保資料一致。
- [ ] 5.3 實作 `api/routers/stream.py`：`GET /api/v1/stream` 推送符合 RFC 1341 之 MJPEG Boundary 串流。
- [ ] 5.4 實作 `api/routers/realtime.py`：每秒讀取 GlobalSafeStorage 返回 `ClassMetrics`，供儀表板輪詢。
- [ ] 5.5 實作 `api/routers/reports.py`：`GET /api/v1/report/{session_id}`，加上 **速率限制 (Rate Limiting)** (`API_RATE_LIMIT`)。

## 6. 即時儀表板 (Dashboard — `dashboard/`)

- [ ] 6.1 實作 `dashboard/app.py`：使用 Streamlit 建構 4 個分頁。所有時間顯示必須根據 `config.TIMEZONE` 進行本地化轉換。
- [ ] 6.2 實作「課程設定」分頁：包含重複 Session 防護。繪製 ROI 必須自動校正轉換為 `[0,1]` 區間之正規化多邊形。
- [ ] 6.3 實作「即時監控」分頁：- 增加 **隱私模式切換 (Extreme Privacy Mode)**：僅呈現指標，隱藏 MJPEG。- 增加 **心跳監測 (Heartbeat Indicator)**：若 `ClassMetrics.timestamp` 停滯大於 1.5 秒，警告 AI 引擎死鎖並切換狀態燈。- 增加 **圖表降級保護 (Graceful Degradation)**：若資料 < 2 點則顯示等待提示，不渲染空白圖表防止報錯。
- [ ] 6.4 實作「歷史記錄」與「報告下載」分頁：利用 `limit/offset` 分頁載入 Session 列表，確保大量歷史時依然流暢。

## 7. PDF 報表生成 (Report Generation — `report/`)

- [ ] 7.1 實作 `report/generator.py`：引入文字字型檔案 `NotoSansTC-Regular.ttf` 以解決 PDF 中文顯示亂碼問題。
- [ ] 7.2 實作 `report/charts.py`：使用 Matplotlib 繪圖。**必須實質應用每分鐘降採樣 (Downsampling)** 處理時序圖表，確保 PDF 檔案容量與轉檔速度。
- [ ] 7.3 實作 `report/pdf_layout.py`：ReportLab 排版邏輯。表格設計**必須**支援若跨頁時於新頁首行**自動重複顯示欄位標題 (Sticky Header)**。
- [ ] 7.4 整合測試：驗證觸發生成至 PDF 完成時間 ≤ 30 秒，文字顯示無亂碼。

## 8. 系統整合測試與最佳化 (Integration Testing & Optimization)

- [ ] 8.1 整合所有模組：攝影機每 0.2s → YOLO (帶 Trace ID) → 評分 (FSM) → MJPEG 串流 + DB 批次(500筆) 寫入完整管線通跑。
- [ ] 8.2 壓力測試：傳送 SIGTERM 測試優雅停機、中斷連線測試 FSM 重啟接關。
- [ ] 8.3 撰寫 `README.md` 操作手冊，註記環境啟動與除錯指令。
