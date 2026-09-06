# 學生專注度與異常行為分析系統 (Edge AI Student Analytics System)

本專案為跨平台邊緣端 AI 視覺學生專注度與異常行為分析系統，具備零組態一鍵全自動化部署機制，支援在任何 Windows、Linux 或 macOS 電腦環境下一鍵啟動。

---

## 🚀 跨環境一鍵啟動方式 (Universal One-Click Boot)

### 🪟 Windows 環境
直接在專案根目錄**雙擊執行 [`start.bat`](file:///g:/graduate_project/start.bat)** 檔即可！

### 🐧 Linux / 🍎 macOS 環境
在終端機開啟專案目錄並執行：
```bash
chmod +x start.sh
./start.sh
```

### 🐍 使用 Python 跨平台指令啟動
在任何安裝有 Python 3.10+ 的電腦上執行：
```bash
python scripts/deploy_server.py
```

---

## ⚙️ 一鍵啟動自動處理事項 (Automated Setup)

當您執行上述一鍵啟動時，系統會自動在背景為您完成：
1. **虛擬環境**：自動建立並切換至 Python 虛擬環境 (`.venv`)。
2. **依賴套件**：自動檢查並升級/安裝所有相依套件 (`pip install -r requirements.txt`)。
3. **AI ONNX 模型**：自動檢查 `models/yolov8n-pose.onnx` 模型，若缺失則自動匯出。
4. **環境變數**：自動設定 `.env` 設定檔。
5. **MongoDB 時序庫**：自動連線本機 MongoDB 8.3.7 並建置 `Classes_Session`, `Attention_Metrics` (Time-Series Collection) 與 `Abnormal_Events` 三大集合索引與 TTL 機制。
6. **API 後端**：自動啟動 FastAPI RESTful API 伺服器 (`http://localhost:8000`)。
7. **Cloudflare Tunnel**：自動建立對外 HTTPS 穿透通道，並即時印出全球對外存取網址。

---

## 📡 系統端點與介面位址

| 服務項目 | 位址 / URL | 說明 |
| :--- | :--- | :--- |
| **雲端儀表板體驗** | [https://studentanalytics-91cd1.web.app](https://studentanalytics-91cd1.web.app) | 前端 Firebase Hosting 體驗網址 |
| **本機儀表板位址** | [http://localhost:8000/dashboard](http://localhost:8000/dashboard) | 邊緣端本機靜態儀表板 |
| **後端 RESTful API** | `http://localhost:8000` | 本機 FastAPI API 位址 |
| **Cloudflare HTTPS 穿透** | 動態生成 `https://xxx.trycloudflare.com` | 對外安全穿透通道 (自動發布) |
| **Swagger API 文件** | `https://xxx.trycloudflare.com/docs` | OpenAPI 互動測試文件 |

---

## 🧪 功能測試與除錯 (Testing & Troubleshooting)

執行全系統一鍵自動化測試腳本：
```bash
.venv/Scripts/python scripts/test_all_features.py
```
或單獨測試 RESTful API 7 大端點：
```bash
.venv/Scripts/python scripts/test_api_v1.py
```

---

## 🛠️ 系統需求

- **作業系統**：Windows 10/11, macOS 12+, Linux (Ubuntu 20.04+)
- **Python 版本**：Python 3.10 ~ 3.13
- **資料庫**：MongoDB 7.0+ (建議 8.3.7+)
