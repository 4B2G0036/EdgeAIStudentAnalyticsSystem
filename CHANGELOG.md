# 學生專注度與異常行為分析系統 — 完整版本變更履歷 (CHANGELOG.md)

本文件紀錄【學生專注度與異常行為分析系統 (Edge AI Student Analytics System)】自專案建立以來的所有版本更新歷程、釋出時間、包含的核心功能與技術變更細節。

---

## 📌 版本總覽 (Version History Index)

| 版本號 (Version) | 打包日期 (Release Date) | 壓縮檔名稱 | 主要核心更新內容摘要 |
|---|---|---|---|
| **v0.9.0** 🌟 *(最新)* | 2026-10-22 10:00 | `student_analytics_v0.9.0_20261022.zip` | 邊緣 AI 視覺核心 (`core/`) 規格全面實作與驗證：純 ONNX 推論、ByteTrack 追蹤 (30幀遮擋/ID防漂移)、高斯隱私模糊 (先模糊後標籤)、三段式頭部朝向、ROI 多邊形過濾、7 項單元測試 100% 通過 |
| **v0.8.1** | 2026-10-21 21:35 | `student_analytics_v0.8.1_20261021.zip` | 實時攝影機與 AI 監控 (Live Stream) 除錯：修復在線人數 `--人` 顯示、專注度動態姿態變化反饋、異常警報通知、新增 POST `/api/v1/realtime/frame` WebCam 推論端點 |
| **v0.8.0** | 2026-09-06 23:20 | `student_analytics_v0.8.0_20260906.zip` | 全自動 API 對外穿透通道生成器 (`scripts/generate_tunnel.py`, `start_tunnel.bat`)、多引擎備援 (Cloudflare/Pinggy)、正則表達式 URL 解析與 `/api/v1/system/tunnel` 查詢端點 |

---

## 📝 詳細版本變更內容 (Detailed Release Notes)

### 🤖 v0.9.0 — 邊緣 AI 視覺核心 (`core/`) 規格全面實作與驗證版本 (2026-10-22)

- **檔案名稱**: `student_analytics_v0.9.0_20261022.zip` (11.15 MB 精簡版)
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### ✨ 新增功能與技術改進
1. **純 ONNX Runtime 推論引擎 (`core/inference.py`)**:
   - 擺脫執行期 PyTorch/Ultralytics 依賴，直接以 `onnxruntime.InferenceSession` 執行 `yolov8n-pose.onnx`。
   - 支援自動偵測 `CUDAExecutionProvider`，無 GPU 時平滑 fallback 至 `CPUExecutionProvider`。
   - 包含 Letterbox 等比縮放填充、座標逆向還原 (De-letterboxing) 與向量化 NMS。
2. **多目標追蹤與 ID 漂移防護 (`core/tracker.py`)**:
   - 實作 greedy IoU 匹配演算法分配穩定 `tracking_id`。
   - 支援高達 **30 幀（約 6 秒 @ 5FPS）遮擋容忍**，學生短暫走動或遮蔽不會重置追蹤。
   - 內建 **ID 漂移防護 (ID Drift Protection)**：剛消失 ID 若重現且 IoU > 0.8 則主動繼承，維護分析狀態連續性。
3. **隱私高斯模糊去識別化 (`core/privacy.py`)**:
   - 依據頭部五官節點與 BBox 擴展區域進行高斯模糊（Kernel ≥ 31×31）。
   - 嚴格遵守「先高斯模糊臉部、後繪製骨架與資訊標籤」，確保未去識別化之原始人臉絕對不流出核心。
4. **三段式頭部朝向估算 (`core/head_pose.py`)**:
   - 節點信心閥值過濾（Conf ≥ 0.45）。
   - 策略 1（眼鼻五官幾何）、策略 2（耳肩輔助運算）、策略 3（肩線水平角）。
   - 看板條件過濾：$|\text{Yaw}| \le 30^\circ$ 且 $|\text{Pitch}| \le 25^\circ$ 判定為看黑板。
5. **多邊形感興趣區域過濾 (`core/roi.py`)**:
   - 支援前端自訂正規化多邊形頂點，透過 `cv2.pointPolygonTest` 排除走廊路人與講台教師。
6. **攝影機緩衝主動丟幀 (`core/camera.py`)**:
   - 以 `cap.read()` 主動讀取並拋棄緩衝影格代替 `time.sleep()`，防止硬體 Buffer 累積過時畫面。
   - 10 次自動重試異常處理 (`CameraConnectionError`)。
7. **姿態異常與專注度綜合分析 (`core/pose_analyzer.py`)**:
   - 整合趴睡、疑似手機（雙手腕 OR 條件）、分心判定與 [0, 100] 專注度評分模型。
