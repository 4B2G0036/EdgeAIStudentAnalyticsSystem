# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.1.1

- **版本號 (Version)**: `v0.1.1`
- **打包日期 (Release Date)**: 2026-08-16 17:00 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (支援 Time Series Collection) / Node.js 18+ (用於 Firebase CLI)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 雲端部署與 Firebase Hosting 整合 (Firebase Integration — `v0.1.1` 新增)
- [x] **Firebase Hosting 發布**: 完成 `firebase.json` 與 `.firebaserc` 設定，將 `dashboard/` 前端靜態網頁成功部署上線至 `https://studentanalytics-91cd1.web.app`。
- [x] **動態 API 網址設定 (Dynamic API Base)**:
  - 徹底移除前端 `localhost:8000` 硬編碼限制。
  - 在控制台右上角新增 **「⚙️ API 網址」** 互動式設定按鈕，支援 `localStorage` 持久化記錄。
  - 支援跨網域、Cloudflare Tunnel / Ngrok 穿透網址或雲端後端無縫介接。

### 邊緣 AI 視覺核心 (Vision AI Core — `core/`)
- [x] **攝影機串流處理 (`core/camera.py`)**: 實現 OpenCV 廣角攝影機讀取迴圈，支援 Target FPS (預設 5 FPS) 幀率鎖定，並具備 `SIGTERM` / `SIGINT` 優雅停機 (Graceful Shutdown) 機制。

### 資料庫層 (Database Layer — `database/`)
- [x] **MongoDB 時序集合與索引建置 (`database/collections.py`)**: 
  - `Classes_Session`: 課程 UUID 唯一索引及複合防重索引。
  - `Attention_Metrics`: Time Series 集合 (秒級粒度)，套用 TTL 自動過期清理索引 (預設 365 天)。
  - `Abnormal_Events`: 異常事件集合與複合查詢索引。
- [x] **伺服器自我修復 (Self-Healing)**: 伺服器啟動時自動掃描未正常結束之掛起異常事件並排空 force-close。
- [x] **統計查詢與 CRUD 函式 (`database/queries.py`)**: 提供完整 Session 建立、結束、分頁查詢、摘要統計、資料更新與刪除等函式。

### FastAPI 後端 (API Layer — `api/`)
- [x] **主程式與 CORS 整合 (`api/main.py`)**: 整合 FastAPI 生命週期事件、日誌追蹤 (`trace_id`) 與 `/dashboard` 靜態儀表板掛載。
- [x] **Session 生命週期 API 路由 (`api/routers/sessions.py`)**:
  - `POST /api/v1/sessions` - 開始新課程 (具備重複 Session 防衝突)
  - `PATCH /api/v1/sessions/{id}/end` - 結束進行中課程並觸發資料排空與報表任務
  - `GET /api/v1/sessions` - 查詢歷史課程列表 (支援 `limit`, `offset`, `search`, `status` 篩選)
  - `GET /api/v1/sessions/{id}` - 查詢特定課程元數據
  - `GET /api/v1/sessions/{id}/summary` - 查詢課程統計摘要
  - `PATCH /api/v1/sessions/{id}` - 更新課程資訊
  - `DELETE /api/v1/sessions/{id}` - 刪除歷史課程紀錄
  - `GET /api/v1/sessions/{id}/report` - 下載課程報告
  - `GET /api/v1/sessions/{id}/realtime` - 即時輪詢課程指標

### 即時儀表板 (Dashboard — `dashboard/`)
- [x] **Web 前端儀表板 (`dashboard/index.html`)**: 包含即時監控、課程設定、歷史記錄、報告下載與動態 API 網址切換介面。

---

## 2. 版本打包目錄結構 (Package Structure)

```
student_analytics_v0.1.1_20260816/
├── .firebaserc                 # Firebase 專案對應設定檔
├── firebase.json               # Firebase Hosting 發布設定檔
├── api/                        # FastAPI 後端服務
│   ├── routers/
│   │   └── sessions.py         # 課程生命週期與 REST 端點
│   ├── __init__.py
│   └── main.py                 # FastAPI 進入點與靜態掛載
├── core/                       # 邊緣 AI 視覺模組
│   ├── __init__.py
│   └── camera.py               # 攝影機串流與優雅停機
├── database/                   # MongoDB 資料庫維護與查詢
│   ├── __init__.py
│   ├── collections.py          # Time Series 集合與 TTL 索引初始化
│   ├── connection.py           # PyMongo 連線管理
│   └── queries.py              # 資料庫 CRUD 與聚合查詢
├── dashboard/                  # 前端儀表板 (已上線至 Firebase)
│   └── index.html              # 具備動態 API 網址設定功能
├── openspec/                   # OpenSpec 專案規格與工作項
│   ├── changes/
│   │   └── student-analytics-system-init/
│   └── config.yaml
├── config.py                   # 集中化環境常數設定
├── init_db.py                  # 資料庫初始化獨立指令
├── test_api.py                 # API 測試腳本
├── test_connection.py          # 資料庫連線測試
├── testcam.py                  # 攝影機硬體測試
├── VERSION.md                  # 本版本發行說明 (v0.1.1)
├── implementation_plan.md      # 系統實作規劃
├── project_proposal_and_architecture.md  # 系統架構與提案
└── 學生專注度與異常行為分析系統專題製作計畫書.md  # 專題計畫書
```

---

## 3. 快速啟動指南 (Quick Start)

### 前端線上訪問 (Web Frontend)
訪問正式部署網址：[https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

### 本機後端與資料庫啟動
1. **安裝環境與相依套件**:
   ```bash
   pip install -r format_requirements.txt
   ```
2. **啟動 MongoDB 服務**:
   確保本地 MongoDB 7.0+ 正常執行於 `mongodb://localhost:27017`
3. **初始化資料庫**:
   ```bash
   python init_db.py
   ```
4. **啟動 FastAPI 後端服務**:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. **雲端與本機穿透連線 (選用)**:
   ```bash
   npx cloudflared tunnel --url http://localhost:8000
   ```
   將穿透產生的 `https://xxxx.trycloudflare.com` 填入線上儀表板右上角 **「⚙️ API 網址」** 即可。
