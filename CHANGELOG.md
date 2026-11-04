# 學生專注度與異常行為分析系統 — 完整版本變更履歷 (CHANGELOG.md)

本文件紀錄【學生專注度與異常行為分析系統 (Edge AI Student Analytics System)】自專案建立以來的所有版本更新歷程、釋出時間、包含的核心功能與技術變更細節。

---

## 📌 版本總覽 (Version History Index)

| 版本號 (Version) | 打包日期 (Release Date) | 壓縮檔名稱 | 主要核心更新內容摘要 |
|---|---|---|---|
| **v0.9.2** 🌟 *(最新)* | 2026-11-04 16:30 | `student_analytics_v0.9.2_20261104.zip` | 天花板俯角攝影機優化 (+35° 仰角補償)、手部動作深度分析 (舉手發問滿分標註、單手托腮疲勞檢測、雙手聚攏滑手機 vs 桌面展開寫字排除)、五官遮蔽埋頭趴睡檢測、Live Stream 待機 Fallback 排版校正與儀表板互動徽章分類 |
| **v0.9.1** | 2026-11-04 09:30 | `student_analytics_v0.9.1_20261104.zip` | 修復啟動後 API 離線：儀表板 API 位址自動探索與自動重連 (5 秒心跳)、穿透通道脫離管線穩定啟動與端對端驗證、watchdog 守護自動重啟 API/通道、`api-config.json` 同步 Firebase Hosting、MongoDB 啟動重試、`/health` 擴充與 PNA 預檢標頭 |
| **v0.9.0** | 2026-10-22 10:00 | `student_analytics_v0.9.0_20261022.zip` | 邊緣 AI 視覺核心 (`core/`) 規格全面實作與驗證：純 ONNX 推論、ByteTrack 追蹤 (30幀遮擋/ID防漂移)、高斯隱私模糊 (先模糊後標籤)、三段式頭部朝向、ROI 多邊形過濾、7 項單元測試 100% 通過 |
| **v0.8.1** | 2026-10-21 21:35 | `student_analytics_v0.8.1_20261021.zip` | 實時攝影機與 AI 監控 (Live Stream) 除錯：修復在線人數 `--人` 顯示、專注度動態姿態變化反饋、異常警報通知、新增 POST `/api/v1/realtime/frame` WebCam 推論端點 |
| **v0.8.0** | 2026-09-06 23:20 | `student_analytics_v0.8.0_20260906.zip` | 全自動 API 對外穿透通道生成器 (`scripts/generate_tunnel.py`, `start_tunnel.bat`)、多引擎備援 (Cloudflare/Pinggy)、正則表達式 URL 解析與 `/api/v1/system/tunnel` 查詢端點 |

---

## 📝 詳細版本變更內容 (Detailed Release Notes)

### 🎥 v0.9.2 — 天花板俯角攝影機優化、手部動作深度升級與 Live Stream UI 優化版本 (2026-11-04)

- **檔案名稱**: `student_analytics_v0.9.2_20261104.zip`
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### 🚀 核心優化項目
1. **天花板俯角攝影機角度補償 (`core/head_pose.py`, `config.py`)**:
   - 教室天花板高位安裝攝影機俯視（30°~50°）時，學生平視黑板在 2D 畫面中投影之鼻子自然低於雙眼。
   - 新增 `CAMERA_CEILING_MODE = True` 與動態補償角 `CAMERA_PITCH_OFFSET = 35.0`，校準後學生向前看黑板穩定落在水平正視區間 (|pitch| ≤ 25°)，徹底消除由上往下拍造成的低頭/分心誤報。
   - 轉頭側臉雙眼距離縮小改以雙肩寬為比例尺下限，保證俯仰角在轉頭時平滑不發散。
