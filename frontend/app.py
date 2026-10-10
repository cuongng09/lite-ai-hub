import streamlit as st
import requests
import json

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Lite-AI Hub", page_icon="⚡", layout="wide")
st.title("⚡ Lite-AI Hub (Local RAG & Web Search)")

# Khởi tạo session state lưu lịch sử chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- SIDEBAR: Cấu hình & Quản lý file ---
with st.sidebar:
    st.header("⚙️ Cấu hình hệ thống")
    enable_rag = st.checkbox("Bật RAG (Tài liệu nội bộ)", value=True)
    enable_web = st.checkbox("Bật Web Search (SearXNG)", value=True)
    
    st.divider()
    st.header("📄 Tải lên tài liệu")
    uploaded_file = st.file_uploader("Chọn file PDF hoặc TXT", type=["pdf", "txt"])
    if uploaded_file is not None:
        if st.button("Xử lý & Lưu vào ChromaDB"):
            with st.spinner("Đang trích xuất & nhúng vector (bge-m3)..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    resp = requests.post(f"{BACKEND_URL}/api/upload", files=files, timeout=60)
                    if resp.status_code == 200:
                        st.success(f"Đã nạp file: {uploaded_file.name} thành công!")
                    else:
                        st.error(f"Lỗi tải file: {resp.text}")
                except Exception as ex:
                    st.error(f"Không thể kết nối Backend: {ex}")

    st.divider()
    if st.button("Xóa lịch sử chat"):
        st.session_state.messages = []
        st.rerun()

# --- KHUNG HIỂN THỊ CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander("📌 Trích dẫn nguồn (Citations)"):
                for idx, cit in enumerate(msg["citations"], 1):
                    title = cit.get("title", "Nguồn")
                    url = cit.get("url", "")
                    content = cit.get("content", "")
                    if url:
                        st.markdown(f"**[{idx}] [{title}]({url})**")
                    else:
                        st.markdown(f"**[{idx}] {title}**")
                    st.caption(content)

# --- NHẬN TIN NHẮN TỪ NGƯỜI DÙNG ---
if prompt := st.chat_input("Nhập câu hỏi tại đây..."):
    # Thêm câu hỏi vào UI & session
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Hiển thị phản hồi AI kèm Streaming
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        citations = []

        try:
            payload = {
                "message": prompt,
                "enable_rag": enable_rag,
                "enable_web": enable_web
            }
            # Gửi request stream tới FastAPI
            response = requests.post(
                f"{BACKEND_URL}/api/chat",
                json=payload,
                stream=True,
                timeout=60
            )

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode("utf-8")
                        if decoded_line.startswith("data: "):
                            raw_data = decoded_line[6:].strip()
                            try:
                                data = json.loads(raw_data)
                                if data.get("type") == "citations":
                                    citations = data.get("citations", [])
                                elif data.get("type") == "token":
                                    token = data.get("content", "")
                                    full_response += token
                                    response_placeholder.markdown(full_response + "▌")
                                elif data.get("type") == "done":
                                    break
                            except json.JSONDecodeError:
                                pass

                # Hiển thị nội dung hoàn chỉnh không còn con trỏ
                response_placeholder.markdown(full_response)

                # Hiển thị trích dẫn nguồn
                if citations:
                    with st.expander("📌 Trích dẫn nguồn (Citations)"):
                        for idx, cit in enumerate(citations, 1):
                            title = cit.get("title", "Nguồn")
                            url = cit.get("url", "")
                            content = cit.get("content", "")
                            if url:
                                st.markdown(f"**[{idx}] [{title}]({url})**")
                            else:
                                st.markdown(f"**[{idx}] {title}**")
                            st.caption(content)

                # Lưu vào session
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "citations": citations
                })
            else:
                response_placeholder.error(f"Lỗi từ server: {response.status_code}")
        except Exception as e:
            response_placeholder.error(f"Lỗi kết nối: {e}")
