# Spec: 即時監控儀表板

## 新增需求 (ADDED Requirements)

---

### 需求 1：Streamlit 儀表板整體架構 (Dashboard Architecture)

系統「必須」(SHALL) 提供一個以 **Streamlit** 建構的本機端網頁儀表板，
**作為獨立的 Python 行程運行**，不與 FastAPI 推論後端共用同一行程，
以避免多行程競爭本機攝影機（`cv2.VideoCapture`）資源。

**儀表板頁面分頁（Tabs / Pages）**：

| 分頁名稱                    | 說明                           |
| --------------------------- | ------------------------------ |
| 📡 即時監控 (Live Monitor)  | 即時畫面 + 即時指標 + 異常通知 |
| ⚙️ 課程設定 (Session Setup) | 開始/結束課程、ROI 設定        |
| 📊 歷史記錄 (History)       | 瀏覽過去課程的統計資料         |
| 📄 報告下載 (Report)        | 觸發並下載 PDF 報告            |

**資料來源**：儀表板從不直接存取 MongoDB，所有資料**必須**透過呼叫 FastAPI 端點取得。

**FastAPI 服務基礎 URL**：由 `config.py` 的 `FASTAPI_BASE_URL` 設定，預設 `http://localhost:8000`

#### 情境：儀表板啟動前置條件

- **當 (WHEN)** 教師啟動 Streamlit 應用程式時
- **則 (THEN)** 系統在右上角顯示連線狀態指示：
  - FastAPI：🟢 已連線 / 🔴 未連線
  - 資料庫：🟢 正常寫入 / 🟡 降級寫入 (JSONL) / 🔴 斷線
    若 API 未連線則顯示「請先啟動後端服務 (api/main.py)」的提示訊息。

#### 情境：Session 啟動衝突

- **當 (WHEN)** 教師嘗試開始新課程，但 API 回傳已有進行中的 Session ID 時
- **則 (THEN)** 儀表板彈出警告視窗，提示「當前已有課程正在進行中」，並提供「結束舊課程並開始」或「加入監控」的選項。

---

### 需求 2：即時 MJPEG 影像串流顯示 (Live MJPEG Stream Display)

系統「必須」(SHALL) 透過嵌入 `<img>` 標籤或使用 `streamlit.image()` 週期性更新，
呈現來自 FastAPI `GET /api/v1/stream` 端點的 **MJPEG 影像串流**。
儀表板本身絕對不可直接呼叫 `cv2.VideoCapture`。

**畫面標記要素**：
MJPEG 串流中的每一幀影像已由 FastAPI 後端繪製以下標記：

- 每位學生的 Bounding Box（顏色依專注度：綠 ≥ 70 / 黃 40~70 / 紅 < 40）
- 每個 Bounding Box 上方顯示：`ID:{tracking_id} 分:{score}`
- 臉部區域套用高斯模糊（隱私保護，後端已處理）
- ROI 多邊形邊框（白色半透明線條）
- 異常學生（FSM 為 WARNING 或 CONFIRMED 狀態）的 Bounding Box 閃爍紅色邊框

**影像更新率**：與後端推論同步，約 **5 FPS**

#### 情境：即時監控正常運作

- **當 (WHEN)** 使用者在「即時監控」分頁，且課程已開始運行時
- **則 (THEN)**
  - 左側顯示 MJPEG 畫面（佔頁面寬度約 60%）
  - 右側顯示即時指標面板（佔 40%），包含：
    - 「全班即時平均專注度」的大數字儀表（Gauge 顯示）
    - 「看黑板人數 / 總人數」比例
    - 最近觸發的異常事件列表（最多顯示 5 筆）

#### 情境：後端斷線

- **當 (WHEN)** MJPEG 串流連線中斷超過 3 秒，或 `ClassMetrics.timestamp` 停滯超過 1.5 秒（推論心跳死鎖）時
- **則 (THEN)** 畫面區域顯示灰色背景與訊息「⚠️ 分析引擎已停擺，正在嘗試重新連線...」，並將狀態燈標記為 🔴。