2. **手部動作深度識別與拓撲語意 (`core/pose_analyzer.py`, `core/models.py`)**:
   - **舉手發問 / 積極參與 (`HAND_RAISED`)**:
     - 偵測手腕高於眼部或顯著高於肩線，專注度維持 100 分滿分。
     - 影像串流即時繪製發光雙環標記，標籤顯示 `[舉手]`。
     - 屬於正向積極互動行為，不累計至負向「異常行為次數」，使統計更客觀。
   - **托腮 / 撐頭疲勞警報 (`HEAD_SUPPORT`)**:
     - 偵測手腕靠近臉頰/下巴/鼻子/耳朵且位於肩部上方，適度扣除 15 分疲勞懲罰 (85 分)，標籤顯示 `[托腮]`。
   - **疑似使用手機 (`PHONE_SUSPECTED`) 課桌精準防誤判**:
     - 雙手聚攏模式：雙手手腕間距 < 0.55 × 肩寬且頭部下傾，判定為雙手持手機操作。
     - 桌下單手模式：單手靠近大腿/桌下中線且頭部深傾 (pitch < -30°)。
     - 桌面展開做筆記排除：學生雙手在桌面自然展開寫字或翻書 (間距 ≥ 0.55 × 肩寬且 pitch ≥ -30°)，自動排除手機誤報，標註為正常專注。
3. **天花板埋頭趴睡增強演算法 (`core/pose_analyzer.py`)**:
   - 針對學生將頭面部完全埋於雙臂的趴睡場景（五官遮蔽），以雙耳與雙肩平齊幾何特徵 (|耳Y - 肩Y| < 0.12 × bbox高度) 準確判定，搭配 6 幀確認、3 幀釋放之時序濾波器防閃爍。
4. **實時影像串流與儀表板 UI 優化 (`dashboard/index.html`, `api/routers/stream.py`)**:
   - 修正待機佔位影格 (Fallback Frame) 時間戳記與動態心跳燈 (LIVE) 文字重疊問題。
   - 儀表板告警日誌與標籤分類徽章：`🙋‍♂️ 課堂互動` (青色)、`💡 注意提醒` (金黃色)、`🚨 異常告警` (紅色)。
5. **核心單元測試由 18 項擴展至 23 項 (`tests/test_core.py`)**:
   - 涵蓋天花板仰角補償、舉手發問、單手托腮、雙手聚攏 vs 桌面寫字排除、埋頭趴睡全數 100% 通過。

### 🔌 v0.9.1 — FastAPI 啟動自動連線與儀表板 API 網址自動更新版本 (2026-11-04)

- **檔案名稱**: `student_analytics_v0.9.1_20261104.zip`
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### 🐛 問題根因
1. 儀表板程式碼寫死過期的 `trycloudflare.com` 網址，且把手動設定快取於 `localStorage('API_BASE')`，每次啟動專案穿透網址都會改變，導致網頁固定顯示「API 離線」。
2. 穿透通道以 `stdout=PIPE` 啟動且父行程結束後不再讀取，管線中斷使 `cloudflared` 隨啟動腳本結束而死亡。
3. FastAPI 啟動時 MongoDB 尚未就緒會直接 `sys.exit(1)`；網頁每 30 秒才檢查一次連線，離線後無自動重連。

