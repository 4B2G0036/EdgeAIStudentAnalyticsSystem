# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)
## 版本說明 (Release Notes) - v0.4.0

- **版本號 (Version)**: `v0.4.0`
- **打包日期 (Release Date)**: 2026-08-16 17:16 (Asia/Taipei)
- **線上預覽網址 (Live URL)**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **專案名稱**: 學生專注度與異常行為分析系統 (Student Analytics System)
- **環境需求**: Python 3.10+ / MongoDB 7.0+ / HTML5 相容瀏覽器 (Chrome / Edge / Firefox)

---

## 1. 已完成之核心功能與進度摘要 (Completed Progress)

### WebCam 真實動態骨架跟隨與動態專注度評分 (`v0.4.0` 重大修復)
- [x] **MediaPipe Pose 實時 33 節點 3D 骨架關節定位**:
  - 骨架連線與關節點 100% 貼合使用者在鏡頭前的真實動作（頭部轉動、手部舉起、身體擺動、站立/坐姿）。
- [x] **動態專注度與異常姿勢規則演算法**:
  - **頭部朝向 Yaw 角度動態估算**: 依據眼睛與耳朵相對位置即時計算轉頭角度（`|Yaw| ≤ 25°` 為看黑板 +50分）。
  - **趴睡姿態警報 (`SLEEPING`)**: 偵測頭部下降低於肩膀水平高度時，即時觸發 `💤 趴睡警報！(-30分)` 並且 BBox 變更為紅色。
  - **疑似手機警報 (`PHONE_SUSPECTED`)**: 偵測低頭且手部在膝上區域活動時，觸發 `📱 疑似手機！(-50分)` 並且 BBox 變更為橘色。
  - **動態即時分數更新**: 分數 (0~100) 與 HUD 警報紀錄隨著使用者在鏡頭前的實際動作每 100ms 即時變動！

### 本機 WebCam 瀏覽器鏡頭直接存取
- [x] **HTML5 `getUserMedia` 直連鏡頭**: 支援 `[ 📷 本機 WebCam | 📡 伺服器 AI 串流 ]` 雙來源切換。

### 雲端部署與 Firebase Hosting 整合
- [x] **Firebase Hosting 發布**: 完成最新版本發布至 `https://studentanalytics-91cd1.web.app`。
