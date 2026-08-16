# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)

## 版本說明 (Release Notes) - v0.5.0

- **版本號 (Version)**: `v0.5.0`
- **打包日期 (Release Date)**: 2026-08-16 17:51 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ (已通過 8.3.7 測試) / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 📷 WebCam 實時監控與 UI 修復
- [x] **WebCam 串流崩潰與重複函數修復**: 清除重複 JavaScript 函數、修正初始 UI 遮罩顯示邏輯與 DOM 就緒初始化，確保 HTML5 `getUserMedia` WebCam 開啟即用。
- [x] **Firebase Hosting 發布**: 更新版本並完成靜態頁面發布。

### 🗄️ 基礎設施與 MongoDB 8.3.7 整合
- [x] **MongoDB 8.3.7 服務安裝**: 本機服務成功安裝與開機自動啟動。
- [x] **Time Series Collection 驗證**: 完成 7.0+ 原生 Time Series Collection 建置、寫入與自動過期 TTL 測試。
- [x] **`.env` 環境組態更新**: 自動切換 `MONGO_URI=mongodb://127.0.0.1:27017`。

### 🤖 邊緣 AI 模型匯出 (YOLO-Pose ONNX)
- [x] **YOLOv8n-Pose (輕量主用)**: 匯出 `models/yolov8n-pose.onnx` (12.9 MB)，CPU 單次推論耗時 **21ms** (≤ 200ms 標準)。
- [x] **YOLOv8m-Pose (高精度備用)**: 匯出 `models/yolov8m-pose.onnx` (101.2 MB)，CPU 單次推論耗時 **103ms** (≤ 200ms 標準)。
- [x] **自動化環境驗證腳本**: 提供 `scripts/verify_setup.py` 一鍵檢測 MongoDB 與 ONNX 模型狀態。

