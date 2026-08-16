# Spec: 專注度評分引擎

## 新增需求 (ADDED Requirements)

---

### 需求 1：專注度指標計算 (Attention Score Calculation)

系統「必須」(SHALL) 根據頭部朝向角度（Head Yaw / Pitch）、姿勢幾何標記（PoseFlags），
以及 FSM 確認的連續異常狀態，計算出每位學生每一幀的「即時專注度分數」（0 到 100 的整數或浮點數）。
所有幾何計算（如 Y 軸高度差）應先除以學生的 `bbox_height` 進行正規化。

**評分公式（每幀計算）**：

```python
base_score = 0

# 加分項
if is_looking_at_board(yaw, pitch):          # |Yaw| ≤ 30° 且 |Pitch| ≤ 25°
    base_score += 50

if PoseFlag.SLEEPING not in fsm.active_penalty_flags:
    base_score += 50  # 坐姿端正（無趴睡 WARNING/CONFIRMED flag）

# 扣分項（WARNING 或 CONFIRMED 狀態均觸發，非 PENDING）
if PoseFlag.PHONE_SUSPECTED in fsm.active_penalty_flags:
    base_score -= 50

if PoseFlag.SLEEPING in fsm.active_penalty_flags:
    base_score -= 30  # 坐姿加分已不獲得（上方未加），此處再扣 -30

# 限制分數於 [0, 100]
final_score = max(0, min(100, base_score))
```

**重要說明（FSM 狀態與扣分對應）**：

- **`PENDING` 狀態**（0 ~ 3 秒）：**不扣分**，不寫 DB，觀察等待
- **`WARNING` 狀態**（3 ~ 10 秒）：**開始扣分**（評分公式中的懲罰生效），**不寫** `Abnormal_Events`
- **`CONFIRMED` 狀態**（≥ 10 秒）：**持續扣分**，**並觸發非同步寫入** `Abnormal_Events` 一次
- `fsm.active_penalty_flags`：包含目前處於 `WARNING` 或 `CONFIRMED` 狀態的所有標記（這些標記均會觸發扣分）。
- 不同懲罰可以同時疊加（例如同時趴睡且疑似看手機，可扣到 -80，clamp 至 0）
- 看黑板加分（+50）與坐姿加分（+50）是獨立項目，互不影響

#### 情境 A：正常專注學生

- **當 (WHEN)** 某 tracking_id 的 `|head_yaw| ≤ 30°`、`|head_pitch| ≤ 25°`，
  且 FSM 未確認任何異常標記時
- **則 (THEN)** 該 tracking_id 本幀得分 = `50 + 50 = 100`

#### 情境 B：看黑板但輕微姿勢問題（未達 FSM 確認閾值）

- **當 (WHEN)** 頭部朝向黑板，但 `PoseFlag.PHONE_SUSPECTED` 僅持續 2 秒（< 3 秒 FSM 過濾閾值）時
- **則 (THEN)** FSM 忽略此短暫事件，該幀得分 = `50 + 50 = 100`（不觸發扣分）

#### 情境 C：確認趴睡超過 10 秒

- **當 (WHEN)** `PoseFlag.SLEEPING` 持續超過 10 秒，FSM 進入 `CONFIRMED` 狀態時
- **則 (THEN)** 該 tracking_id 本幀得分 = `0 + 0 - 30 = -30`，clamp 後為 `0`

#### 情境 D：頭轉向但未達異常

- **當 (WHEN)** 學生 `|head_yaw| = 45°`（超出 30° 閾值），但其餘姿態正常時
- **則 (THEN)** 看黑板加分不獲得（+0），坐姿正常仍加分（+50），最終得分 = `50`

---

### 需求 2：有限狀態機連續動作過濾器 (FSM Continuous Action Filter)

系統「必須」(SHALL) 為每個 `tracking_id` 維護一個獨立的 FSM 實例，
以平滑狀態轉換並防止短暫誤判觸發持久性事件。

**FSM 狀態定義**：

```
NORMAL → (偵測到異常標記) → PENDING → (累計 ≥ 3s) → WARNING → (累計 ≥ 10s，即 WARNING 後再持續 ≥ 7s) → CONFIRMED
CONFIRMED → (異常消失 ≥ 3s) → NORMAL
PENDING → (異常消失) → NORMAL（< 3s，雜訊過濾）
(ID 消失 > 6s) → TERMINATED → (清除實例)
```

