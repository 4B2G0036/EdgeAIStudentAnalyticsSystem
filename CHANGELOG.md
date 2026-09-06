# 學生專注度與異常行為分析系統 — 完整版本變更履歷 (CHANGELOG.md)

本文件紀錄【學生專注度與異常行為分析系統 (Edge AI Student Analytics System)】自專案建立以來的所有版本更新歷程、釋出時間、包含的核心功能與技術變更細節。

---

## 📌 版本總覽 (Version History Index)

| 版本號 (Version) | 打包日期 (Release Date) | 壓縮檔名稱 | 主要核心更新內容摘要 |
|---|---|---|---|
| **v0.7.0** 🌟 *(最新)* | 2026-09-06 22:56 | `student_analytics_v0.7.0_20260906.zip` | FastAPI RESTful API (TraceID, Metrics, Events, Realtime, Report RateLimiter)、跨環境一鍵全自動部署啟動檔 (start.bat/sh) 與 Cloudflare HTTPS 穿透 |
| **v0.6.0** | 2026-08-16 20:18 | `student_analytics_v0.6.0_20260816.zip` | MongoDB 8.3.7 CRUD 全面驗證、CORS Preflight (OPTIONS 200) 修復、Cloudflare HTTPS 穿透、core/ 8 大視覺 AI 模組實作與全系統 100% 自動化測試 |
| **v0.5.0** | 2026-08-16 17:51 | `student_analytics_v0.5.0_20260816.zip` | MongoDB 8.3.7 服務安裝與 Time Series Collection 測試、YOLOv8-Pose ONNX (n/m) 模型匯出與推論驗證 (21ms/103ms)、WebCam 重複函數修復 |
| **v0.2.1** *(穩定版)* | 2026-08-16 17:23 | `student_analytics_v0.2.1_20260816.zip` | 本機 WebCam HTML5 `getUserMedia` 直連畫面修復、雙鏡頭切換模式、隱私保護遮罩、Firebase Hosting 發布 |
| **v0.2.0** | 2026-08-16 16:30 | `student_analytics_v0.2.0_20260816.zip` | 前端儀表板互動式 `⚙️ API 網址` 設定、伺服器即時數據輪詢、介面樣式微調 |
| **v0.1.1** | 2026-08-16 15:10 | `student_analytics_v0.1.1_20260816.zip` | 歷史課程紀錄列表與搜尋分頁、下課確定對話框 (Modal)、數據摘要下載介面 |
| **v0.1.0** | 2026-08-16 14:00 | `student_analytics_v0.1.0_20260816.zip` | 專案初始化、基礎目錄結構、`config.py` 常數、FastAPI 基礎路由、MongoDB 連線基礎 |

---

## 📝 詳細版本變更內容 (Detailed Release Notes)

### 🚀 v0.6.0 — 全系統整合驗證、CORS 修復與 邊緣 AI 核心模組 (2026-08-16 20:18)

- **檔案名稱**: `student_analytics_v0.6.0_20260816.zip` (11.59 MB 精簡實用版)
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **HTTPS 穿透 API 通道**: `https://nickel-establish-incorporated-hopkins.trycloudflare.com`

#### ✨ 新增功能與技術改進
1. **🚀 一鍵全自動伺服器部署工具 (`scripts/deploy_server.py` / `.ps1`)**:
   - 提供 `python scripts/deploy_server.py` 與 PowerShell `deploy_server.ps1` 自動化部署工具。
   - 自動配置 `.env` 設定、初始化 MongoDB 8.3.7 集合與時序結構、啟動 FastAPI 背景服務並執行實地 Health Check 驗證。
   - 建立 `scripts/test_db_full.py` 與 `scripts/verify_db_queries.py` 自動化測試套件。
   - 驗證 `Classes_Session` Unique Index 約束防護、`Attention_Metrics` 原生時序集合寫入與平均專注度聚合計算。
2. **🌐 跨網域 CORS Preflight 根治修復**:
   - 解決瀏覽器預檢請求 `OPTIONS /` 返回 `400 Bad Request` 導致前端顯示離線的 bug。
   - 修改 `api/main.py` CORS Middleware 為 `allow_origin_regex=".*"`，支援包含 Firebase Hosting 在內的所有來源。
3. **🌐 Cloudflare Tunnel 全球 HTTPS 穿透通道**:
   - 成功架設無任何攔截頁面的 Cloudflare Tunnel，解決跨網域 Mixed Content (HTTPS 呼叫 HTTP) 限制。
