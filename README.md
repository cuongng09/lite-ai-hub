# Lite-AI Hub

Ứng dụng Web AI Local siêu nhẹ, tối ưu RAM/VRAM, thay thế Open WebUI.

## 1. Yêu cầu tiên quyết
- Đã cài đặt [Ollama](https://ollama.com/) trên máy.
- Đã cài đặt Docker (để chạy SearXNG local search).
- Python 3.10+

## 2. Chuẩn bị Models
Mở terminal và tải model:
```bash
ollama pull qwen2.5:latest
ollama pull bge-m3:latest
```

## 3. Khởi động SearXNG (Web Search local)
```bash
docker compose up -d
```

## 4. Cài đặt thư viện Python
```bash
py install 3.12
# Remove the old folder if it exists
Remove-Item -Recurse -Force venv -ErrorAction SilentlyContinue

# Create the venv with 3.12
py -3.12 -m venv venv

# Windows:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\venv\Scripts\Activate.ps1

# Linux/macOS:
source venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Khởi chạy
- Khởi động Backend (FastAPI):
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- Khởi động Frontend (Streamlit) ở tab terminal khác:
```bash
streamlit run frontend/app.py
```
Truy cập giao diện tại: `http://localhost:8501`.
