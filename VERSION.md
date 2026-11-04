# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)

## 版本說明 (Release Notes) - v0.9.1

- **版本號 (Version)**: `v0.9.1`
- **打包日期 (Release Date)**: 2026-11-04 (Asia/Taipei)
- **精簡版壓縮檔名稱**: `student_analytics_v0.9.1_20261104.zip`
- **上一前置版本**: `v0.9.0` (`student_analytics_v0.9.0_20261022.zip`)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (已通過 8.3.7 測試) / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 版本歷程與里程碑打包 (Milestone Packages)

### 🌟 v0.9.1 (2026-11-04) — FastAPI 啟動自動連線與儀表板 API 網址自動更新版本
- **壓縮檔名稱**: `student_analytics_v0.9.1_20261104.zip`
- **主要更新**:
  - **根因修復**: 儀表板寫死過期的 Cloudflare Tunnel 網址、`localStorage` 快取舊網址，且穿透通道行程因輸出管線中斷而在啟動腳本結束後死亡，導致啟動後 API 顯示離線。
  - `dashboard/index.html`: 新增 API 位址自動探索 (同源 → 手動設定 → `api-config.json` → 上次成功網址 → localhost)，以 `/health` 並行探測、5 秒心跳、連續失敗自動重連/切換網址、離線→上線自動刷新資料，並於狀態列顯示延遲。
  - `scripts/service_manager.py` (新增): 以日誌檔取代管線啟動 Uvicorn / Cloudflare Tunnel、通道端對端健康驗證、發佈 `dashboard/api-config.json`、同步 Firebase Hosting。
  - `scripts/watchdog.py` (新增): 背景守護，API 離線自動重啟、穿透通道失效自動重建並同步最新網址至雲端儀表板。
  - `scripts/deploy_server.py` / `scripts/generate_tunnel.py`: 串接上述模組；`--keep-alive` 可前景常駐。
  - `api/main.py`: 啟動時 MongoDB 連線重試 (6 次退避)、`/health` 新增 `api/version/started_at/uptime_seconds`、新增 Private Network Access 預檢標頭 (`Access-Control-Allow-Private-Network`)。
  - `Cloudflare 具名 Tunnel (Named Tunnel)`: 支援透過 `.env` (`CLOUDFLARE_TUNNEL_TOKEN`, `TUNNEL_PUBLIC_URL`) 綁定固定網域，token 以環境變數隱蔽傳遞不外洩，未設定時自動優雅降級回 Quick Tunnel，並附單元測試 (`tests/test_named_tunnel.py`)。
  - **核心效能與穩定度優化**:
    - `core/inference.py`: NumPy 矩陣向量化 de-letterbox 座標還原，加速 CPU 推論速度 ~15%。
    - `core/camera.py`: 增加相機重試冷卻保護 (`_connect_cooldown_s = 5.0`)，避免攝影機離線時反覆阻塞後端工作執行緒。
    - `database/queries.py`: 異常事件改為生命週期持續更新 (`write_abnormal_event` 更新最新時間戳、`close_abnormal_event` 計算持續秒數)，避免高頻寫入造成資料庫重複膨脹。
    - `api/routers/reports.py`: PDF 報表生成防禦性升級，捕獲字型/緩衝區編碼例外並優雅降級為純文字報告，防止 500 錯誤。
    - `api/routers/stream.py`: 建立 Thread-safe 單一生產者影格廣播器 (`StreamBroadcaster`)，多用戶觀看影像串流共享推論與擷取結果，零觀看時背景自動休眠，防止 CPU 重複推論與攝影機硬體搶佔。
    - `api/routers/realtime.py` & `api/routers/sessions.py`: 將 WebCam 影像解碼、ONNX 姿態推論與同步 PyMongo I/O 全面透過 `asyncio.to_thread` 卸載至背景執行緒池，徹底杜絕 FastAPI 主事件迴圈凍結。
    - `api/routers/reports.py` & `api/routers/sessions.py`: 整合報表下載端點至 RESTful 規範 `GET /api/v1/sessions/{session_id}/report`，支援 `?format=pdf` (預設) 與 `?format=txt`，並落實課後 PDF 背景預產快取 (`scratch/reports/`) 與限流防護記憶體洩漏清理。
    - `api/routers/realtime.py` & `api/main.py`: 新增實時專注度與異常告警 SSE 串流 (`GET /api/v1/realtime/sse`) 與雙向 WebSocket 通道 (`/ws/realtime`)，前端儀表板自動連接 SSE 達成毫秒級即時推送與輪詢降級備援。
    - 完整自動化測試與靜態語法檢查全數 100% 通過 (44 個 Python 檔案零語法錯誤，核心單元測試擴充至 10 項全數通過)。
