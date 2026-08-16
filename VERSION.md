# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.2.0

- **版本號 (Version)**: `v0.2.0`
- **打包日期 (Release Date)**: 2026-08-16 17:03 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (支援 Time Series Collection) / Node.js 18+ (用於 Firebase CLI)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 實時攝影機監控與 MJPEG 串流 (`v0.2.0` 新增)
- [x] **API 實時串流路由 (`api/routers/stream.py`)**:
  - `GET /api/v1/stream`: 提供符合 RFC 1341 之 `multipart/x-mixed-replace` MJPEG 影像串流。
  - `GET /api/v1/camera/status`: 提供攝影機硬體連線狀態、解析度 (640x480) 與 FPS 鎖定查詢。
  - 具備硬體與模擬模式自動 Fallback (繪製實時動態 AI 時間戳記與狀態點)。
- [x] **Web 控制台實時監控面板 ([dashboard/index.html](file:///g:/graduate_project/dashboard/index.html))**:
  - 新增 **「🎥 實時攝影機與 AI 監控 (Live Stream)」** 區塊。
  - 支援 **串流啟動/暫停** 切換。
  - 支援 **極致隱私模式 (Extreme Privacy Mode)** 一鍵高斯模糊防護。
  - 顯示即時 AI 專注度評分 HUD (分步顯示全班專注度、在線人數與 FSM 10s 連續警報日誌)。

### 雲端部署與 Firebase Hosting 整合
- [x] **Firebase Hosting 發布**: 完成 `firebase.json` 與 `.firebaserc` 設定，將 `dashboard/` 前端靜態網頁成功部署上線至 `https://studentanalytics-91cd1.web.app`。
- [x] **動態 API 網址設定 (Dynamic API Base)**:
  - 在控制台右上角新增 **「⚙️ API 網址」** 互動式設定按鈕，支援 `localStorage` 持久化記錄。

### 邊緣 AI 視覺核心 (Vision AI Core — `core/`)
- [x] **攝影機串流處理 (`core/camera.py`)**: 實現 OpenCV 廣角攝影機讀取迴圈，支援 Target FPS (預設 5 FPS) 幀率鎖定，並具備 `SIGTERM` / `SIGINT` 優雅停機 (Graceful Shutdown) 機制。

### 資料庫層 (Database Layer — `database/`)
- [x] **MongoDB 時序集合與索引建置 (`database/collections.py`)**: 
  - `Classes_Session`: 課程 UUID 唯一索引及複合防重索引。
  - `Attention_Metrics`: Time Series 集合 (秒級粒度)，套用 TTL 自動過期清理索引 (預設 365 天)。
  - `Abnormal_Events`: 異常事件集合與複合查詢索引。
- [x] **伺服器自我修復 (Self-Healing)**: 伺服器啟動時自動掃描未正常結束之掛起異常事件並排空 force-close。
- [x] **統計查詢與 CRUD 函式 (`database/queries.py`)**: 提供完整 Session 讀寫、分頁查詢、摘要統計、資料更新與刪除。

### FastAPI 後端 (API Layer — `api/`)
- [x] **主程式與 CORS 整合 (`api/main.py`)**: 整合 FastAPI 生命週期事件、日誌追蹤 (`trace_id`) 與 `/dashboard` 靜態儀表板掛載。
- [x] **Session 生命週期 API 路由 (`api/routers/sessions.py`)**: 全套 Session 建立、結束、分頁查詢、摘要統計、編輯與刪除。

---

## 2. 版本打包目錄結構 (Package Structure)

```
student_analytics_v0.2.0_20260816/
├── .firebaserc                 # Firebase 專案對應設定檔
├── firebase.json               # Firebase Hosting 發布設定檔
├── api/                        # FastAPI 後端服務
│   ├── routers/
│   │   ├── sessions.py         # 課程生命週期與 REST 端點
│   │   └── stream.py           # [v0.2.0] MJPEG 實時串流端點
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
│   └── index.html              # [v0.2.0] 新增 🎥 實時攝影機監控 HUD 面板
├── openspec/                   # OpenSpec 專案規格與工作項
├── config.py                   # 集中化環境常數設定
├── init_db.py                  # 資料庫初始化獨立指令
├── test_api.py                 # API 測試腳本
├── test_connection.py          # 資料庫連線測試
├── testcam.py                  # 攝影機硬體測試
├── VERSION.md                  # 本版本發行說明 (v0.2.0)
├── implementation_plan.md      # 系統實作規劃
├── project_proposal_and_architecture.md  # 系統架構與提案
└── 學生專注度與異常行為分析系統專題製作計畫書.md  # 專題計畫書
```

---

## 3. 快速啟動指南 (Quick Start)

### 1. 訪問線上控制台
開啟：[https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

### 2. 啟動本機後端與資料庫
```bash
pip install -r format_requirements.txt
python init_db.py
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 本機後端穿透網址 (供 Firebase 線上控制台連接)
```bash
npx cloudflared tunnel --url http://localhost:8000
```
在線上網頁右上角點擊 **「⚙️ API 網址」** 貼上 `https://xxxx.trycloudflare.com`，即可在網頁上觀看實時攝影機串流與專注度指標！
