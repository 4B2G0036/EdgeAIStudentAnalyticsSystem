# Spec: 視覺AI核心

## 新增需求 (ADDED Requirements)

---

### 需求 1：即時特徵擷取 (Real-time Feature Extraction)

系統「必須」(SHALL) 以嚴格鉗制的幀率（**上限 5 FPS**）處理攝影機輸入，
單次 YOLO-Pose 前向傳播同時抓取全班所有人的骨架節點，
並在任何資料離開此模組前，完成臉部模糊與 PII 去除。
原始含有可識別人臉的影像**絕對不可**寫入硬碟或傳遞至資料庫。

#### 情境 A：正常課堂處理迴圈

- **當 (WHEN)** `core/camera.py` 從 `cv2.VideoCapture` 讀取到一幀畫面，
  且距離上一次推論已超過 200 毫秒（5 FPS 限制）時
- **則 (THEN)**
  1. 執行 YOLOv8-Pose（或 YOLOv11-Pose）ONNX 單次推論，取得全班骨架節點列表與人臉/頭部 BBox
  2. 依據推論輸出的頭部 BBox 區域（若無 BBox 則以頭部節點中心擴張區域），對原始幀套用高斯模糊（kernel ≥ 31×31）產生隱私版影像
  3. 將含有模糊遮罩的推論後影像（**標籤繪製順序**：先進行 PII 模糊 -> 再於模糊區域上疊加 ID 與分數標籤，確保 UI 資訊清晰）與純節點向量（用於評分），
     封裝為 `FrameResult` 物件往下傳遞
  4. **注意**：節點座標（`keypoints`）取自原始推論輸出，模糊僅影響影像像素，不影響骨架數據精準度

#### 情境 B：幀率超過上限的保護

- **當 (WHEN)** 上游攝影機原始幀率超過 5 FPS 時
- **則 (THEN)** 主迴圈在每次推論後，必須持續以 `cap.read()` **主動讀取並丟棄**攝影機緩衝中的多餘幀，直到距離上一次推論已超過 200 毫秒（5 FPS 節流間隔），再執行下一次推論。
  - ⚠️ **禁止**使用 `time.sleep()` 代替主動讀幀：sleep 期間攝影機 Buffer 持續累積，恢復後會讀取到過時幀，導致推論使用非即時畫面。

---

### 需求 2：ONNX 輕量化推論 (ONNX Inference)

系統「必須」(SHALL) 以 `.onnx` 格式搭配 `onnxruntime`（或 `onnxruntime-gpu`）
執行所有深度學習模型，禁止在推論時期動態載入 PyTorch 或 TensorFlow 框架。

**允許的模型**：

- `yolov8n-pose.onnx`（速度優先，適用低階 GPU）
- `yolov8m-pose.onnx`（平衡精準度，適用中階 GPU）
- `yolov11n-pose.onnx`（新一代架構，如硬體支援）

**模型輸入規格**：

- 輸入解析度：預設 `640 × 640`（可於 `config.IMG_SZ` 調整，支援 `480`~`1280`）。
- **座標換算規範**：推論輸出之座標必須考慮 Letterbox 填充（Padding），正確換算回原始影像解析度比例。
- 輸入格式：`float32 [1, 3, H, W]`，BGR 轉 RGB，值域 `[0.0, 1.0]`

#### 情境 A：引擎啟動

- **當 (WHEN)** `core/inference.py` 的 `InferenceEngine.load()` 被呼叫時
- **則 (THEN)** 系統只透過 `onnxruntime.InferenceSession` 載入指定 `.onnx` 檔案；
  若 GPU 執行提供者 (`CUDAExecutionProvider`) 不可用，自動 fallback 至 `CPUExecutionProvider`，
  並於日誌輸出 `WARNING: 使用 CPU 推論，效能可能不足`。
  **日誌規範**：啟動後必須輸出當前啟用的 Provider 名稱與 `onnxruntime.get_device()` 之詳情。

#### 情境 B：不允許的推論方式

- **當 (WHEN)** 程式碼中出現 `from ultralytics import YOLO` 並直接呼叫 `model.predict()` 時
- **則 (THEN)** 此為架構違規（Tech Debt），應改為透過 ONNX 推論路徑執行