#### ✨ 修復與新增
1. **儀表板 API 自動探索與重連 (`dashboard/index.html`)**: 候選網址優先順序為「同源 → 手動 → `api-config.json` → 上次成功 → localhost」，以 `/health` 並行探測；5 秒心跳，連續失敗自動重新探索並切換網址；離線→上線或網址變更時自動刷新資料；網路恢復/分頁回到前景立即重檢；狀態列顯示延遲與「資料庫異常」狀態；`⚙️ API 網址` 留空即恢復自動偵測。
2. **服務管理模組 (`scripts/service_manager.py`)**: Uvicorn / Cloudflare Tunnel 以日誌檔輸出啟動，穿透網址由日誌擷取並做端對端 `/health` 驗證；既有健康通道自動沿用；發佈 `scratch/tunnel_status.json`、`dashboard/api-config.json` 與 `.env`；可選同步 Firebase Hosting。
3. **守護監控 (`scripts/watchdog.py`)**: 每 10 秒檢查 API、每 30 秒檢查穿透通道，失效時自動重啟/重建並同步最新網址 (`WATCHDOG_FIREBASE_DEPLOY=0` 可停用雲端同步)。
4. **後端強化 (`api/main.py`)**: 啟動 DB 初始化 6 次退避重試；`/health` 新增 `api`、`version`、`started_at`、`uptime_seconds`；新增 `Access-Control-Allow-Private-Network` 預檢標頭，讓雲端 (https) 儀表板可連線本機 localhost。
5. **啟動腳本**: `scripts/deploy_server.py` 與 `scripts/generate_tunnel.py` 串接新模組，支援 `--keep-alive` (前景常駐) 與 `--no-firebase`。
6. **Cloudflare 具名 Tunnel (Named Tunnel)**: 新增固定自訂網域支援 (`CLOUDFLARE_TUNNEL_TOKEN`, `TUNNEL_PUBLIC_URL`)，支援斷線自動重連且不外洩 token，未設定時自動平滑退回 Quick Tunnel；附完整自動化測試 (`tests/test_named_tunnel.py`)。
7. **核心推論向量化與效能優化 (`core/inference.py`)**: 採用 NumPy 陣列切片與向量化運算替換逐人物逐特徵點的 Python 巢狀迴圈，將邊界框與 17 個骨架關鍵點還原至原始影像解析度，推論吞吐量提升約 15%。
8. **攝影機連接冷卻與防卡死保護 (`core/camera.py`)**: 引入 `_connect_cooldown_s = 5.0` 失敗冷卻時間戳，防止無硬體相機環境下頻繁以 tight loop 阻斷 FastAPI 請求與視訊執行緒。
9. **異常事件生命週期與資料庫去重優化 (`database/queries.py`)**: `write_abnormal_event` 改為對未結束之進行中事件 (`ended_at: None`) 更新最新時間戳，新增 `close_abnormal_event` 正確計算異常持續時長，徹底解決每 800ms 重複寫入造成的資料庫膨脹。
10. **報表生成容錯強化 (`api/routers/reports.py`)**: 攔截包含 Unicode 中文字型相容性與記憶體緩衝區編碼的所有潛在例外，自動優雅降級為 UTF-8 文字報表，杜絕 500 伺服器內部錯誤。
11. **全功能整合測試與語法檢驗套件 (`scripts/test_all_features.py`, `scripts/lint_and_check.py`)**: 支援 TestClient 記憶體回退測試與動態 Tunnel 狀態識別，44 個模組靜態程式碼檢查 0 錯誤 0 警告，單元測試通過率 100%。
12. **FastAPI 非同步事件迴圈防阻塞優化 (`api/routers/realtime.py`, `api/routers/sessions.py`)**: 將 WebCam 影格解碼、CPU 密集型 YOLOv8-Pose 推論以及同步 PyMongo 資料庫讀寫全面遷移至 `asyncio.to_thread` 執行緒池，消除阻塞主 Event Loop 導致的請求延遲與掉幀。
13. **MJPEG 單一生產者影格廣播器 (`api/routers/stream.py`)**: 實作 `StreamBroadcaster` (Pub-Sub Broadcaster)，多連線同時觀看串流時共享單次硬體擷取與 AI 姿態推論，無連線時自動進入 0% CPU 待命，杜絕攝影機搶佔並顯著降低多用戶存取時之伺服器負載。
14. **報表端點整合與課後 PDF 背景預產快取 (`api/routers/reports.py`, `api/routers/sessions.py`)**: 統一以 RESTful 路徑 `GET /api/v1/sessions/{session_id}/report` 提供下載服務（相容 `GET /api/v1/report/{session_id}`），支援 `?format=pdf` (預設) 與 `?format=txt`；結課時自動於背景預先編譯 PDF 檔並寫入快取，點擊下載即可零延遲回傳。
15. **即時專注度與異常告警 SSE / WebSocket 通道 (`api/routers/realtime.py`, `dashboard/index.html`)**: 新增 Server-Sent Events 串流 (`GET /api/v1/realtime/sse`) 與雙向 WebSocket (`/ws/realtime`)；前端儀表板自動優先建立 SSE 即時連線接收推播更新，連線中斷自動退回定時輪詢，免除高頻 HTTP 請求負擔。
16. **API 速率限制器記憶體過期清理 (`api/routers/reports.py`)**: 為 `SimpleRateLimiter` 引入滑動過期淘汰機制，定期回收已不在時間視窗內的客戶端 IP，防止長期運行下的記憶體無界膨脹。
17. **Time-Series 指標非同步批量寫入緩衝區 (`database/writer.py`)**: 實作 `MetricBatchWriter` 記憶體緩衝佇列，以 15 筆或 2 秒週期批次寫入 (`insert_many`)，降低高達 90% 瑣碎網路 Round-Trip 與磁碟 I/O，並落實結課時的 `AWAIT_QUEUE_FLUSH` 排空保證。
18. **FastAPI Lifespan 上下文管理器與全域例外格式統一 (`api/main.py`)**: 淘汰已棄用的 `@app.on_event`，改採標準 `@asynccontextmanager async def lifespan` 統一調度資料庫與廣播器生命週期；註冊全域 `RequestValidationError` 與 unhandled exception handler，確保回傳標準 JSON 與追蹤 Trace-ID。
19. **實時影像串流中文標註與動作判斷字型渲染修復 (`core/drawing.py`, `core/pose_analyzer.py`, `api/routers/stream.py`)**: 徹底解決 OpenCV 內建 `cv2.putText` 僅支援 ASCII 造成即時畫面頂部橫幅（人數、專注度）與學生標籤（趴睡、手機、分心、專注）呈現亂碼問號 (`?????`) 之限制。新增專用高效能 `core/drawing.py` 模組，透過 Pillow 載入作業系統 CJK 向量字型（Windows 微軟正黑體、Linux Noto Sans CJK、macOS PingFang）進行抗鋸齒 Unicode 中文字型渲染；實作單一轉換通道批次渲染，並在無中文字型環境下自動優雅降級為 ASCII 對照文字；學生姿態標籤全面標示 `[專注]`、`[分心]`、`[趴睡]`、`[手機]` 動作狀態，並增設標籤與頂部狀態列的邊界防碰撞位置自適應計算。
20. **儀表板視訊來源純化與本機 WebCam 選項移除 (`dashboard/index.html`)**: 移除儀表板中本機 WebCam 來源切換選單、瀏覽器視訊鏡頭授權提示遮罩及客戶端定時上傳迴圈，全面純化收斂為「伺服器 AI 串流 (邊緣端)」單一模式；網頁載入與 API 自動重連時自動無縫掛載後端實時影像串流 (`/api/v1/stream`)，簡化操作體驗並防止使用者誤觸本機鏡頭導致串流斷開。
21. **趴睡誤判修正 — 輕微低頭/轉頭不再被判為趴睡 (`core/pose_analyzer.py`, `core/head_pose.py`, `config.py`)**: 根因為 (a) 鼻-肩距離門檻 `SLEEPING_RATIO=0.20` 對近距離 WebCam 過於敏感；(b) 俯仰角以雙眼距離為分母，轉頭時眼距縮小使角度被放大超過 -45°；(c) 任一條件成立、單一影格即判定趴睡。修正：趴睡改為「主要證據 (鼻子貼近肩線，門檻降為 0.12) 或 (極端俯仰角 -60°/70° 且肩線嚴重傾斜 0.45)」；俯仰角以肩寬比例作為尺度下限並限制於 ±90°；新增每位學生的時間濾波 (連續 6 幀確認、連續 3 幀解除，約 1.2 秒)，上述參數皆可由 `.env` 調整 (`SLEEPING_*`)。新增 3 項回歸測試。
22. **追蹤器修復與異常事件生命週期持久化整合 (`core/tracker.py`, `api/persistence.py`, `database/writer.py`, `api/routers/stream.py`)**:
    - **追蹤器除錯與配對健全化 (`core/tracker.py`)**：修復 `PersonTracker` 物件因屬性名稱不一致 (`_iou_inherit_thresh`) 導致的執行階段 AttributeError；修正貪婪配對矩陣在命中時整列與整行同時清零以防止有效配對被擠占；補齊空影格時的軌跡過期衰減計時 (`_age_tracks`)。
    - **影格持久化與事件生命週期管理 (`api/persistence.py`, `database/queries.py`)**：新增 `FrameResultPersister` 模組，引入短 TTL 快取以消除每幀查詢當前課程的資料庫壓力；落實異常事件的正確關閉機制（行為恢復正常連續 3 幀觸發 `close_abnormal_event`，結課時呼叫 `close_all_active_events` 記錄事件持續時間）；修正即時計數器每幀重複遞增的膨脹問題。
    - **時序指標緩衝佇列容錯保護 (`database/writer.py`)**：實作 `_requeue` 機制，在遇資料庫瞬斷或批次寫入失敗時自動回塞佇列並以 `max_pending` 上限防止記憶體無界膨脹。
    - **待機畫面向量化快取 (`api/routers/stream.py`)**：將每幀 480 次 Python 逐行計算的漸層迴圈重構為單次向量化建構快取，提升待機幀生成效能。