> ⚠️ **閾值計算基準**：所有時間閾值（3s、10s）均以**異常首次偵測時刻（`detected_at`）為基準**累計計算，而非從每次「進入該狀態」重新計時。即：PENDING 進入後累計滿 3s 轉 WARNING，累計滿 10s 轉 CONFIRMED（WARNING 共持續 7s）。

**狀態說明**：

| 狀態         | 中文說明 | 持續時間  | 行為                                       |
| ------------ | -------- | --------- | ------------------------------------------ |
| `NORMAL`     | 正常     | —         | 不扣分，不寫 DB                            |
| `PENDING`    | 觀察中   | 0 ~ 3 秒  | 不扣分，不寫 DB                            |
| `WARNING`    | 預警     | 3 ~ 10 秒 | 觸發扣分，不寫 `Abnormal_Events`           |
| `CONFIRMED`  | 確認異常 | ≥ 10 秒   | 觸發扣分，**非同步寫入** `Abnormal_Events` |
| `TERMINATED` | 已終止   | —         | 執行最終事件關閉並清除實例                 |

**實作要求**：

- 每個 FSM 實例需追蹤：`current_state`, `detected_at`（異常首次偵測時刻，閾值基準）, `entered_state_at`（進入目前狀態的時刻，用於 CONFIRMED 後恢復計時）, `current_flag`
- 每個 `tracking_id` 可同時有多個並行 FSM 實例（各自監控不同的 `PoseFlag`）
- **閾值判斷**：`time.time() - detected_at >= 3.0` 進入 WARNING；`time.time() - detected_at >= 10.0` 進入 CONFIRMED

**資料結構**：

```python
@dataclass
class FSMInstance:
    tracking_id: int
    flag: PoseFlag
    state: FSMState  # Enum: NORMAL | PENDING | WARNING | CONFIRMED | TERMINATED
    detected_at: float       # 異常首次被偵測到的 Unix 時間戳記 (秒)，作為 3s/10s 閾值的計算基準
    entered_state_at: float  # 進入「目前狀態」的 Unix 時間戳記 (秒)，用於 CONFIRMED 後恢復至 NORMAL 的 3s 計時
    confirmed_event_id: str | None = None  # 寫入 DB 後的 event ObjectId
```

#### 情境 A：短暫低頭撿筆（雜訊過濾）

- **當 (WHEN)** `PoseFlag.PHONE_SUSPECTED` 出現後 **2 秒內**消失時
- **則 (THEN)** FSM 從 `PENDING` 返回 `NORMAL`，不觸發任何扣分或資料庫寫入

#### 情境 B：長時間低頭滑手機（確認異常）

- **當 (WHEN)** `PoseFlag.PHONE_SUSPECTED` 持續 **12 秒**時
- **則 (THEN)**
  1. 第 0~3 秒：FSM 處於 `PENDING`
  2. 第 3~10 秒：FSM 進入 `WARNING`，評分引擎開始扣分（-50）
  3. 第 10 秒：FSM 進入 `CONFIRMED`，觸發非同步寫入一筆 `Abnormal_Events` 記錄

#### 情境 C：異常結束後的狀態恢復

- **當 (WHEN)** 異常標記在 FSM 處於 `CONFIRMED` 狀態時消失，且消失持續 ≥ 3 秒時
- **則 (THEN)** FSM 返回 `NORMAL`，並同時更新 `Abnormal_Events` 記錄的以下欄位：
  - `ended_at`：異常消失確認的時間戳記
  - `ended_reason`：設為 `"recovered"`
  - `duration_seconds`：根據 `started_at` 與 `ended_at` 重新計算

#### 情境 D：tracking_id 消失（學生離開畫面）

- **當 (WHEN)** 某 `tracking_id` 在 30 幀（≈6 秒）內未出現時
- **則 (THEN)**
  1. 清除該 `tracking_id` 的所有 FSM 實例，釋放記憶體。
  2. **銷毀平滑器 (Destroy Smoother)**：必須同時清除該 ID 對應的滾動平均視窗緩衝區，防止新 ID 繼承舊數據。
  3. **重要**：若該學生尚有未結束的事件（`confirmed_event_id` 不為 `None`），系統必須呼叫資料庫層介面同時更新該事件：
     - `ended_at`：目前時間
     - `ended_reason`：設為 `"tracking_lost"`
     - `duration_seconds`：根據 `started_at` 與 `ended_at` 重新計算