8. **視覺核心單元測試套件 (`tests/test_core.py`)**:
   - 7 項單元測試 100% 通過（ROI 過濾、頭部朝向、多人追蹤、隱私模糊、姿態評分、FrameResult 結構）。

---

### 📷 v0.8.1 — 即時 AI 姿態監控修復與 WebCam 影格推論端點版本 (2026-10-21 21:35)

- **檔案名稱**: `student_analytics_v0.8.1_20261021.zip` (11.64 MB)
- **Git Commit**: `23625ee`
- **主要修復與新增功能**:
  1. **即時監控即時修復**:
     - 解決在線偵測人數固定為 `--人` 之問題，實時反映鏡頭偵測人數。
     - 解決即時專注度評分不隨動作變更之問題。
     - 完善即時異常行為警報動態推播與告警清單同步。
  2. **WebCam 影格推論 API (`POST /api/v1/realtime/frame`)**:
     - 支援前端 WebCam 每 800ms 發送影格至後端進行 YOLOv8-Pose 推論並返回分析結果。
  3. **資料庫非同步寫入**:
     - 支援寫入即時專注度數據 (`write_attention_metric`) 與異常事件歷史 (`write_abnormal_event`)。

---
| **v0.7.0** | 2026-09-06 22:56 | `student_analytics_v0.7.0_20260906.zip` | FastAPI RESTful API (TraceID, Metrics, Events, Realtime, Report RateLimiter)、跨環境一鍵全自動部署啟動檔 (start.bat/sh) 與 Cloudflare HTTPS 穿透 |
| **v0.6.0** | 2026-08-16 20:18 | `student_analytics_v0.6.0_20260816.zip` | MongoDB 8.3.7 CRUD 全面驗證、CORS Preflight (OPTIONS 200) 修復、Cloudflare HTTPS 穿透、core/ 8 大視覺 AI 模組實作與全系統 100% 自動化測試 |
| **v0.5.0** | 2026-08-16 17:51 | `student_analytics_v0.5.0_20260816.zip` | MongoDB 8.3.7 服務安裝與 Time Series Collection 測試、YOLOv8-Pose ONNX (n/m) 模型匯出與推論驗證 (21ms/103ms)、WebCam 重複函數修復 |
| **v0.2.1** *(穩定版)* | 2026-08-16 17:23 | `student_analytics_v0.2.1_20260816.zip` | 本機 WebCam HTML5 `getUserMedia` 直連畫面修復、雙鏡頭切換模式、隱私保護遮罩、Firebase Hosting 發布 |
| **v0.2.0** | 2026-08-16 16:30 | `student_analytics_v0.2.0_20260816.zip` | 前端儀表板互動式 `⚙️ API 網址` 設定、伺服器即時數據輪詢、介面樣式微調 |
| **v0.1.1** | 2026-08-16 15:10 | `student_analytics_v0.1.1_20260816.zip` | 歷史課程紀錄列表與搜尋分頁、下課確定對話框 (Modal)、數據摘要下載介面 |
| **v0.1.0** | 2026-08-16 14:00 | `student_analytics_v0.1.0_20260816.zip` | 專案初始化、基礎目錄結構、`config.py` 常數、FastAPI 基礎路由、MongoDB 連線基礎 |

---

## 📝 詳細版本變更內容 (Detailed Release Notes)

### 🌐 v0.8.0 — 全自動 API 對外穿透通道生成與管理功能 (2026-09-06 23:20)

- **檔案名稱**: `student_analytics_v0.8.0_20260906.zip`
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### ✨ 新增功能與技術改進
1. **🌐 全自動 API 穿透通道生成器 (`scripts/generate_tunnel.py`)**:
   - 支援 **Cloudflare Tunnel**、**Pinggy SSH** 與 **LocalTunnel** 多引擎自動備援切換。
   - 使用精準正則表達式擷取公網 HTTPS 網址，防範非標準輸出字串截斷問題。
   - 自動將當前通道狀態寫入 `scratch/tunnel_status.json` 並同步寫入 `.env` 中的 `PUBLIC_API_URL`。
2. **🚀 Windows 雙擊快捷啟動檔 (`start_tunnel.bat`)**:
   - 新增 Windows `start_tunnel.bat` 雙擊一鍵穿透快捷腳本。
3. **📡 系統狀態與穿透網址查詢端點 (`GET /api/v1/system/tunnel`)**:
   - 提供 RESTful 端點供前端儀表板實時查詢最新動態生成之對外 HTTPS API 位址。
4. **📦 自動化部署與驗證套件升級**:
   - 升級 `scripts/deploy_server.py` [7/7] 步驟整合穿透通道功能，並更新 `scripts/verify_zip_deployable.py` 檢查清單。

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