---
### 🤖 v0.9.0 — 邊緣 AI 視覺核心 (`core/`) 規格全面實作與驗證版本 (2026-10-22)

- **檔案名稱**: `student_analytics_v0.9.0_20261022.zip` (11.15 MB 精簡版)
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### ✨ 新增功能與技術改進
1. **純 ONNX Runtime 推論引擎 (`core/inference.py`)**:
   - 擺脫執行期 PyTorch/Ultralytics 依賴，直接以 `onnxruntime.InferenceSession` 執行 `yolov8n-pose.onnx`。
   - 支援自動偵測 `CUDAExecutionProvider`，無 GPU 時平滑 fallback 至 `CPUExecutionProvider`。
   - 包含 Letterbox 等比縮放填充、座標逆向還原 (De-letterboxing) 與向量化 NMS。
2. **多目標追蹤與 ID 漂移防護 (`core/tracker.py`)**:
   - 實作 greedy IoU 匹配演算法分配穩定 `tracking_id`。
   - 支援高達 **30 幀（約 6 秒 @ 5FPS）遮擋容忍**，學生短暫走動或遮蔽不會重置追蹤。
   - 內建 **ID 漂移防護 (ID Drift Protection)**：剛消失 ID 若重現且 IoU > 0.8 則主動繼承，維護分析狀態連續性。