#### 情境：隱私模式 (Extreme Privacy Mode)

- **當 (WHEN)** 教師開啟 `st.session_state.privacy_mode` 開關時
- **則 (THEN)** 儀表板停止拉取並顯示 MJPEG 串流影像，僅呈現去識別化的統計圖表與指標。

---

### 需求 3：即時指標儀表板 (Real-time Metrics Dashboard)

系統「必須」(SHALL) 在即時監控分頁週期性輪詢 FastAPI 的 `GET /api/v1/realtime` 端點，
並以視覺化元件即時更新班級統計指標。

**輪詢間隔**：每 **1 秒** 更新一次（Streamlit `st.rerun()` 或 `time.sleep(1)` 迴圈）

**必要視覺元件**：

| 元件                  | 資料來源                                            | 顯示內容                               |
| --------------------- | --------------------------------------------------- | -------------------------------------- |
| Metric Card（大數字） | `avg_attention_score`                               | 全班即時平均分數，帶箭頭（↑↓）顯示趨勢 |
| Progress Bar          | `students_looking_at_board / active_student_count`  | 看黑板比例                             |
| Plotly 折線圖         | 最近 5 分鐘的 `avg_attention_score`                 | 移動平均趨勢線                         |
| 異常事件警報          | `Abnormal_Events` (最新 5 筆) 或 `active_penalties` | 顏色 badge 顯示事件類型與累積人數      |

**圖表降級保護 (Graceful Degradation)**：

- 若資料點數量 < 2 時，顯示「📊 正在收集數據，請稍候...」提示，不渲染空白圖表，防止 JS 報錯。

#### 情境：全班專注度突然下降

- **前提實作**：儀表板必須在 `st.session_state.score_history` 中維護一個滾動隊列（`collections.deque(maxlen=30)`，儲存最近 30 秒每秒一筆的 `avg_attention_score`），以支援下方的趨勢比較。每次輪詢成功時將新分數追加入列。
- **當 (WHEN)** `st.session_state.score_history` 已滿 30 筆，且**最新分數**比 **30 秒前的分數**低 20 分以上時
- **則 (THEN)** 儀表板頂部顯示紅色警示橫幅「⚠️ 注意力下降警示：全班平均 {score} 分」，
  並播放 `st.warning()` 提示

---

### 需求 4：課程狀態管理 (Session Management)

系統「必須」(SHALL) 在「課程設定」分頁提供完整的課程生命週期管理表單。

**課程開始流程**：

```
[教師填寫表單]
  ↓  課程名稱（必填）
  ↓  教師姓名（必填）
  ↓  教室編號（可選）
  ↓  備注（可選）
[點擊「開始課程」按鈕]
  ↓
[後端 POST /api/v1/sessions]
  ↓  返回 session_id
[儀表板儲存 session_id 至 st.session_state]
  ↓
[自動切換至「即時監控」分頁]
```

**課程結束流程**：

```
[點擊「結束課程」按鈕（確認對話框）]
  ↓
[後端 PATCH /api/v1/sessions/{session_id}/end]
  ↓  後端開始生成 PDF 報告
[儀表板切換至「報告下載」分頁]
  ↓
[顯示「報告生成中...」轉圈動畫]
  ↓
[輪詢後端直到 PDF 就緒]
[顯示「下載 PDF 報告」按鈕]
```

#### 情境：新課程初始化

- **當 (WHEN)** 教師填寫表單並點擊「開始課程」後
- **則 (THEN)**
  1. POST 請求成功，返回 `{ "session_id": "uuid" }`
  2. `st.session_state.session_id` 儲存該 ID
  3. `st.session_state.session_active = True`
  4. 儀表板自動切換至「即時監控」分頁
  5. AI 推論後端開始向 `Attention_Metrics` 寫入資料

#### 情境：防止未結束的課程重複開始

- **當 (WHEN)** `st.session_state.session_active == True` 時
- **則 (THEN)** 「開始課程」按鈕顯示為 disabled，並提示「請先結束目前課程」

---