---

### 需求 3：多目標追蹤 (Multi-Object Tracking with ByteTrack)

系統「必須」(SHALL) 整合 ByteTrack 演算法，為每個偵測到的人體骨架分配一個穩定的
`tracking_id`（整數），並在連續畫面間維持 ID 的一致性，允許最多 **30 幀**的遮擋容忍。

**資料結構**：

```python
@dataclass
class TrackedPerson:
    tracking_id: int
    bbox: tuple[float, float, float, float]  # [x1, y1, x2, y2] 正規化座標 (0.0~1.0)
    keypoints: np.ndarray  # shape: (17, 3) — (x, y, confidence) 原始影像像素座標
    confidence: float      # YOLO 偵測信心分數
    in_roi: bool           # 是否在 ROI 區域內
```

#### 情境 A：學生被遮擋後重新出現

- **當 (WHEN)** `tracking_id = 5` 的學生因站起身或被遮擋消失，於 **30 幀以內**（即 ≤ 6 秒 @ 5FPS）重新出現時
- **則 (THEN)** ByteTrack 繼續分配同一個 `tracking_id = 5`，
  確保 FSM 的連續動作分析狀態不被中斷

#### 需求 3.1：ID 漂移防護 (ID Drift Protection)

- **當 (WHEN)** ByteTrack 分配一個新 `tracking_id` 時，若該骨架與前一幀消失的某 ID 之 Bbox IoU > 0.8
- **則 (THEN)** 系統「應」(SHOULD) 嘗試繼承該消失 ID 的狀態，防止 FSM 被不必要地重置。

---

### 需求 4：頭部朝向估計 (Head Pose Estimation)

系統「必須」(SHALL) 基於 YOLO-Pose 輸出的面部與肩部骨架節點，
計算每位學生的頭部朝向（Yaw / Pitch 角度），並根據節點信心分數自動切換計算策略。

**節點信心閾值**：所有關節點 confidence < **0.45** 視為無效，不納入計算。

**計算策略優先順序**：

| 優先级    | 條件                                           | 使用節點                                   | 方法                                  |
| --------- | ---------------------------------------------- | ------------------------------------------ | ------------------------------------- |
| 1（最高） | nose, left_eye, right_eye 均有效 (conf ≥ 0.45) | 0, 1, 2                                    | 基於五官相對位置的幾何 Yaw/Pitch 估算 |
| 2         | 只有耳朵有效（學生背對鏡頭） (conf ≥ 0.45)     | 3(left_ear), 4(right_ear) + 5,6(shoulders) | 耳肩幾何輔助演算法                    |
| 3（最低） | 僅有肩部有效 (conf ≥ 0.45)                     | 5, 6                                       | 肩線水平角估算 Yaw（Pitch 設為 0）    |

**朝向判斷閾值（看黑板條件）**：

- `|Yaw| ≤ 30°` 且 `|Pitch| ≤ 25°` → 視為「看向黑板方向」
- 超出上述範圍 → 視為「未看黑板」

#### 情境 A：學生正面朝向攝影機（五官清晰）

- **當 (WHEN)** nose, left_eye, right_eye 的 confidence 均 ≥ 0.45 時
- **則 (THEN)** 使用這三個節點進行向量分析計算，輸出投影後的 Yaw / Pitch 角度

#### 情境 B：學生背對鏡頭（眼鼻節點噪音過多）

- **當 (WHEN)** nose, left_eye, right_eye 的 confidence 均 < 0.45，
  但 left_ear, right_ear 的 confidence ≥ 0.45 時
- **則 (THEN)** 自動切換至耳肩幾何輔助計算，
  並於日誌記錄 `DEBUG: tracking_id={id} 使用耳肩備用演算法`

---

### 需求 5：異常姿態推導 (Abnormal Pose Deduction)

系統「必須」(SHALL) 基於骨架節點的相對幾何位置判定兩種異常狀態，
完全不依賴實體物件（如手機）的視覺辨識。

#### 5.1 趴睡判定 (Sleeping Detection)

**觸發條件**（以下任一成立）：