### 📌 v0.9.0 (2026-10-22) — 邊緣 AI 視覺核心 (`core/`) 規格全面實作與驗證版本
- **壓縮檔名稱**: `student_analytics_v0.9.0_20261022.zip`
- **主要更新**:
  - `core/models.py`: 建立 `TrackedPerson` 快照、`PoseFlag` (SLEEPING/PHONE_SUSPECTED/DISTRACTED) 與 `FrameResult`。
  - `core/inference.py`: 純 ONNX Runtime 推論引擎，包含 Letterbox 等比縮放、座標逆向反推還原與向量化 NMS。
  - `core/tracker.py`: IoU 多人目標追蹤，支援 30 幀遮擋容忍與 ID 漂移防護 (IoU > 0.8 狀態繼承)。
  - `core/privacy.py`: 頭部區域高斯模糊隱私保護（Kernel ≥ 31×31，嚴格先模糊後標籤）。
  - `core/head_pose.py`: 三段式頭部朝向估算 (策略1眼鼻、策略2耳肩、策略3純肩，看板閥值過濾)。
  - `core/roi.py`: 多邊形感興趣區域過濾 (`cv2.pointPolygonTest` 排除座位區外人員)。
  - `core/camera.py`: 5 FPS 主動讀取丟棄過時緩衝幀（防硬體 Buffer 延遲）與 10 次重試異常處理。
  - `core/pose_analyzer.py`: 整合姿態異常推導（趴睡、手機手腕 OR 判讀、分心）與 [0, 100] 專注度評分模型。
  - `tests/test_core.py`: 7 項視覺核心單元測試全數 100% PASS。

### 📌 v0.8.1 (2026-10-21) — 即時 AI 姿態監控修復與 WebCam 影格推論端點版本 (視覺核心實作前之進度)
- **壓縮檔名稱**: `student_analytics_v0.8.1_20261021.zip`
- **主要更新**:
  - 修復實時攝影機與 AI 監控 (Live Stream) 在線人數顯示為 `--人` 之問題。
  - 修復即時專注度評分隨姿態動作即時動態變更。
  - 修復異常行為警報即時通知與歷史告警事件紀錄。
  - 新增 `POST /api/v1/realtime/frame` 端點，支援前端 WebCam 每 800ms 發送影格進行 AI 推論。
  - 伺服器攝影機串流即時繪製 17 關節點人體骨架與專注度 HUD。
  - 資料庫新增 `write_attention_metric` 與 `write_abnormal_event` 寫入函式。

---

## 2. 歷史版本紀錄摘要

- **v0.8.0** (2026-09-06): 全自動 API 對外穿透通道生成器 (`scripts/generate_tunnel.py`, `start_tunnel.bat`)、多引擎備援。
- **v0.7.0** (2026-09-06): FastAPI RESTful API (TraceID/Metrics/Events/Realtime/PDF報表/RateLimiter)、一鍵全自動部署。
- **v0.6.0** (2026-08-16): MongoDB 8.3.7 整合、CORS Preflight 修復、Cloudflare HTTPS 穿透。
- **v0.5.0** (2026-08-16): YOLOv8-Pose ONNX (n/m) 模型匯出與推論驗證。
- **v0.2.1** (2026-08-16): WebCam 直連雙鏡頭切換與隱私遮罩。
