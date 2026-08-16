# Spec: 數據與報表

## 新增需求 (ADDED Requirements)

---

### 需求 1：MongoDB 持久化儲存層 (MongoDB Persistence Layer)

系統「必須」(SHALL) 在啟動時建立與本機（或可設定的遠端）MongoDB 實例的連線，
並確保三個核心集合（Collection）以正確的設定存在。
若集合不存在，系統「必須」(SHALL) 自動建立，並套用指定的索引策略。

**連線設定（存放於 `.env` 或 `config.py`）**：

- `MONGO_URI`：預設 `mongodb://localhost:27017`
- `MONGO_DB_NAME`：預設 `student_analytics`

**三個核心集合**：

#### Collection 1：`Classes_Session`（課程元數據）

```json
{
  "_id": "ObjectId（自動生成）",
  "session_id": "string（UUID v4，系統生成）",
  "class_name": "string（例如：計算機概論）",
  "teacher": "string",
  "room": "string",
  "started_at": "ISODate",
  "ended_at": "ISODate | null",
  "student_count": "int（該 Session 中單一幀偵測到的最大並行在線人數）",
  "roi_polygon": "[[float, float], ...]（正規化多邊形頂點）",
  "notes": "string（可選，教師備注）"
}
```

- 索引：`session_id` 建立唯一索引；`class_name + teacher + started_at` 建立複合唯一索引防止重複啟動。

#### Collection 2：`Attention_Metrics`（**必須**設定為 Time Series Collection）

```json
{
  "timestamp": "ISODate（timefield，必須是 UTC 時間）",
  "metadata": {
    "session_id": "string",
    "tracking_id": "int"
  },
  "attention_score": "float（0.0 ~ 100.0）",
  "head_yaw": "float（角度，-180 ~ 180）",
  "head_pitch": "float（角度，-90 ~ 90）",
  "is_looking_at_board": "bool",
  "pose_flags": "string[]（例如：['phone_suspected', 'sleeping']，可為空）",
  "fsm_state": "string（NORMAL | PENDING | WARNING | CONFIRMED | TERMINATED）"
}
```

- **Time Series 設定**：
  ```python
  db.create_collection("Attention_Metrics", timeseries={
      "timeField": "timestamp",
      "metaField": "metadata",
      "granularity": "seconds"
  }, expireAfterSeconds=RETENTION_DAYS * 86400)  # 須對應 config.RETENTION_DAYS，預設 365 天
  ```
- granularity：`seconds`（資料點間隔約 0.2 秒）
- **索引優化**：必須在 `metadata.session_id` 與 `timestamp` 建立複合索引，以優化歷史時序圖表的查詢速度。

#### Collection 3：`Abnormal_Events`（異常事件記錄）

```json
{
  "_id": "ObjectId",
  "session_id": "string",
  "tracking_id": "int",
  "event_type": "string（phone_suspected | sleeping）",
  "started_at": "ISODate",
  "updated_at": "ISODate",
  "ended_at": "ISODate | null（null 代表事件仍在持續）",
  "duration_seconds": "float（ended_at - started_at，null 時為動態計算）",
  "peak_pitch": "float（事件期間偏離水平面最遠之原始 Pitch 值）",
  "confirmed": "bool（FSM 是否已進入 CONFIRMED 狀態）",
  "ended_reason": "string | null（null 代表仍在持續；結案時必填，允許值：'recovered' | 'server_restart' | 'tracking_lost'）"
}
```

**`peak_pitch` 更新策略**：事件首次寫入 DB 後（FSM 進入 `CONFIRMED` 時），每一幀若偵測到的 `abs(head_pitch)` 大於目前記錄值，系統「應」使用 `update_one({"_id": event_id}, {"$max": {"peak_pitch": abs(current_pitch)}})` 更新。`Abnormal_Events` 為普通 Collection（非 Time Series），支援 `update` 操作，此為正確行為。

- 索引：`session_id + started_at` 建立複合索引

#### 情境 A：系統啟動時的初始化

- **當 (WHEN)** FastAPI 應用程式或任何需要 DB 的服務啟動時
- **則 (THEN)**
  1. 嘗試連線 MongoDB，失敗則拋出 `DatabaseConnectionError` 並阻止服務啟動
  2. 檢查三個集合是否存在，不存在則建立（含 Time Series 設定與索引）
  3. 日誌輸出 `INFO: MongoDB 連線成功，資料庫：{db_name}`

#### 情境 B：集合已存在時的冪等性（Idempotency）

- **當 (WHEN)** 系統重啟，集合已存在時
- **則 (THEN)** 系統跳過建立步驟（不清除既有資料），僅驗證連線可用性

---

### 需求 2：高頻率時序資料批次寫入 (Batch Write for High-frequency Metrics)

系統「必須」(SHALL) 使用**批次（Batch）非同步插入**策略，
將 5 FPS 的高頻指標累積後定期寫入 MongoDB，避免每幀一次寫入造成 I/O 瓶頸。

**批次寫入規格**：

