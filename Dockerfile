# 使用輕量級 Python 映像檔
FROM python:3.12-slim

# 設定工作目錄
WORKDIR /app

# 複製 `requirements.txt` 並安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 FastAPI 伺服器程式碼
COPY . .

# 指定 FastAPI 服務的端口
EXPOSE 8000

# 啟動 FastAPI 應用程式
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