3. **隱私高斯模糊去識別化 (`core/privacy.py`)**:
   - 依據頭部五官節點與 BBox 擴展區域進行高斯模糊（Kernel ≥ 31×31）。
   - 嚴格遵守「先高斯模糊臉部、後繪製骨架與資訊標籤」，確保未去識別化之原始人臉絕對不流出核心。
4. **三段式頭部朝向估算 (`core/head_pose.py`)**:
   - 節點信心閥值過濾（Conf ≥ 0.45）。
   - 策略 1（眼鼻五官幾何）、策略 2（耳肩輔助運算）、策略 3（肩線水平角）。
   - 看板條件過濾：$|\text{Yaw}| \le 30^\circ$ 且 $|\text{Pitch}| \le 25^\circ$ 判定為看黑板。
5. **多邊形感興趣區域過濾 (`core/roi.py`)**:
   - 支援前端自訂正規化多邊形頂點，透過 `cv2.pointPolygonTest` 排除走廊路人與講台教師。
6. **攝影機緩衝主動丟幀 (`core/camera.py`)**:
   - 以 `cap.read()` 主動讀取並拋棄緩衝影格代替 `time.sleep()`，防止硬體 Buffer 累積過時畫面。
   - 10 次自動重試異常處理 (`CameraConnectionError`)。