- 批次大小：**500 個資料點**（全班混合全局緩衝，即每 500 筆資料寫入一次）
- 觸發條件：累積滿 **500 筆** 或 距上次寫入超過 **3 秒**，兩者以先到者為準。
- 實作方式：`pymongo.collection.insert_many(batch_list)`（非同步包裝）
- 錯誤處理：批次寫入失敗時，記錄日誌並**保留該批次**重試，最多 3 次

**非同步架構要求**：

- DB 寫入必須在獨立的 `asyncio.Task` 中執行，不可阻塞推論或儀表板渲染
- 使用 `asyncio.Queue` 作為推論結果與寫入任務之間的緩衝區

```python
# 概念性架構（非最終程式碼）
BATCH_SIZE = 500          # 來自 config.DB_BATCH_SIZE
FLUSH_INTERVAL = 3.0     # 秒，超時強制 Flush

inference_queue: asyncio.Queue[AttentionMetricDoc]

async def db_writer_worker():
    batch: list[AttentionMetricDoc] = []
    while True:
        timed_out = False
        try:
            # 等待一筆資料，最多等 FLUSH_INTERVAL 秒
            doc = await asyncio.wait_for(
                inference_queue.get(),
                timeout=FLUSH_INTERVAL
            )
            batch.append(doc)
        except asyncio.TimeoutError:
            # 超過 3 秒無新資料 → 設旗標，下方判斷強制 Flush
            timed_out = True

        # 數量觸發（500 筆）或超時觸發（3 秒無新資料且有待寫入資料）
        if len(batch) >= BATCH_SIZE or (timed_out and len(batch) > 0):
            for attempt in range(3):  # 最多重試 3 次
                try:
                    await async_insert_many("Attention_Metrics", batch)
                    batch.clear()
                    break
                except Exception as e:
                    if attempt == 2:
                        # 3 次均失敗 → 寫入本地備份
                        append_to_jsonl_backup(batch)
                        batch.clear()
```

#### 情境 A：正常課堂中的批次寫入

- **當 (WHEN)** 全域緩衝區（Global Buffer）累積滿 500 筆資料時
- **則 (THEN)** 非同步寫入任務呼叫 `insert_many` 一次性插入 500 筆，大幅降低磁碟 I/O 持續寫入壓力。

#### 情境 B：強制 Flush（課程即將結束）

- **當 (WHEN)** 教師在儀表板點擊「結束課程」且佇列中還有未滿批次的資料時
- **則 (THEN)** 立即 Flush 所有剩餘資料，確保最後幾秒的記錄不遺失

---

### 需求 3：課後 PDF 分析報告自動生成 (Automated PDF Report Generation)

系統「必須」(SHALL) 在課程結束時，從 MongoDB 查詢當前課程的所有資料，
使用 **ReportLab** 自動排版並輸出 A4 格式的 PDF 分析報告。
必須載入並使用 `NotoSansTC-Regular.ttf` 字體以正確渲染中文。

**報告內容結構（A4 單份報告）**：

1. **封面**
   - 標題：「學生專注度與異常行為分析報告」
   - 課程名稱、教師、教室、日期、分析時段（started_at ~ ended_at）
   - 分析學生數量

2. **全班整體摘要（Executive Summary）**
   - 課程時長（分鐘）
   - 全班平均專注度分數
   - 最高 / 最低專注度時段（時間點）
   - 異常事件總次數（趴睡 / 疑似手機個別計數）

   - X 軸：課程進行時間（分鐘）
   - Y 軸：全班平均專注度分數（0-100）
   - **數據處理**：必須進行每分鐘一次的降採樣 (Downsampling) 取得平均值，以提升 PDF 渲染效能與可讀性。
   - 使用 Matplotlib/Plotly 生成圖像後嵌入 PDF

3. **異常行為分佈圖**
   - 圓餅圖：趴睡 vs 疑似手機的次數佔比
   - 長條圖：異常事件發生的時間分佈（每 5 分鐘一個區間）

4. **個別學生摘要表格**
   - 欄位：`tracking_id`、平均分數、看黑板比例（%）、異常事件次數、最長異常持續時間
   - **排版要求**：若表格跨頁，必須自動於新頁次首行重複顯示欄位標題。
   - **時區處理**：報表內所有時間標註必須依據 `config.TIMEZONE` 進行本地化轉換（預設 `Asia/Taipei`）。

5. **建議（Recommendations）**
   - 依規則自動生成文字建議
     - 若全班平均 < 60：「建議調整課堂節奏或互動頻率」
     - 若趴睡事件率 > 10%（佔總學生人數比例）：「建議注意課堂環境（光線/溫度）」

**PDF 輸出位置**：

- 路徑：`./reports/{session_id}_{class_name}_{date}.pdf`
- 同時透過 FastAPI `/api/v1/report/{session_id}` 端點提供下載

**報告觸發條件**：

- 方式 A（自動）：儀表板點擊「結束課程」後由後端自動生成
- 方式 B（手動）：呼叫 GET `/api/v1/report/{session_id}` 觸發生成

