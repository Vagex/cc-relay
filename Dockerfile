# 使用輕量級 Python 鏡像
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 複製當前目錄下的所有檔案到容器
COPY . .

# 安裝必要的依賴 (FastAPI, Uvicorn, HTTPX)
RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic

# 開放腳本中定義的 4446 端口
EXPOSE 4446

# 啟動命令
CMD ["python", "codex_web_relay.py"]