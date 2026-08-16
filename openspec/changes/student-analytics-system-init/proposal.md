## 為什麼需要這項變更 (Why)

目前的教學環境缺乏客觀、量化的工具來衡量學生的參與度與教學方法的有效性。
教師無法同時追蹤全班所有學生的注意力狀態，也缺少課後量化紀錄作為教學改善的依據。

本專案旨在建立一個**「邊緣 AI 學生專注度分析系統」**(Edge AI Student Analytics System)，
利用架設於教室中上方的廣角 Webcam，透過電腦視覺技術自動評估學生的注意力（頭部角度、姿態），
即時識別異常行為（趴睡、桌面下疑似滑手機），同時以骨架特徵取代人臉識別，確保不侵犯學生隱私。

---

## 變更內容 (What Changes)

### 技術選型決策（為何不採用臉部識別）

廣角俯瞰鏡頭下，學生人臉像素可能僅有 20×20 px，傳統近場臉部情緒辨識（DeepFace、MediaPipe Face）
在此場景下幾乎完全失效。本系統全面改用 `YOLO-Pose` 骨架節點幾何，原因如下：

- **效能**：單一 YOLO-Pose ONNX 模型在一次前向傳播中偵測全班 40+ 人骨架，
  MediaPipe 需為每人獨立執行，40 次推論在邊緣設備上必然過載
- **可靠性**：即使臉部模糊或背對鏡頭，骨架的肩頸角度仍可推算頭部朝向
- **隱私**：骨架節點是匿名的幾何數據，完全無法反推個人身份

### 實作範疇

- 實作**邊緣 AI 視覺層**（`core/`）：全面採用 `YOLOv8-Pose`（或 `YOLOv11-Pose`）+ `ByteTrack`，
  以 ONNX Runtime 加速推論，硬性鎖定 5 FPS 運算上限，保護邊緣硬體
- 實作**邏輯與資料層**（`engine/`, `api/`, `database/`）：
  定義評分公式（看黑板 +50 分 + 坐姿 +50 分；疑似手機 -50、趴睡 -30），
  以有限狀態機（FSM）進行連續行為分析（3 秒雜訊過濾 / 10 秒確認閾值，並具備斷電重啟自癒能力），
  透過 FastAPI 非同步批次寫入（每批 500 筆）MongoDB Time Series 集合，並以 TTL 索引自動維護。
- 實作**展示層**（`dashboard/`, `report/`）：
  使用 Streamlit 消費 FastAPI 的 MJPEG 影像串流與 REST 數據 API，
  完全解耦推論後端與前端對本機攝影機的資源競爭；加上極致隱私模式保護；
  ReportLab 自動生成 A4 PDF 課後報告（經每分鐘降採樣優化），確保 I/O 不超載。

---

## 系統能力 (Capabilities)

### 新增能力 (New Capabilities)

- **`vision-ai-core`**：
  管理廣角攝影機串流（5 FPS）、YOLO-Pose ONNX 單次多人推論、
  ByteTrack 追蹤 ID 管理（最大 30 幀遮擋容忍，含 ID 漂移防護），
  三段式頭部朝向估算（五官優先 → 耳肩備用 → 僅肩線，嚴格過濾 confidence < 0.45 節點），
  骨架幾何異常判定（趴睡、疑似手機），
  ROI 多邊形正規化過濾、推論後隱私模糊（先套用高斯模糊，再繪製標籤）、
  優雅停機 (Graceful Shutdown) 確保資料不遺失。

- **`attention-scoring-engine`**：
  每幀專注度評分（0~100），FSM 連續動作分析（NORMAL → PENDING → WARNING → CONFIRMED → TERMINATED），
  Trace ID 跨模組追蹤審計，時序平滑（30 點滾動平均，並同步記憶體銷毀），
  班級整體 `ClassMetrics` 聚合，且由 `GlobalSafeStorage` 執行緒安全導出。

- **`realtime-dashboard`**：
  Streamlit 4 分頁介面（即時監控、課程設定、歷史記錄、報告下載），
  呈現 MJPEG 串流（每秒更新一次指標）、極致隱私模式與 AI 心跳監控，
  `streamlit-drawable-canvas` 互動式 ROI 多邊形標記（自動正規化），
  課程生命週期管理（開始/結束 Session），圖表降級保護，支援 `Asia/Taipei` 本地時區。

- **`data-and-reporting`**：
  MongoDB 三集合（`Classes_Session`、`Attention_Metrics` 時序附 TTL 索引、`Abnormal_Events`），
  非同步批次寫入 (每批 500 筆)、API 速率限制與 `QUEUE_FLUSH` 排空阻塞，
  ReportLab A4 PDF 自動排版（降採樣折線圖 + Sticky Header + 支援中文字體）。

### 修改的能力 (Modified Capabilities)

- (無，本系統為全新開發)

---

## 影響範圍 (Impact)

- **程式碼/架構**：引入 `core/`, `engine/`, `api/`, `database/`, `dashboard/`, `report/` 六大模組，
  加上 `models/`（ONNX 檔案）、`reports/`（PDF 輸出目錄）、`config.py`、`.env`
- **相依套件**：`ultralytics`（用於匯出 ONNX）、`onnxruntime-gpu`、`opencv-python`、
  `fastapi`、`uvicorn`、`streamlit`、`streamlit-drawable-canvas`、`pymongo`、
  `pandas`、`matplotlib`、`plotly`、`reportlab`、`python-dotenv`
- **資料庫**：本機 MongoDB 7.0+（需支援 Time Series Collection）
- **硬體需求**：具獨立顯卡（建議 ≥ GTX 1060）之電腦、廣角 Webcam（建議 ≥ 90° 視角）
- **隱私合規**：原始影像不儲存，僅保留骨架向量與模糊後的 MJPEG 串流幀