### 需求 5：ROI 感興趣區域設定 (ROI Configuration)

系統「必須」(SHALL) 提供在開課前讓教師於靜態攝影機畫面上，
以互動方式標記學生座位區域的功能（ROI 設定）。

**ROI 設定流程**：

1. 系統顯示攝影機當前靜態截圖（從 FastAPI 取得單幀畫面）
2. 教師在圖片上透過 **Streamlit Canvas Component**（`streamlit-drawable-canvas` 套件）
   繪製多邊形，標記全班座位區域
3. 點擊「確認 ROI」後，多邊形座標正規化（值域 [0.0, 1.0]）並存入儀表板設定
4. 開始課程時，ROI 座標作為 `roi_polygon` 一起傳送至後端的 `Classes_Session` 記錄

**ROI 顯示**：

- 在即時監控畫面上以白色半透明線框標示 ROI 邊界（後端已疊加於 MJPEG 畫面）

#### 情境 A：教師設定 ROI

- **當 (WHEN)** 教師在「課程設定」分頁的靜態截圖上繪製多邊形後點擊「確認 ROI」時
- **則 (THEN)**
  1. 將 Canvas 輸出的像素座標 $(x_p, y_p)$ 轉換為正規化座標：$x_{norm} = x_p / CanvasWidth, y_{norm} = y_p / CanvasHeight$。
  2. 將正規化頂點列表 `[[x1, y1], ...]` 儲存至 `st.session_state.roi_polygon`。
  3. 並在畫面上疊加顯示綠色確認線框。

#### 情境 B：跳過 ROI 設定（使用全畫面）

- **當 (WHEN)** 教師未設定 ROI 直接點擊「開始課程」時
- **則 (THEN)** `roi_polygon` 設為 `[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]`（全畫面矩形），
  系統顯示警告「⚠️ 未設定 ROI，將分析全畫面（可能包含非學生區域）」

#### 情境 C：ROI 設定錯誤或 API 異常

- **當 (WHEN)** 教師點擊「確認 ROI」但 Canvas 未偵測到多邊形，或 API 回傳錯誤時
- **則 (THEN)** 儀表板顯示錯誤訊息「❌ ROI 設定失敗，請確保已繪製封閉多邊形」，不儲存任何座標。

---

### 需求 6：歷史記錄瀏覽 (History Browsing)

系統「應」(SHOULD) 在「歷史記錄」分頁提供過去課程的瀏覽功能。

**必要功能**：

- 表格列出所有 `Classes_Session` 記錄（課程名稱、日期、時長、平均專注度）
- 點擊任一課程，展開顯示該課程的：
  - 全班專注度折線圖（查詢 `Attention_Metrics`）
  - 異常事件列表（查詢 `Abnormal_Events`）
- 提供「重新下載 PDF 報告」按鈕

#### 情境：瀏覽歷史課程

- **當 (WHEN)** 教師在「歷史記錄」分頁點擊某一課程行時
- **則 (THEN)** 展開顯示該課程的 Plotly 折線圖（X 軸：時間，Y 軸：平均分）
  與異常事件詳細列表。
  **時區規範**：所有顯示之時間點必須依據 `config.TIMEZONE` 進行本地化（例如 `Asia/Taipei`）。

---

## 非功能性需求 (Non-functional Requirements)

- **UI 響應時間**：儀表板頁面初始載入 ≤ 3 秒
- **圖表更新延遲**：從 FastAPI 返回資料到圖表更新完成 ≤ 1 秒
- **套件**：需安裝 `streamlit`, `streamlit-drawable-canvas`, `plotly`, `requests`, `pillow`
- **相容性**：儀表板以 `streamlit run dashboard/app.py` 啟動，
  支援 Chrome / Firefox / Edge 最新版本瀏覽器
- **安全性**：儀表板不加入身份驗證（假設僅限教師本機存取）。
- **速率限制 (Rate Limiting)**：FastAPI 必須對 `/api/v1/report` 與 `/api/v1/sessions` 實作速率限制（如 5 次/分鐘），防止惡意或手誤導致的資源溢出。
