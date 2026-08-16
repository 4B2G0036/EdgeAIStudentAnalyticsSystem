# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.2.1

- **版本號 (Version)**: `v0.2.1`
- **打包日期 (Release Date)**: 2026-08-16 17:08 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 本機 WebCam 瀏覽器鏡頭直接存取 (`v0.2.1` 重大新增)
- [x] **HTML5 `getUserMedia` 直連鏡頭**:
  - 網頁開啟時即可直接要求存取使用者的本機 WebCam (視訊鏡頭)，零延遲直出高清影像！
  - 支援鏡頭來源切換下拉選單：**`[ 📷 本機 WebCam (瀏覽器鏡頭) | 📡 伺服器 AI 串流 (邊緣端) ]`**。
  - 支援鏡頭授權提示遮罩與一鍵開啟。
- [x] **實時 AI 指標 HUD**:
  - 本機視訊與邊緣端 AI 分析數據雙向切換，呈現專注度評分、在線人數與異常狀態。

### 實時攝影機監控與 MJPEG 串流
- [x] **API 實時串流路由 (`api/routers/stream.py`)**:
  - `GET /api/v1/stream`: 提供符合 RFC 1341 之 `multipart/x-mixed-replace` MJPEG 影像串流。
  - `GET /api/v1/camera/status`: 提供攝影機硬體連線狀態與 FPS 查詢。
- [x] **Web 控制台監控面板 ([dashboard/index.html](file:///g:/graduate_project/dashboard/index.html))**:
  - 支援 **串流啟動/暫停** 與 **極致隱私模式 (Extreme Privacy Mode)**。

### 雲端部署與 Firebase Hosting 整合
- [x] **Firebase Hosting 發布**: 完成靜態網頁發布至 `https://studentanalytics-91cd1.web.app`。
- [x] **動態 API 網址設定 (Dynamic API Base)**:
  - 支援 **「⚙️ API 網址」** 互動式設定按鈕與 `localStorage` 記憶機制。

---

## 2. 版本打包目錄結構 (Package Structure)

```
student_analytics_v0.2.1_20260816/
├── .firebaserc                 # Firebase 專案設定檔
├── firebase.json               # Firebase Hosting 發布設定檔
├── api/                        # FastAPI 後端服務
│   ├── routers/
│   │   ├── sessions.py         # Session 生命週期 API
│   │   └── stream.py           # MJPEG 實時串流端點
│   ├── __init__.py
│   └── main.py                 # FastAPI 進入點
├── core/                       # 邊緣 AI 視覺模組
│   ├── __init__.py
│   └── camera.py               # 攝影機串流管理
├── database/                   # MongoDB 資料庫維護
├── dashboard/                  # 前端儀表板 (已上線至 Firebase)
│   └── index.html              # [v0.2.1] 新增 HTML5 本機 WebCam 直連與切換
├── config.py                   # 集中化環境設定
├── init_db.py                  # 資料庫初始化
├── VERSION.md                  # 發行說明 (v0.2.1)
├── implementation_plan.md      # 系統實作規劃
└── project_proposal_and_architecture.md
```
