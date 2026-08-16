# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.3.0

- **版本號 (Version)**: `v0.3.0`
- **打包日期 (Release Date)**: 2026-08-16 17:12 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### WebCam 實時 AI 人體追蹤與姿態識別 (`v0.3.0` 重大新增)
- [x] **WebCam 實時 17 骨架節點 Canvas 疊加 (Skeleton Overlay)**:
  - 直接在 WebCam 畫面即時疊加 COCO-17 骨架關節連線、人臉/五官中心與肩肘手關節點。
- [x] **ByteTrack 目標 ID 與姿態框選標籤 (BBox & Tracking Tag)**:
  - 動態標註 `[ID: #1 | 專注: 95% | 朝向: 看黑板 (Yaw: 8.2°)]` 螢光綠框與金屬包角。
- [x] **實時 AI 專注度與異常狀態 HUD 評分**:
  - 即時計算頭部偏轉 Yaw / Pitch 角度、坐姿標準度、並於右側 HUD 呈現 95分 高分指標與 🟢 姿勢端正狀態紀錄。
- [x] **一鍵開關 AI 追蹤 (AI Tracking Toggle)**:
  - 畫面右上角提供 `[ 🎯 AI 追蹤: 開 ]` 開關按鈕，可自由控制追蹤圖層之繪製。

### 本機 WebCam 瀏覽器鏡頭直接存取
- [x] **HTML5 `getUserMedia` 直連鏡頭**: 支援 `[ 📷 本機 WebCam | 📡 伺服器 AI 串流 ]` 雙來源切換與授權開關。

### 雲端部署與 Firebase Hosting 整合
- [x] **Firebase Hosting 發布**: 完成靜態網頁與 AI 引擎部署至 `https://studentanalytics-91cd1.web.app`。
- [x] **動態 API 網址設定 (Dynamic API Base)**: 支援 `⚙️ API 網址` 互動式設定。

---

## 2. 版本打包目錄結構 (Package Structure)

```
student_analytics_v0.3.0_20260816/
├── .firebaserc                 # Firebase 專案設定檔
├── firebase.json               # Firebase Hosting 發布設定檔
├── api/                        # FastAPI 後端服務
│   ├── routers/
│   │   ├── sessions.py         # Session 生命週期 API
│   │   └── stream.py           # MJPEG 實時串流端點
│   ├── __init__.py
│   └── main.py                 # FastAPI 進入點
├── core/                       # 邊緣 AI 視覺模組
├── database/                   # MongoDB 資料庫維護
├── dashboard/                  # 前端儀表板 (已上線至 Firebase)
│   └── index.html              # [v0.3.0] 具備 WebCam 實時 AI 骨架追蹤與姿態標籤
├── config.py                   # 集中化環境設定
├── init_db.py                  # 資料庫初始化
├── VERSION.md                  # 發行說明 (v0.3.0)
├── implementation_plan.md      # 系統實作規劃
└── project_proposal_and_architecture.md
```
