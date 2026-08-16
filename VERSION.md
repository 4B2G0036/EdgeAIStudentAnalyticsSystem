# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.4.1

- **版本號 (Version)**: `v0.4.1`
- **打包日期 (Release Date)**: 2026-08-16 17:19 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### 免卡頓、即時視覺動態 AI 人體跟隨與動態扣分 (`v0.4.1` 重大修復)
- [x] **解決 MediaPipe 網路資產下載卡死**:
  - 改採 **非同步背景載入機制** + **高速零延遲 Canvas 視覺動態追蹤引擎**。
  - 開啟 WebCam 後，畫面 **零秒等待** 立即鎖定目標人像與動態骨架！
- [x] **真實動作即時感應與動態扣分**:
  - **人像動態擺動跟隨**: BBox 與骨架節點會跟隨您在鏡頭前的左右移動與前後俯仰即時位移。
  - **轉頭偏離黑板動態扣分 (Yaw 角度)**: 轉頭角度超出 22° 時，分數即時扣減 30分 並且跳出黃色警報。
  - **低頭/趴睡動態扣分 (`SLEEPING`)**: 當頭部相對於肩膀下沉俯仰時，觸發 `💤 趴睡警報！(-45分)` 且 BBox 轉為紅色！

### 本機 WebCam 瀏覽器鏡頭直接存取
- [x] **HTML5 `getUserMedia` 直連鏡頭**: 支援 `[ 📷 本機 WebCam | 📡 伺服器 AI 串流 ]` 雙來源切換。

### 雲端部署與 Firebase Hosting 整合
- [x] **Firebase Hosting 發布**: 完成最新修復版發布至 `https://studentanalytics-91cd1.web.app`。
