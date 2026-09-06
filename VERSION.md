# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)

## 版本說明 (Release Notes) - v0.7.0

- **版本號 (Version)**: `v0.7.0`
- **打包日期 (Release Date)**: 2026-09-06 22:56 (Asia/Taipei)
- **精簡版壓縮檔名稱**: `student_analytics_v0.7.0_20260906.zip`
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **HTTPS 穿透 API 網址**: `https://slot-config-seventh-posting.trycloudflare.com`
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (已通過 8.3.7 測試) / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### ⚡ FastAPI RESTful API 完整端點實作 (`api/`)
- [x] **Trace ID 日誌中介軟體 (`TraceIDMiddleware`)**: 為所有進站 HTTP 請求自動產生與攜帶 `X-Trace-ID` 標頭，並連結至全系統結構化日誌。
- [x] **時序數據與異常事件 API (`/metrics`, `/events`)**: 提供以時間區間查詢 `Attention_Metrics` 時序專注度數據，以及按類型過濾 `Abnormal_Events` 之 RESTful 端點。
- [x] **AWAIT_QUEUE_FLUSH 資料一致性排空**: `PATCH /sessions/{id}/end` 支援 10 秒超時保護之非同步資料庫寫入佇列排空機制。
- [x] **即時指標輪詢 API (`GET /api/v1/realtime`)**: 供儀表板每秒輪詢獲取當前課程人數、即時專注度與告警狀態。
- [x] **PDF 課後報表與 Rate Limiting 保護 (`GET /api/v1/report/{session_id}`)**: 支援自動排版產出 PDF/文本 報告下載，並套用 `API_RATE_LIMIT` (5 次/分鐘) 視窗速率限制攔截。

### 🚀 跨環境一鍵全自動部署機制 (`start.bat`, `start.sh`, `scripts/deploy_server.py`)
- [x] **Windows / Linux / macOS 一鍵啟動腳本**: 提供雙擊 [`start.bat`](file:///g:/graduate_project/start.bat) 或執行 `./start.sh` 無痛啟動全套服務。
- [x] **全自動環境自我修復**: 自動檢測/建立 Python 虛擬環境 (`.venv`)、自動補齊相依套件 (`requirements.txt`)、自動匯出 AI ONNX 模型權重。
- [x] **Cloudflare Tunnel 動態穿透**: 自動啟動 `npx cloudflared` 並實時抓取列印 TryCloudflare 全球 HTTPS 對外網址。

### 🤖 邊緣 AI 視覺核心模組 (`core/`)
- [x] **核心 8 大模組完成**:
  - `core/models.py`: `TrackedPerson` 快照、`PoseFlag` (趴睡/手機) 與 `FrameResult`。
  - `core/inference.py`: YOLOv8-Pose ONNX Runtime 解碼、letterbox 前處理與 NMS。
  - `core/tracker.py`: IoU-based PersonTracker 人員追蹤、30 幀遮擋容忍與 ID 漂移防護。
  - `core/privacy.py`: 頭部區域高斯模糊隱私保護（先模糊後標記）。
  - `core/head_pose.py`: 三段式頭部朝向估算 (Yaw/Pitch 角度)。
  - `core/pose_analyzer.py`: 趴睡 (SLEEPING) 與疑似使用手機 (PHONE_SUSPECTED) 姿態規則判讀。
  - `core/roi.py`: ROI 正規化多邊形與 `cv2.pointPolygonTest` 點過濾。
  - `core/camera.py`: 5 FPS 鎖定廣角攝影機讀取。

### 🧪 全系統綜合整合測試
- [x] **`scripts/test_api_v1.py` 7 大 RESTful API 測試**: 100% PASS。
- [x] **`scripts/test_all_features.py` 全功能整合測試**: 100% PASS (0 失敗)。