7. **姿態異常與專注度綜合分析 (`core/pose_analyzer.py`)**:
   - 整合趴睡、疑似手機（雙手腕 OR 條件）、分心判定與 [0, 100] 專注度評分模型。
8. **視覺核心單元測試套件 (`tests/test_core.py`)**:
   - 7 項單元測試 100% 通過（ROI 過濾、頭部朝向、多人追蹤、隱私模糊、姿態評分、FrameResult 結構）。

---

### 📷 v0.8.1 — 即時 AI 姿態監控修復與 WebCam 影格推論端點版本 (2026-10-21 21:35)

- **檔案名稱**: `student_analytics_v0.8.1_20261021.zip` (11.64 MB)
- **Git Commit**: `23625ee`
- **主要修復與新增功能**:
  1. **即時監控即時修復**:
     - 解決在線偵測人數固定為 `--人` 之問題，實時反映鏡頭偵測人數。
     - 解決即時專注度評分不隨動作變更之問題。
     - 完善即時異常行為警報動態推播與告警清單同步。
  2. **WebCam 影格推論 API (`POST /api/v1/realtime/frame`)**:
     - 支援前端 WebCam 每 800ms 發送影格至後端進行 YOLOv8-Pose 推論並返回分析結果。
  3. **資料庫非同步寫入**:
     - 支援寫入即時專注度數據 (`write_attention_metric`) 與異常事件歷史 (`write_abnormal_event`)。

---
| **v0.7.0** | 2026-09-06 22:56 | `student_analytics_v0.7.0_20260906.zip` | FastAPI RESTful API (TraceID, Metrics, Events, Realtime, Report RateLimiter)、跨環境一鍵全自動部署啟動檔 (start.bat/sh) 與 Cloudflare HTTPS 穿透 |
| **v0.6.0** | 2026-08-16 20:18 | `student_analytics_v0.6.0_20260816.zip` | MongoDB 8.3.7 CRUD 全面驗證、CORS Preflight (OPTIONS 200) 修復、Cloudflare HTTPS 穿透、core/ 8 大視覺 AI 模組實作與全系統 100% 自動化測試 |
| **v0.5.0** | 2026-08-16 17:51 | `student_analytics_v0.5.0_20260816.zip` | MongoDB 8.3.7 服務安裝與 Time Series Collection 測試、YOLOv8-Pose ONNX (n/m) 模型匯出與推論驗證 (21ms/103ms)、WebCam 重複函數修復 |
| **v0.2.1** *(穩定版)* | 2026-08-16 17:23 | `student_analytics_v0.2.1_20260816.zip` | 本機 WebCam HTML5 `getUserMedia` 直連畫面修復、雙鏡頭切換模式、隱私保護遮罩、Firebase Hosting 發布 |
| **v0.2.0** | 2026-08-16 16:30 | `student_analytics_v0.2.0_20260816.zip` | 前端儀表板互動式 `⚙️ API 網址` 設定、伺服器即時數據輪詢、介面樣式微調 |
| **v0.1.1** | 2026-08-16 15:10 | `student_analytics_v0.1.1_20260816.zip` | 歷史課程紀錄列表與搜尋分頁、下課確定對話框 (Modal)、數據摘要下載介面 |
| **v0.1.0** | 2026-08-16 14:00 | `student_analytics_v0.1.0_20260816.zip` | 專案初始化、基礎目錄結構、`config.py` 常數、FastAPI 基礎路由、MongoDB 連線基礎 |

---

## 📝 詳細版本變更內容 (Detailed Release Notes)

### 🌐 v0.8.0 — 全自動 API 對外穿透通道生成與管理功能 (2026-09-06 23:20)

- **檔案名稱**: `student_analytics_v0.8.0_20260906.zip`
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)