#### 情境 A：自動觸發報告生成

- **當 (WHEN)** 教師在 Streamlit 儀表板點擊「結束課程 (End Session)」時
- **則 (THEN)**
  1. FastAPI 接收到 `PATCH /api/v1/sessions/{session_id}/end` 請求
  2. 後端更新 `Classes_Session.ended_at`。
  3. **強制排空佇列 (AWAIT_QUEUE_FLUSH)**：系統必須等待 `asyncio.Queue` 完全排空並確認所有批次均已寫入 MongoDB 後，方可啟動 `generate_report`。為防止死鎖，此等待「必須」加上 `AWAIT_FLUSH_TIMEOUT` (預設 10 秒) 的超時保護；若超時則紀錄 `WARNING` 狀態、強制放棄剩餘快取並繼續產生報告。
  4. 觸發後台任務 `generate_report(session_id)` 非同步執行。
  5. Streamlit 顯示「資料排空與報告生成中，請稍候...」並輪詢狀態。
  6. 報告完成後返回 PDF 下載連結。

#### 情境 B：手動下載歷史報告

- **當 (WHEN)** 使用者請求一個已完成但無 PDF 的歷史 session 時
- **則 (THEN)** 系統重新從 DB 查詢並生成 PDF，回傳 `Content-Type: application/pdf`

### 需求 4：資料保存與自動清理 (Data Retention & Pruning)

系統「應」(SHOULD) 具備基礎的資料清理機制，防止資料庫體積隨著學期累積而無限膨脹。

- **清理對象**：`Attention_Metrics` 集合中的原始時序資料。
- **保留策略**：
  - 原始時序資料：預設保留 **365 天** (可於 `config.RETENTION_DAYS` 設定)。
  - 摘要資料：`Classes_Session` 與 `Abnormal_Events` 永久保留，不自動刪除。
- **執行方式**：
  1. 系統啟動時以 `delete_many({"timestamp": {"$lt": cutoff}})` 執行一次清理任務（清除 TTL 索引建立前的歷史殘留資料）。
  2. **TTL 自動過期設定**：`Attention_Metrics` 是 MongoDB Time Series Collection，**不支援**以 `create_index("timestamp", expireAfterSeconds=...)` 方式建立 TTL 索引。正確做法是在建立 Collection 時直接指定 `expireAfterSeconds`：
     ```python
     db.create_collection("Attention_Metrics", timeseries={
         "timeField": "timestamp",
         "metaField": "metadata",
         "granularity": "seconds"
     }, expireAfterSeconds=RETENTION_DAYS * 86400)
     ```
  3. 若 Collection 已存在（重啟場景），可使用 `collMod` 命令修改 `expireAfterSeconds` 值：
     ```python
     db.command("collMod", "Attention_Metrics",
                expireAfterSeconds=RETENTION_DAYS * 86400)
     ```

### 需求 5：資料查詢 API (Data Query API)

FastAPI「必須」(SHALL) 提供以下資料查詢端點，供 Streamlit 儀表板即時拉取統計數據。

| HTTP 方法 | 端點路徑                        | 說明                                                 |
| --------- | ------------------------------- | ---------------------------------------------------- | --------- |
| `GET`     | `/api/v1/sessions`              | 列出所有課程記錄（支援 `limit`, `offset` 參數）      |
| `POST`    | `/api/v1/sessions`              | 建立新課程（返回 `session_id`）                      |
| `PATCH`   | `/api/v1/sessions/{id}/end`     | 結束課程                                             |
| `GET`     | `/api/v1/sessions/{id}/metrics` | 時序分數。參數：`start_ts` (float), `end_ts` (float) |
| `GET`     | `/api/v1/sessions/{id}/events`  | 異常事件列表。參數：`type` (phone_suspected          | sleeping) |
| `GET`     | `/api/v1/sessions/{id}/summary` | 查詢課程統計摘要                                     |
| `GET`     | `/api/v1/report/{id}`           | 生成並下載 PDF 報告                                  |
| `GET`     | `/api/v1/stream`                | MJPEG 即時影像串流                                   |
| `GET`     | `/api/v1/realtime`              | 每秒輪詢獲取即時聚合指標                             |

#### 情境：儀表板輪詢即時指標

- **當 (WHEN)** Streamlit 儀表板每秒向 `/api/v1/realtime` 發出請求時
- **則 (THEN)** FastAPI 返回最新的 `ClassMetrics` JSON，
  包含 `avg_attention_score`, `active_student_count`, `per_student_scores`

---

## 非功能性需求 (Non-functional Requirements)

- **DB 寫入延遲**：從推論結果產生到寫入 MongoDB 的最大延遲 ≤ **3 秒**（批次緩衝時間）
- **PDF 生成時間**：一堂 90 分鐘課程的完整報告生成時間 ≤ **30 秒**
- **錯誤隔離**：DB 寫入失敗不可影響 AI 推論主迴圈繼續運作
