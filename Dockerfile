# 學生專注度與異常行為分析系統 — 雲端 Dockerfile
FROM python:3.10-slim

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# 安裝系統相依套件 (包含 OpenCV 所需之 Linux 圖像庫)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 需求套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼與模型
COPY . .

# 開放 API 埠號
EXPOSE 8000

# 啟動 FastAPI Uvicorn 服務 (自動適應雲端平台 PORT 變數)
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