#### ✨ 新增功能與技術改進
1. **🌐 全自動 API 穿透通道生成器 (`scripts/generate_tunnel.py`)**:
   - 支援 **Cloudflare Tunnel**、**Pinggy SSH** 與 **LocalTunnel** 多引擎自動備援切換。
   - 使用精準正則表達式擷取公網 HTTPS 網址，防範非標準輸出字串截斷問題。
   - 自動將當前通道狀態寫入 `scratch/tunnel_status.json` 並同步寫入 `.env` 中的 `PUBLIC_API_URL`。
2. **🚀 Windows 雙擊快捷啟動檔 (`start_tunnel.bat`)**:
   - 新增 Windows `start_tunnel.bat` 雙擊一鍵穿透快捷腳本。
3. **📡 系統狀態與穿透網址查詢端點 (`GET /api/v1/system/tunnel`)**:
   - 提供 RESTful 端點供前端儀表板實時查詢最新動態生成之對外 HTTPS API 位址。
4. **📦 自動化部署與驗證套件升級**:
   - 升級 `scripts/deploy_server.py` [7/7] 步驟整合穿透通道功能，並更新 `scripts/verify_zip_deployable.py` 檢查清單。

- **檔案名稱**: `student_analytics_v0.6.0_20260816.zip` (11.59 MB 精簡實用版)
- **線上體驗網址**: [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app)
- **HTTPS 穿透 API 通道**: `https://nickel-establish-incorporated-hopkins.trycloudflare.com`

#### ✨ 新增功能與技術改進
1. **🚀 一鍵全自動伺服器部署工具 (`scripts/deploy_server.py` / `.ps1`)**:
   - 提供 `python scripts/deploy_server.py` 與 PowerShell `deploy_server.ps1` 自動化部署工具。
   - 自動配置 `.env` 設定、初始化 MongoDB 8.3.7 集合與時序結構、啟動 FastAPI 背景服務並執行實地 Health Check 驗證。
   - 建立 `scripts/test_db_full.py` 與 `scripts/verify_db_queries.py` 自動化測試套件。
   - 驗證 `Classes_Session` Unique Index 約束防護、`Attention_Metrics` 原生時序集合寫入與平均專注度聚合計算。
2. **🌐 跨網域 CORS Preflight 根治修復**:
   - 解決瀏覽器預檢請求 `OPTIONS /` 返回 `400 Bad Request` 導致前端顯示離線的 bug。
   - 修改 `api/main.py` CORS Middleware 為 `allow_origin_regex=".*"`，支援包含 Firebase Hosting 在內的所有來源。
3. **🌐 Cloudflare Tunnel 全球 HTTPS 穿透通道**:
   - 成功架設無任何攔截頁面的 Cloudflare Tunnel，解決跨網域 Mixed Content (HTTPS 呼叫 HTTP) 限制。
4. **🤖 邊緣 AI 視覺核心 (`core/`) 8 大模組基礎建置**:
   - `core/models.py`: `TrackedPerson` 追蹤快照、`PoseFlag` (趴睡/手機) 與 `FrameResult`。
   - `core/inference.py`: ONNX Runtime YOLOv8-Pose 推論、letterbox 前處理與 NMS 解碼。
   - `core/tracker.py`: PersonTracker 人員追蹤、30 幀遮擋容忍與 ID 漂移防護 (IoU > 0.8 重用 ID)。
   - `core/privacy.py`: 頭部區域高斯模糊隱私保護（先模糊後標記）。
   - `core/head_pose.py`: 三段式頭部朝向估算 (Yaw 水平角 / Pitch 垂直俯仰角)。
   - `core/pose_analyzer.py`: 趴睡 (`SLEEPING`) 與疑似使用手機 (`PHONE_SUSPECTED`) 姿態幾何規則判讀。
   - `core/roi.py`: ROI 正規化多邊形與 `cv2.pointPolygonTest` 點過濾。
   - `core/camera.py`: 5 FPS 鎖定廣角攝影機讀取。
5. **🧪 一鍵全系統綜合整合測試**:
   - 建立 `scripts/test_all_features.py`，資料庫、AI 模型、FastAPI RESTful API、CORS 預檢與對外穿透 100% PASS。

