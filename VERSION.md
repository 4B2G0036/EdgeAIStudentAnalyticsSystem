# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)

## 版本說明 (Release Notes) - v0.6.0

- **版本號 (Version)**: `v0.6.0`
- **打包日期 (Release Date)**: 2026-08-16 20:46 (Asia/Taipei)
- **精簡版壓縮檔大小**: `11.59 MB` (已精簡排除 101MB 備用大檔，僅保留有用實用檔案)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **HTTPS 穿透 API 網址**: `https://nickel-establish-incorporated-hopkins.trycloudflare.com`
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (已通過 8.3.7 測試) / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 🚀 一鍵全自動伺服器部署工具 (`scripts/deploy_server.py`)
- [x] **一鍵自動部署與啟動 (`python scripts/deploy_server.py`)**: 自動配置 `.env`、自動初始化 MongoDB 8.3.7 時序資料庫、自動啟動 FastAPI 後端與驗證健康狀態。
- [x] **PowerShell 部署工具 (`scripts/deploy_server.ps1`)**: 提供 Windows 系統一鍵自動部署指令。
- [x] **MongoDB 8.3.7 連線與 Time Series 驗證**: 通過 `Attention_Metrics` 原生時序集合、`Classes_Session` 與 `Abnormal_Events` 三大 Collection 的自動建置、索引與 TTL 測試。
- [x] **完整 CRUD 與時序聚合測試**: `scripts/test_db_full.py` 與 `scripts/verify_db_queries.py` 通過 100% 讀寫與時序平均專注度聚合測試。

### 🌐 網路層與跨網域 CORS Preflight 根治
- [x] **CORS Preflight (OPTIONS 200 OK) 修復**: 修復 FastAPI 的 CORS 預檢攔截，使用 `allow_origin_regex=".*"` 支援全來源安全跨網域存取。
- [x] **Cloudflare Tunnel 全球 HTTPS 通道**: 成功架設 `https://nickel-establish-incorporated-hopkins.trycloudflare.com`，解決 Firebase Hosting HTTPS 與本機 HTTP 的 Mixed Content 限制。

### 🤖 邊緣 AI 視覺核心模組 (`core/`)
- [x] **核心 8 大模組基礎結構完成**:
  - `core/models.py`: 定義 `TrackedPerson` 快照、`PoseFlag` (趴睡/手機) 與 `FrameResult`。
  - `core/inference.py`: YOLOv8-Pose ONNX Runtime 解碼、letterbox 前處理與 NMS。
  - `core/tracker.py`: IoU-based PersonTracker 人員追蹤、30 幀遮擋容忍與 ID 漂移防護。
  - `core/privacy.py`: 頭部區域高斯模糊隱私保護（先模糊後標記）。
  - `core/head_pose.py`: 三段式頭部朝向估算 (Yaw/Pitch 角度)。
  - `core/pose_analyzer.py`: 趴睡 (SLEEPING) 與疑似使用手機 (PHONE_SUSPECTED) 姿態規則判讀。
  - `core/roi.py`: ROI 正規化多邊形與 `cv2.pointPolygonTest` 點過濾。
  - `core/camera.py`: 5 FPS 鎖定廣角攝影機讀取。

### 🧪 全系統綜合整合測試
- [x] **一鍵自動化測試套件**: `scripts/test_all_features.py` 100% 測試通過。