- 肩頸 Y 距離過短：`abs(avg_shoulder_y - nose_y) < SLEEPING_RATIO * bbox_height`
  - `SLEEPING_RATIO = 0.20`（可於 `config.py` 調整）
- 頭部 Pitch > 60°（頭極度向下低垂）
- 兩肩 Y 座標之差 > bbox_height × 0.3（身體明顯側傾趴下）

**輸出標記**：`PoseFlag.SLEEPING`

##### 情境：趴睡觸發

- **當 (WHEN)** `abs(avg_shoulder.y - nose.y) / bbox_height < SLEEPING_RATIO` 時
- **則 (THEN)** 對該 `tracking_id` 發出 `PoseFlag.SLEEPING` 標記，
  傳遞至評分引擎，由 FSM 判斷是否持續超過 3 秒

#### 5.2 疑似使用手機判定 (Phone Usage Detection)

**觸發條件**（以下兩者同時成立）：

1. 手腕有效且過低：
   - 條件：`left_wrist.conf > 0.45` 且 `left_wrist.y > (avg_shoulder.y + avg_hip.y) / 2`
   - 或：`right_wrist.conf > 0.45` 且 `right_wrist.y > (avg_shoulder.y + avg_hip.y) / 2`
2. 頭部重度下傾：`head_pitch < -35°`（Pitch 負值代表向下）

**輸出標記**：`PoseFlag.PHONE_SUSPECTED`

##### 情境：疑似滑手機

- **當 (WHEN)** （`left_wrist.conf > 0.45` 且 `left_wrist.y > (avg_shoulder.y + avg_hip.y) / 2`）
  **或** （`right_wrist.conf > 0.45` 且 `right_wrist.y > (avg_shoulder.y + avg_hip.y) / 2`）
  且 `head_pitch < -35°` 時
- **則 (THEN)** 對該 `tracking_id` 發出 `PoseFlag.PHONE_SUSPECTED` 標記

> ⚠️ **注意**：手腕條件為 **OR**（任一手腕满足即可）而非 AND，此跟觸發條件正文一致。若用 `min(left_wrist.y, right_wrist.y) > threshold`，則必須兩手腕同時超出（AND 語意），將大幅漏失單手持機事件，實作上必須分別判斷每個手腕。

---

### 需求 6：感興趣區域過濾 (ROI Filtering)

系統「必須」(SHALL) 依照儀表板設定的 ROI 多邊形座標，
過濾所有不在座位區域內的骨架，避免將走廊路人或講台教師納入分析。

**ROI 格式**：正規化多邊形頂點列表 `[[x1, y1], [x2, y2], ...]`，值域 `[0.0, 1.0]`

**過濾邏輯**：

1. 取得骨架 Bounding Box 中心點之正規化座標 `(cx, cy)`
2. 使用 `cv2.pointPolygonTest()` 判斷該中心點是否落於 `roi_polygon` 內。
3. 若中心點不在多邊形內，則該骨架不列入統計。

#### 情境：教師站在 ROI 外

- **當 (WHEN)** YOLO 偵測到一個骨架，其 bbox 中心點不在 ROI 多邊形內時
- **則 (THEN)** 該骨架的 `TrackedPerson.in_roi = False`，
  評分引擎跳過此 `tracking_id` 的所有計算

---

## 非功能性需求 (Non-functional Requirements)

- **效能**：視覺核心主迴圈（從讀幀到輸出 `FrameResult`）單次執行時間 ≤ **200 毫秒**（即 5 FPS）
- **記憶體**：單一畫面處理峰值記憶體增量 ≤ **200 MB**
- **錯誤處理**：攝影機連線中斷時，主迴圈以 1 秒間隔重試，最多 10 次後拋出 `CameraConnectionError`。
- **通訊規範 (CORS)**：FastAPI 進入點 (`api/main.py`) **必須** 配置 `CORSMiddleware`，並將 `config.CORS_ORIGINS`（預設包含 `http://localhost:8501`）列入允許清單，確保微服務架構通訊順暢。
- **優雅停機 (Graceful Shutdown)**：主迴圈必須捕獲 `KeyboardInterrupt` 或 `SIGTERM` 信號。在結束進程前，必須呼叫 `Queue.join()` 確保所有偵測到的資料已完成批次寫入。
