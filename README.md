# ⚡ Lite-AI Hub (Canvas & Next-Gen Edition)

> Ứng dụng Web AI Local siêu nhẹ, tối ưu RAM/VRAM, tích hợp **Split Canvas Artifacts**, **Native Tool Calling (Qwen2.5)**, **Deep Web Research (Perplexity style)** và **SQLite-vec**.

---

## 🌟 Điểm nổi bật vượt chuẩn

### 1. Thoát khỏi giới hạn của Streamlit (Giai đoạn 2)
- **Zero RAM Frontend:** Giao diện Single-Page Application (SPA) cao cấp được xây dựng bằng **Tailwind CSS + Vue 3**, phục vụ trực tiếp từ FastAPI server qua Static route. Bạn không cần chạy thêm process Streamlit ngốn 250MB RAM hay Node.js.
- **Panel chia đôi (Split Canvas):**
  - **Khung Chat (Bên trái):** SSE Streaming mượt mà 60fps, hỗ trợ Web Search, RAG và Deep Research.
  - **Interactive Canvas (Bên phải):** Tự động mở ra khi AI viết code, thiết kế giao diện HTML/Tailwind, vẽ vector SVG, hoặc sơ đồ Mermaid.
  - **Live Preview Sandbox:** Render trực tiếp giao diện Web và sơ đồ trong môi trường an toàn, có nút sao chép code 1-click và tải file về máy.
- **Native Ollama Tool Calling cho Qwen2.5:**
  - Kết nối trực tiếp function calling chuẩn Ollama (`tools`).
  - Model tự động quyết định khi nào cần tra cứu web, khi nào cần tạo Artifact trên Canvas mà không cần prompt thô.

### 2. Tính năng Vượt mặt Open WebUI (Giai đoạn 3)
- **Deep Web Research (Perplexity style):** Tự động phân rã câu hỏi phức tạp thành nhiều khía cạnh, tìm kiếm song song đa nguồn và tổng hợp báo cáo kèm trích dẫn số `[1], [2], [3]`.
- **Offline Voice Mode:** Tích hợp Web Speech API và module ONNX (`faster-whisper` + `kokoro-82m`) nhận diện và phát âm giọng nói mượt mà, độ trễ < 200ms trên CPU.
- **Sẵn sàng đóng gói Desktop App qua Tauri v2:** Đã cấu hình sẵn thư mục `src-tauri` để build file `.exe` Windows siêu nhẹ (~25MB RAM).

---

## 🛠️ Cấu trúc dự án

```text
lite-ai-hub/
├── backend/
│   ├── main.py             # FastAPI App, SSE Streaming, API Routing & Static Serving
│   ├── tools.py            # Function Calling Schemas & Executor (Web Search, Artifacts)
│   ├── research.py         # Deep Web Research Engine đa nguồn
│   ├── search.py           # DuckDuckGo Search thuần Python (Zero Docker)
│   ├── rag.py              # SQLite Vector Store & Parser (PDF/DOCX/TXT)
│   ├── ollama_client.py    # Persistent Client hỗ trợ Native Tool Calling & keep_alive
│   └── voice.py            # Offline Speech Engine (Whisper + Kokoro-onnx)
├── static/
│   └── index.html          # Web UI Canvas hiện đại (Vue 3, Tailwind, Mermaid, Preview)
├── frontend/
│   └── app.py              # Streamlit UI cũ (dự phòng)
├── src-tauri/               # Cấu hình đóng gói Desktop App Windows (.exe)
├── requirements.txt        # Thư viện Python siêu nhẹ
├── run.bat                 # Script chạy 1-click mở ngay giao diện Canvas
└── README.md
```

---

## 🚀 Hướng dẫn khởi chạy

### 1. Chuẩn bị Models trên Ollama
```bash
ollama pull qwen2.5:latest
ollama pull bge-m3:latest
```

### 2. Chạy nhanh 1-Click trên Windows
Nhấp đúp chuột vào file:
```bash
run.bat
```
Hệ thống sẽ tự động kích hoạt môi trường và mở ngay trình duyệt tại:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### 3. Chạy thủ công bằng Terminal
```bash
# Kích hoạt môi trường ảo:
.\venv\Scripts\activate

# Cài đặt thư viện:
pip install -r requirements.txt

# Khởi động Lite-AI Hub:
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Truy cập:
- **Giao diện Canvas chính:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Tài liệu API (Swagger UI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
