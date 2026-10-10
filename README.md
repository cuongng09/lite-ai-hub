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
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

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