#### 需求 2.5：系統重啟強制結案 (Force-close on Restart)

- **當 (WHEN)** FastAPI 服務啟動時
- **則 (THEN)** 系統必須查詢 `Abnormal_Events` 中 `ended_at` 為 `null` 的所有記錄，一律執行以下操作：
  1. 將 `ended_at` 強制設為服務啟動當前時間（`datetime.utcnow()`）
  2. 將 `ended_reason` 設為 `"server_restart"`
  3. 根據 `started_at` 與 `ended_at` 重新計算並更新 `duration_seconds`
  4. **不**嘗試為任何 `tracking_id` 初始化或繼承 FSM 狀態
- **理由**：系統重啟後 ByteTrack 重新啟動，所有 `tracking_id` 從 0 重新動態分配。舊 Session 中的 `id=7` 在新一輪中可能對應完全不同的學生，若繼承其 FSM 狀態將導致異常事件張冠李戴、`ended_at` 永遠無法正確關閉。強制結案是唯一確保資料一致性的安全策略。

---

### 需求 3：時序資料平滑 (Time-series Smoothing)

系統「應」(SHOULD) 使用滾動平均（Rolling Average）對即時專注度分數進行平滑處理，
以消除單幀異常干擾儀表板顯示。

**平滑規格**：

- 視窗大小：**30 個資料點**（30 × 0.2s = **6 秒**的移動平均）
- 實作方式：`pandas.Series.rolling(window=30, min_periods=1).mean()`
- 平滑後分數用於**儀表板顯示**與**報告摘要統計**
- 原始（未平滑）分數寫入 `Attention_Metrics` Time Series Collection（保留原始精度）

#### 情境：儀表板圖表顯示

- **當 (WHEN)** 儀表板從 DB 或記憶體中讀取最新 30 筆分數並渲染圖表時
- **則 (THEN)** 顯示的折線圖是平滑後的分數，而非逐幀原始數值

---

### 需求 4：班級整體專注度聚合 (Class-level Aggregation)

系統「必須」(SHALL) 在每個推論週期（每幀）計算全班的聚合指標，供儀表板即時顯示。

**聚合指標定義**：

```python
@dataclass
class ClassMetrics:
    timestamp: datetime
    session_id: str
    active_student_count: int          # 在 ROI 內被追蹤的學生數量
    avg_attention_score: float         # 全班即時平均專注度 (0-100)
    students_looking_at_board: int     # 正在看黑板的人數
    students_with_active_penalties: int  # 處於 WARNING 或 CONFIRMED 狀態的人數
    per_student_scores: dict[int, float]   # {tracking_id: smoothed_score}
```

**注意**：此處的分數必須先經過 `engine/smoother.py` 的 30 點滾動平均處理。

#### 情境：儀表板即時更新

- **當 (WHEN)** 每一幀推論完成後
- **則 (THEN)**
  1. 評分引擎將 `ClassMetrics` 更新至 **全域執行緒安全容器 (GlobalSafeStorage)**。
  2. FastAPI 的 `/realtime` 輪詢端點（每秒一次）從該容器讀取最新指標並傳送至 Streamlit。
  3. 必須使用 `asyncio.Lock` 或 `copy.deepcopy` 確保讀寫原子性，防止讀取到中斷的內部 dict 狀態。

---

## 非功能性需求 (Non-functional Requirements)

- **延遲**：每幀評分計算（從 `FrameResult` 輸入到 `ClassMetrics` 輸出）≤ **20 毫秒**
- **記憶體**：所有 FSM 實例的記憶體總量，以 50 名學生為上限不超過 **5 MB**
- **執行緒安全**：FSM 狀態更新與 DB 非同步寫入必須在同一個 asyncio 事件迴圈中執行，
  避免競態條件（Race Condition）
- **結構化日誌 (Structured Logging)**：
  - 推論引擎必須為每一幀生成一個唯一的 `trace_id`。
  - 所有模組（視覺、評分、資料庫）在處理該幀資料時，日誌必須攜帶此 `trace_id`，以利於跨模組追蹤單一幀的處理路徑。