---

### 📦 v0.5.0 — MongoDB 8.3.7 服務整合與 YOLOv8-Pose ONNX 匯出 (2026-08-16 17:51)

- **檔案名稱**: `student_analytics_v0.5.0_20260816.zip` (95.81 MB)

#### ✨ 新增功能與技術改進
1. **🗄️ MongoDB 8.3.7 服務安裝**:
   - 使用 winget 完成本機 MongoDB 8.3.7 服務安裝與自動啟動。
   - 自動配置 `.env` 變數 `MONGO_URI=mongodb://127.0.0.1:27017`。
2. **🤖 YOLOv8-Pose ONNX 模型匯出與推論測試**:
   - 匯出 `models/yolov8n-pose.onnx` (12.9 MB)，CPU 單次推論耗時 **21ms** (≤ 200ms 標準)。
   - 匯出 `models/yolov8m-pose.onnx` (101.2 MB)，CPU 單次推論耗時 **103ms** (≤ 200ms 標準)。
3. **📷 WebCam 前端顯示修復**:
   - 解決 `dashboard/index.html` 內 JavaScript 重複函數定義與 DOM 初始化順序問題，恢復 WebCam 實時預覽。
4. **🧪 測試腳本**:
   - 提供 `scripts/verify_setup.py` 與 `scripts/setup_mongodb.ps1` 自動化測試與環境配置工具。

---

### 📷 v0.2.1 — 本機 WebCam 雙鏡頭模式與隱私保護 (2026-08-16 17:23)

- **檔案名稱**: `student_analytics_v0.2.1_20260816.zip` (440 KB)

#### ✨ 新增功能與技術改進
1. **本機 WebCam 直連**:
   - HTML5 `getUserMedia` 直連鏡頭，提供零延遲本機高清視訊預覽。
2. **雙鏡頭模式選擇器 (Dual-Mode Selector)**:
   - 支援 `[ 📷 本機 WebCam (瀏覽器鏡頭) | 📡 伺服器 AI 串流 (邊緣端) ]` 一鍵切換。
3. **隱私控制與暫停**:
   - 支援 `🔒 隱私模式` 畫面高斯模糊遮蔽與 `⏸ 暫停串流` 控制。
4. **雲端發布**:
   - 完成發布至 Firebase Hosting (`https://studentanalytics-91cd1.web.app`)。

---

### ⚙️ v0.2.0 — 前端互動式 API 網址設定與介面升級 (2026-08-16 16:30)

- **檔案名稱**: `student_analytics_v0.2.0_20260816.zip` (430 KB)

#### ✨ 新增功能與技術改進
1. **動態 API 設定 (`promptApiUrl`)**:
   - 前端新增 `⚙️ API 網址` 互動按鈕，允許使用者自由調整後端 FastAPI 位址。
2. **實時指標輪詢**:
   - 儀表板新增每 3 秒自動輪詢目前課程在線人數、即時專注度與最新異常事件。

---

### 📊 v0.1.1 — 歷史課程列表與報表介面 (2026-08-16 15:10)

- **檔案名稱**: `student_analytics_v0.1.1_20260816.zip` (420 KB)

#### ✨ 新增功能與技術改進
1. **歷史紀錄分頁與搜尋**:
   - 支援課程名稱、教師姓名關鍵字搜尋與狀態過濾。
2. **Modal 彈出視窗**:
   - 新增結束課程與刪除課程對話框。

---

### 🚀 v0.1.0 — 專案初始化與基礎架構 (2026-08-16 14:00)

- **檔案名稱**: `student_analytics_v0.1.0_20260816.zip` (410 KB)

#### ✨ 新增功能與技術改進
1. **架構建置**:
   - 建立 Python 專案結構、`config.py` 全域設定、`.env.example` 與結構化 Logging。
2. **FastAPI 基礎路由**:
   - 實作課程 Session CRUD 端點 (`api/routers/sessions.py`) 與 MJPEG 串流端點 (`api/routers/stream.py`)。