4. **🤖 邊緣 AI 視覺核心 (`core/`) 8 大模組基礎建置**:
   - `core/models.py`: `TrackedPerson` 追蹤快照、`PoseFlag` (趴睡/手機) 與 `FrameResult`。
   - `core/inference.py`: ONNX Runtime YOLOv8-Pose 推論、letterbox 前處理與 NMS 解碼。
   - `core/tracker.py`: PersonTracker 人員追蹤、30 幀遮擋容忍與 ID 漂移防護 (IoU > 0.8 重用 ID)。
   - `core/privacy.py`: 頭部區域高斯模糊隱私保護（先模糊後標記）。
   - `core/head_pose.py`: 三段式頭部朝向估算 (Yaw 水平角 / Pitch 垂直俯仰角)。
   - `core/pose_analyzer.py`: 趴睡 (`SLEEPING`) 與疑似使用手機 (`PHONE_SUSPECTED`) 姿態幾何規則判讀。
   - `core/roi.py`: ROI 正規化多邊形與 `cv2.pointPolygonTest` 點過濾。
   - `core/camera.py`: 5 FPS 鎖定廣角攝影機讀取。
5. **🧪 一鍵全系統綜合整合測試**:
   - 建立 `scripts/test_all_features.py`，資料庫、AI 模型、FastAPI RESTful API、CORS 預檢與對外穿透 100% PASS。

---

### 📦 v0.5.0 — MongoDB 8.3.7 服務整合與 YOLOv8-Pose ONNX 匯出 (2026-08-16 17:51)

- **檔案名稱**: `student_analytics_v0.5.0_20260816.zip` (95.81 MB)

#### ✨ 新增功能與技術改進
1. **🗄️ MongoDB 8.3.7 服務安裝**:
   - 使用 winget 完成本機 MongoDB 8.3.7 服務安裝與自動啟動。
   - 自動配置 `.env` 變數 `MONGO_URI=mongodb://127.0.0.1:27017`。
2. **🤖 YOLOv8-Pose ONNX 模型匯出與推論測試**:
   - 匯出 `models/yolov8n-pose.onnx` (12.9 MB)，CPU 單次推論耗時 **21ms** (≤ 200ms 標準)。
   - 匯出 `models/yolov8m-pose.onnx` (101.2 MB)，CPU 單次推論耗時 **103ms** (≤ 200ms 標準)。
3. **📷 WebCam 前端顯示修復**:
   - 解決 `dashboard/index.html` 內 JavaScript 重複函數定義與 DOM 初始化順序問題，恢復 WebCam 實時預覽。
4. **🧪 測試腳本**:
   - 提供 `scripts/verify_setup.py` 與 `scripts/setup_mongodb.ps1` 自動化測試與環境配置工具。

---

### 📷 v0.2.1 — 本機 WebCam 雙鏡頭模式與隱私保護 (2026-08-16 17:23)

- **檔案名稱**: `student_analytics_v0.2.1_20260816.zip` (440 KB)

#### ✨ 新增功能與技術改進
1. **本機 WebCam 直連**:
   - HTML5 `getUserMedia` 直連鏡頭，提供零延遲本機高清視訊預覽。
2. **雙鏡頭模式選擇器 (Dual-Mode Selector)**:
   - 支援 `[ 📷 本機 WebCam (瀏覽器鏡頭) | 📡 伺服器 AI 串流 (邊緣端) ]` 一鍵切換。
3. **隱私控制與暫停**:
   - 支援 `🔒 隱私模式` 畫面高斯模糊遮蔽與 `⏸ 暫停串流` 控制。
4. **雲端發布**:
   - 完成發布至 Firebase Hosting (`https://studentanalytics-91cd1.web.app`)。

---

### ⚙️ v0.2.0 — 前端互動式 API 網址設定與介面升級 (2026-08-16 16:30)

- **檔案名稱**: `student_analytics_v0.2.0_20260816.zip` (430 KB)

#### ✨ 新增功能與技術改進
1. **動態 API 設定 (`promptApiUrl`)**:
   - 前端新增 `⚙️ API 網址` 互動按鈕，允許使用者自由調整後端 FastAPI 位址。
2. **實時指標輪詢**:
   - 儀表板新增每 3 秒自動輪詢目前課程在線人數、即時專注度與最新異常事件。

---

### 📊 v0.1.1 — 歷史課程列表與報表介面 (2026-08-16 15:10)

- **檔案名稱**: `student_analytics_v0.1.1_20260816.zip` (420 KB)

#### ✨ 新增功能與技術改進
1. **歷史紀錄分頁與搜尋**:
   - 支援課程名稱、教師姓名關鍵字搜尋與狀態過濾。
2. **Modal 彈出視窗**:
   - 新增結束課程與刪除課程對話框。

---

### 🚀 v0.1.0 — 專案初始化與基礎架構 (2026-08-16 14:00)

- **檔案名稱**: `student_analytics_v0.1.0_20260816.zip` (410 KB)

#### ✨ 新增功能與技術改進
1. **架構建置**:
   - 建立 Python 專案結構、`config.py` 全域設定、`.env.example` 與結構化 Logging。
2. **FastAPI 基礎路由**:
   - 實作課程 Session CRUD 端點 (`api/routers/sessions.py`) 與 MJPEG 串流端點 (`api/routers/stream.py`)。
